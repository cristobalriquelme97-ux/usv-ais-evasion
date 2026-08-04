from __future__ import annotations

import argparse
import csv
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from usv_avoidance.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from usv_avoidance.ais_type1_generator import (
    generate_moving_target_scenario,
)
from usv_avoidance.random_encounter_generator import (
    RandomEncounterCandidate,
    RandomEncounterConfig,
    generate_random_candidate,
    simulate_independent_baseline,
    xy_to_latlon,
)
from usv_avoidance.ripa_reference_evaluator import (
    classify_ripa_reference,
    evaluate_ripa_compliance,
    extract_algorithm_behavior,
)
from usv_avoidance.scenario_config import (
    DEFAULT_SCENARIO_CONFIG,
    PROJECT_ROOT,
)
from usv_avoidance.simulation_runner import run_scenario


DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "results" / "monte_carlo_random"
)


RUN_FIELDS = [
    "ejecucion",
    "semilla_maestra",
    "semilla_escenario",
    "intentos_hasta_aceptacion",
    "candidatos_generados_acumulados",
    "usv_sog_kn",
    "usv_cog_deg",
    "target_sog_kn",
    "target_cog_deg",
    "target_x_inicial_m",
    "target_y_inicial_m",
    "distancia_inicial_m",
    "demarcacion_verdadera_inicial_deg",
    "demarcacion_relativa_inicial_deg",
    "distancia_minima_baseline_m",
    "tiempo_minimo_baseline_s",
    "ripa_evaluable",
    "encuentro_referencia",
    "rol_referencia",
    "accion_inicial_esperada",
    "motivo_referencia_ripa",
    "encuentro_inicial_algoritmo",
    "rol_inicial_algoritmo",
    "primera_maniobra_s",
    "primera_accion_algoritmo",
    "primera_salida_rumbo_original_s",
    "cumplimiento_ripa",
    "motivo_cumplimiento_ripa",
    "riesgo_detectado_algoritmo",
    "resultado_seguro",
    "violo_seguridad",
    "distancia_minima_algoritmo_m",
    "margen_seguridad_m",
    "mejora_distancia_minima_m",
    "ejecucion_exitosa",
    "tiempo_reaccion_s",
    "tiempo_total_evasion_s",
    "ruta_recuperada",
    "cantidad_cambios_rumbo_ordenado",
    "variacion_total_rumbo_ordenado_deg",
]


SUMMARY_FIELDS = [
    "numero_ejecuciones",
    "semilla_maestra",
    "candidatos_generados",
    "candidatos_rechazados",
    "tasa_aceptacion_generador_pct",
    "numero_ripa_evaluable",
    "numero_ripa_ambiguo",
    "numero_ejecuciones_con_evasion",
    "tasa_cumplimiento_ripa_pct",
    "tasa_exito_pct",
    "tasa_seguridad_pct",
    "tasa_violacion_seguridad_pct",
    "margen_seguridad_medio_m",
    "tiempo_evasion_promedio_s",
]


@dataclass(frozen=True)
class MonteCarloRandomConfig:
    runs: int = 1000
    master_seed: int = 20260804
    ais_step_s: int = 5
    stand_on_hold_s: float = 20.0
    max_candidates: int = 1_000_000
    progress_every: int = 25
    keep_scenarios: bool = False

    def __post_init__(self) -> None:
        if self.runs <= 0:
            raise ValueError("runs debe ser mayor que cero.")
        if self.ais_step_s <= 0:
            raise ValueError("ais_step_s debe ser mayor que cero.")
        if self.stand_on_hold_s < 0.0:
            raise ValueError("stand_on_hold_s no puede ser negativo.")
        if self.max_candidates < self.runs:
            raise ValueError(
                "max_candidates debe ser al menos igual a runs."
            )
        if self.progress_every <= 0:
            raise ValueError("progress_every debe ser mayor que cero.")


def _percentage_true(
    rows: Iterable[Mapping[str, Any]],
    field: str,
) -> float | None:
    row_list = list(rows)
    if not row_list:
        return None

    return 100.0 * sum(
        bool(row.get(field)) for row in row_list
    ) / len(row_list)


def _mean_or_none(values: Iterable[float]) -> float | None:
    value_list = list(values)
    return statistics.fmean(value_list) if value_list else None


def _save_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _build_scenario_config(
    candidate: RandomEncounterCandidate,
    *,
    duration_s: int,
    ais_step_s: int,
):
    return replace(
        DEFAULT_SCENARIO_CONFIG,
        usv_sog_kn=candidate.usv_sog_kn,
        usv_cog_deg=candidate.usv_cog_deg,
        usv_heading_deg=candidate.usv_cog_deg,
        duration_s=duration_s,
        step_s=ais_step_s,
    )


def run_random_monte_carlo(
    *,
    monte_carlo_config: MonteCarloRandomConfig,
    encounter_config: RandomEncounterConfig,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_dir = output_dir / "generated_scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    algorithm_config = replace(
        DEFAULT_ALGORITHM_CONFIG,
        safety_radius_m=encounter_config.safety_radius_m,
        time_horizon_s=encounter_config.duration_s,
    )

    master_rng = random.Random(monte_carlo_config.master_seed)

    rows: list[dict[str, Any]] = []
    candidates_generated = 0
    attempts_since_acceptance = 0

    while len(rows) < monte_carlo_config.runs:
        if candidates_generated >= monte_carlo_config.max_candidates:
            raise RuntimeError(
                "Se alcanzó max_candidates antes de reunir todas las "
                "ejecuciones aceptadas. Aumente --max-candidates o "
                "revise los intervalos de generación."
            )

        candidates_generated += 1
        attempts_since_acceptance += 1

        scenario_seed = master_rng.randrange(0, 2**32)
        scenario_rng = random.Random(scenario_seed)

        candidate = generate_random_candidate(
            rng=scenario_rng,
            config=encounter_config,
        )
        baseline = simulate_independent_baseline(
            candidate=candidate,
            config=encounter_config,
        )

        # Única condición de aceptación relacionada con riesgo:
        # la trayectoria basal entra a menos del radio de seguridad.
        if not baseline.safety_radius_violated:
            continue

        run_number = len(rows) + 1
        scenario_config = _build_scenario_config(
            candidate,
            duration_s=int(encounter_config.duration_s),
            ais_step_s=monte_carlo_config.ais_step_s,
        )

        target_lat, target_lon = xy_to_latlon(
            x_east_m=candidate.target_x0_m,
            y_north_m=candidate.target_y0_m,
            ref_lat_deg=scenario_config.usv_lat0,
            ref_lon_deg=scenario_config.usv_lon0,
        )

        mmsi = 725200000 + run_number
        scenario_path = scenario_dir / (
            f"mc_random_{run_number:05d}.txt"
        )

        generate_moving_target_scenario(
            output_file=str(scenario_path),
            mmsi=mmsi,
            lat0=target_lat,
            lon0=target_lon,
            sog_kn=candidate.target_sog_kn,
            cog_deg=candidate.target_cog_deg,
            heading_deg=(
                int(round(candidate.target_cog_deg)) % 360
            ),
            duration_s=scenario_config.duration_s,
            step_s=scenario_config.step_s,
        )

        simulation_result = run_scenario(
            scenario_name=str(scenario_path),
            save_results=False,
            playback_delay_s=0.0,
            algorithm_config=algorithm_config,
            scenario_config=scenario_config,
            expected_encounter=None,
            expected_ownship_role=None,
            expected_action=None,
        )

        summary = simulation_result["summary"]

        reference = classify_ripa_reference(candidate)
        behavior = extract_algorithm_behavior(
            simulation_result=simulation_result,
            original_course_deg=candidate.usv_cog_deg,
        )
        compliance = evaluate_ripa_compliance(
            reference=reference,
            behavior=behavior,
            baseline_time_at_minimum_s=(
                baseline.time_at_minimum_s
            ),
            stand_on_hold_s=monte_carlo_config.stand_on_hold_s,
        )

        algorithm_min_distance_m = summary.get(
            "distancia_minima_m"
        )
        if algorithm_min_distance_m is None:
            safe_result = False
            safety_margin_m = None
            improvement_m = None
        else:
            algorithm_min_distance_m = float(
                algorithm_min_distance_m
            )
            safe_result = (
                algorithm_min_distance_m
                >= encounter_config.safety_radius_m
            )
            safety_margin_m = (
                algorithm_min_distance_m
                - encounter_config.safety_radius_m
            )
            improvement_m = (
                algorithm_min_distance_m
                - baseline.minimum_distance_m
            )

        successful_run: bool | None
        if compliance.evaluable:
            successful_run = (
                safe_result
                and compliance.compliant is True
            )
        else:
            successful_run = None

        row = {
            "ejecucion": run_number,
            "semilla_maestra": monte_carlo_config.master_seed,
            "semilla_escenario": scenario_seed,
            "intentos_hasta_aceptacion": attempts_since_acceptance,
            "candidatos_generados_acumulados": candidates_generated,
            "usv_sog_kn": candidate.usv_sog_kn,
            "usv_cog_deg": candidate.usv_cog_deg,
            "target_sog_kn": candidate.target_sog_kn,
            "target_cog_deg": candidate.target_cog_deg,
            "target_x_inicial_m": candidate.target_x0_m,
            "target_y_inicial_m": candidate.target_y0_m,
            "distancia_inicial_m": candidate.initial_distance_m,
            "demarcacion_verdadera_inicial_deg": (
                candidate.initial_true_bearing_deg
            ),
            "demarcacion_relativa_inicial_deg": (
                candidate.initial_relative_bearing_deg
            ),
            "distancia_minima_baseline_m": (
                baseline.minimum_distance_m
            ),
            "tiempo_minimo_baseline_s": (
                baseline.time_at_minimum_s
            ),
            "ripa_evaluable": reference.evaluable,
            "encuentro_referencia": reference.encounter,
            "rol_referencia": reference.ownship_role,
            "accion_inicial_esperada": (
                reference.expected_initial_action
            ),
            "motivo_referencia_ripa": reference.reason,
            "encuentro_inicial_algoritmo": (
                behavior.initial_algorithm_encounter
            ),
            "rol_inicial_algoritmo": (
                behavior.initial_algorithm_role
            ),
            "primera_maniobra_s": behavior.first_maneuver_time_s,
            "primera_accion_algoritmo": (
                behavior.first_maneuver_action
            ),
            "primera_salida_rumbo_original_s": (
                behavior.first_course_departure_time_s
            ),
            "cumplimiento_ripa": compliance.compliant,
            "motivo_cumplimiento_ripa": compliance.reason,
            "riesgo_detectado_algoritmo": summary.get(
                "riesgo_detectado"
            ),
            "resultado_seguro": safe_result,
            "violo_seguridad": not safe_result,
            "distancia_minima_algoritmo_m": (
                algorithm_min_distance_m
            ),
            "margen_seguridad_m": safety_margin_m,
            "mejora_distancia_minima_m": improvement_m,
            "ejecucion_exitosa": successful_run,
            "tiempo_reaccion_s": summary.get("tiempo_reaccion_s"),
            "tiempo_total_evasion_s": summary.get(
                "tiempo_total_evasion_s"
            ),
            "ruta_recuperada": summary.get(
                "ruta_recuperada_despues_evasion"
            ),
            "cantidad_cambios_rumbo_ordenado": summary.get(
                "cantidad_cambios_rumbo_ordenado"
            ),
            "variacion_total_rumbo_ordenado_deg": summary.get(
                "variacion_total_rumbo_ordenado_deg"
            ),
        }
        rows.append(row)
        attempts_since_acceptance = 0

        if not monte_carlo_config.keep_scenarios:
            scenario_path.unlink(missing_ok=True)

        if (
            run_number == 1
            or run_number % monte_carlo_config.progress_every == 0
            or run_number == monte_carlo_config.runs
        ):
            acceptance_rate = (
                100.0 * run_number / candidates_generated
            )
            print(
                f"Aceptadas {run_number:4d}/"
                f"{monte_carlo_config.runs} | "
                f"candidatos={candidates_generated} | "
                f"aceptación={acceptance_rate:.2f}% | "
                f"seguro={safe_result}"
            )

    ripa_rows = [
        row for row in rows
        if row["ripa_evaluable"] is True
    ]
    evasive_rows = [
        row for row in rows
        if row.get("tiempo_total_evasion_s") is not None
        and float(row["tiempo_total_evasion_s"]) > 0.0
    ]

    safety_rate = _percentage_true(rows, "resultado_seguro")
    violation_rate = _percentage_true(rows, "violo_seguridad")
    ripa_rate = _percentage_true(ripa_rows, "cumplimiento_ripa")
    success_rate = _percentage_true(ripa_rows, "ejecucion_exitosa")

    summary_row = {
        "numero_ejecuciones": len(rows),
        "semilla_maestra": monte_carlo_config.master_seed,
        "candidatos_generados": candidates_generated,
        "candidatos_rechazados": candidates_generated - len(rows),
        "tasa_aceptacion_generador_pct": (
            100.0 * len(rows) / candidates_generated
        ),
        "numero_ripa_evaluable": len(ripa_rows),
        "numero_ripa_ambiguo": len(rows) - len(ripa_rows),
        "numero_ejecuciones_con_evasion": len(evasive_rows),
        "tasa_cumplimiento_ripa_pct": ripa_rate,
        "tasa_exito_pct": success_rate,
        "tasa_seguridad_pct": safety_rate,
        "tasa_violacion_seguridad_pct": violation_rate,
        "margen_seguridad_medio_m": _mean_or_none(
            float(row["margen_seguridad_m"])
            for row in rows
            if row["margen_seguridad_m"] is not None
        ),
        "tiempo_evasion_promedio_s": _mean_or_none(
            float(row["tiempo_total_evasion_s"])
            for row in evasive_rows
        ),
    }

    return rows, summary_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta un Monte Carlo de encuentros aleatorios riesgosos "
            "sin usar CPA/TCPA ni el clasificador del algoritmo para "
            "construir o aceptar los escenarios."
        )
    )

    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260804)

    parser.add_argument(
        "--area-radius-m",
        type=float,
        default=1000.0,
    )
    parser.add_argument(
        "--min-initial-distance-m",
        type=float,
        default=100.0,
    )
    parser.add_argument(
        "--safety-radius-m",
        type=float,
        default=50.0,
    )

    parser.add_argument(
        "--usv-speed-min-kn",
        type=float,
        default=4.0,
    )
    parser.add_argument(
        "--usv-speed-max-kn",
        type=float,
        default=8.0,
    )
    parser.add_argument(
        "--target-speed-min-kn",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--target-speed-max-kn",
        type=float,
        default=10.0,
    )

    parser.add_argument("--duration-s", type=int, default=200)
    parser.add_argument("--ais-step-s", type=int, default=5)
    parser.add_argument(
        "--independent-step-s",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--stand-on-hold-s",
        type=float,
        default=20.0,
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=1_000_000,
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--keep-scenarios",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    monte_carlo_config = MonteCarloRandomConfig(
        runs=args.runs,
        master_seed=args.seed,
        ais_step_s=args.ais_step_s,
        stand_on_hold_s=args.stand_on_hold_s,
        max_candidates=args.max_candidates,
        progress_every=args.progress_every,
        keep_scenarios=args.keep_scenarios,
    )

    encounter_config = RandomEncounterConfig(
        area_radius_m=args.area_radius_m,
        min_initial_distance_m=args.min_initial_distance_m,
        safety_radius_m=args.safety_radius_m,
        usv_speed_min_kn=args.usv_speed_min_kn,
        usv_speed_max_kn=args.usv_speed_max_kn,
        target_speed_min_kn=args.target_speed_min_kn,
        target_speed_max_kn=args.target_speed_max_kn,
        duration_s=float(args.duration_s),
        propagation_step_s=args.independent_step_s,
    )

    rows, summary_row = run_random_monte_carlo(
        monte_carlo_config=monte_carlo_config,
        encounter_config=encounter_config,
        output_dir=args.output_dir,
    )

    runs_path = args.output_dir / "random_monte_carlo_runs.csv"
    summary_path = (
        args.output_dir / "random_monte_carlo_summary.csv"
    )

    _save_csv(runs_path, rows, RUN_FIELDS)
    _save_csv(summary_path, [summary_row], SUMMARY_FIELDS)

    print("\nMonte Carlo aleatorio finalizado.")
    print(f"Resultados detallados: {runs_path}")
    print(f"Resumen: {summary_path}")
    print(
        "Tasa cumplimiento RIPA: "
        f"{summary_row['tasa_cumplimiento_ripa_pct']}%"
    )
    print(
        "Tasa de éxito: "
        f"{summary_row['tasa_exito_pct']}%"
    )
    print(
        "Tasa de seguridad: "
        f"{summary_row['tasa_seguridad_pct']}%"
    )
    print(
        "Tasa de violación: "
        f"{summary_row['tasa_violacion_seguridad_pct']}%"
    )
    print(
        "Margen de seguridad medio: "
        f"{summary_row['margen_seguridad_medio_m']} m"
    )
    print(
        "Tiempo de evasión promedio: "
        f"{summary_row['tiempo_evasion_promedio_s']} s"
    )


if __name__ == "__main__":
    main()
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from usv_avoidance.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from usv_avoidance.multiship_nmea_generator import (
    AisTargetDefinition,
    generate_multiship_nmea_scenario,
)
from usv_avoidance.random_multiship_generator import (
    MultishipGenerationConfig,
    RipaTargetReference,
    classify_ripa_reference,
    generate_multiship_candidate,
    normalize_signed,
    xy_to_latlon,
)
from usv_avoidance.scenario_config import DEFAULT_SCENARIO_CONFIG, PROJECT_ROOT
from usv_avoidance.simulation_runner import run_scenario

OUTPUT_DIR_DEFAULT = PROJECT_ROOT / "data" / "results" / "monte_carlo_multiship"

RUN_FIELDS = [
    "ejecucion", "semilla_maestra", "semilla_escenario", "numero_blancos",
    "intentos_generacion", "usv_sog_kn", "usv_cog_deg", "tiempo_ancla_s",
    "ventana_simultaneidad_s", "referencias_ripa_json", "baseline_json",
    "ripa_evaluable", "accion_global_esperada", "cumplimiento_ripa",
    "motivo_cumplimiento_ripa", "primera_maniobra_s", "primera_accion",
    "resultado_seguro", "violo_seguridad", "distancia_minima_m",
    "margen_seguridad_m", "ejecucion_exitosa", "tiempo_reaccion_s",
    "tiempo_total_evasion_s", "ruta_recuperada", "max_contactos_activos",
    "max_contactos_riesgo_simultaneo", "tiempo_riesgo_simultaneo_s",
    "cambios_contacto_prioritario", "cantidad_replanificaciones",
    "planes_condicionados_contacto_secundario", "planes_mejor_esfuerzo",
]

TARGET_FIELDS = [
    "ejecucion", "numero_blancos", "target_index", "mmsi", "x0_m", "y0_m",
    "distancia_inicial_m", "sog_kn", "cog_deg", "distancia_minima_baseline_m",
    "tiempo_minimo_baseline_s", "ripa_evaluable", "encuentro_referencia",
    "rol_referencia", "accion_esperada",
]

SUMMARY_FIELDS = [
    "numero_ejecuciones", "semilla_maestra", "promedio_blancos_por_escenario",
    "escenarios_2_blancos", "escenarios_3_blancos", "escenarios_4_blancos",
    "tasa_cumplimiento_ripa_pct", "tasa_exito_pct", "tasa_seguridad_pct",
    "tasa_violacion_seguridad_pct", "margen_seguridad_medio_m",
    "tiempo_evasion_promedio_s", "promedio_replanificaciones",
    "promedio_cambios_contacto_prioritario",
    "promedio_max_contactos_riesgo_simultaneo",
]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _pct(rows: list[Mapping[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return 100.0 * sum(row.get(field) is True for row in rows) / len(rows)


def _extract_behavior(
    result: Mapping[str, Any],
    original_course_deg: float,
) -> tuple[float | None, str | None, float | None]:
    first_maneuver_s = None
    first_action = None
    first_departure_s = None

    for step in result.get("steps") or []:
        time_s = float(step.get("time_s", 0.0))
        decision = step.get("avoidance_decision")
        if (
            first_maneuver_s is None
            and isinstance(decision, Mapping)
            and bool(decision.get("maneuver_required", False))
        ):
            first_maneuver_s = time_s
            action = decision.get("action")
            first_action = str(action) if action is not None else None

        commanded = step.get("commanded_course_deg")
        if first_departure_s is None and commanded is not None:
            if abs(normalize_signed(float(commanded) - original_course_deg)) > 3.0:
                first_departure_s = time_s

    return first_maneuver_s, first_action, first_departure_s


def _global_ripa_expectation(
    references: list[RipaTargetReference],
    baseline_times_s: list[float],
) -> tuple[bool, str | None, float | None]:
    evaluable = [
        (reference, time_s)
        for reference, time_s in zip(references, baseline_times_s)
        if reference.evaluable
    ]
    if not evaluable:
        return False, None, None

    give_way_times = [
        time_s
        for reference, time_s in evaluable
        if reference.ownship_role == "give_way"
    ]
    if give_way_times:
        return True, "alter_course_starboard", min(give_way_times)

    return True, "maintain_course", min(time_s for _, time_s in evaluable)


def _evaluate_global_ripa(
    expected_action: str | None,
    deadline_s: float | None,
    first_maneuver_s: float | None,
    first_action: str | None,
    first_departure_s: float | None,
    stand_on_hold_s: float,
) -> tuple[bool | None, str]:
    if expected_action is None or deadline_s is None:
        return None, "No existen contactos RIPA evaluables."

    if expected_action == "alter_course_starboard":
        starboard = first_action in {
            "alter_course_starboard",
            "alter_course_starboard_best_effort",
        }
        timely = first_maneuver_s is not None and first_maneuver_s <= deadline_s
        compliant = starboard and timely
        return compliant, (
            "Maniobra global a estribor y oportuna."
            if compliant
            else "No se ejecutó una maniobra global a estribor antes del conflicto basal."
        )

    hold_required_s = min(stand_on_hold_s, deadline_s)
    compliant = first_departure_s is None or first_departure_s >= hold_required_s
    return compliant, (
        "Mantuvo inicialmente el rumbo."
        if compliant
        else "Alteró el rumbo antes del periodo stand-on requerido."
    )


def run_monte_carlo(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not 2 <= args.min_targets <= args.max_targets <= 4:
        raise ValueError("Use entre 2 y 4 blancos.")

    output_dir: Path = args.output_dir
    scenario_dir = output_dir / "generated_scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    generation_config = MultishipGenerationConfig(
        area_radius_m=args.area_radius_m,
        min_initial_distance_m=args.min_initial_distance_m,
        min_intertarget_distance_m=args.min_intertarget_distance_m,
        safety_radius_m=args.safety_radius_m,
        usv_speed_min_kn=args.usv_speed_min_kn,
        usv_speed_max_kn=args.usv_speed_max_kn,
        target_speed_min_kn=args.target_speed_min_kn,
        target_speed_max_kn=args.target_speed_max_kn,
        duration_s=float(args.duration_s),
        propagation_step_s=args.independent_step_s,
        simultaneity_window_s=args.simultaneity_window_s,
        max_attempts_per_target=args.max_attempts_per_target,
    )

    algorithm_config = replace(
        DEFAULT_ALGORITHM_CONFIG,
        safety_radius_m=args.safety_radius_m,
        time_horizon_s=float(args.duration_s),
    )

    rng = random.Random(args.seed)
    run_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []

    for run_number in range(1, args.runs + 1):
        scenario_seed = rng.randrange(0, 2**32)
        scenario_rng = random.Random(scenario_seed)
        target_count = scenario_rng.randint(args.min_targets, args.max_targets)
        candidate = generate_multiship_candidate(
            scenario_rng,
            generation_config,
            target_count,
        )

        scenario_cfg = replace(
            DEFAULT_SCENARIO_CONFIG,
            usv_sog_kn=candidate.ownship.sog_kn,
            usv_cog_deg=candidate.ownship.cog_deg,
            usv_heading_deg=candidate.ownship.cog_deg,
            duration_s=args.duration_s,
            step_s=args.ais_step_s,
        )

        ais_targets: list[AisTargetDefinition] = []
        references: list[RipaTargetReference] = []
        baseline_times: list[float] = []
        reference_payload: list[dict[str, Any]] = []
        baseline_payload: list[dict[str, Any]] = []

        for target, baseline in zip(candidate.targets, candidate.baselines):
            mmsi = 725300000 + run_number * 10 + target.target_index
            lat, lon = xy_to_latlon(
                target.x0_m,
                target.y0_m,
                scenario_cfg.usv_lat0,
                scenario_cfg.usv_lon0,
            )
            ais_targets.append(
                AisTargetDefinition(
                    mmsi=mmsi,
                    lat0=lat,
                    lon0=lon,
                    sog_kn=target.sog_kn,
                    cog_deg=target.cog_deg,
                    heading_deg=int(round(target.cog_deg)) % 360,
                )
            )

            reference = classify_ripa_reference(candidate.ownship, target)
            references.append(reference)
            baseline_times.append(baseline.time_at_minimum_s)

            reference_payload.append({
                "mmsi": mmsi,
                "encounter": reference.encounter,
                "role": reference.ownship_role,
                "expected_action": reference.expected_action,
                "evaluable": reference.evaluable,
            })
            baseline_payload.append({
                "mmsi": mmsi,
                "minimum_distance_m": baseline.minimum_distance_m,
                "time_at_minimum_s": baseline.time_at_minimum_s,
            })

            target_rows.append({
                "ejecucion": run_number,
                "numero_blancos": target_count,
                "target_index": target.target_index,
                "mmsi": mmsi,
                "x0_m": target.x0_m,
                "y0_m": target.y0_m,
                "distancia_inicial_m": target.initial_distance_m,
                "sog_kn": target.sog_kn,
                "cog_deg": target.cog_deg,
                "distancia_minima_baseline_m": baseline.minimum_distance_m,
                "tiempo_minimo_baseline_s": baseline.time_at_minimum_s,
                "ripa_evaluable": reference.evaluable,
                "encuentro_referencia": reference.encounter,
                "rol_referencia": reference.ownship_role,
                "accion_esperada": reference.expected_action,
            })

        scenario_path = scenario_dir / f"mc_multiship_{run_number:05d}.txt"
        generate_multiship_nmea_scenario(
            scenario_path,
            ais_targets,
            duration_s=args.duration_s,
            step_s=args.ais_step_s,
        )

        result = run_scenario(
            scenario_name=str(scenario_path),
            save_results=False,
            playback_delay_s=0.0,
            algorithm_config=algorithm_config,
            scenario_config=scenario_cfg,
            expected_encounter=None,
            expected_ownship_role=None,
            expected_action=None,
        )
        summary = result["summary"]

        first_maneuver_s, first_action, first_departure_s = _extract_behavior(
            result,
            candidate.ownship.cog_deg,
        )
        ripa_evaluable, expected_action, deadline_s = _global_ripa_expectation(
            references,
            baseline_times,
        )
        compliance, compliance_reason = _evaluate_global_ripa(
            expected_action,
            deadline_s,
            first_maneuver_s,
            first_action,
            first_departure_s,
            args.stand_on_hold_s,
        )

        safe = bool(summary.get("resultado_seguro", False))
        success = safe and compliance is True if ripa_evaluable else None

        run_rows.append({
            "ejecucion": run_number,
            "semilla_maestra": args.seed,
            "semilla_escenario": scenario_seed,
            "numero_blancos": target_count,
            "intentos_generacion": candidate.attempts_used,
            "usv_sog_kn": candidate.ownship.sog_kn,
            "usv_cog_deg": candidate.ownship.cog_deg,
            "tiempo_ancla_s": candidate.anchor_time_s,
            "ventana_simultaneidad_s": args.simultaneity_window_s,
            "referencias_ripa_json": json.dumps(reference_payload, ensure_ascii=False),
            "baseline_json": json.dumps(baseline_payload, ensure_ascii=False),
            "ripa_evaluable": ripa_evaluable,
            "accion_global_esperada": expected_action,
            "cumplimiento_ripa": compliance,
            "motivo_cumplimiento_ripa": compliance_reason,
            "primera_maniobra_s": first_maneuver_s,
            "primera_accion": first_action,
            "resultado_seguro": safe,
            "violo_seguridad": not safe,
            "distancia_minima_m": summary.get("distancia_minima_m"),
            "margen_seguridad_m": summary.get("margen_seguridad_minimo_m"),
            "ejecucion_exitosa": success,
            "tiempo_reaccion_s": summary.get("tiempo_reaccion_s"),
            "tiempo_total_evasion_s": summary.get("tiempo_total_evasion_s"),
            "ruta_recuperada": summary.get("ruta_recuperada_despues_evasion"),
            "max_contactos_activos": summary.get("max_contactos_activos_simultaneos"),
            "max_contactos_riesgo_simultaneo": summary.get("max_contactos_en_riesgo_simultaneos"),
            "tiempo_riesgo_simultaneo_s": summary.get("tiempo_riesgo_simultaneo_s"),
            "cambios_contacto_prioritario": summary.get("cantidad_cambios_contacto_prioritario"),
            "cantidad_replanificaciones": summary.get("cantidad_replanificaciones"),
            "planes_condicionados_contacto_secundario": summary.get("planes_condicionados_por_contacto_secundario"),
            "planes_mejor_esfuerzo": summary.get("planes_mejor_esfuerzo"),
        })

        if not args.keep_scenarios:
            scenario_path.unlink(missing_ok=True)

        if run_number == 1 or run_number % args.progress_every == 0 or run_number == args.runs:
            print(f"Completadas {run_number}/{args.runs} simulaciones multibuque.")

    ripa_rows = [row for row in run_rows if row["ripa_evaluable"] is True]
    evasive_times = [
        float(row["tiempo_total_evasion_s"])
        for row in run_rows
        if row["tiempo_total_evasion_s"] is not None
        and float(row["tiempo_total_evasion_s"]) > 0.0
    ]

    summary_row = {
        "numero_ejecuciones": len(run_rows),
        "semilla_maestra": args.seed,
        "promedio_blancos_por_escenario": _mean([float(row["numero_blancos"]) for row in run_rows]),
        "escenarios_2_blancos": sum(row["numero_blancos"] == 2 for row in run_rows),
        "escenarios_3_blancos": sum(row["numero_blancos"] == 3 for row in run_rows),
        "escenarios_4_blancos": sum(row["numero_blancos"] == 4 for row in run_rows),
        "tasa_cumplimiento_ripa_pct": _pct(ripa_rows, "cumplimiento_ripa"),
        "tasa_exito_pct": _pct(ripa_rows, "ejecucion_exitosa"),
        "tasa_seguridad_pct": _pct(run_rows, "resultado_seguro"),
        "tasa_violacion_seguridad_pct": _pct(run_rows, "violo_seguridad"),
        "margen_seguridad_medio_m": _mean([
            float(row["margen_seguridad_m"])
            for row in run_rows if row["margen_seguridad_m"] is not None
        ]),
        "tiempo_evasion_promedio_s": _mean(evasive_times),
        "promedio_replanificaciones": _mean([
            float(row["cantidad_replanificaciones"] or 0) for row in run_rows
        ]),
        "promedio_cambios_contacto_prioritario": _mean([
            float(row["cambios_contacto_prioritario"] or 0) for row in run_rows
        ]),
        "promedio_max_contactos_riesgo_simultaneo": _mean([
            float(row["max_contactos_riesgo_simultaneo"] or 0) for row in run_rows
        ]),
    }

    return run_rows, target_rows, summary_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monte Carlo aleatorio con 2 a 4 blancos simultáneos."
    )
    parser.add_argument("--runs", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260804)
    parser.add_argument("--min-targets", type=int, default=2)
    parser.add_argument("--max-targets", type=int, default=4)
    parser.add_argument("--area-radius-m", type=float, default=1000.0)
    parser.add_argument("--min-initial-distance-m", type=float, default=100.0)
    parser.add_argument("--min-intertarget-distance-m", type=float, default=75.0)
    parser.add_argument("--safety-radius-m", type=float, default=50.0)
    parser.add_argument("--usv-speed-min-kn", type=float, default=4.0)
    parser.add_argument("--usv-speed-max-kn", type=float, default=8.0)
    parser.add_argument("--target-speed-min-kn", type=float, default=2.0)
    parser.add_argument("--target-speed-max-kn", type=float, default=10.0)
    parser.add_argument("--duration-s", type=int, default=200)
    parser.add_argument("--ais-step-s", type=int, default=5)
    parser.add_argument("--independent-step-s", type=float, default=0.5)
    parser.add_argument("--simultaneity-window-s", type=float, default=60.0)
    parser.add_argument("--stand-on-hold-s", type=float, default=20.0)
    parser.add_argument("--max-attempts-per-target", type=int, default=20000)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR_DEFAULT)
    parser.add_argument("--keep-scenarios", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.runs <= 0:
        raise ValueError("--runs debe ser positivo.")

    run_rows, target_rows, summary_row = run_monte_carlo(args)
    _write_csv(args.output_dir / "multiship_runs.csv", run_rows, RUN_FIELDS)
    _write_csv(args.output_dir / "multiship_targets.csv", target_rows, TARGET_FIELDS)
    _write_csv(args.output_dir / "multiship_summary.csv", [summary_row], SUMMARY_FIELDS)

    print("\nMonte Carlo multibuque finalizado.")
    print(args.output_dir / "multiship_summary.csv")


if __name__ == "__main__":
    main()
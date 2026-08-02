from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from usv_avoidance.algorithm_config import (
    AlgorithmConfig,
    DEFAULT_ALGORITHM_CONFIG,
)
from usv_avoidance.ais_type1_generator import (
    generate_moving_target_scenario,
    move_position,
)
from usv_avoidance.cpa_tcpa import (
    EARTH_RADIUS_M,
    calculate_cpa_tcpa,
    latlon_to_xy_m,
    velocity_components,
)
from usv_avoidance.encounter_classifier import classify_encounter
from usv_avoidance.encounter_geometry import calculate_bearing_info
from usv_avoidance.scenario_config import (
    DEFAULT_SCENARIO_CONFIG,
    PROJECT_ROOT,
    ScenarioConfig,
)
from usv_avoidance.simulation_runner import run_scenario


@dataclass(frozen=True)
class EncounterFamily:
    key: str
    expected_encounter: str
    expected_role: str
    expected_action: str


FAMILIES: dict[str, EncounterFamily] = {
    "crossing_starboard": EncounterFamily(
        key="crossing_starboard",
        expected_encounter="cruce",
        expected_role="give_way",
        expected_action="alter_course_starboard",
    ),
    "crossing_port": EncounterFamily(
        key="crossing_port",
        expected_encounter="cruce",
        expected_role="stand_on",
        expected_action="maintain_course",
    ),
    "head_on": EncounterFamily(
        key="head_on",
        expected_encounter="vuelta encontrada",
        expected_role="give_way",
        expected_action="alter_course_starboard",
    ),
    "overtaking": EncounterFamily(
        key="overtaking",
        expected_encounter="alcance",
        expected_role="give_way",
        expected_action="alter_course_starboard",
    ),
    "being_overtaken": EncounterFamily(
        key="being_overtaken",
        expected_encounter="alcance por blanco",
        expected_role="stand_on",
        expected_action="maintain_course",
    ),
}


RUN_FIELDS = [
    "familia",
    "ejecucion",
    "semilla_maestra",
    "semilla_ejecucion",
    "intentos_generacion",
    "usv_sog_kn",
    "usv_cog_deg",
    "target_sog_kn",
    "target_cog_deg",
    "distancia_inicial_m",
    "bearing_relativo_inicial_deg",
    "cpa_inicial_m",
    "tcpa_inicial_s",
    "distancia_minima_baseline_m",
    "baseline_violo_seguridad",
    "resultado_seguro",
    "comportamiento_esperado",
    "escenario_exitoso",
    "distancia_minima_algoritmo_m",
    "margen_seguridad_minimo_m",
    "mejora_distancia_minima_m",
    "tiempo_reaccion_s",
    "caida_seleccionada_deg",
    "ruta_recuperada",
    "cantidad_cambios_rumbo_ordenado",
    "variacion_total_rumbo_ordenado_deg",
    "cantidad_replanificaciones",
]


SUMMARY_FIELDS = [
    "familia",
    "n",
    "semilla_maestra",
    "tasa_seguridad_pct",
    "tasa_comportamiento_pct",
    "tasa_exito_pct",
    "violaciones_baseline_pct",
    "violaciones_algoritmo_pct",
    "distancia_minima_mediana_m",
    "distancia_minima_p05_m",
    "margen_seguridad_mediana_m",
    "mejora_mediana_m",
    "tiempo_reaccion_mediana_s",
]


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "results" / "monte_carlo"


def normalize_course_deg(value: float) -> float:
    return value % 360.0


def xy_to_latlon_m(
    x_east_m: float,
    y_north_m: float,
    ref_lat: float,
    ref_lon: float,
) -> tuple[float, float]:
    lat = ref_lat + math.degrees(y_north_m / EARTH_RADIUS_M)

    cos_lat = math.cos(math.radians(ref_lat))
    if abs(cos_lat) < 1e-12:
        raise ValueError("La latitud de referencia no es válida.")

    lon = ref_lon + math.degrees(
        x_east_m / (EARTH_RADIUS_M * cos_lat)
    )

    return lat, lon


def sample_speeds_and_course(
    family: EncounterFamily,
    rng: random.Random,
) -> tuple[float, float, float]:
    ownship_sog_kn = rng.uniform(4.0, 8.0)
    ownship_cog_deg = rng.uniform(0.0, 360.0)

    if family.key == "crossing_starboard":
        target_sog_kn = rng.uniform(4.0, 10.0)
        target_cog_deg = ownship_cog_deg - 90.0 + rng.uniform(-10.0, 10.0)

    elif family.key == "crossing_port":
        target_sog_kn = rng.uniform(4.0, 10.0)
        target_cog_deg = ownship_cog_deg + 90.0 + rng.uniform(-10.0, 10.0)

    elif family.key == "head_on":
        target_sog_kn = rng.uniform(4.0, 10.0)
        target_cog_deg = ownship_cog_deg + 180.0 + rng.uniform(-5.0, 5.0)

    elif family.key == "overtaking":
        ownship_sog_kn = rng.uniform(6.0, 9.0)
        target_sog_kn = rng.uniform(2.5, ownship_sog_kn - 0.5)
        target_cog_deg = ownship_cog_deg + rng.uniform(-2.0, 2.0)

    elif family.key == "being_overtaken":
        ownship_sog_kn = rng.uniform(3.0, 6.5)
        target_sog_kn = rng.uniform(ownship_sog_kn + 0.5, 10.0)
        target_cog_deg = ownship_cog_deg + rng.uniform(-2.0, 2.0)

    else:
        raise ValueError(f"Familia no soportada: {family.key}")

    return (
        ownship_sog_kn,
        normalize_course_deg(ownship_cog_deg),
        normalize_course_deg(target_cog_deg),
        target_sog_kn,
    )


def build_candidate(
    family: EncounterFamily,
    rng: random.Random,
    algorithm_config: AlgorithmConfig,
    base_scenario_config: ScenarioConfig,
) -> tuple[ScenarioConfig, dict[str, Any], dict[str, Any]]:
    max_tcpa_s = min(
        algorithm_config.time_horizon_s - base_scenario_config.step_s,
        base_scenario_config.duration_s - base_scenario_config.step_s,
        180.0,
    )

    if max_tcpa_s <= 45.0:
        raise ValueError(
            "El horizonte o la duración son demasiado cortos para Monte Carlo."
        )

    for attempt in range(1, 501):
        (
            ownship_sog_kn,
            ownship_cog_deg,
            target_cog_deg,
            target_sog_kn,
        ) = sample_speeds_and_course(family, rng)

        tcpa_target_s = rng.uniform(45.0, max_tcpa_s)

        own_vx, own_vy = velocity_components(
            ownship_sog_kn,
            ownship_cog_deg,
        )
        target_vx, target_vy = velocity_components(
            target_sog_kn,
            target_cog_deg,
        )

        rel_vx = target_vx - own_vx
        rel_vy = target_vy - own_vy
        rel_speed = math.hypot(rel_vx, rel_vy)

        if rel_speed < 0.2:
            continue

        if family.key == "head_on":
            max_offset_m = min(
                0.25 * algorithm_config.safety_radius_m,
                15.0,
            )
        else:
            max_offset_m = 0.80 * algorithm_config.safety_radius_m

        offset_m = rng.uniform(0.0, max_offset_m)
        if rng.random() < 0.5:
            offset_m *= -1.0

        perpendicular_x = -rel_vy / rel_speed
        perpendicular_y = rel_vx / rel_speed

        target_x_m = (
            own_vx * tcpa_target_s
            - target_vx * tcpa_target_s
            + perpendicular_x * offset_m
        )
        target_y_m = (
            own_vy * tcpa_target_s
            - target_vy * tcpa_target_s
            + perpendicular_y * offset_m
        )

        target_lat, target_lon = xy_to_latlon_m(
            x_east_m=target_x_m,
            y_north_m=target_y_m,
            ref_lat=base_scenario_config.usv_lat0,
            ref_lon=base_scenario_config.usv_lon0,
        )

        scenario_config = replace(
            base_scenario_config,
            usv_sog_kn=ownship_sog_kn,
            usv_cog_deg=ownship_cog_deg,
            usv_heading_deg=ownship_cog_deg,
        )

        ownship = {
            "lat": scenario_config.usv_lat0,
            "lon": scenario_config.usv_lon0,
            "sog_kn": scenario_config.usv_sog_kn,
            "cog_deg": scenario_config.usv_cog_deg,
            "heading_deg": scenario_config.usv_heading_deg,
        }

        target = {
            "mmsi": 725100001,
            "lat": target_lat,
            "lon": target_lon,
            "sog_kn": target_sog_kn,
            "cog_deg": target_cog_deg,
            "heading_deg": target_cog_deg,
        }

        cpa_result = calculate_cpa_tcpa(
            ownship=ownship,
            target=target,
            safety_radius_m=algorithm_config.safety_radius_m,
            time_horizon_s=algorithm_config.time_horizon_s,
        )
        bearing_info = calculate_bearing_info(
            ownship=ownship,
            target=target,
        )
        classification = classify_encounter(
            ownship=ownship,
            target=target,
            cpa_result=cpa_result,
            bearing_info=bearing_info,
        )

        valid = (
            cpa_result["risk"] is True
            and float(cpa_result["distance_m"])
            >= 2.0 * algorithm_config.safety_radius_m
            and float(cpa_result["tcpa_s"]) > 0.0
            and classification["encounter_name"]
            == family.expected_encounter
            and classification["ownship_role"]
            == family.expected_role
        )

        if not valid:
            continue

        initial_info = {
            "attempt": attempt,
            "target": target,
            "cpa_result": cpa_result,
            "bearing_info": bearing_info,
            "classification": classification,
        }

        return scenario_config, target, initial_info

    raise RuntimeError(
        f"No fue posible generar un caso válido para {family.key}."
    )


def simulate_baseline_min_distance(
    scenario_config: ScenarioConfig,
    target: dict[str, Any],
) -> float:
    own_lat = scenario_config.usv_lat0
    own_lon = scenario_config.usv_lon0
    target_lat = float(target["lat"])
    target_lon = float(target["lon"])

    min_distance_m = math.inf

    for _ in range(
        0,
        scenario_config.duration_s + 1,
        scenario_config.step_s,
    ):
        x_m, y_m = latlon_to_xy_m(
            lat=target_lat,
            lon=target_lon,
            ref_lat=own_lat,
            ref_lon=own_lon,
        )
        min_distance_m = min(
            min_distance_m,
            math.hypot(x_m, y_m),
        )

        own_lat, own_lon = move_position(
            lat=own_lat,
            lon=own_lon,
            sog_kn=scenario_config.usv_sog_kn,
            cog_deg=scenario_config.usv_cog_deg,
            delta_t_s=scenario_config.step_s,
        )
        target_lat, target_lon = move_position(
            lat=target_lat,
            lon=target_lon,
            sog_kn=float(target["sog_kn"]),
            cog_deg=float(target["cog_deg"]),
            delta_t_s=scenario_config.step_s,
        )

    return min_distance_m


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    fraction = position - lower
    return ordered[lower] + fraction * (
        ordered[upper] - ordered[lower]
    )


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def run_monte_carlo(
    families: tuple[str, ...],
    runs_per_family: int,
    master_seed: int,
    output_dir: Path,
    keep_scenarios: bool,
) -> list[dict[str, Any]]:
    if runs_per_family <= 0:
        raise ValueError("runs_per_family debe ser mayor que cero.")

    algorithm_config = DEFAULT_ALGORITHM_CONFIG
    base_scenario_config = DEFAULT_SCENARIO_CONFIG

    temp_dir = output_dir / "generated_scenarios"
    temp_dir.mkdir(parents=True, exist_ok=True)

    master_rng = random.Random(master_seed)
    rows: list[dict[str, Any]] = []

    for family_index, family_key in enumerate(families):
        family = FAMILIES[family_key]
        print(f"\nFamilia: {family.key}")

        for run_index in range(1, runs_per_family + 1):
            trial_seed = master_rng.randrange(0, 2**32)
            rng = random.Random(trial_seed)

            scenario_config, target, initial_info = build_candidate(
                family=family,
                rng=rng,
                algorithm_config=algorithm_config,
                base_scenario_config=base_scenario_config,
            )

            mmsi = (
                725100000
                + family_index * 10000
                + run_index
            )
            target["mmsi"] = mmsi

            scenario_path = temp_dir / (
                f"mc_{family.key}_{run_index:05d}.txt"
            )

            generate_moving_target_scenario(
                output_file=str(scenario_path),
                mmsi=mmsi,
                lat0=float(target["lat"]),
                lon0=float(target["lon"]),
                sog_kn=float(target["sog_kn"]),
                cog_deg=float(target["cog_deg"]),
                heading_deg=int(round(float(target["heading_deg"]))) % 360,
                duration_s=scenario_config.duration_s,
                step_s=scenario_config.step_s,
            )

            baseline_min_distance_m = simulate_baseline_min_distance(
                scenario_config=scenario_config,
                target=target,
            )

            result = run_scenario(
                scenario_name=str(scenario_path),
                save_results=False,
                playback_delay_s=0.0,
                algorithm_config=algorithm_config,
                scenario_config=scenario_config,
                expected_encounter=family.expected_encounter,
                expected_ownship_role=family.expected_role,
                expected_action=family.expected_action,
            )
            summary = result["summary"]

            algorithm_min_distance_m = summary.get(
                "distancia_minima_m"
            )
            improvement_m = None
            if algorithm_min_distance_m is not None:
                improvement_m = (
                    float(algorithm_min_distance_m)
                    - baseline_min_distance_m
                )

            cpa_result = initial_info["cpa_result"]
            bearing_info = initial_info["bearing_info"]

            row = {
                "familia": family.key,
                "ejecucion": run_index,
                "semilla_maestra": master_seed,
                "semilla_ejecucion": trial_seed,
                "intentos_generacion": initial_info["attempt"],
                "usv_sog_kn": scenario_config.usv_sog_kn,
                "usv_cog_deg": scenario_config.usv_cog_deg,
                "target_sog_kn": target["sog_kn"],
                "target_cog_deg": target["cog_deg"],
                "distancia_inicial_m": cpa_result["distance_m"],
                "bearing_relativo_inicial_deg": (
                    bearing_info["relative_bearing_deg"]
                ),
                "cpa_inicial_m": cpa_result["cpa_m"],
                "tcpa_inicial_s": cpa_result["tcpa_s"],
                "distancia_minima_baseline_m": baseline_min_distance_m,
                "baseline_violo_seguridad": (
                    baseline_min_distance_m
                    < algorithm_config.safety_radius_m
                ),
                "resultado_seguro": summary.get("resultado_seguro"),
                "comportamiento_esperado": summary.get(
                    "comportamiento_esperado"
                ),
                "escenario_exitoso": summary.get(
                    "escenario_exitoso"
                ),
                "distancia_minima_algoritmo_m": algorithm_min_distance_m,
                "margen_seguridad_minimo_m": summary.get(
                    "margen_seguridad_minimo_m"
                ),
                "mejora_distancia_minima_m": improvement_m,
                "tiempo_reaccion_s": summary.get("tiempo_reaccion_s"),
                "caida_seleccionada_deg": summary.get(
                    "caida_seleccionada_deg"
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
                "cantidad_replanificaciones": summary.get(
                    "cantidad_replanificaciones"
                ),
            }
            rows.append(row)

            if not keep_scenarios:
                scenario_path.unlink(missing_ok=True)

            print(
                f"  {run_index:4d}/{runs_per_family}: "
                f"seguro={row['resultado_seguro']}, "
                f"dmin={row['distancia_minima_algoritmo_m']}"
            )

    return rows


def build_summary(
    rows: list[dict[str, Any]],
    master_seed: int,
) -> list[dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []

    for family_key in sorted({row["familia"] for row in rows}):
        family_rows = [
            row for row in rows
            if row["familia"] == family_key
        ]
        n = len(family_rows)

        algorithm_distances = [
            float(row["distancia_minima_algoritmo_m"])
            for row in family_rows
            if row["distancia_minima_algoritmo_m"] is not None
        ]
        margins = [
            float(row["margen_seguridad_minimo_m"])
            for row in family_rows
            if row["margen_seguridad_minimo_m"] is not None
        ]
        improvements = [
            float(row["mejora_distancia_minima_m"])
            for row in family_rows
            if row["mejora_distancia_minima_m"] is not None
        ]
        reaction_times = [
            float(row["tiempo_reaccion_s"])
            for row in family_rows
            if row["tiempo_reaccion_s"] is not None
        ]

        def percentage(field: str) -> float:
            return 100.0 * sum(
                bool(row[field]) for row in family_rows
            ) / n

        summary_rows.append(
            {
                "familia": family_key,
                "n": n,
                "semilla_maestra": master_seed,
                "tasa_seguridad_pct": percentage("resultado_seguro"),
                "tasa_comportamiento_pct": percentage(
                    "comportamiento_esperado"
                ),
                "tasa_exito_pct": percentage("escenario_exitoso"),
                "violaciones_baseline_pct": percentage(
                    "baseline_violo_seguridad"
                ),
                "violaciones_algoritmo_pct": (
                    100.0 - percentage("resultado_seguro")
                ),
                "distancia_minima_mediana_m": median_or_none(
                    algorithm_distances
                ),
                "distancia_minima_p05_m": percentile(
                    algorithm_distances,
                    0.05,
                ),
                "margen_seguridad_mediana_m": median_or_none(margins),
                "mejora_mediana_m": median_or_none(improvements),
                "tiempo_reaccion_mediana_s": median_or_none(
                    reaction_times
                ),
            }
        )

    return summary_rows


def save_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta simulaciones Monte Carlo para las familias "
            "de encuentro definidas."
        )
    )
    parser.add_argument(
        "--runs-per-family",
        type=int,
        default=100,
        help="Cantidad de ejecuciones aceptadas por familia.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260729,
        help="Semilla maestra reproducible.",
    )
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(FAMILIES),
        dest="families",
        help="Familia a ejecutar. Puede repetirse.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--keep-scenarios",
        action="store_true",
        help="Conserva los archivos NMEA generados.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    families = (
        tuple(args.families)
        if args.families
        else tuple(FAMILIES)
    )

    rows = run_monte_carlo(
        families=families,
        runs_per_family=args.runs_per_family,
        master_seed=args.seed,
        output_dir=args.output_dir,
        keep_scenarios=args.keep_scenarios,
    )
    summary_rows = build_summary(
        rows=rows,
        master_seed=args.seed,
    )

    runs_path = args.output_dir / "monte_carlo_runs.csv"
    summary_path = args.output_dir / "monte_carlo_summary.csv"

    save_csv(runs_path, rows, RUN_FIELDS)
    save_csv(summary_path, summary_rows, SUMMARY_FIELDS)

    print("\nMonte Carlo finalizado.")
    print(f"Ejecuciones aceptadas: {len(rows)}")
    print(f"Resultados detallados: {runs_path}")
    print(f"Resumen: {summary_path}")


if __name__ == "__main__":
    main()
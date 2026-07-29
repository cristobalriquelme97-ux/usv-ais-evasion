from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path
from typing import Any

from usv_avoidance.algorithm_config import (
    DEFAULT_ALGORITHM_CONFIG,
)
from usv_avoidance.scenario_config import PROJECT_ROOT
from usv_avoidance.simulation_runner import run_scenario


DEFAULT_SCENARIOS = (
    "crossing_starboard_risk_nmea.txt",
    "head_on_risk_nmea.txt",
    "overtaking_ownship_give_way_nmea.txt",
)


SENSITIVITY_PLAN: dict[str, tuple[float, ...]] = {
    "safety_radius_m": (
        30.0,
        40.0,
        50.0,
        60.0,
        75.0,
    ),
    "time_horizon_s": (
        120.0,
        160.0,
        200.0,
        240.0,
        300.0,
    ),
    "maneuver_decision_delay_s": (
        0.0,
        10.0,
        20.0,
        30.0,
        40.0,
    ),
}


OUTPUT_FIELDS = [
    "escenario",
    "parametro",
    "valor",

    "resultado_seguro",
    "comportamiento_esperado",
    "escenario_exitoso",

    "distancia_minima_m",
    "margen_seguridad_minimo_m",
    "cpa_minimo_m",

    "tiempo_reaccion_s",
    "caida_seleccionada_deg",
    "tiempo_total_evasion_s",
    "ruta_recuperada_despues_evasion",

    "cantidad_cambios_estado",
    "cantidad_cambios_rumbo_ordenado",
    "variacion_total_rumbo_ordenado_deg",
    "cantidad_replanificaciones",
]


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "results"
    / "sensitivity_analysis.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta un análisis de sensibilidad variando un "
            "parámetro algorítmico a la vez."
        )
    )

    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help=(
            "Escenario que se analizará. Puede repetirse para "
            "incluir varios escenarios."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Archivo CSV de salida.",
    )

    return parser.parse_args()


def build_result_row(
    scenario_name: str,
    parameter_name: str,
    parameter_value: float,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "escenario": scenario_name,
        "parametro": parameter_name,
        "valor": parameter_value,

        "resultado_seguro": summary.get(
            "resultado_seguro"
        ),
        "comportamiento_esperado": summary.get(
            "comportamiento_esperado"
        ),
        "escenario_exitoso": summary.get(
            "escenario_exitoso"
        ),

        "distancia_minima_m": summary.get(
            "distancia_minima_m"
        ),
        "margen_seguridad_minimo_m": summary.get(
            "margen_seguridad_minimo_m"
        ),
        "cpa_minimo_m": summary.get(
            "cpa_minimo_m"
        ),

        "tiempo_reaccion_s": summary.get(
            "tiempo_reaccion_s"
        ),
        "caida_seleccionada_deg": summary.get(
            "caida_seleccionada_deg"
        ),
        "tiempo_total_evasion_s": summary.get(
            "tiempo_total_evasion_s"
        ),
        "ruta_recuperada_despues_evasion": summary.get(
            "ruta_recuperada_despues_evasion"
        ),

        "cantidad_cambios_estado": summary.get(
            "cantidad_cambios_estado"
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


def run_sensitivity_analysis(
    scenario_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for scenario_name in scenario_names:
        print(f"\nEscenario: {scenario_name}")

        for parameter_name, values in SENSITIVITY_PLAN.items():
            print(f"  Parámetro: {parameter_name}")

            for value in values:
                config = replace(
                    DEFAULT_ALGORITHM_CONFIG,
                    **{
                        parameter_name: value,
                    },
                )

                result = run_scenario(
                    scenario_name=scenario_name,
                    save_results=False,
                    playback_delay_s=0.0,
                    algorithm_config=config,
                )

                summary = result["summary"]

                row = build_result_row(
                    scenario_name=scenario_name,
                    parameter_name=parameter_name,
                    parameter_value=value,
                    summary=summary,
                )

                rows.append(row)

                print(
                    f"    {value:7.1f} -> "
                    f"seguro={row['resultado_seguro']}, "
                    f"dist_min="
                    f"{row['distancia_minima_m']}"
                )

    return rows


def save_results(
    rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=OUTPUT_FIELDS,
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    if args.scenarios:
        scenario_names = tuple(args.scenarios)
    else:
        scenario_names = DEFAULT_SCENARIOS

    rows = run_sensitivity_analysis(
        scenario_names=scenario_names,
    )

    save_results(
        rows=rows,
        output_path=args.output,
    )

    print("\nAnálisis completado.")
    print(f"Ejecuciones realizadas: {len(rows)}")
    print(f"Resultados: {args.output}")


if __name__ == "__main__":
    main()
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from usv_avoidance.scenario_config import PROJECT_ROOT


RESULTS_DIR = PROJECT_ROOT / "data" / "results"
DEFAULT_OUTPUT_FILE = RESULTS_DIR / "evaluation_summary.csv"


SUMMARY_FIELDS = [
    "nombre_escenario",
    "escenario_exitoso",
    "riesgo_detectado",
    "violo_radio_seguridad",
    "estado_final",
    "accion_seleccionada",
    "caida_seleccionada_deg",
    "distancia_minima_m",
    "cpa_minimo_m",
    "margen_seguridad_minimo_m",
    "tiempo_reaccion_s",
    "tiempo_total_evasion_s",
    "tiempo_total_despeje_s",
    "tiempo_total_retorno_ruta_s",
    "ruta_recuperada_despues_evasion",
    "desviacion_maxima_rumbo_usv_deg",
    "cantidad_cambios_estado",
    "cantidad_cambios_rumbo_ordenado",
    "variacion_total_rumbo_ordenado_deg",
    "max_cambio_rumbo_ordenado_deg",
    "total_muestras",
]


def parse_args() -> argparse.Namespace:
    """
    Lee argumentos desde la terminal.

    Ejemplo:
        python -m usv_avoidance.evaluation_report
    """

    parser = argparse.ArgumentParser(
        description=(
            "Genera una tabla resumen de evaluación a partir de los archivos "
            "*_summary.json guardados en data/results."
        )
    )

    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help="Directorio donde están los archivos *_summary.json.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Ruta del archivo CSV resumen de salida.",
    )

    return parser.parse_args()


def load_summary(path: Path) -> dict[str, Any]:
    """
    Carga un archivo JSON de resumen de simulación.
    """

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def find_summary_files(results_dir: Path) -> list[Path]:
    """
    Busca todos los archivos *_summary.json generados por SimulationMetrics.
    """

    return sorted(results_dir.glob("*_summary.json"))


def build_rows(summary_files: list[Path]) -> list[dict[str, Any]]:
    """
    Construye filas normalizadas para el CSV final.
    """

    rows = []

    for summary_file in summary_files:
        summary = load_summary(summary_file)

        row = {
            field: summary.get(field)
            for field in SUMMARY_FIELDS
        }

        rows.append(row)

    return rows


def save_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    """
    Guarda la tabla resumen en formato CSV.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def print_compact_table(rows: list[dict[str, Any]]) -> None:
    """
    Imprime una tabla simple en la terminal para revisar rápidamente
    el desempeño de cada escenario.
    """

    if not rows:
        print("No hay filas para mostrar.")
        return

    print("\nResumen comparativo de evaluación")
    print("-" * 100)

    header = (
        f"{'Escenario':30} | "
        f"{'Éxito':6} | "
        f"{'Riesgo':6} | "
        f"{'Violó':6} | "
        f"{'Dist min [m]':12} | "
        f"{'CPA min [m]':11} | "
        f"{'Cambios estado':14}"
    )

    print(header)
    print("-" * 100)

    for row in rows:
        scenario_name = str(row.get("nombre_escenario"))
        success = str(row.get("escenario_exitoso"))
        risk = str(row.get("riesgo_detectado"))
        violation = str(row.get("violo_radio_seguridad"))
        min_distance = row.get("distancia_minima_m")
        min_cpa = row.get("cpa_minimo_m")
        state_changes = row.get("cantidad_cambios_estado")

        min_distance_text = (
            f"{min_distance:.2f}"
            if isinstance(min_distance, int | float)
            else "sin datos"
        )

        min_cpa_text = (
            f"{min_cpa:.2f}"
            if isinstance(min_cpa, int | float)
            else "sin datos"
        )

        print(
            f"{scenario_name[:30]:30} | "
            f"{success:6} | "
            f"{risk:6} | "
            f"{violation:6} | "
            f"{min_distance_text:12} | "
            f"{min_cpa_text:11} | "
            f"{str(state_changes):14}"
        )


def main() -> None:
    args = parse_args()

    summary_files = find_summary_files(args.results_dir)

    if not summary_files:
        print(f"No se encontraron archivos *_summary.json en: {args.results_dir}")
        return

    rows = build_rows(summary_files)
    save_csv(rows, args.output)
    print_compact_table(rows)

    print("\nArchivo CSV generado:")
    print(args.output)


if __name__ == "__main__":
    main()
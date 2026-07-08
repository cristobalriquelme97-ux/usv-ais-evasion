# Sirve para ejecutar automáticamente varios escenarios de simulación AIS/NMEA y guardar sus resultados en data/results.

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from usv_avoidance.scenario_config import PROJECT_ROOT, SCENARIOS_DIR


RESULTS_DIR = PROJECT_ROOT / "data" / "results"
LOGS_DIR = RESULTS_DIR / "logs"


def parse_args() -> argparse.Namespace:
    """
    Lee argumentos desde la terminal para ejecutar varios escenarios.

    Ejemplos:
        python -m usv_avoidance.batch_simulation

        python -m usv_avoidance.batch_simulation --pattern "*risk*.txt"

        python -m usv_avoidance.batch_simulation --stop-on-error
    """

    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta automáticamente escenarios AIS/NMEA ubicados "
            "en data/scenarios y guarda sus resultados en data/results."
        )
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="*.txt",
        help="Patrón de archivos de escenario a ejecutar. Por defecto: *.txt",
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Detiene la ejecución si un escenario falla.",
    )

    return parser.parse_args()


def find_scenarios(pattern: str) -> list[Path]:
    """
    Busca escenarios dentro de data/scenarios usando un patrón.
    """

    scenario_files = sorted(SCENARIOS_DIR.glob(pattern))

    return [
        scenario_file
        for scenario_file in scenario_files
        if scenario_file.is_file()
    ]


def run_scenario(scenario_file: Path) -> int:
    """
    Ejecuta un escenario llamando a main.py como módulo.

    Se usa sys.executable para asegurar que se utilice el mismo entorno
    virtual activo.
    """

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOGS_DIR / f"{scenario_file.stem}.log"

    command = [
        sys.executable,
        "-m",
        "usv_avoidance.main",
        "--scenario",
        scenario_file.name,
    ]

    print("=" * 70)
    print(f"Ejecutando escenario: {scenario_file.name}")
    print(f"Log: {log_path}")
    print("=" * 70)

    with log_path.open("w", encoding="utf-8") as log_file:
        completed_process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    if completed_process.returncode == 0:
        print(f"OK: {scenario_file.name}")
    else:
        print(f"ERROR: {scenario_file.name}")
        print(f"Revisar log: {log_path}")

    return completed_process.returncode


def main() -> None:
    args = parse_args()

    scenario_files = find_scenarios(args.pattern)

    if not scenario_files:
        print(f"No se encontraron escenarios con patrón: {args.pattern}")
        print(f"Directorio revisado: {SCENARIOS_DIR}")
        return

    print("\nEscenarios encontrados:")
    for scenario_file in scenario_files:
        print(f" - {scenario_file.name}")

    total = len(scenario_files)
    successful = 0
    failed = 0

    for scenario_file in scenario_files:
        return_code = run_scenario(scenario_file)

        if return_code == 0:
            successful += 1
        else:
            failed += 1

            if args.stop_on_error:
                break

    print("\nResumen ejecución batch")
    print("-" * 70)
    print(f"Total escenarios encontrados: {total}")
    print(f"Escenarios ejecutados correctamente: {successful}")
    print(f"Escenarios con error: {failed}")
    print(f"Resultados guardados en: {RESULTS_DIR}")
    print(f"Logs guardados en: {LOGS_DIR}")


if __name__ == "__main__":
    main()
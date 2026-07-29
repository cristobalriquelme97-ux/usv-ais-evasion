from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from usv_avoidance.scenario_config import (
    PROJECT_ROOT,
    SCENARIOS_DIR,
)
from usv_avoidance.simulation_runner import (
    run_scenario as run_simulation,
)


RESULTS_DIR = PROJECT_ROOT / "data" / "results"
LOGS_DIR = RESULTS_DIR / "logs"


def parse_args() -> argparse.Namespace:
    """
    Lee argumentos desde la terminal para ejecutar varios escenarios.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta automáticamente escenarios AIS/NMEA ubicados "
            "en data/scenarios y guarda sus resultados."
        )
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="*.txt",
        help=(
            "Patrón de escenarios que se ejecutarán. "
            "Por defecto: *.txt"
        ),
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help=(
            "Detiene la ejecución cuando un escenario presenta "
            "un error."
        ),
    )

    return parser.parse_args()


def find_scenarios(pattern: str) -> list[Path]:
    """
    Busca escenarios dentro de data/scenarios.
    """

    return [
        scenario_file
        for scenario_file in sorted(
            SCENARIOS_DIR.glob(pattern)
        )
        if scenario_file.is_file()
    ]


def save_execution_log(
    scenario_file: Path,
    result: dict[str, Any],
) -> Path:
    """
    Guarda un resumen legible de la ejecución batch.
    """

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOGS_DIR / f"{scenario_file.stem}.log"

    log_data = {
        "scenario": result.get("scenario"),
        "config": result.get("config"),
        "summary": result.get("summary"),
        "metric_paths": result.get("metric_paths"),
    }

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log_file:
        json.dump(
            log_data,
            log_file,
            indent=4,
            ensure_ascii=False,
        )

    return log_path


def save_error_log(
    scenario_file: Path,
    error: Exception,
) -> Path:
    """
    Guarda el traceback cuando falla un escenario.
    """

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_path = LOGS_DIR / f"{scenario_file.stem}.log"

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log_file:
        log_file.write(
            f"Error ejecutando {scenario_file.name}\n\n"
        )
        log_file.write(
            f"{type(error).__name__}: {error}\n\n"
        )
        log_file.write(traceback.format_exc())

    return log_path


def execute_scenario(scenario_file: Path) -> bool:
    """
    Ejecuta un escenario utilizando el motor único.
    """

    print("=" * 70)
    print(f"Ejecutando escenario: {scenario_file.name}")
    print("=" * 70)

    try:
        result = run_simulation(
            scenario_name=scenario_file.name,
            save_results=True,
            playback_delay_s=0.0,
        )

        log_path = save_execution_log(
            scenario_file=scenario_file,
            result=result,
        )

    except Exception as error:
        log_path = save_error_log(
            scenario_file=scenario_file,
            error=error,
        )

        print(f"ERROR: {scenario_file.name}")
        print(f"Revisar log: {log_path}")

        return False

    print(f"OK: {scenario_file.name}")
    print(f"Log: {log_path}")

    return True


def main() -> None:
    args = parse_args()

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    scenario_files = find_scenarios(
        args.pattern
    )

    if not scenario_files:
        print(
            "No se encontraron escenarios con patrón: "
            f"{args.pattern}"
        )
        print(
            f"Directorio revisado: {SCENARIOS_DIR}"
        )
        return

    print("\nEscenarios encontrados:")

    for scenario_file in scenario_files:
        print(f" - {scenario_file.name}")

    total = len(scenario_files)
    successful = 0
    failed = 0

    for scenario_file in scenario_files:
        success = execute_scenario(
            scenario_file
        )

        if success:
            successful += 1
        else:
            failed += 1

            if args.stop_on_error:
                break

    print("\nResumen ejecución batch")
    print("-" * 70)
    print(
        f"Total escenarios encontrados: {total}"
    )
    print(
        "Escenarios ejecutados correctamente: "
        f"{successful}"
    )
    print(
        f"Escenarios con error: {failed}"
    )
    print(
        f"Resultados guardados en: {RESULTS_DIR}"
    )
    print(
        f"Logs guardados en: {LOGS_DIR}"
    )


if __name__ == "__main__":
    main()
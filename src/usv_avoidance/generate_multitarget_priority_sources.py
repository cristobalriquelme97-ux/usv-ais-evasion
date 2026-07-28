from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Sequence

from usv_avoidance.ais_type1_generator import (
    generate_moving_target_scenario,
)
from usv_avoidance.generate_representative_scenarios import (
    offset_m_to_latlon,
)
from usv_avoidance.scenario_config import (
    DURATION_S,
    SCENARIOS_DIR,
    STEP_S,
    USV_LAT0,
    USV_LON0,
)


# Carpeta temporal que contiene las trayectorias individuales.
# Esta carpeta está excluida mediante .gitignore.
SOURCE_DIR = SCENARIOS_DIR / "multitarget_sources"

# Archivo definitivo que será utilizado por main.py,
# simulation_runner.py y la interfaz.
FINAL_SCENARIO_FILE = (
    SCENARIOS_DIR / "multitarget_priority_test.txt"
)


@dataclass(frozen=True)
class TargetSourceConfig:
    """
    Configuración de una trayectoria AIS utilizada para construir
    el escenario multiblanco de priorización.
    """

    name: str
    mmsi: int
    offset_east_m: float
    offset_north_m: float
    sog_kn: float
    cog_deg: float


TARGET_SOURCES = (
    TargetSourceConfig(
        name="priority_target_1_far",
        mmsi=725000101,
        offset_east_m=450.0,
        offset_north_m=450.0,
        sog_kn=6.0,
        cog_deg=270.0,
    ),
    TargetSourceConfig(
        name="priority_target_2_near",
        mmsi=725000102,
        offset_east_m=300.0,
        offset_north_m=300.0,
        sog_kn=6.0,
        cog_deg=270.0,
    ),
)


def generate_source_trajectory(
    config: TargetSourceConfig,
) -> Path:
    """
    Genera la trayectoria AIS individual de un contacto.
    """

    target_lat0, target_lon0 = offset_m_to_latlon(
        ref_lat=USV_LAT0,
        ref_lon=USV_LON0,
        east_m=config.offset_east_m,
        north_m=config.offset_north_m,
    )

    output_file = SOURCE_DIR / f"{config.name}_nmea.txt"

    generate_moving_target_scenario(
        output_file=str(output_file),
        mmsi=config.mmsi,
        lat0=target_lat0,
        lon0=target_lon0,
        sog_kn=config.sog_kn,
        cog_deg=config.cog_deg,
        heading_deg=int(round(config.cog_deg)) % 360,
        duration_s=DURATION_S,
        step_s=STEP_S,
    )

    return output_file


def read_source_sentences(
    source_file: Path,
) -> list[str]:
    """
    Lee las sentencias AIS contenidas en una trayectoria fuente.

    Rechaza archivos vacíos o líneas que no correspondan a
    sentencias AIVDM/AIVDO.
    """

    if not source_file.exists():
        raise FileNotFoundError(
            f"No existe la trayectoria fuente: {source_file}"
        )

    sentences = [
        line.strip()
        for line in source_file.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    if not sentences:
        raise ValueError(
            f"La trayectoria fuente está vacía: {source_file}"
        )

    invalid_sentences = [
        sentence
        for sentence in sentences
        if not sentence.startswith(
            ("!AIVDM", "!AIVDO")
        )
    ]

    if invalid_sentences:
        raise ValueError(
            "La trayectoria contiene líneas que no son "
            f"sentencias AIS: {source_file}"
        )

    return sentences


def build_multitarget_scenario(
    *,
    source_files: Sequence[Path],
    output_file: Path,
    step_s: float,
) -> Path:
    """
    Intercala las trayectorias AIS bajo marcadores #FRAME.

    Para cada instante se escribe:

        #FRAME,t
        sentencia contacto 1
        sentencia contacto 2

    Todos los contactos contenidos en el mismo frame serán
    evaluados antes de avanzar el USV.
    """

    if len(source_files) < 2:
        raise ValueError(
            "El escenario multiblanco requiere al menos "
            "dos trayectorias fuente."
        )

    step_s = float(step_s)

    if not isfinite(step_s) or step_s <= 0.0:
        raise ValueError(
            "El intervalo entre frames debe ser positivo "
            "y finito."
        )

    source_sentences = [
        read_source_sentences(source_file)
        for source_file in source_files
    ]

    sentence_counts = [
        len(sentences)
        for sentences in source_sentences
    ]

    if len(set(sentence_counts)) != 1:
        source_details = ", ".join(
            f"{source_file.name}={count}"
            for source_file, count in zip(
                source_files,
                sentence_counts,
            )
        )

        raise ValueError(
            "Las trayectorias fuente deben contener la misma "
            f"cantidad de sentencias: {source_details}"
        )

    frame_count = sentence_counts[0]

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        for frame_index, frame_sentences in enumerate(
            zip(*source_sentences)
        ):
            timestamp_s = frame_index * step_s

            file.write(
                f"#FRAME,{timestamp_s:.1f}\n"
            )

            for sentence in frame_sentences:
                file.write(sentence + "\n")

            # Línea vacía para hacer más legible el archivo.
            # NmeaFileSource ignora estas líneas.
            if frame_index < frame_count - 1:
                file.write("\n")

    return output_file


def main() -> None:
    """
    Genera:

    1. Las trayectorias AIS individuales.
    2. El escenario multiblanco sincronizado.
    """

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Generando trayectorias AIS multiblanco...\n")

    generated_source_files: list[Path] = []

    for config in TARGET_SOURCES:
        output_file = generate_source_trajectory(config)

        generated_source_files.append(output_file)

        print(
            f"MMSI={config.mmsi} | "
            f"Este={config.offset_east_m:.1f} m | "
            f"Norte={config.offset_north_m:.1f} m | "
            f"SOG={config.sog_kn:.1f} kn | "
            f"COG={config.cog_deg:.1f}°"
        )

        print(f"Fuente: {output_file}\n")

    final_scenario = build_multitarget_scenario(
        source_files=generated_source_files,
        output_file=FINAL_SCENARIO_FILE,
        step_s=STEP_S,
    )

    frame_count = (
        DURATION_S // STEP_S
    ) + 1

    print("-" * 70)
    print("Escenario multiblanco generado correctamente.")
    print(f"Archivo final: {final_scenario}")
    print(f"Frames generados: {frame_count}")
    print(f"Contactos por frame: {len(TARGET_SOURCES)}")


if __name__ == "__main__":
    main()
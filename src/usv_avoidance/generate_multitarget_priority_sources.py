from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


SOURCE_DIR = SCENARIOS_DIR / "multitarget_sources"


@dataclass(frozen=True)
class TargetSourceConfig:
    """
    Configuración de una trayectoria AIS utilizada como fuente
    para construir posteriormente un escenario multiblanco.
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
    Genera una trayectoria AIS individual.

    Cada archivo contiene una sentencia AIS por instante.
    En el siguiente avance ambos archivos serán intercalados
    mediante marcadores #FRAME.
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


def main() -> None:
    """
    Genera las dos fuentes AIS del escenario de priorización.
    """

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Generando trayectorias AIS multiblanco...\n")

    for config in TARGET_SOURCES:
        output_file = generate_source_trajectory(config)

        print(
            f"MMSI={config.mmsi} | "
            f"Este={config.offset_east_m:.1f} m | "
            f"Norte={config.offset_north_m:.1f} m | "
            f"SOG={config.sog_kn:.1f} kn | "
            f"COG={config.cog_deg:.1f}°"
        )

        print(f"Archivo: {output_file}\n")

    print("Trayectorias fuente generadas correctamente.")


if __name__ == "__main__":
    main()
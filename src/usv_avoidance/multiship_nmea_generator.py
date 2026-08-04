from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from usv_avoidance.ais_type1_generator import (
    encode_type1_position_report,
    move_position,
)


@dataclass(frozen=True)
class AisTargetDefinition:
    mmsi: int
    lat0: float
    lon0: float
    sog_kn: float
    cog_deg: float
    heading_deg: int


def generate_multiship_nmea_scenario(
    output_file: str | Path,
    targets: list[AisTargetDefinition],
    duration_s: int,
    step_s: int,
) -> None:
    """Genera frames explícitos con todos los blancos en cada instante."""

    if len(targets) < 2 or len(targets) > 4:
        raise ValueError("El escenario debe contener entre 2 y 4 blancos.")
    if duration_s <= 0 or step_s <= 0:
        raise ValueError("duration_s y step_s deben ser positivos.")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    positions = {
        target.mmsi: [target.lat0, target.lon0]
        for target in targets
    }

    with output_path.open("w", encoding="utf-8") as file:
        for time_s in range(0, duration_s + 1, step_s):
            file.write(f"#FRAME,{float(time_s):.1f}\n")

            for target in targets:
                lat, lon = positions[target.mmsi]
                sentence = encode_type1_position_report(
                    mmsi=target.mmsi,
                    lat=lat,
                    lon=lon,
                    sog_kn=target.sog_kn,
                    cog_deg=target.cog_deg,
                    heading_deg=target.heading_deg,
                    timestamp=time_s,
                )
                file.write(sentence + "\n")

            for target in targets:
                lat, lon = positions[target.mmsi]
                positions[target.mmsi][:] = move_position(
                    lat=lat,
                    lon=lon,
                    sog_kn=target.sog_kn,
                    cog_deg=target.cog_deg,
                    delta_t_s=step_s,
                )
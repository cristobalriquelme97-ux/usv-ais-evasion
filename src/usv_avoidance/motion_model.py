#Permite actualizar la posición del propio USV y calcular el CPA/TCPA con cada
#objetivo detectado en cada iteración del bucle principal.

from __future__ import annotations

import math
from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import EARTH_RADIUS_M, KNOT_TO_MPS


def advance_position(
    lat: float,
    lon: float,
    sog_kn: float,
    cog_deg: float,
    dt_s: float,
) -> tuple[float, float]:
    """
    Calcula la nueva posición de una embarcación después de avanzar
    durante dt_s segundos con una velocidad SOG y un rumbo COG.

    Convención náutica:
    - COG = 0°   → Norte
    - COG = 90°  → Este
    - COG = 180° → Sur
    - COG = 270° → Oeste
    """

    speed_mps = sog_kn * KNOT_TO_MPS
    cog_rad = math.radians(cog_deg)

    dx_east = speed_mps * math.sin(cog_rad) * dt_s
    dy_north = speed_mps * math.cos(cog_rad) * dt_s

    delta_lat_deg = math.degrees(dy_north / EARTH_RADIUS_M)

    delta_lon_deg = math.degrees(
        dx_east / (EARTH_RADIUS_M * math.cos(math.radians(lat)))
    )

    new_lat = lat + delta_lat_deg
    new_lon = lon + delta_lon_deg

    return new_lat, new_lon


def advance_vessel_state(
    vessel: Mapping[str, Any],
    dt_s: float,
) -> dict[str, Any]:
    """
    Actualiza el estado cinemático de una embarcación.

    Sirve tanto para el USV propio como para cualquier otra embarcación
    simulada.

    Requiere:
    - lat
    - lon
    - sog_kn
    - cog_deg

    Mantiene:
    - heading_deg
    - mmsi, si existe
    - otros campos adicionales
    """

    required_fields = ("lat", "lon", "sog_kn", "cog_deg")

    for field in required_fields:
        if vessel.get(field) is None:
            raise ValueError(f"Falta el campo '{field}' en vessel")

    new_lat, new_lon = advance_position(
        lat=float(vessel["lat"]),
        lon=float(vessel["lon"]),
        sog_kn=float(vessel["sog_kn"]),
        cog_deg=float(vessel["cog_deg"]),
        dt_s=dt_s,
    )

    updated_vessel = dict(vessel)
    updated_vessel["lat"] = new_lat
    updated_vessel["lon"] = new_lon
    updated_vessel["timestamp"] = float(updated_vessel.get("timestamp", 0.0)) + dt_s

    return updated_vessel


if __name__ == "__main__":
    usv = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 45.0,
        "heading_deg": 45.0,
        "timestamp": 0.0,
    }

    for step in range(5):
        print(
            f"Reporte USV {step} | "
            f"t={usv['timestamp']:.1f} s | "
            f"lat={usv['lat']:.6f} | "
            f"lon={usv['lon']:.6f}"
        )

        usv = advance_vessel_state(
            vessel=usv,
            dt_s=5.0,
        )
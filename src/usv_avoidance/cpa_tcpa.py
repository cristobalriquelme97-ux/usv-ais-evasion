from __future__ import annotations

import math
from typing import Any, Mapping


KNOT_TO_MPS = 0.514444
EARTH_RADIUS_M = 6371000.0


def knots_to_mps(speed_kn: float) -> float:
    """
    Convierte velocidad desde nudos a metros por segundo.
    """
    return speed_kn * KNOT_TO_MPS


def velocity_components(sog_kn: float, cog_deg: float) -> tuple[float, float]:
    """
    Convierte SOG y COG en componentes de velocidad Este/Norte.

    Sistema usado:
    - x positivo: Este
    - y positivo: Norte

    En navegación:
    - COG = 0°   → Norte
    - COG = 90°  → Este
    - COG = 180° → Sur
    - COG = 270° → Oeste
    """
    speed_mps = knots_to_mps(sog_kn)
    cog_rad = math.radians(cog_deg)

    vx_east = speed_mps * math.sin(cog_rad)
    vy_north = speed_mps * math.cos(cog_rad)

    return vx_east, vy_north


def latlon_to_xy_m(
    lat: float,
    lon: float,
    ref_lat: float,
    ref_lon: float,
) -> tuple[float, float]:
    """
    Convierte latitud/longitud a coordenadas locales x/y en metros.

    La referencia es la posición del USV propio.
    Esta aproximación es válida para distancias locales o escenarios
    de simulación cercanos.
    """
    delta_lat_rad = math.radians(lat - ref_lat)
    delta_lon_rad = math.radians(lon - ref_lon)

    x_east = EARTH_RADIUS_M * math.cos(math.radians(ref_lat)) * delta_lon_rad
    y_north = EARTH_RADIUS_M * delta_lat_rad

    return x_east, y_north


def calculate_cpa_tcpa(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    safety_radius_m: float = 50.0,
    time_horizon_s: float = 300.0,
) -> dict[str, Any]:
    """
    Calcula distancia actual, CPA y TCPA entre el USV propio y un blanco AIS.

    CPA:
    Closest Point of Approach, distancia mínima de aproximación.

    TCPA:
    Time to Closest Point of Approach, tiempo hasta esa distancia mínima.

    El cálculo usa:
    - posición actual del USV
    - posición actual del blanco
    - velocidad y curso del USV
    - velocidad y curso del blanco
    """

    required_fields = ("lat", "lon", "sog_kn", "cog_deg")

    for field in required_fields:
        if ownship.get(field) is None:
            raise ValueError(f"Falta el campo '{field}' en ownship")

        if target.get(field) is None:
            raise ValueError(f"Falta el campo '{field}' en target")

    own_lat = float(ownship["lat"])
    own_lon = float(ownship["lon"])
    own_sog = float(ownship["sog_kn"])
    own_cog = float(ownship["cog_deg"])

    target_lat = float(target["lat"])
    target_lon = float(target["lon"])
    target_sog = float(target["sog_kn"])
    target_cog = float(target["cog_deg"])

    # Posición relativa del blanco respecto del USV.
    rel_x, rel_y = latlon_to_xy_m(
        lat=target_lat,
        lon=target_lon,
        ref_lat=own_lat,
        ref_lon=own_lon,
    )

    # Velocidad del USV y del blanco.
    own_vx, own_vy = velocity_components(own_sog, own_cog)
    target_vx, target_vy = velocity_components(target_sog, target_cog)

    # Velocidad relativa del blanco respecto del USV.
    rel_vx = target_vx - own_vx
    rel_vy = target_vy - own_vy

    distance_m = math.hypot(rel_x, rel_y)

    rel_speed_squared = rel_vx**2 + rel_vy**2

    # Si ambos se mueven igual, no hay aproximación relativa.
    if rel_speed_squared < 1e-9:
        tcpa_s = 0.0
        cpa_m = distance_m
    else:
        # Tiempo al punto de mínima distancia.
        tcpa_s = -((rel_x * rel_vx) + (rel_y * rel_vy)) / rel_speed_squared

        # Para evaluar riesgo futuro, no interesa un CPA que ya ocurrió.
        tcpa_eval = max(tcpa_s, 0.0)

        cpa_x = rel_x + rel_vx * tcpa_eval
        cpa_y = rel_y + rel_vy * tcpa_eval

        cpa_m = math.hypot(cpa_x, cpa_y)

    risk = (
        tcpa_s >= 0.0
        and tcpa_s <= time_horizon_s
        and cpa_m <= safety_radius_m
    )

    return {
        "target_mmsi": target.get("mmsi"),
        "distance_m": distance_m,
        "cpa_m": cpa_m,
        "tcpa_s": tcpa_s,
        "risk": risk,
        "safety_radius_m": safety_radius_m,
        "time_horizon_s": time_horizon_s,
    }


if __name__ == "__main__":
    ownship_state = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 50.0,
    }

    target_state = {
        "mmsi": 725000001,
        "lat": -33.023336666666665,
        "lon": -71.62398,
        "sog_kn": 8.5,
        "cog_deg": 225.0,
    }

    result = calculate_cpa_tcpa(
        ownship=ownship_state,
        target=target_state,
        safety_radius_m=50.0,
        time_horizon_s=300.0,
    )

    print(result)
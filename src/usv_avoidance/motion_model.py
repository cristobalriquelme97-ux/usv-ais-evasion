#Permite actualizar la posición del propio USV y calcular el CPA/TCPA con cada
#objetivo detectado en cada iteración del bucle principal.

from __future__ import annotations

import math
from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import EARTH_RADIUS_M, KNOT_TO_MPS



def shortest_angle_difference_deg(
    target_deg: float,
    current_deg: float,
) -> float:
    """
    Calcula la diferencia angular más corta entre dos rumbos.

    Retorna un valor entre -180° y +180°.

    Positivo:
        giro a estribor.

    Negativo:
        giro a babor.
    """

    return (target_deg - current_deg + 180.0) % 360.0 - 180.0


def normalize_angle_360(angle_deg: float) -> float:
    """
    Normaliza un ángulo al rango 0° a 360°.
    """

    return angle_deg % 360.0


def update_course_towards_command(
    current_course_deg: float,
    commanded_course_deg: float,
    turn_rate_deg_s: float,
    dt_s: float,
) -> float:
    """
    Actualiza progresivamente el rumbo actual hacia un rumbo ordenado.

    Ejemplo:
    - rumbo actual: 0°
    - rumbo ordenado: 15°
    - razón de caída: 1°/s
    - dt: 5 s

    Resultado:
    - nuevo rumbo: 5°
    """

    angle_error = shortest_angle_difference_deg(
        target_deg=commanded_course_deg,
        current_deg=current_course_deg,
    )

    max_change_deg = turn_rate_deg_s * dt_s

    if abs(angle_error) <= max_change_deg:
        new_course = commanded_course_deg
    elif angle_error > 0:
        new_course = current_course_deg + max_change_deg
    else:
        new_course = current_course_deg - max_change_deg

    return normalize_angle_360(new_course)


def advance_vessel_state_with_course_command(
    vessel,
    commanded_course_deg: float,
    dt_s: float,
    turn_rate_deg_s: float,
):
    """
    Avanza una embarcación considerando un rumbo ordenado.

    A diferencia de advance_vessel_state(), esta función no cambia
    instantáneamente al rumbo deseado. Primero ajusta gradualmente
    COG/HDG y luego avanza la posición.
    """

    current_course = float(vessel["cog_deg"])

    new_course = update_course_towards_command(
        current_course_deg=current_course,
        commanded_course_deg=commanded_course_deg,
        turn_rate_deg_s=turn_rate_deg_s,
        dt_s=dt_s,
    )

    updated_vessel = dict(vessel)
    updated_vessel["cog_deg"] = new_course
    updated_vessel["heading_deg"] = new_course

    updated_vessel = advance_vessel_state(
        vessel=updated_vessel,
        dt_s=dt_s,
    )

    return updated_vessel

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
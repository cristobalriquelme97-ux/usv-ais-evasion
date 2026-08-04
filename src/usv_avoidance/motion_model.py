# Permite actualizar la posición del propio USV y calcular el CPA/TCPA con cada
# objetivo detectado en cada iteración del bucle principal.

from __future__ import annotations

import math
from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import EARTH_RADIUS_M, KNOT_TO_MPS


def shortest_angle_difference_deg(
    target_deg: float,
    current_deg: float,
) -> float:
    """
    Calcula la diferencia angular más corta entre dos rumbos o cursos.

    Retorna un valor entre -180° y +180°.
    Positivo representa giro a estribor y negativo giro a babor.
    """

    return (target_deg - current_deg + 180.0) % 360.0 - 180.0


def normalize_angle_360(angle_deg: float) -> float:
    """Normaliza un ángulo al rango 0° a 360°."""

    return angle_deg % 360.0


def update_course_towards_command(
    current_course_deg: float,
    commanded_course_deg: float,
    turn_rate_deg_s: float,
    dt_s: float,
) -> float:
    """Actualiza progresivamente el rumbo hacia el rumbo ordenado."""

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


def update_speed_towards_command(
    current_speed_kn: float,
    commanded_speed_kn: float,
    speed_change_rate_kn_s: float,
    dt_s: float,
) -> float:
    """
    Actualiza progresivamente la velocidad hacia la velocidad ordenada.

    La función sirve tanto para disminuir la velocidad durante la acción
    stand-on como para recuperarla posteriormente al retornar al track.
    """

    current_speed_kn = max(0.0, float(current_speed_kn))
    commanded_speed_kn = max(0.0, float(commanded_speed_kn))

    if speed_change_rate_kn_s <= 0.0:
        raise ValueError(
            "speed_change_rate_kn_s debe ser mayor que cero."
        )

    max_change_kn = speed_change_rate_kn_s * dt_s
    speed_error_kn = commanded_speed_kn - current_speed_kn

    if abs(speed_error_kn) <= max_change_kn:
        return commanded_speed_kn

    if speed_error_kn > 0.0:
        return current_speed_kn + max_change_kn

    return max(0.0, current_speed_kn - max_change_kn)


def advance_vessel_state_with_course_command(
    vessel: Mapping[str, Any],
    commanded_course_deg: float,
    dt_s: float,
    turn_rate_deg_s: float,
) -> dict[str, Any]:
    """
    Avanza una embarcación considerando únicamente un rumbo ordenado.

    Se conserva para compatibilidad con el resto del proyecto. La velocidad
    permanece igual a la registrada en ``vessel['sog_kn']``.
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

    return advance_vessel_state(
        vessel=updated_vessel,
        dt_s=dt_s,
    )


def advance_vessel_state_with_course_and_speed_command(
    vessel: Mapping[str, Any],
    commanded_course_deg: float,
    commanded_speed_kn: float,
    dt_s: float,
    turn_rate_deg_s: float,
    speed_change_rate_kn_s: float,
) -> dict[str, Any]:
    """
    Avanza una embarcación considerando rumbo y velocidad ordenados.

    El rumbo y la velocidad cambian progresivamente. Esta función no altera
    la lógica de las maniobras por rumbo existentes; solamente permite que
    una decisión stand-on ordene una reducción de velocidad gradual.
    """

    new_course = update_course_towards_command(
        current_course_deg=float(vessel["cog_deg"]),
        commanded_course_deg=float(commanded_course_deg),
        turn_rate_deg_s=float(turn_rate_deg_s),
        dt_s=float(dt_s),
    )

    new_speed_kn = update_speed_towards_command(
        current_speed_kn=float(vessel["sog_kn"]),
        commanded_speed_kn=float(commanded_speed_kn),
        speed_change_rate_kn_s=float(speed_change_rate_kn_s),
        dt_s=float(dt_s),
    )

    updated_vessel = dict(vessel)
    updated_vessel["cog_deg"] = new_course
    updated_vessel["heading_deg"] = new_course
    updated_vessel["sog_kn"] = new_speed_kn

    return advance_vessel_state(
        vessel=updated_vessel,
        dt_s=dt_s,
    )


def advance_position(
    lat: float,
    lon: float,
    sog_kn: float,
    cog_deg: float,
    dt_s: float,
) -> tuple[float, float]:
    """
    Calcula la nueva posición de una embarcación después de avanzar.

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

    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 1e-12:
        raise ValueError("La latitud no permite calcular longitud.")

    delta_lon_deg = math.degrees(
        dx_east / (EARTH_RADIUS_M * cos_lat)
    )

    return lat + delta_lat_deg, lon + delta_lon_deg


def advance_vessel_state(
    vessel: Mapping[str, Any],
    dt_s: float,
) -> dict[str, Any]:
    """Actualiza el estado cinemático de una embarcación."""

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
    updated_vessel["timestamp"] = (
        float(updated_vessel.get("timestamp", 0.0)) + dt_s
    )

    return updated_vessel


if __name__ == "__main__":
    usv = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 0.0,
        "heading_deg": 0.0,
        "timestamp": 0.0,
    }

    for _ in range(5):
        print(usv)
        usv = advance_vessel_state_with_course_and_speed_command(
            vessel=usv,
            commanded_course_deg=0.0,
            commanded_speed_kn=3.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
            speed_change_rate_kn_s=0.10,
        )
# Geometría de encuentro entre USV propio y blanco AIS. Se calcula demarcación verdadera, 
# demarcación relativa y sector del blanco (Proa/Babor/Estribor/Popa).
from __future__ import annotations

import math
from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import latlon_to_xy_m


def normalize_angle_360(angle_deg: float) -> float:
    """
    Normaliza un ángulo al rango 0° a 360°.
    """
    return angle_deg % 360.0


def normalize_angle_signed(angle_deg: float) -> float:
    """
    Normaliza un ángulo al rango -180° a +180°.

    Convención:
    - positivo: hacia estribor
    - negativo: hacia babor
    """
    return (angle_deg + 180.0) % 360.0 - 180.0


def calculate_true_bearing_deg(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
) -> float:
    """
    Calcula la demarcación verdadera desde el USV propio hacia el blanco.

    La demarcación verdadera es el ángulo medido desde el norte verdadero
    hacia la posición del blanco.

    Convención náutica:
    - 0°   = norte
    - 90°  = este
    - 180° = sur
    - 270° = oeste
    """

    own_lat = float(ownship["lat"])
    own_lon = float(ownship["lon"])

    target_lat = float(target["lat"])
    target_lon = float(target["lon"])

    rel_x, rel_y = latlon_to_xy_m(
        lat=target_lat,
        lon=target_lon,
        ref_lat=own_lat,
        ref_lon=own_lon,
    )

    # atan2(x, y) porque el ángulo náutico se mide desde el norte.
    bearing_rad = math.atan2(rel_x, rel_y)
    bearing_deg = math.degrees(bearing_rad)

    return normalize_angle_360(bearing_deg)


def get_reference_heading_deg(ownship: Mapping[str, Any]) -> float:
    """
    Obtiene el rumbo de referencia del USV.

    Prioridad:
    1. heading_deg: proa real del USV.
    2. cog_deg: curso sobre el fondo, si no hay heading disponible.

    Para simulaciones simples sin deriva ni corriente, heading_deg y cog_deg
    pueden ser iguales.
    """

    heading = ownship.get("heading_deg")

    if heading is not None:
        return float(heading)

    cog = ownship.get("cog_deg")

    if cog is not None:
        return float(cog)

    raise ValueError("ownship debe tener 'heading_deg' o 'cog_deg'")


def calculate_relative_bearing_deg(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
) -> float:
    """
    Calcula la demarcación relativa del blanco AIS respecto a la proa del USV.

    Resultado:
    - 0° aproximadamente: blanco por proa
    - positivo: blanco por estribor
    - negativo: blanco por babor
    - ±180° aproximadamente: blanco por popa
    """

    true_bearing = calculate_true_bearing_deg(ownship, target)
    reference_heading = get_reference_heading_deg(ownship)

    relative_bearing = true_bearing - reference_heading

    return normalize_angle_signed(relative_bearing)


def classify_relative_side(
    relative_bearing_deg: float,
    ahead_threshold_deg: float = 5.0,
    astern_threshold_deg: float = 5.0,
) -> str:
    """
    Clasifica la ubicación relativa del blanco.

    Retorna:
    - proa
    - estribor
    - babor
    - popa
    """

    if abs(relative_bearing_deg) <= ahead_threshold_deg:
        return "proa"

    if abs(abs(relative_bearing_deg) - 180.0) <= astern_threshold_deg:
        return "popa"

    if relative_bearing_deg > 0:
        return "estribor"

    return "babor"


def calculate_bearing_info(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Calcula la demarcación verdadera, demarcación relativa y sector del blanco.
    """

    true_bearing = calculate_true_bearing_deg(ownship, target)
    reference_heading = get_reference_heading_deg(ownship)
    relative_bearing = calculate_relative_bearing_deg(ownship, target)

    return {
        "target_mmsi": target.get("mmsi"),
        "true_bearing_deg": true_bearing,
        "relative_bearing_deg": relative_bearing,
        "relative_bearing_360_deg": normalize_angle_360(relative_bearing),
        "side": classify_relative_side(relative_bearing),
        "reference_heading_deg": reference_heading,
    }


if __name__ == "__main__":
    ownship_state = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 45.0,
        "heading_deg": 45.0,
    }

    target_state = {
        "mmsi": 725000001,
        "lat": -33.023336666666665,
        "lon": -71.62398,
        "sog_kn": 8.5,
        "cog_deg": 225.0,
    }

    result = calculate_bearing_info(
        ownship=ownship_state,
        target=target_state,
    )

    print(result)
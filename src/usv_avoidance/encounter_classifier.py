from __future__ import annotations

from typing import Any, Mapping

from usv_avoidance.encounter_geometry import (
    calculate_relative_bearing_deg,
    normalize_angle_signed,
)

STARBOARD_CROSSING_SECTORS = frozenset({
    "starboard_bow_beam",
    "starboard_quarter",
})

PORT_CROSSING_SECTORS = frozenset({
    "port_quarter",
    "port_beam_bow",
})

def abs_course_difference_deg(course_a_deg: float, course_b_deg: float) -> float:
    """
    Calcula la diferencia absoluta entre dos rumbos o cursos.

    Resultado:
    - 0°   → mismos cursos
    - 90°  → cursos aproximadamente perpendiculares
    - 180° → cursos opuestos o recíprocos
    """

    difference = normalize_angle_signed(course_a_deg - course_b_deg)
    return abs(difference)


def is_head_on_situation(
    relative_bearing_deg: float,
    course_difference_deg: float,
    ahead_threshold_deg: float = 10.0,
    reciprocal_course_threshold_deg: float = 165.0,
) -> bool:
    """
    Determina si existe una situación de vuelta encontrada.

    Criterio usado:
    - El blanco está por proa o casi por proa del USV.
    - Los cursos son opuestos o casi opuestos.

    El RIPA indica que la vuelta encontrada ocurre cuando dos buques
    se encuentran en rumbos recíprocos o casi recíprocos y el otro buque
    se observa por proa o casi por proa.
    """

    target_ahead = abs(relative_bearing_deg) <= ahead_threshold_deg
    nearly_reciprocal = course_difference_deg >= reciprocal_course_threshold_deg

    return target_ahead and nearly_reciprocal


def is_ownship_overtaking_target(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    overtaking_sector_limit_deg: float = 112.5,
) -> bool:
    """
    Determina si el USV propio está alcanzando al blanco AIS.

    Para evaluar alcance, no basta con mirar dónde está el blanco respecto
    al USV. También se debe mirar dónde está el USV respecto al blanco.

    Según RIPA, una embarcación alcanza a otra si se aproxima desde una
    dirección mayor a 22.5° a popa del través del buque alcanzado.
    Eso equivale a estar dentro del sector de popa del blanco:
    |demarcación relativa desde el blanco hacia el USV| > 112.5°.
    """

    relative_bearing_from_target_to_ownship = calculate_relative_bearing_deg(
        ownship=target,
        target=ownship,
    )

    ownship_is_abaft_target_beam = (
        abs(relative_bearing_from_target_to_ownship) > overtaking_sector_limit_deg
    )

    ownship_is_faster = float(ownship.get("sog_kn", 0.0)) > float(
        target.get("sog_kn", 0.0)
    )

    return ownship_is_abaft_target_beam and ownship_is_faster


def is_target_overtaking_ownship(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    relative_bearing_deg: float,
    overtaking_sector_limit_deg: float = 112.5,
) -> bool:
    """
    Determina si el blanco AIS está alcanzando al USV propio.

    En este caso, el blanco aparece por el sector de popa del USV
    y además tiene mayor velocidad que el USV.
    """

    target_is_abaft_ownship_beam = (
        abs(relative_bearing_deg) > overtaking_sector_limit_deg
    )

    target_is_faster = float(target.get("sog_kn", 0.0)) > float(
        ownship.get("sog_kn", 0.0)
    )

    return target_is_abaft_ownship_beam and target_is_faster


def classify_encounter(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    cpa_result: Mapping[str, Any],
    bearing_info: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Clasifica el tipo de encuentro entre el USV propio y un blanco AIS.

    Entradas:
    - ownship: estado actual del USV propio.
    - target: estado actual del blanco AIS.
    - cpa_result: resultado de calculate_cpa_tcpa().
    - bearing_info: resultado de calculate_bearing_info().

    Salida:
    - encounter_type: tipo interno del encuentro.
    - encounter_name: nombre en español.
    - ownship_role: rol del USV.
    - should_maneuver: indica si el USV debería maniobrar.
    """

    risk = bool(cpa_result.get("risk", False))

    relative_bearing_deg = float(bearing_info["relative_bearing_deg"])
    target_side = str(bearing_info["side"])
    target_sector = str(bearing_info["sector"])


    ownship_cog = float(ownship["cog_deg"])
    target_cog = float(target["cog_deg"])

    course_difference = abs_course_difference_deg(
        ownship_cog,
        target_cog,
    )

    # Si no hay riesgo CPA/TCPA, no se clasifica una situación peligrosa.
    if not risk:
        return {
            "encounter_type": "safe",
            "encounter_name": "sin riesgo",
            "risk": False,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "none",
            "should_maneuver": False,
            "reason": "No existe riesgo de colisión según CPA/TCPA.",
        }

    # 1. Vuelta encontrada.
    if is_head_on_situation(
        relative_bearing_deg=relative_bearing_deg,
        course_difference_deg=course_difference,
    ):
        return {
            "encounter_type": "head_on",
            "encounter_name": "vuelta encontrada",
            "risk": True,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "give_way",
            "should_maneuver": True,
            "reason": "Blanco por proa y cursos aproximadamente recíprocos.",
        }

    # 2. Alcance: el USV alcanza al blanco.
    if is_ownship_overtaking_target(
        ownship=ownship,
        target=target,
    ):
        return {
            "encounter_type": "overtaking",
            "encounter_name": "alcance",
            "risk": True,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "give_way",
            "should_maneuver": True,
            "reason": "El USV se aproxima desde el sector de popa del blanco.",
        }

    # 3. Alcance: el blanco alcanza al USV.
    if is_target_overtaking_ownship(
        ownship=ownship,
        target=target,
        relative_bearing_deg=relative_bearing_deg,
    ):
        return {
            "encounter_type": "being_overtaken",
            "encounter_name": "alcance por blanco",
            "risk": True,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "stand_on",
            "should_maneuver": False,
            "reason": "El blanco se aproxima desde el sector de popa del USV.",
        }

    # 4. Cruce con el blanco por estribor.
    target_in_starboard_crossing_sector = (
        target_sector in STARBOARD_CROSSING_SECTORS
        or (
            target_sector == "ahead"
            and relative_bearing_deg > 0.0
        )
    )

    if target_in_starboard_crossing_sector:
        return {
            "encounter_type": "crossing",
            "encounter_name": "cruce",
            "risk": True,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "give_way",
            "should_maneuver": True,
            "reason": (
                "Cruce con blanco por estribor; "
                "el USV debe mantenerse apartado."
            ),
        }

    # 5. Cruce con el blanco por babor.
    target_in_port_crossing_sector = (
        target_sector in PORT_CROSSING_SECTORS
        or (
            target_sector == "ahead"
            and relative_bearing_deg < 0.0
        )
    )

    if target_in_port_crossing_sector:
        return {
            "encounter_type": "crossing",
            "encounter_name": "cruce",
            "risk": True,
            "target_side": target_side,
            "target_sector": target_sector,
            "relative_bearing_deg": relative_bearing_deg,
            "course_difference_deg": course_difference,
            "ownship_role": "stand_on",
            "should_maneuver": False,
            "reason": (
                "Cruce con blanco por babor; "
                "el USV mantiene rumbo y velocidad."
            ),
        }
    # 5. Caso ambiguo.
    return {
        "encounter_type": "undefined",
        "encounter_name": "indefinido",
        "risk": True,
        "target_side": target_side,
        "target_sector": target_sector,
        "relative_bearing_deg": relative_bearing_deg,
        "course_difference_deg": course_difference,
        "ownship_role": "caution",
        "should_maneuver": True,
        "reason": "Existe riesgo, pero la geometría no permite clasificar con claridad.",
    }


if __name__ == "__main__":
    from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
    from usv_avoidance.encounter_geometry import calculate_bearing_info

    ownship_state = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 0.0,
        "heading_deg": 0.0,
    }

    target_state = {
        "mmsi": 725000001,
        "lat": -33.023336666666665,
        "lon": -71.625000,
        "sog_kn": 8.5,
        "cog_deg": 180.0,
        "heading_deg": 180.0,
    }

    cpa = calculate_cpa_tcpa(
        ownship=ownship_state,
        target=target_state,
        safety_radius_m=50.0,
        time_horizon_s=300.0,
    )

    bearing = calculate_bearing_info(
        ownship=ownship_state,
        target=target_state,
    )

    classification = classify_encounter(
        ownship=ownship_state,
        target=target_state,
        cpa_result=cpa,
        bearing_info=bearing,
    )

    print("CPA/TCPA:")
    print(cpa)

    print("\nGeometría:")
    print(bearing)

    print("\nClasificación:")
    print(classification)
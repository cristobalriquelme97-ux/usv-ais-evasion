#Transforma de USV + lista de contactos
#a lista de evaluaciones de colisión

from __future__ import annotations

from typing import Any, Iterable, Mapping

from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_classifier import classify_encounter
from usv_avoidance.encounter_geometry import calculate_bearing_info


def build_assessments(
    *,
    ownship: Mapping[str, Any],
    targets: Iterable[Mapping[str, Any]],
    return_course_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
) -> list[dict[str, Any]]:
    """
    Evalúa todos los contactos activos respecto del USV.

    Para cada contacto calcula:

    - distancia actual;
    - CPA y TCPA;
    - CPA/TCPA suponiendo que el USV retorna a su rumbo original;
    - demarcación verdadera y relativa;
    - sector geométrico;
    - situación de encuentro;
    - responsabilidad RIPA del USV.

    Esta función solamente construye evaluaciones. No selecciona el
    contacto prioritario y tampoco determina una maniobra evasiva.
    """

    assessments: list[dict[str, Any]] = []

    return_course_ownship = dict(ownship)
    return_course_ownship["cog_deg"] = float(return_course_deg)
    return_course_ownship["heading_deg"] = float(return_course_deg)

    for target in targets:
        cpa_result = calculate_cpa_tcpa(
            ownship=ownship,
            target=target,
            safety_radius_m=safety_radius_m,
            time_horizon_s=time_horizon_s,
        )

        return_cpa_result = calculate_cpa_tcpa(
            ownship=return_course_ownship,
            target=target,
            safety_radius_m=safety_radius_m,
            time_horizon_s=time_horizon_s,
        )

        bearing_info = calculate_bearing_info(
            ownship=ownship,
            target=target,
        )

        classification = classify_encounter(
            ownship=ownship,
            target=target,
            cpa_result=cpa_result,
            bearing_info=bearing_info,
        )

        assessments.append(
            {
                "target": target,
                "cpa_result": cpa_result,
                "return_cpa_result": return_cpa_result,
                "bearing_info": bearing_info,
                "classification": classification,
            }
        )

    return assessments
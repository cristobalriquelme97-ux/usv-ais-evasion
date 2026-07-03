from __future__ import annotations

from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import normalize_angle_360


def build_candidate_ownship(
    ownship: Mapping[str, Any],
    candidate_course_deg: float,
) -> dict[str, Any]:
    """
    Crea una copia del estado del USV con un nuevo rumbo candidato.

    No modifica el ownship original.
    Solo se usa para simular qué ocurriría si el USV cambia de rumbo.
    """

    candidate = dict(ownship)

    normalized_course = normalize_angle_360(candidate_course_deg)

    candidate["cog_deg"] = normalized_course
    candidate["heading_deg"] = normalized_course

    return candidate


def evaluate_course_candidate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    course_change_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
) -> dict[str, Any]:
    """
    Evalúa una maniobra candidata.

    Ejemplo:
    - rumbo actual: 45°
    - course_change_deg: +30°
    - rumbo candidato: 75°

    Luego calcula CPA/TCPA proyectado con ese rumbo candidato.
    """

    current_course = float(ownship["cog_deg"])
    candidate_course = normalize_angle_360(current_course + course_change_deg)

    candidate_ownship = build_candidate_ownship(
        ownship=ownship,
        candidate_course_deg=candidate_course,
    )

    projected_cpa = calculate_cpa_tcpa(
        ownship=candidate_ownship,
        target=target,
        safety_radius_m=safety_radius_m,
        time_horizon_s=time_horizon_s,
    )

    candidate_is_safe = (
        not projected_cpa["risk"]
        and projected_cpa["cpa_m"] >= safety_radius_m
    )

    return {
        "course_change_deg": course_change_deg,
        "candidate_course_deg": candidate_course,
        "projected_cpa_m": projected_cpa["cpa_m"],
        "projected_tcpa_s": projected_cpa["tcpa_s"],
        "projected_risk": projected_cpa["risk"],
        "candidate_is_safe": candidate_is_safe,
    }


def recommend_avoidance_maneuver(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    classification: Mapping[str, Any],
    state_info: Mapping[str, Any],
    safety_radius_m: float = 50.0,
    time_horizon_s: float = 300.0,
    starboard_changes_deg: tuple[float, ...] = (15.0, 30.0, 45.0, 60.0),
) -> dict[str, Any]:
    """
    Recomienda una maniobra evasiva.

    Esta función NO gobierna directamente el USV.
    Solo recomienda:
    - mantener rumbo
    - caer a estribor cierta cantidad de grados

    La maniobra se elige probando cambios de rumbo candidatos
    y calculando CPA/TCPA proyectado para cada uno.
    """

    current_state = state_info.get("current_state")
    should_maneuver = bool(classification.get("should_maneuver", False))
    ownship_role = classification.get("ownship_role")
    encounter_type = classification.get("encounter_type")
    encounter_name = classification.get("encounter_name")

    current_course = float(ownship["cog_deg"])

    # Si la máquina de estados no está en evasión,
    # no recomendamos alterar rumbo todavía.
    if current_state != "AVOIDING_TARGET":
        return {
            "action": "maintain_course",
            "maneuver_required": False,
            "recommended_course_deg": current_course,
            "course_change_deg": 0.0,
            "recommended_speed_kn": ownship.get("sog_kn"),
            "reason": f"Estado actual {current_state}; no corresponde ejecutar evasión.",
            "candidate_results": [],
        }

    # Si el clasificador indica que el USV no debe maniobrar,
    # se mantiene rumbo y velocidad.
    if not should_maneuver or ownship_role != "give_way":
        return {
            "action": "maintain_course",
            "maneuver_required": False,
            "recommended_course_deg": current_course,
            "course_change_deg": 0.0,
            "recommended_speed_kn": ownship.get("sog_kn"),
            "reason": "El USV no es buque que debe mantenerse apartado.",
            "candidate_results": [],
        }

    candidate_results = []

    for course_change in starboard_changes_deg:
        result = evaluate_course_candidate(
            ownship=ownship,
            target=target,
            course_change_deg=course_change,
            safety_radius_m=safety_radius_m,
            time_horizon_s=time_horizon_s,
        )

        candidate_results.append(result)

        # Se elige la primera maniobra segura.
        # Esto significa: el menor cambio claro que logra CPA seguro.
        if result["candidate_is_safe"]:
            return {
                "action": "alter_course_starboard",
                "maneuver_required": True,
                "encounter_type": encounter_type,
                "encounter_name": encounter_name,
                "recommended_course_deg": result["candidate_course_deg"],
                "course_change_deg": result["course_change_deg"],
                "recommended_speed_kn": ownship.get("sog_kn"),
                "projected_cpa_m": result["projected_cpa_m"],
                "projected_tcpa_s": result["projected_tcpa_s"],
                "projected_risk": result["projected_risk"],
                "reason": (
                    f"Maniobra segura encontrada: caer a estribor "
                    f"{result['course_change_deg']:.1f}°."
                ),
                "candidate_results": candidate_results,
            }

    # Si ninguna maniobra deja el CPA completamente seguro,
    # se elige la que entregue el mayor CPA proyectado.
    best_candidate = max(
        candidate_results,
        key=lambda item: item["projected_cpa_m"],
    )

    return {
        "action": "alter_course_starboard_best_effort",
        "maneuver_required": True,
        "encounter_type": encounter_type,
        "encounter_name": encounter_name,
        "recommended_course_deg": best_candidate["candidate_course_deg"],
        "course_change_deg": best_candidate["course_change_deg"],
        "recommended_speed_kn": ownship.get("sog_kn"),
        "projected_cpa_m": best_candidate["projected_cpa_m"],
        "projected_tcpa_s": best_candidate["projected_tcpa_s"],
        "projected_risk": best_candidate["projected_risk"],
        "reason": (
            "Ninguna maniobra candidata eliminó completamente el riesgo; "
            "se selecciona la que maximiza el CPA proyectado."
        ),
        "candidate_results": candidate_results,
    }


if __name__ == "__main__":
    ownship_state = {
        "lat": -33.025000,
        "lon": -71.625000,
        "sog_kn": 6.0,
        "cog_deg": 45.0,
        "heading_deg": 45.0,
        "timestamp": 0.0,
    }

    target_state = {
        "mmsi": 725000001,
        "lat": -33.023336666666665,
        "lon": -71.623980,
        "sog_kn": 8.5,
        "cog_deg": 225.0,
        "heading_deg": 225.0,
    }

    classification = {
        "encounter_type": "crossing",
        "encounter_name": "cruce",
        "risk": True,
        "ownship_role": "give_way",
        "should_maneuver": True,
    }

    state_info = {
        "current_state": "AVOIDING_TARGET",
        "active_target_mmsi": 725000001,
    }

    decision = recommend_avoidance_maneuver(
        ownship=ownship_state,
        target=target_state,
        classification=classification,
        state_info=state_info,
        safety_radius_m=50.0,
        time_horizon_s=300.0,
    )

    print("Decisión evasiva:")
    print(decision)

    print("\nManiobras candidatas evaluadas:")
    for candidate in decision["candidate_results"]:
        print(candidate)
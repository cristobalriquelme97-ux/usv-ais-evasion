from __future__ import annotations

import math
from typing import Any, Mapping

from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import normalize_angle_360
from usv_avoidance.motion_model import (
    advance_vessel_state,
    advance_vessel_state_with_course_command,
    shortest_angle_difference_deg,
)


def simulate_course_candidate_with_turn_rate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    candidate_course_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float,
    course_tolerance_deg: float = 1.0,
) -> dict[str, Any]:
    """
    Simula una maniobra candidata considerando razón de giro.

    A diferencia de una evaluación instantánea, aquí el USV no cambia
    inmediatamente al nuevo rumbo. El rumbo se modifica progresivamente
    según turn_rate_deg_s.

    Retorna información útil para evaluar si la maniobra mantiene una
    distancia segura durante la evolución simulada.
    """

    simulated_ownship = dict(ownship)
    simulated_target = dict(target)

    steps = max(1, int(math.ceil(time_horizon_s / dt_s)))

    min_distance_m = math.inf
    time_at_min_distance_s = 0.0

    final_cpa_result = None
    reached_commanded_course_at_s = None

    for step in range(steps + 1):
        elapsed_s = min(step * dt_s, time_horizon_s)
        remaining_horizon_s = max(time_horizon_s - elapsed_s, dt_s)

        cpa_result = calculate_cpa_tcpa(
            ownship=simulated_ownship,
            target=simulated_target,
            safety_radius_m=safety_radius_m,
            time_horizon_s=remaining_horizon_s,
        )

        final_cpa_result = cpa_result

        current_distance_m = float(cpa_result["distance_m"])

        if current_distance_m < min_distance_m:
            min_distance_m = current_distance_m
            time_at_min_distance_s = elapsed_s

        course_error_deg = shortest_angle_difference_deg(
            target_deg=candidate_course_deg,
            current_deg=float(simulated_ownship["cog_deg"]),
        )

        if (
            reached_commanded_course_at_s is None
            and abs(course_error_deg) <= course_tolerance_deg
        ):
            reached_commanded_course_at_s = elapsed_s

        if step == steps:
            break

        step_dt_s = min(dt_s, time_horizon_s - elapsed_s)

        if step_dt_s <= 0:
            break

        simulated_ownship = advance_vessel_state_with_course_command(
            vessel=simulated_ownship,
            commanded_course_deg=candidate_course_deg,
            dt_s=step_dt_s,
            turn_rate_deg_s=turn_rate_deg_s,
        )

        simulated_target = advance_vessel_state(
            vessel=simulated_target,
            dt_s=step_dt_s,
        )

    final_cpa_m = float(final_cpa_result["cpa_m"])
    final_tcpa_s = float(final_cpa_result["tcpa_s"])
    final_risk = bool(final_cpa_result["risk"])

    safety_radius_was_violated = min_distance_m < safety_radius_m

    candidate_is_safe = (
        not safety_radius_was_violated
        and not final_risk
        and final_cpa_m >= safety_radius_m
    )

    return {
        "candidate_course_deg": candidate_course_deg,
        "min_distance_m": min_distance_m,
        "time_at_min_distance_s": time_at_min_distance_s,
        "final_cpa_m": final_cpa_m,
        "final_tcpa_s": final_tcpa_s,
        "final_risk": final_risk,
        "safety_radius_was_violated": safety_radius_was_violated,
        "candidate_is_safe": candidate_is_safe,
        "reached_commanded_course_at_s": reached_commanded_course_at_s,
    }


def evaluate_course_candidate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    course_change_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float,
) -> dict[str, Any]:
    """
    Evalúa una maniobra candidata considerando giro progresivo.

    Ejemplo:
    - rumbo actual: 0°
    - course_change_deg: +30°
    - rumbo candidato: 30°
    - el USV llega progresivamente según turn_rate_deg_s.
    """

    current_course = float(ownship["cog_deg"])
    candidate_course = normalize_angle_360(current_course + course_change_deg)

    simulation = simulate_course_candidate_with_turn_rate(
        ownship=ownship,
        target=target,
        candidate_course_deg=candidate_course,
        safety_radius_m=safety_radius_m,
        time_horizon_s=time_horizon_s,
        dt_s=dt_s,
        turn_rate_deg_s=turn_rate_deg_s,
    )

    return {
        "course_change_deg": course_change_deg,
        "candidate_course_deg": candidate_course,
        "projected_cpa_m": simulation["min_distance_m"],
        "projected_tcpa_s": simulation["time_at_min_distance_s"],
        "projected_risk": simulation["safety_radius_was_violated"],
        "candidate_is_safe": simulation["candidate_is_safe"],
        "final_cpa_m": simulation["final_cpa_m"],
        "final_tcpa_s": simulation["final_tcpa_s"],
        "final_risk": simulation["final_risk"],
        "reached_commanded_course_at_s": simulation["reached_commanded_course_at_s"],
    }


def recommend_avoidance_maneuver(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    classification: Mapping[str, Any],
    state_info: Mapping[str, Any],
    safety_radius_m: float = 50.0,
    time_horizon_s: float = 300.0,
    dt_s: float = 5.0,
    turn_rate_deg_s: float = 1.0,
    starboard_changes_deg: tuple[float, ...] = (15.0, 30.0, 45.0, 60.0),
) -> dict[str, Any]:
    """
    Recomienda una maniobra evasiva.

    Esta versión evalúa cada rumbo candidato considerando que el USV
    gira gradualmente según su razón de caída o turn rate.
    """

    current_state = state_info.get("current_state")
    should_maneuver = bool(classification.get("should_maneuver", False))
    ownship_role = classification.get("ownship_role")
    encounter_type = classification.get("encounter_type")
    encounter_name = classification.get("encounter_name")

    current_course = float(ownship["cog_deg"])

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
            dt_s=dt_s,
            turn_rate_deg_s=turn_rate_deg_s,
        )

        candidate_results.append(result)

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
                "final_cpa_m": result["final_cpa_m"],
                "final_tcpa_s": result["final_tcpa_s"],
                "final_risk": result["final_risk"],
                "reason": (
                    f"Maniobra segura considerando turn rate: caer a estribor "
                    f"{result['course_change_deg']:.1f}°."
                ),
                "candidate_results": candidate_results,
            }

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
        "final_cpa_m": best_candidate["final_cpa_m"],
        "final_tcpa_s": best_candidate["final_tcpa_s"],
        "final_risk": best_candidate["final_risk"],
        "reason": (
            "Ninguna maniobra candidata eliminó completamente el riesgo "
            "considerando turn rate; se selecciona la que maximiza la "
            "distancia mínima proyectada."
        ),
        "candidate_results": candidate_results,
    }
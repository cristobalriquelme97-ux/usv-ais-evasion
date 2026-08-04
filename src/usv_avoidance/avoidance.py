from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import normalize_angle_360
from usv_avoidance.motion_model import (
    advance_vessel_state,
    advance_vessel_state_with_course_command,
    advance_vessel_state_with_course_and_speed_command,
    shortest_angle_difference_deg,
)


def simulate_course_candidate_with_turn_rate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    candidate_course_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float = 10.0,
    course_tolerance_deg: float = 1.0,
) -> dict[str, Any]:
    """Simula una maniobra candidata considerando razón de giro."""

    simulated_ownship = dict(ownship)
    simulated_target = dict(target)

    steps = max(1, int(math.ceil(time_horizon_s / dt_s)))
    min_distance_m = math.inf
    time_at_min_distance_s = 0.0
    final_cpa_result = None
    reached_commanded_course_at_s = None

    for step in range(steps + 1):
        elapsed_s = min(step * dt_s, time_horizon_s)
        remaining_horizon_s = max(
            time_horizon_s - elapsed_s,
            dt_s,
        )

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

        step_dt_s = min(
            dt_s,
            time_horizon_s - elapsed_s,
        )
        if step_dt_s <= 0.0:
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

    if final_cpa_result is None:
        raise RuntimeError("No fue posible evaluar la maniobra candidata.")

    candidate_is_safe = min_distance_m >= safety_radius_m

    return {
        "candidate_course_deg": candidate_course_deg,
        "min_distance_m": min_distance_m,
        "time_at_min_distance_s": time_at_min_distance_s,
        "final_cpa_m": float(final_cpa_result["cpa_m"]),
        "final_tcpa_s": float(final_cpa_result["tcpa_s"]),
        "final_risk": bool(final_cpa_result["risk"]),
        "safety_radius_was_violated": not candidate_is_safe,
        "candidate_is_safe": candidate_is_safe,
        "reached_commanded_course_at_s": (
            reached_commanded_course_at_s
        ),
    }


def _merge_simulation_targets(
    *,
    primary_target: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    """Construye una lista de contactos sin MMSI repetidos."""

    merged_targets: list[Mapping[str, Any]] = []
    seen_identifiers: set[tuple[str, Any]] = set()

    for target in [primary_target, *(targets or ())]:
        mmsi = target.get("mmsi")
        identifier = (
            ("mmsi", mmsi)
            if mmsi is not None
            else ("object", id(target))
        )

        if identifier in seen_identifiers:
            continue

        seen_identifiers.add(identifier)
        merged_targets.append(target)

    return merged_targets


def simulate_course_candidate_against_targets(
    *,
    ownship: Mapping[str, Any],
    primary_target: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]] | None,
    candidate_course_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float = 10.0,
) -> dict[str, Any]:
    """Evalúa un mismo rumbo candidato frente a todos los contactos."""

    simulation_targets = _merge_simulation_targets(
        primary_target=primary_target,
        targets=targets,
    )

    per_target_results: list[dict[str, Any]] = []

    for index, target in enumerate(simulation_targets):
        target_result = simulate_course_candidate_with_turn_rate(
            ownship=ownship,
            target=target,
            candidate_course_deg=candidate_course_deg,
            safety_radius_m=safety_radius_m,
            time_horizon_s=time_horizon_s,
            dt_s=dt_s,
            turn_rate_deg_s=turn_rate_deg_s,
        )
        per_target_results.append(
            {
                "target_mmsi": target.get("mmsi"),
                "is_primary": index == 0,
                **target_result,
            }
        )

    if not per_target_results:
        raise ValueError(
            "Se requiere al menos un contacto para evaluar la maniobra."
        )

    blocking_result = min(
        per_target_results,
        key=lambda item: item["min_distance_m"],
    )
    unsafe_target_mmsi = [
        result["target_mmsi"]
        for result in per_target_results
        if not result["candidate_is_safe"]
    ]
    candidate_is_safe = not unsafe_target_mmsi

    return {
        "candidate_course_deg": candidate_course_deg,
        "candidate_is_safe": candidate_is_safe,
        "safety_radius_was_violated": not candidate_is_safe,
        "global_min_distance_m": blocking_result["min_distance_m"],
        "time_at_global_min_distance_s": blocking_result[
            "time_at_min_distance_s"
        ],
        "blocking_target_mmsi": blocking_result["target_mmsi"],
        "unsafe_target_mmsi": unsafe_target_mmsi,
        "primary_result": per_target_results[0],
        "per_target_results": per_target_results,
    }


def evaluate_course_candidate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    course_change_deg: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float,
    targets: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evalúa una maniobra de cambio de rumbo."""

    candidate_course = normalize_angle_360(
        float(ownship["cog_deg"]) + course_change_deg
    )

    simulation = simulate_course_candidate_against_targets(
        ownship=ownship,
        primary_target=target,
        targets=targets,
        candidate_course_deg=candidate_course,
        safety_radius_m=safety_radius_m,
        time_horizon_s=time_horizon_s,
        dt_s=dt_s,
        turn_rate_deg_s=turn_rate_deg_s,
    )
    primary_result = simulation["primary_result"]

    return {
        "course_change_deg": course_change_deg,
        "candidate_course_deg": candidate_course,
        "projected_cpa_m": simulation["global_min_distance_m"],
        "projected_tcpa_s": simulation[
            "time_at_global_min_distance_s"
        ],
        "projected_risk": simulation[
            "safety_radius_was_violated"
        ],
        "candidate_is_safe": simulation["candidate_is_safe"],
        "primary_projected_cpa_m": primary_result[
            "min_distance_m"
        ],
        "primary_projected_tcpa_s": primary_result[
            "time_at_min_distance_s"
        ],
        "final_cpa_m": primary_result["final_cpa_m"],
        "final_tcpa_s": primary_result["final_tcpa_s"],
        "final_risk": primary_result["final_risk"],
        "blocking_target_mmsi": simulation[
            "blocking_target_mmsi"
        ],
        "unsafe_target_mmsi": simulation["unsafe_target_mmsi"],
        "per_target_results": simulation["per_target_results"],
        "reached_commanded_course_at_s": primary_result[
            "reached_commanded_course_at_s"
        ],
    }


def simulate_speed_candidate_with_rate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    candidate_speed_kn: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    speed_change_rate_kn_s: float,
) -> dict[str, Any]:
    """
    Simula una reducción de velocidad manteniendo el rumbo actual.

    El blanco conserva su SOG/COG. El USV modifica gradualmente su velocidad
    según ``speed_change_rate_kn_s`` y no altera el rumbo.
    """

    simulated_ownship = dict(ownship)
    simulated_target = dict(target)
    maintained_course_deg = float(ownship["cog_deg"])

    steps = max(1, int(math.ceil(time_horizon_s / dt_s)))
    min_distance_m = math.inf
    time_at_min_distance_s = 0.0
    final_cpa_result = None
    reached_commanded_speed_at_s = None

    for step in range(steps + 1):
        elapsed_s = min(step * dt_s, time_horizon_s)
        remaining_horizon_s = max(
            time_horizon_s - elapsed_s,
            dt_s,
        )

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

        if (
            reached_commanded_speed_at_s is None
            and abs(
                float(simulated_ownship["sog_kn"])
                - candidate_speed_kn
            ) <= 1e-6
        ):
            reached_commanded_speed_at_s = elapsed_s

        if step == steps:
            break

        step_dt_s = min(
            dt_s,
            time_horizon_s - elapsed_s,
        )
        if step_dt_s <= 0.0:
            break

        simulated_ownship = (
            advance_vessel_state_with_course_and_speed_command(
                vessel=simulated_ownship,
                commanded_course_deg=maintained_course_deg,
                commanded_speed_kn=candidate_speed_kn,
                dt_s=step_dt_s,
                turn_rate_deg_s=1.0,
                speed_change_rate_kn_s=speed_change_rate_kn_s,
            )
        )
        simulated_target = advance_vessel_state(
            vessel=simulated_target,
            dt_s=step_dt_s,
        )

    if final_cpa_result is None:
        raise RuntimeError("No fue posible evaluar la reducción de velocidad.")

    candidate_is_safe = min_distance_m >= safety_radius_m

    return {
        "candidate_speed_kn": candidate_speed_kn,
        "candidate_course_deg": maintained_course_deg,
        "min_distance_m": min_distance_m,
        "time_at_min_distance_s": time_at_min_distance_s,
        "final_cpa_m": float(final_cpa_result["cpa_m"]),
        "final_tcpa_s": float(final_cpa_result["tcpa_s"]),
        "final_risk": bool(final_cpa_result["risk"]),
        "candidate_is_safe": candidate_is_safe,
        "safety_radius_was_violated": not candidate_is_safe,
        "reached_commanded_speed_at_s": (
            reached_commanded_speed_at_s
        ),
    }


def simulate_speed_candidate_against_targets(
    *,
    ownship: Mapping[str, Any],
    primary_target: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]] | None,
    candidate_speed_kn: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    speed_change_rate_kn_s: float,
) -> dict[str, Any]:
    """Evalúa una reducción de velocidad frente a todos los contactos."""

    simulation_targets = _merge_simulation_targets(
        primary_target=primary_target,
        targets=targets,
    )

    per_target_results: list[dict[str, Any]] = []

    for index, target in enumerate(simulation_targets):
        result = simulate_speed_candidate_with_rate(
            ownship=ownship,
            target=target,
            candidate_speed_kn=candidate_speed_kn,
            safety_radius_m=safety_radius_m,
            time_horizon_s=time_horizon_s,
            dt_s=dt_s,
            speed_change_rate_kn_s=speed_change_rate_kn_s,
        )
        per_target_results.append(
            {
                "target_mmsi": target.get("mmsi"),
                "is_primary": index == 0,
                **result,
            }
        )

    if not per_target_results:
        raise ValueError(
            "Se requiere al menos un contacto para evaluar la reducción."
        )

    blocking_result = min(
        per_target_results,
        key=lambda item: item["min_distance_m"],
    )
    unsafe_target_mmsi = [
        result["target_mmsi"]
        for result in per_target_results
        if not result["candidate_is_safe"]
    ]

    return {
        "candidate_speed_kn": candidate_speed_kn,
        "candidate_course_deg": float(ownship["cog_deg"]),
        "candidate_is_safe": not unsafe_target_mmsi,
        "global_min_distance_m": blocking_result["min_distance_m"],
        "time_at_global_min_distance_s": blocking_result[
            "time_at_min_distance_s"
        ],
        "blocking_target_mmsi": blocking_result["target_mmsi"],
        "unsafe_target_mmsi": unsafe_target_mmsi,
        "primary_result": per_target_results[0],
        "per_target_results": per_target_results,
    }


def evaluate_speed_candidate(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    candidate_speed_kn: float,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    speed_change_rate_kn_s: float,
    targets: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normaliza la salida de una reducción de velocidad candidata."""

    simulation = simulate_speed_candidate_against_targets(
        ownship=ownship,
        primary_target=target,
        targets=targets,
        candidate_speed_kn=candidate_speed_kn,
        safety_radius_m=safety_radius_m,
        time_horizon_s=time_horizon_s,
        dt_s=dt_s,
        speed_change_rate_kn_s=speed_change_rate_kn_s,
    )
    primary_result = simulation["primary_result"]

    return {
        "speed_change_kn": (
            candidate_speed_kn - float(ownship["sog_kn"])
        ),
        "candidate_speed_kn": candidate_speed_kn,
        "candidate_course_deg": float(ownship["cog_deg"]),
        "course_change_deg": 0.0,
        "projected_cpa_m": simulation["global_min_distance_m"],
        "projected_tcpa_s": simulation[
            "time_at_global_min_distance_s"
        ],
        "projected_risk": not simulation["candidate_is_safe"],
        "candidate_is_safe": simulation["candidate_is_safe"],
        "final_cpa_m": primary_result["final_cpa_m"],
        "final_tcpa_s": primary_result["final_tcpa_s"],
        "final_risk": primary_result["final_risk"],
        "blocking_target_mmsi": simulation[
            "blocking_target_mmsi"
        ],
        "unsafe_target_mmsi": simulation["unsafe_target_mmsi"],
        "per_target_results": simulation["per_target_results"],
        "reached_commanded_speed_at_s": primary_result[
            "reached_commanded_speed_at_s"
        ],
    }


def recommend_avoidance_maneuver(
    ownship: Mapping[str, Any],
    target: Mapping[str, Any],
    classification: Mapping[str, Any],
    state_info: Mapping[str, Any],
    safety_radius_m: float = 50.0,
    time_horizon_s: float = 300.0,
    dt_s: float = 5.0,
    turn_rate_deg_s: float = 10.0,
    starboard_changes_deg: tuple[float, ...] = (
        5.0,
        10.0,
        15.0,
        20.0,
        25.0,
        30.0,
        35.0,
        40.0,
        45.0,
    ),
    targets: Sequence[Mapping[str, Any]] | None = None,
    stand_on_speed_factors: tuple[float, ...] = (
        0.75,
        0.50,
        0.25,
    ),
    speed_change_rate_kn_s: float = 0.10,
) -> dict[str, Any]:
    """
    Recomienda una maniobra evasiva.

    La rama give-way conserva exactamente el criterio anterior: evaluar
    caídas a estribor y escoger la primera segura. La única extensión es
    una rama stand-on tardía que mantiene el rumbo y evalúa reducciones de
    velocidad cuando ``state_info['stand_on_emergency_active']`` es True.
    """

    current_state = state_info.get("current_state")
    should_maneuver = bool(
        classification.get("should_maneuver", False)
    )
    ownship_role = classification.get("ownship_role")
    encounter_type = classification.get("encounter_type")
    encounter_name = classification.get("encounter_name")

    current_course = float(ownship["cog_deg"])
    current_speed = float(ownship["sog_kn"])
    stand_on_emergency = bool(
        state_info.get("stand_on_emergency_active", False)
    )

    if current_state != "AVOIDING_TARGET":
        return {
            "action": "maintain_course",
            "maneuver_required": False,
            "recommended_course_deg": current_course,
            "course_change_deg": 0.0,
            "recommended_speed_kn": current_speed,
            "reason": (
                f"Estado actual {current_state}; no corresponde "
                "ejecutar evasión."
            ),
            "candidate_results": [],
        }

    stand_on_reduction_allowed = (
        current_state == "AVOIDING_TARGET"
        and ownship_role == "stand_on"
        and should_maneuver is False
        and stand_on_emergency
        and bool(
            state_info.get(
                "stand_on_mode_eligible",
                False,
            )
        )
    )

    if stand_on_reduction_allowed:
        candidate_results: list[dict[str, Any]] = []

        # Se prueba primero la reducción menos intrusiva.
        for factor in sorted(stand_on_speed_factors, reverse=True):
            candidate_speed_kn = max(0.0, current_speed * factor)
            result = evaluate_speed_candidate(
                ownship=ownship,
                target=target,
                targets=targets,
                candidate_speed_kn=candidate_speed_kn,
                safety_radius_m=safety_radius_m,
                time_horizon_s=time_horizon_s,
                dt_s=dt_s,
                speed_change_rate_kn_s=speed_change_rate_kn_s,
            )
            candidate_results.append(result)

            if result["candidate_is_safe"]:
                return {
                    "action": "reduce_speed",
                    "maneuver_required": True,
                    "encounter_type": encounter_type,
                    "encounter_name": encounter_name,
                    "recommended_course_deg": current_course,
                    "course_change_deg": 0.0,
                    "recommended_speed_kn": candidate_speed_kn,
                    "speed_change_kn": result["speed_change_kn"],
                    "projected_cpa_m": result["projected_cpa_m"],
                    "projected_tcpa_s": result["projected_tcpa_s"],
                    "projected_risk": result["projected_risk"],
                    "candidate_is_safe": True,
                    "final_cpa_m": result["final_cpa_m"],
                    "final_tcpa_s": result["final_tcpa_s"],
                    "final_risk": result["final_risk"],
                    "blocking_target_mmsi": result[
                        "blocking_target_mmsi"
                    ],
                    "unsafe_target_mmsi": result[
                        "unsafe_target_mmsi"
                    ],
                    "per_target_results": result[
                        "per_target_results"
                    ],
                    "reason": (
                        "El USV mantuvo inicialmente rumbo y velocidad "
                        "como stand-on. Al persistir el riesgo, reduce "
                        f"la velocidad a {candidate_speed_kn:.2f} kn "
                        "sin alterar el rumbo."
                    ),
                    "candidate_results": candidate_results,
                }

        best_candidate = max(
            candidate_results,
            key=lambda item: item["projected_cpa_m"],
        )

        return {
            "action": "reduce_speed_best_effort",
            "maneuver_required": True,
            "encounter_type": encounter_type,
            "encounter_name": encounter_name,
            "recommended_course_deg": current_course,
            "course_change_deg": 0.0,
            "recommended_speed_kn": best_candidate[
                "candidate_speed_kn"
            ],
            "speed_change_kn": best_candidate["speed_change_kn"],
            "projected_cpa_m": best_candidate["projected_cpa_m"],
            "projected_tcpa_s": best_candidate["projected_tcpa_s"],
            "projected_risk": best_candidate["projected_risk"],
            "candidate_is_safe": False,
            "final_cpa_m": best_candidate["final_cpa_m"],
            "final_tcpa_s": best_candidate["final_tcpa_s"],
            "final_risk": best_candidate["final_risk"],
            "blocking_target_mmsi": best_candidate[
                "blocking_target_mmsi"
            ],
            "unsafe_target_mmsi": best_candidate[
                "unsafe_target_mmsi"
            ],
            "per_target_results": best_candidate[
                "per_target_results"
            ],
            "reason": (
                "Ninguna reducción de velocidad respetó completamente "
                "el radio de seguridad; se escoge la reducción que "
                "maximiza la menor distancia proyectada."
            ),
            "candidate_results": candidate_results,
        }

    # Desde aquí se conserva la lógica give-way original.
    if not should_maneuver or ownship_role != "give_way":
        return {
            "action": "maintain_course",
            "maneuver_required": False,
            "recommended_course_deg": current_course,
            "course_change_deg": 0.0,
            "recommended_speed_kn": current_speed,
            "reason": "El USV no es buque que debe mantenerse apartado.",
            "candidate_results": [],
        }

    candidate_results = []

    for course_change in starboard_changes_deg:
        result = evaluate_course_candidate(
            ownship=ownship,
            target=target,
            targets=targets,
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
                "recommended_course_deg": result[
                    "candidate_course_deg"
                ],
                "course_change_deg": result["course_change_deg"],
                "recommended_speed_kn": current_speed,
                "projected_cpa_m": result["projected_cpa_m"],
                "projected_tcpa_s": result["projected_tcpa_s"],
                "projected_risk": result["projected_risk"],
                "candidate_is_safe": True,
                "final_cpa_m": result["final_cpa_m"],
                "final_tcpa_s": result["final_tcpa_s"],
                "final_risk": result["final_risk"],
                "blocking_target_mmsi": result[
                    "blocking_target_mmsi"
                ],
                "unsafe_target_mmsi": result[
                    "unsafe_target_mmsi"
                ],
                "per_target_results": result["per_target_results"],
                "reason": (
                    "Maniobra segura frente a todos los contactos "
                    "activos considerando la razón de giro: caer a "
                    f"estribor {result['course_change_deg']:.1f}°."
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
        "recommended_course_deg": best_candidate[
            "candidate_course_deg"
        ],
        "course_change_deg": best_candidate["course_change_deg"],
        "recommended_speed_kn": current_speed,
        "projected_cpa_m": best_candidate["projected_cpa_m"],
        "projected_tcpa_s": best_candidate["projected_tcpa_s"],
        "projected_risk": best_candidate["projected_risk"],
        "candidate_is_safe": False,
        "final_cpa_m": best_candidate["final_cpa_m"],
        "final_tcpa_s": best_candidate["final_tcpa_s"],
        "final_risk": best_candidate["final_risk"],
        "blocking_target_mmsi": best_candidate[
            "blocking_target_mmsi"
        ],
        "unsafe_target_mmsi": best_candidate[
            "unsafe_target_mmsi"
        ],
        "per_target_results": best_candidate[
            "per_target_results"
        ],
        "reason": (
            "Ninguna maniobra candidata respetó el radio de "
            "seguridad frente a todos los contactos activos; "
            "se selecciona la alternativa que maximiza la menor "
            "distancia global proyectada."
        ),
        "candidate_results": candidate_results,
    }
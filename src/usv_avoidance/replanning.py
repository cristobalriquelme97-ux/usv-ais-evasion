from __future__ import annotations

from typing import Any, Mapping, Sequence

from usv_avoidance.avoidance import (
    simulate_course_candidate_against_targets,
)


def get_assessment_mmsi(
    assessment: Mapping[str, Any] | None,
) -> int | None:
    """
    Obtiene el MMSI asociado a una evaluación de contacto.
    """

    if assessment is None:
        return None

    target = assessment.get("target", {})
    cpa_result = assessment.get("cpa_result", {})

    mmsi = target.get(
        "mmsi",
        cpa_result.get("target_mmsi"),
    )

    if mmsi is None:
        return None

    return int(mmsi)


def evaluate_active_evasive_course(
    *,
    ownship: Mapping[str, Any],
    critical_assessment: Mapping[str, Any] | None,
    targets: Sequence[Mapping[str, Any]],
    active_evasive_course_deg: float | None,
    safety_radius_m: float,
    time_horizon_s: float,
    dt_s: float,
    turn_rate_deg_s: float,
) -> dict[str, Any] | None:
    """
    Comprueba si el rumbo evasivo actualmente ordenado continúa
    siendo seguro frente a todos los contactos activos.

    Retorna None cuando todavía no existe un rumbo evasivo o no
    existe un contacto prioritario.
    """

    if (
        active_evasive_course_deg is None
        or critical_assessment is None
    ):
        return None

    primary_target = critical_assessment["target"]

    return simulate_course_candidate_against_targets(
        ownship=ownship,
        primary_target=primary_target,
        targets=targets,
        candidate_course_deg=float(
            active_evasive_course_deg
        ),
        safety_radius_m=safety_radius_m,
        time_horizon_s=time_horizon_s,
        dt_s=dt_s,
        turn_rate_deg_s=turn_rate_deg_s,
    )


def determine_replanning_need(
    *,
    current_state: str,
    critical_assessment: Mapping[str, Any] | None,
    active_evasive_course_deg: float | None,
    active_avoidance_decision: Mapping[str, Any] | None,
    active_course_evaluation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Determina si corresponde calcular una nueva maniobra.

    Causas posibles:

    - initial_plan:
        Se ingresó a evasión y todavía no existe un rumbo.

    - priority_changed:
        El contacto prioritario actual es diferente del contacto
        para el cual se calculó la maniobra activa.

    - active_course_became_unsafe:
        La maniobra fue inicialmente segura, pero la evaluación
        actual indica que vulnerará el radio de seguridad.
    """

    critical_target_mmsi = get_assessment_mmsi(
        critical_assessment
    )

    planned_target_mmsi = None

    if active_avoidance_decision is not None:
        planned_target_mmsi = (
            active_avoidance_decision.get(
                "priority_target_mmsi"
            )
        )

        if planned_target_mmsi is not None:
            planned_target_mmsi = int(
                planned_target_mmsi
            )

    active_course_is_safe = None

    if active_course_evaluation is not None:
        active_course_is_safe = bool(
            active_course_evaluation.get(
                "candidate_is_safe",
                False,
            )
        )

    result = {
        "replan_required": False,
        "trigger": "none",
        "reason": "No se requiere recalcular la maniobra.",
        "critical_target_mmsi": critical_target_mmsi,
        "planned_target_mmsi": planned_target_mmsi,
        "priority_changed": False,
        "active_course_is_safe": active_course_is_safe,
        "active_course_became_unsafe": False,
    }

    if (
        current_state != "AVOIDING_TARGET"
        or critical_assessment is None
    ):
        return result

    if (
        active_evasive_course_deg is None
        or active_avoidance_decision is None
    ):
        result.update(
            {
                "replan_required": True,
                "trigger": "initial_plan",
                "reason": (
                    "Se inicia la evasión y todavía no existe "
                    "una maniobra activa."
                ),
            }
        )

        return result

    priority_changed = (
        critical_target_mmsi is not None
        and planned_target_mmsi is not None
        and critical_target_mmsi
        != planned_target_mmsi
    )

    # Si una decisión antigua no contiene el MMSI para el cual
    # fue calculada, se fuerza una actualización única.
    missing_planned_target = (
        planned_target_mmsi is None
    )

    plan_was_safe = bool(
        active_avoidance_decision.get(
            "candidate_is_safe",
            False,
        )
    )

    active_course_became_unsafe = (
        plan_was_safe
        and active_course_evaluation is not None
        and not bool(
            active_course_evaluation.get(
                "candidate_is_safe",
                False,
            )
        )
    )

    result["priority_changed"] = priority_changed
    result[
        "active_course_became_unsafe"
    ] = active_course_became_unsafe

    if priority_changed and active_course_became_unsafe:
        result.update(
            {
                "replan_required": True,
                "trigger": (
                    "priority_changed_and_course_unsafe"
                ),
                "reason": (
                    "Cambió el contacto prioritario y el rumbo "
                    "evasivo activo dejó de ser seguro."
                ),
            }
        )

    elif priority_changed:
        result.update(
            {
                "replan_required": True,
                "trigger": "priority_changed",
                "reason": (
                    "Cambió el contacto prioritario durante "
                    "la maniobra evasiva."
                ),
            }
        )

    elif active_course_became_unsafe:
        result.update(
            {
                "replan_required": True,
                "trigger": (
                    "active_course_became_unsafe"
                ),
                "reason": (
                    "El rumbo evasivo activo dejó de ser "
                    "seguro frente a los contactos actuales."
                ),
            }
        )

    elif missing_planned_target:
        result.update(
            {
                "replan_required": True,
                "trigger": "missing_plan_target",
                "reason": (
                    "La maniobra activa no identifica el "
                    "contacto para el cual fue calculada."
                ),
            }
        )

    return result


def decorate_avoidance_decision(
    decision: Mapping[str, Any],
    *,
    critical_assessment: Mapping[str, Any],
    current_time_s: float,
    replanning_info: Mapping[str, Any],
    replan_count: int,
) -> dict[str, Any]:
    """
    Agrega metadatos de planificación a una decisión evasiva.
    """

    decorated_decision = dict(decision)

    decorated_decision.update(
        {
            "priority_target_mmsi": (
                get_assessment_mmsi(
                    critical_assessment
                )
            ),
            "planned_at_s": float(current_time_s),
            "plan_trigger": replanning_info.get(
                "trigger"
            ),
            "plan_reason": replanning_info.get(
                "reason"
            ),
            "replan_count": int(replan_count),
        }
    )

    return decorated_decision
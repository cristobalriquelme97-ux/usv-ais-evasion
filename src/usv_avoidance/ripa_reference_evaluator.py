from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from usv_avoidance.random_encounter_generator import (
    RandomEncounterCandidate,
    normalize_angle_360,
    normalize_angle_signed,
)


@dataclass(frozen=True)
class RipaReference:
    """Clasificación RIPA obtenida sin usar el clasificador del algoritmo."""

    evaluable: bool
    encounter: str
    ownship_role: str
    expected_initial_action: str | None

    relative_bearing_deg: float
    relative_bearing_from_target_deg: float
    course_difference_deg: float
    reason: str


@dataclass(frozen=True)
class AlgorithmBehavior:
    """Conducta observada en la salida de run_scenario()."""

    first_maneuver_time_s: float | None
    first_maneuver_action: str | None
    first_course_departure_time_s: float | None
    initial_algorithm_encounter: str | None
    initial_algorithm_role: str | None


@dataclass(frozen=True)
class RipaCompliance:
    """Resultado de comparar la conducta con la referencia independiente."""

    evaluable: bool
    compliant: bool | None
    reason: str


def _absolute_course_difference_deg(
    course_a_deg: float,
    course_b_deg: float,
) -> float:
    return abs(
        normalize_angle_signed(course_a_deg - course_b_deg)
    )


def _bearing_deg(
    origin_x_m: float,
    origin_y_m: float,
    target_x_m: float,
    target_y_m: float,
) -> float:
    delta_x_m = target_x_m - origin_x_m
    delta_y_m = target_y_m - origin_y_m

    return normalize_angle_360(
        math.degrees(math.atan2(delta_x_m, delta_y_m))
    )


def classify_ripa_reference(
    candidate: RandomEncounterCandidate,
    *,
    ahead_threshold_deg: float = 10.0,
    reciprocal_course_threshold_deg: float = 165.0,
    overtaking_sector_limit_deg: float = 112.5,
    boundary_margin_deg: float = 2.5,
) -> RipaReference:
    """
    Clasifica la geometría inicial sin importar módulos del algoritmo.

    Los casos próximos a límites angulares se marcan como ambiguos. No se
    eliminan del Monte Carlo: siguen contando para seguridad, pero no para
    las tasas de cumplimiento RIPA y éxito RIPA.
    """

    ownship_to_target_bearing_deg = _bearing_deg(
        0.0,
        0.0,
        candidate.target_x0_m,
        candidate.target_y0_m,
    )
    ownship_relative_bearing_deg = normalize_angle_signed(
        ownship_to_target_bearing_deg - candidate.usv_cog_deg
    )

    target_to_ownship_bearing_deg = _bearing_deg(
        candidate.target_x0_m,
        candidate.target_y0_m,
        0.0,
        0.0,
    )
    target_relative_bearing_deg = normalize_angle_signed(
        target_to_ownship_bearing_deg - candidate.target_cog_deg
    )

    course_difference_deg = _absolute_course_difference_deg(
        candidate.usv_cog_deg,
        candidate.target_cog_deg,
    )

    near_boundaries = any(
        (
            abs(
                abs(ownship_relative_bearing_deg)
                - ahead_threshold_deg
            ) <= boundary_margin_deg,
            abs(
                course_difference_deg
                - reciprocal_course_threshold_deg
            ) <= boundary_margin_deg,
            abs(
                abs(ownship_relative_bearing_deg)
                - overtaking_sector_limit_deg
            ) <= boundary_margin_deg,
            abs(
                abs(target_relative_bearing_deg)
                - overtaking_sector_limit_deg
            ) <= boundary_margin_deg,
            abs(ownship_relative_bearing_deg)
            <= boundary_margin_deg,
        )
    )

    if near_boundaries:
        return RipaReference(
            evaluable=False,
            encounter="ambiguo",
            ownship_role="caution",
            expected_initial_action=None,
            relative_bearing_deg=ownship_relative_bearing_deg,
            relative_bearing_from_target_deg=(
                target_relative_bearing_deg
            ),
            course_difference_deg=course_difference_deg,
            reason=(
                "La geometría inicial está próxima a un límite angular "
                "de clasificación RIPA."
            ),
        )

    head_on = (
        abs(ownship_relative_bearing_deg) <= ahead_threshold_deg
        and course_difference_deg >= reciprocal_course_threshold_deg
    )

    if head_on:
        return RipaReference(
            evaluable=True,
            encounter="vuelta encontrada",
            ownship_role="give_way",
            expected_initial_action="alter_course_starboard",
            relative_bearing_deg=ownship_relative_bearing_deg,
            relative_bearing_from_target_deg=(
                target_relative_bearing_deg
            ),
            course_difference_deg=course_difference_deg,
            reason=(
                "Blanco por proa y cursos aproximadamente recíprocos."
            ),
        )

    ownship_overtaking = (
        abs(target_relative_bearing_deg)
        > overtaking_sector_limit_deg
        and candidate.usv_sog_kn > candidate.target_sog_kn
    )

    if ownship_overtaking:
        return RipaReference(
            evaluable=True,
            encounter="alcance",
            ownship_role="give_way",
            expected_initial_action="alter_course_starboard",
            relative_bearing_deg=ownship_relative_bearing_deg,
            relative_bearing_from_target_deg=(
                target_relative_bearing_deg
            ),
            course_difference_deg=course_difference_deg,
            reason=(
                "El USV se aproxima desde el sector de popa del blanco."
            ),
        )

    target_overtaking = (
        abs(ownship_relative_bearing_deg)
        > overtaking_sector_limit_deg
        and candidate.target_sog_kn > candidate.usv_sog_kn
    )

    if target_overtaking:
        return RipaReference(
            evaluable=True,
            encounter="alcance por blanco",
            ownship_role="stand_on",
            expected_initial_action="maintain_course",
            relative_bearing_deg=ownship_relative_bearing_deg,
            relative_bearing_from_target_deg=(
                target_relative_bearing_deg
            ),
            course_difference_deg=course_difference_deg,
            reason=(
                "El blanco se aproxima desde el sector de popa del USV."
            ),
        )

    if ownship_relative_bearing_deg > 0.0:
        return RipaReference(
            evaluable=True,
            encounter="cruce",
            ownship_role="give_way",
            expected_initial_action="alter_course_starboard",
            relative_bearing_deg=ownship_relative_bearing_deg,
            relative_bearing_from_target_deg=(
                target_relative_bearing_deg
            ),
            course_difference_deg=course_difference_deg,
            reason=(
                "El blanco se encuentra por estribor del USV."
            ),
        )

    return RipaReference(
        evaluable=True,
        encounter="cruce",
        ownship_role="stand_on",
        expected_initial_action="maintain_course",
        relative_bearing_deg=ownship_relative_bearing_deg,
        relative_bearing_from_target_deg=target_relative_bearing_deg,
        course_difference_deg=course_difference_deg,
        reason="El blanco se encuentra por babor del USV.",
    )


def _first_target_value(
    steps: Sequence[Mapping[str, Any]],
    field: str,
) -> Any:
    for step in steps:
        targets = step.get("targets") or []
        if not targets:
            continue

        value = targets[0].get(field)
        if value is not None:
            return value

    return None


def extract_algorithm_behavior(
    simulation_result: Mapping[str, Any],
    original_course_deg: float,
    *,
    course_departure_tolerance_deg: float = 3.0,
) -> AlgorithmBehavior:
    steps = list(simulation_result.get("steps") or [])

    first_maneuver_time_s: float | None = None
    first_maneuver_action: str | None = None
    first_course_departure_time_s: float | None = None

    for step in steps:
        time_s = float(step.get("time_s", 0.0))
        decision = step.get("avoidance_decision")

        if (
            first_maneuver_time_s is None
            and isinstance(decision, Mapping)
            and bool(decision.get("maneuver_required", False))
        ):
            first_maneuver_time_s = time_s
            action = decision.get("action")
            first_maneuver_action = (
                str(action) if action is not None else None
            )

        commanded_course_deg = step.get("commanded_course_deg")
        if (
            first_course_departure_time_s is None
            and commanded_course_deg is not None
        ):
            course_difference_deg = abs(
                normalize_angle_signed(
                    float(commanded_course_deg)
                    - float(original_course_deg)
                )
            )

            if course_difference_deg > course_departure_tolerance_deg:
                first_course_departure_time_s = time_s

    return AlgorithmBehavior(
        first_maneuver_time_s=first_maneuver_time_s,
        first_maneuver_action=first_maneuver_action,
        first_course_departure_time_s=(
            first_course_departure_time_s
        ),
        initial_algorithm_encounter=_first_target_value(
            steps,
            "encounter_name",
        ),
        initial_algorithm_role=_first_target_value(
            steps,
            "ownship_role",
        ),
    )


def evaluate_ripa_compliance(
    reference: RipaReference,
    behavior: AlgorithmBehavior,
    *,
    baseline_time_at_minimum_s: float,
    stand_on_hold_s: float = 20.0,
) -> RipaCompliance:
    """
    Evalúa la conducta inicial del algoritmo frente a la referencia.

    - give_way: exige una primera maniobra a estribor antes del instante
      de mínima distancia basal.
    - stand_on: exige conservar inicialmente el rumbo. Una maniobra tardía
      no se penaliza, porque el blanco simulado nunca cumple por sí mismo
      su obligación de maniobrar.
    """

    if not reference.evaluable:
        return RipaCompliance(
            evaluable=False,
            compliant=None,
            reason="Caso geométricamente ambiguo; no se califica RIPA.",
        )

    if reference.ownship_role == "give_way":
        action = behavior.first_maneuver_action
        action_is_starboard = action in {
            "alter_course_starboard",
            "alter_course_starboard_best_effort",
        }
        maneuver_is_timely = (
            behavior.first_maneuver_time_s is not None
            and behavior.first_maneuver_time_s
            <= baseline_time_at_minimum_s
        )

        compliant = action_is_starboard and maneuver_is_timely

        if compliant:
            reason = (
                "El USV maniobró a estribor antes del instante de "
                "mínima distancia basal."
            )
        elif behavior.first_maneuver_time_s is None:
            reason = "El USV debía mantenerse apartado y no maniobró."
        elif not action_is_starboard:
            reason = (
                "La primera maniobra no correspondió a una caída "
                "a estribor."
            )
        else:
            reason = (
                "La maniobra comenzó después del instante de mínima "
                "distancia basal."
            )

        return RipaCompliance(
            evaluable=True,
            compliant=compliant,
            reason=reason,
        )

    if reference.ownship_role == "stand_on":
        required_hold_s = min(
            max(0.0, stand_on_hold_s),
            max(0.0, baseline_time_at_minimum_s),
        )

        first_departure_s = behavior.first_course_departure_time_s
        compliant = (
            first_departure_s is None
            or first_departure_s >= required_hold_s
        )

        return RipaCompliance(
            evaluable=True,
            compliant=compliant,
            reason=(
                "El USV mantuvo inicialmente su rumbo."
                if compliant
                else (
                    "El USV alteró su rumbo antes del periodo inicial "
                    "exigido al buque que mantiene rumbo."
                )
            ),
        )

    return RipaCompliance(
        evaluable=False,
        compliant=None,
        reason="El rol de referencia no puede calificarse.",
    )
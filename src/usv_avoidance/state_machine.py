from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import inf
from typing import Any, Mapping


class NavigationState(str, Enum):
    """Estados principales del comportamiento del USV."""

    TRACKING_ROUTE = "TRACKING_ROUTE"
    ASSESSING_TARGET = "ASSESSING_TARGET"
    AVOIDING_TARGET = "AVOIDING_TARGET"
    CLEARING_TARGET = "CLEARING_TARGET"
    RETURNING_TO_TRACK = "RETURNING_TO_TRACK"


@dataclass
class StateMachineConfig:
    """Configuración de la máquina de estados."""

    clear_samples_required: int = 3
    min_distance_increase_m: float = 1.0

    maneuver_decision_delay_s: float = 0.0

    # Tiempo mínimo antes de declarar que un blanco stand-on no actuó.
    # Con reportes AIS cada 5 s, 10 s permite observar tres muestras:
    # t=0, t=5 y t=10 s.
    stand_on_action_delay_s: float = 10.0

    # Se comienza a considerar una acción tardía con mayor anticipación.
    stand_on_critical_tcpa_s: float = 90.0

    # Confirmación de blanco no cooperativo.
    stand_on_confirmation_samples_required: int = 3
    stand_on_course_change_threshold_deg: float = 5.0
    stand_on_speed_change_threshold_kn: float = 0.5

    # Condición física para abandonar una reducción stand-on.
    stand_on_recovery_distance_m: float = 100.0

    def __post_init__(self) -> None:
        if self.clear_samples_required <= 0:
            raise ValueError(
                "clear_samples_required debe ser mayor que cero."
            )
        if self.min_distance_increase_m < 0.0:
            raise ValueError(
                "min_distance_increase_m no puede ser negativo."
            )
        if self.maneuver_decision_delay_s < 0.0:
            raise ValueError(
                "maneuver_decision_delay_s no puede ser negativo."
            )
        if self.stand_on_action_delay_s < 0.0:
            raise ValueError(
                "stand_on_action_delay_s no puede ser negativo."
            )
        if self.stand_on_critical_tcpa_s <= 0.0:
            raise ValueError(
                "stand_on_critical_tcpa_s debe ser mayor que cero."
            )
        if self.stand_on_confirmation_samples_required <= 1:
            raise ValueError(
                "stand_on_confirmation_samples_required debe ser mayor que 1."
            )
        if self.stand_on_course_change_threshold_deg < 0.0:
            raise ValueError(
                "stand_on_course_change_threshold_deg no puede ser negativo."
            )
        if self.stand_on_speed_change_threshold_kn < 0.0:
            raise ValueError(
                "stand_on_speed_change_threshold_kn no puede ser negativo."
            )
        if self.stand_on_recovery_distance_m <= 0.0:
            raise ValueError(
                "stand_on_recovery_distance_m debe ser mayor que cero."
            )


@dataclass
class NavigationStateMachine:
    """Máquina de estados del algoritmo de navegación evasiva."""

    config: StateMachineConfig = field(default_factory=StateMachineConfig)
    state: NavigationState = NavigationState.TRACKING_ROUTE
    active_target_mmsi: int | None = None
    clear_counter: int = 0
    last_distance_by_mmsi: dict[int, float] = field(default_factory=dict)
    risk_detected_at_s: float | None = None

    # El episodio comenzó con el USV como buque stand-on.
    stand_on_mode_eligible: bool = False

    # Ya existe una reducción activa y debe mantenerse hasta despeje físico.
    stand_on_emergency_active: bool = False

    # Seguimiento para detectar si el blanco obligado a maniobrar no actúa.
    stand_on_non_cooperative_counter: int = 0
    stand_on_last_target_course_deg: float | None = None
    stand_on_last_target_speed_kn: float | None = None

    def update(
        self,
        assessment: Mapping[str, Any] | None,
        route_recovered: bool = False,
        current_time_s: float = 0.0,
        global_return_course_safe: bool = False,
    ) -> dict[str, Any]:
        """Actualiza el estado del algoritmo."""

        previous_state = self.state
        current_time_s = float(current_time_s)
        decision_delay_s = float(
            self.config.maneuver_decision_delay_s
        )

        if assessment is None:
            self._reset_stand_on_episode()
            reason = "No hay blancos activos."

            if self.state in (
                NavigationState.AVOIDING_TARGET,
                NavigationState.CLEARING_TARGET,
                NavigationState.RETURNING_TO_TRACK,
            ):
                if route_recovered:
                    self.state = NavigationState.TRACKING_ROUTE
                    self.active_target_mmsi = None
                    self.clear_counter = 0
                    reason = "Sin blancos activos y ruta recuperada."
                else:
                    self.state = NavigationState.RETURNING_TO_TRACK
                    reason = "Sin blancos activos; retornar al track."

            return self._build_result(
                previous_state,
                reason,
                current_time_s,
            )

        target = assessment["target"]
        cpa_result = assessment["cpa_result"]
        classification = assessment["classification"]

        target_mmsi_raw = target.get(
            "mmsi",
            cpa_result.get("target_mmsi"),
        )
        target_mmsi = (
            int(target_mmsi_raw)
            if target_mmsi_raw is not None
            else None
        )

        risk = bool(
            classification.get(
                "risk",
                cpa_result.get("risk", False),
            )
        )
        should_maneuver = bool(
            classification.get("should_maneuver", False)
        )
        ownship_role = str(
            classification.get("ownship_role", "none")
        )

        distance_m = float(cpa_result.get("distance_m", inf))
        tcpa_s = float(cpa_result.get("tcpa_s", inf))

        distance_increasing = self._is_distance_increasing(
            target_mmsi=target_mmsi,
            distance_m=distance_m,
        )
        target_passed_cpa = tcpa_s < 0.0

        # Despeje usado por las maniobras de rumbo existentes.
        target_clear = (
            not risk
            and global_return_course_safe
        )

        # Despeje más estricto para una reducción de velocidad stand-on.
        stand_on_physical_clear = (
            target_passed_cpa
            and distance_increasing
            and distance_m >= self.config.stand_on_recovery_distance_m
        )

        reason = "Estado mantenido."

        if self.state == NavigationState.TRACKING_ROUTE:
            if risk:
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.risk_detected_at_s = current_time_s
                self.stand_on_emergency_active = False

                self.stand_on_mode_eligible = (
                    ownship_role == "stand_on"
                    and should_maneuver is False
                )

                if self.stand_on_mode_eligible:
                    self._initialize_stand_on_observation(target)
                else:
                    self._reset_non_cooperative_observation()

                if should_maneuver and decision_delay_s <= 0.0:
                    self.state = NavigationState.AVOIDING_TARGET
                    reason = (
                        "Riesgo detectado y el USV debe maniobrar."
                    )
                else:
                    self.state = NavigationState.ASSESSING_TARGET
                    if ownship_role == "stand_on":
                        reason = (
                            "Riesgo detectado; se observa si el blanco "
                            "obligado a maniobrar adopta una acción efectiva."
                        )
                    else:
                        reason = (
                            "Riesgo detectado; evaluando el rol del USV."
                        )
            else:
                self._reset_stand_on_episode()
                reason = "Sin riesgo; navegación normal."

        elif self.state == NavigationState.ASSESSING_TARGET:
            if not risk:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                self._reset_stand_on_episode()
                reason = "El riesgo desapareció durante la evaluación."

            elif risk and should_maneuver:
                # Rama give-way original.
                self.active_target_mmsi = target_mmsi
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False
                self._reset_non_cooperative_observation()

                if self.risk_detected_at_s is None:
                    self.risk_detected_at_s = current_time_s

                observation_elapsed_s = max(
                    0.0,
                    current_time_s - self.risk_detected_at_s,
                )

                if observation_elapsed_s >= decision_delay_s:
                    self.state = NavigationState.AVOIDING_TARGET
                    self.clear_counter = 0
                    reason = (
                        "Corresponde ejecutar la maniobra evasiva give-way."
                    )
                else:
                    delay_remaining_s = max(
                        0.0,
                        decision_delay_s - observation_elapsed_s,
                    )
                    reason = (
                        "Observando el encuentro give-way. "
                        f"Tiempo restante: {delay_remaining_s:.1f} s."
                    )

            elif (
                risk
                and ownship_role == "stand_on"
                and should_maneuver is False
                and self.stand_on_mode_eligible
            ):
                self.active_target_mmsi = target_mmsi

                if self.risk_detected_at_s is None:
                    self.risk_detected_at_s = current_time_s

                target_non_cooperative = (
                    self._update_non_cooperative_confirmation(target)
                )
                observation_elapsed_s = max(
                    0.0,
                    current_time_s - self.risk_detected_at_s,
                )
                minimum_observation_elapsed = (
                    observation_elapsed_s
                    >= self.config.stand_on_action_delay_s
                )
                tcpa_is_critical = (
                    0.0 < tcpa_s
                    <= self.config.stand_on_critical_tcpa_s
                )

                if (
                    target_non_cooperative
                    and minimum_observation_elapsed
                    and tcpa_is_critical
                ):
                    self.state = NavigationState.AVOIDING_TARGET
                    self.clear_counter = 0
                    self.stand_on_emergency_active = True
                    reason = (
                        "El blanco no mostró cambios efectivos de COG/SOG "
                        "durante tres muestras y el TCPA es crítico; se "
                        "mantendrá una reducción hasta el despeje físico."
                    )
                else:
                    reason = (
                        "El USV mantiene inicialmente rumbo y velocidad. "
                        "Confirmaciones de blanco no cooperativo: "
                        f"{self.stand_on_non_cooperative_counter}/"
                        f"{self.config.stand_on_confirmation_samples_required}; "
                        f"TCPA: {tcpa_s:.1f} s."
                    )

            else:
                self.active_target_mmsi = target_mmsi
                self.stand_on_emergency_active = False
                reason = (
                    "Se mantiene evaluación; no existe una acción "
                    "adicional definida para el rol actual."
                )

        elif self.state == NavigationState.AVOIDING_TARGET:
            # Una reducción stand-on ya autorizada queda bloqueada hasta
            # completar tres muestras de despeje físico. No se cancela por
            # una reclasificación provocada por la propia reducción.
            if self.stand_on_emergency_active:
                if target_mmsi != self.active_target_mmsi:
                    previous_target_mmsi = self.active_target_mmsi
                    self.state = NavigationState.ASSESSING_TARGET
                    self.active_target_mmsi = target_mmsi
                    self.clear_counter = 0
                    self._reset_stand_on_episode()
                    reason = (
                        "Cambió el contacto prioritario durante la reducción "
                        f"stand-on: {previous_target_mmsi} → {target_mmsi}; "
                        "se cancela el plan y se reevalúa."
                    )

                elif stand_on_physical_clear:
                    self.clear_counter += 1

                    if (
                        self.clear_counter
                        >= self.config.clear_samples_required
                    ):
                        self.state = NavigationState.RETURNING_TO_TRACK
                        self.stand_on_emergency_active = False
                        self.stand_on_mode_eligible = False
                        reason = (
                            "El contacto pasó el CPA, se aleja y supera "
                            f"{self.config.stand_on_recovery_distance_m:.0f} m "
                            "durante tres muestras; se recupera velocidad."
                        )
                    else:
                        reason = (
                            "Manteniendo la reducción y confirmando despeje "
                            f"físico ({self.clear_counter}/"
                            f"{self.config.clear_samples_required})."
                        )
                else:
                    self.clear_counter = 0
                    reason = (
                        "Se mantiene la reducción stand-on hasta que el "
                        "contacto pase el CPA, se aleje y supere la "
                        f"distancia de recuperación de "
                        f"{self.config.stand_on_recovery_distance_m:.0f} m."
                    )

            # Lógica original de las maniobras por rumbo give-way.
            elif target_clear:
                self.state = NavigationState.CLEARING_TARGET
                self.clear_counter = 1
                reason = "El blanco comienza a quedar claro."
            else:
                reason = "Se mantiene estado evasivo."

        elif self.state == NavigationState.CLEARING_TARGET:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "El contacto continúa en riesgo; volver a evasión."
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "El contacto continúa en riesgo; volver a evaluación."
            elif target_clear:
                self.clear_counter += 1
                if self.clear_counter >= self.config.clear_samples_required:
                    self.state = NavigationState.RETURNING_TO_TRACK
                    reason = "Blanco claro durante tres actualizaciones."
                else:
                    reason = "Confirmando que el blanco quedó claro."
            else:
                self.clear_counter = 0
                reason = "Aún no se confirma despeje del blanco."

        elif self.state == NavigationState.RETURNING_TO_TRACK:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self._reset_stand_on_episode()
                reason = "Nuevo riesgo give-way durante retorno al track."
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.risk_detected_at_s = current_time_s
                self.stand_on_mode_eligible = (
                    ownship_role == "stand_on"
                    and should_maneuver is False
                )
                if self.stand_on_mode_eligible:
                    self._initialize_stand_on_observation(target)
                reason = "Nuevo blanco detectado durante retorno."
            elif route_recovered:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                self._reset_stand_on_episode()
                reason = "Track recuperado; navegación normal."
            else:
                reason = "Retornando al track o waypoint."

        return self._build_result(
            previous_state,
            reason,
            current_time_s,
        )

    def _initialize_stand_on_observation(
        self,
        target: Mapping[str, Any],
    ) -> None:
        self.stand_on_non_cooperative_counter = 1
        self.stand_on_last_target_course_deg = self._optional_float(
            target.get("cog_deg")
        )
        self.stand_on_last_target_speed_kn = self._optional_float(
            target.get("sog_kn")
        )

    def _update_non_cooperative_confirmation(
        self,
        target: Mapping[str, Any],
    ) -> bool:
        current_course = self._optional_float(target.get("cog_deg"))
        current_speed = self._optional_float(target.get("sog_kn"))

        previous_course = self.stand_on_last_target_course_deg
        previous_speed = self.stand_on_last_target_speed_kn

        course_changed = False
        speed_changed = False

        if current_course is not None and previous_course is not None:
            course_changed = (
                abs(self._angle_difference_deg(
                    current_course,
                    previous_course,
                ))
                >= self.config.stand_on_course_change_threshold_deg
            )

        if current_speed is not None and previous_speed is not None:
            speed_changed = (
                abs(current_speed - previous_speed)
                >= self.config.stand_on_speed_change_threshold_kn
            )

        if course_changed or speed_changed:
            # El blanco mostró una acción apreciable; se reinicia la cuenta.
            self.stand_on_non_cooperative_counter = 0
        else:
            self.stand_on_non_cooperative_counter += 1

        if current_course is not None:
            self.stand_on_last_target_course_deg = current_course
        if current_speed is not None:
            self.stand_on_last_target_speed_kn = current_speed

        return (
            self.stand_on_non_cooperative_counter
            >= self.config.stand_on_confirmation_samples_required
        )

    def _reset_non_cooperative_observation(self) -> None:
        self.stand_on_non_cooperative_counter = 0
        self.stand_on_last_target_course_deg = None
        self.stand_on_last_target_speed_kn = None

    def _reset_stand_on_episode(self) -> None:
        self.risk_detected_at_s = None
        self.stand_on_mode_eligible = False
        self.stand_on_emergency_active = False
        self._reset_non_cooperative_observation()

    def _is_distance_increasing(
        self,
        target_mmsi: int | None,
        distance_m: float,
    ) -> bool:
        if target_mmsi is None:
            return False

        previous_distance = self.last_distance_by_mmsi.get(target_mmsi)
        self.last_distance_by_mmsi[target_mmsi] = distance_m

        if previous_distance is None:
            return False

        return (
            distance_m
            > previous_distance + self.config.min_distance_increase_m
        )

    @staticmethod
    def _angle_difference_deg(
        angle_a_deg: float,
        angle_b_deg: float,
    ) -> float:
        return (angle_a_deg - angle_b_deg + 180.0) % 360.0 - 180.0

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_result(
        self,
        previous_state: NavigationState,
        reason: str,
        current_time_s: float,
    ) -> dict[str, Any]:
        observation_elapsed_s = None
        decision_delay_remaining_s = None

        if self.risk_detected_at_s is not None:
            observation_elapsed_s = max(
                0.0,
                float(current_time_s) - self.risk_detected_at_s,
            )
            decision_delay_remaining_s = max(
                0.0,
                self.config.maneuver_decision_delay_s
                - observation_elapsed_s,
            )

        return {
            "previous_state": previous_state.value,
            "current_state": self.state.value,
            "active_target_mmsi": self.active_target_mmsi,
            "clear_counter": self.clear_counter,
            "reason": reason,
            "risk_detected_at_s": self.risk_detected_at_s,
            "observation_elapsed_s": observation_elapsed_s,
            "maneuver_decision_delay_s": (
                self.config.maneuver_decision_delay_s
            ),
            "decision_delay_remaining_s": decision_delay_remaining_s,
            "stand_on_action_delay_s": (
                self.config.stand_on_action_delay_s
            ),
            "stand_on_critical_tcpa_s": (
                self.config.stand_on_critical_tcpa_s
            ),
            "stand_on_confirmation_samples_required": (
                self.config.stand_on_confirmation_samples_required
            ),
            "stand_on_non_cooperative_counter": (
                self.stand_on_non_cooperative_counter
            ),
            "stand_on_recovery_distance_m": (
                self.config.stand_on_recovery_distance_m
            ),
            "stand_on_emergency_active": (
                self.stand_on_emergency_active
            ),
            "stand_on_mode_eligible": (
                self.stand_on_mode_eligible
            ),
        }


def select_most_critical_assessment(
    assessments: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Selecciona el blanco más crítico entre varios blancos activos."""

    if not assessments:
        return None

    def score(
        assessment: Mapping[str, Any],
    ) -> tuple[float, float, float, float]:
        cpa_result = assessment["cpa_result"]
        classification = assessment["classification"]

        risk = bool(
            classification.get(
                "risk",
                cpa_result.get("risk", False),
            )
        )
        should_maneuver = bool(
            classification.get("should_maneuver", False)
        )
        cpa_m = float(cpa_result.get("cpa_m", inf))
        tcpa_s = float(cpa_result.get("tcpa_s", inf))
        tcpa_priority = tcpa_s if tcpa_s >= 0.0 else inf

        return (
            0.0 if risk else 1.0,
            0.0 if should_maneuver else 1.0,
            tcpa_priority,
            cpa_m,
        )

    return min(assessments, key=score)
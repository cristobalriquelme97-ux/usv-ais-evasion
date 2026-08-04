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

    # Retardo ya utilizado por las maniobras give-way.
    maneuver_decision_delay_s: float = 0.0

    # Retardo específico durante el cual un stand-on conserva rumbo
    # y velocidad antes de aplicar una acción tardía de seguridad.
    stand_on_action_delay_s: float = 20.0

    # La acción tardía solo se inicia cuando el TCPA entra en esta ventana.
    stand_on_critical_tcpa_s: float = 60.0

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


@dataclass
class NavigationStateMachine:
    """
    Máquina de estados del algoritmo de navegación evasiva.

    La lógica give-way existente se conserva. La única extensión es una
    transición tardía para encuentros stand-on cuando el riesgo persiste y
    el TCPA entra en una ventana crítica. El módulo de evasión interpreta
    esa transición como una orden de reducción de velocidad.
    """

    config: StateMachineConfig = field(default_factory=StateMachineConfig)
    state: NavigationState = NavigationState.TRACKING_ROUTE
    active_target_mmsi: int | None = None
    clear_counter: int = 0
    last_distance_by_mmsi: dict[int, float] = field(default_factory=dict)
    risk_detected_at_s: float | None = None

    # Indica si el encuentro fue identificado como stand-on
    # desde el inicio del episodio de riesgo.
    stand_on_mode_eligible: bool = False

    # Indica que ya se autorizó la reducción tardía.
    stand_on_emergency_active: bool = False

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
            self.risk_detected_at_s = None
            self.stand_on_mode_eligible = False
            self.stand_on_emergency_active = False

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

        target_mmsi = target.get(
            "mmsi",
            cpa_result.get("target_mmsi"),
        )
        target_mmsi = (
            int(target_mmsi)
            if target_mmsi is not None
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

        self._is_distance_increasing(
            target_mmsi=target_mmsi,
            distance_m=distance_m,
        )

        cpa_m = float(cpa_result.get("cpa_m", inf))
        safety_radius_m = float(
            cpa_result.get("safety_radius_m", 50.0)
        )
        cpa_safe = cpa_m >= safety_radius_m
        target_passed_cpa = tcpa_s < 0.0

        # Se conserva la condición original de despeje.
        target_clear = (
            not risk
            and global_return_course_safe
        )

        reason = "Estado mantenido."

        if self.state == NavigationState.TRACKING_ROUTE:
            if risk:
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.risk_detected_at_s = current_time_s
                self.stand_on_emergency_active = False

                # La reducción solo queda habilitada si el encuentro
                # fue stand-on desde la primera detección del riesgo.
                self.stand_on_mode_eligible = (
                    ownship_role == "stand_on"
                    and should_maneuver is False
                )

                if (
                    should_maneuver
                    and decision_delay_s <= 0.0
                ):
                    self.state = NavigationState.AVOIDING_TARGET
                    reason = (
                        "Riesgo detectado y el USV debe maniobrar."
                    )
                else:
                    self.state = NavigationState.ASSESSING_TARGET

                    if should_maneuver:
                        reason = (
                            "Riesgo detectado; comienza el periodo "
                            "de observación previo a la maniobra."
                        )
                    elif ownship_role == "stand_on":
                        reason = (
                            "Riesgo detectado; el USV mantiene rumbo "
                            "y velocidad como buque stand-on."
                        )
                    else:
                        reason = (
                            "Riesgo detectado; evaluando el rol "
                            "del USV."
                        )
            else:
                self.risk_detected_at_s = None
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False
                reason = "Sin riesgo; navegación normal."

        elif self.state == NavigationState.ASSESSING_TARGET:
            if not risk:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                self.risk_detected_at_s = None
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False
                reason = (
                    "El riesgo desapareció durante la evaluación."
                )
                

            elif risk and should_maneuver:
                # Rama give-way original.
                self.active_target_mmsi = target_mmsi

                # Si aparece obligación give-way, este episodio deja
                # de ser elegible para reducción stand-on.
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False
                
                if self.risk_detected_at_s is None:
                    self.risk_detected_at_s = current_time_s

                observation_elapsed_s = max(
                    0.0,
                    current_time_s - self.risk_detected_at_s,
                )

                delay_remaining_s = max(
                    0.0,
                    decision_delay_s - observation_elapsed_s,
                )

                if observation_elapsed_s >= decision_delay_s:
                    self.state = NavigationState.AVOIDING_TARGET
                    self.clear_counter = 0
                    reason = (
                        "Finalizó el periodo de observación; "
                        "corresponde ejecutar la maniobra evasiva."
                    )
                else:
                    reason = (
                        "Observando la evolución del encuentro antes "
                        "de maniobrar. Tiempo restante: "
                        f"{delay_remaining_s:.1f} s."
                    )

            elif (
                risk
                and ownship_role == "stand_on"
                and should_maneuver is False
                and self.stand_on_mode_eligible
            ):
                # Extensión acotada: el USV conserva inicialmente rumbo
                # y velocidad. Si el blanco no resuelve el riesgo, el TCPA
                # sigue disminuyendo hasta la ventana crítica y se autoriza
                # una reducción tardía de velocidad.
                self.active_target_mmsi = target_mmsi

                if self.risk_detected_at_s is None:
                    self.risk_detected_at_s = current_time_s

                observation_elapsed_s = max(
                    0.0,
                    current_time_s - self.risk_detected_at_s,
                )
                stand_on_delay_s = float(
                    self.config.stand_on_action_delay_s
                )
                delay_elapsed = (
                    observation_elapsed_s >= stand_on_delay_s
                )
                tcpa_is_critical = (
                    0.0 < tcpa_s
                    <= self.config.stand_on_critical_tcpa_s
                )

                if delay_elapsed and tcpa_is_critical:
                    self.state = NavigationState.AVOIDING_TARGET
                    self.clear_counter = 0
                    self.stand_on_emergency_active = True
                    reason = (
                        "El blanco no resolvió el riesgo durante el "
                        "periodo stand-on y el TCPA es crítico; se "
                        "autoriza una reducción tardía de velocidad."
                    )
                else:
                    remaining_s = max(
                        0.0,
                        stand_on_delay_s - observation_elapsed_s,
                    )
                    reason = (
                        "El USV mantiene rumbo y velocidad como "
                        "stand-on. "
                        f"Espera restante: {remaining_s:.1f} s; "
                        f"TCPA actual: {tcpa_s:.1f} s."
                    )

            else:
                self.active_target_mmsi = target_mmsi
                self.stand_on_emergency_active = False
                reason = (
                    "Se mantiene evaluación; no existe una acción "
                    "adicional definida para el rol actual."
                )

        elif self.state == NavigationState.AVOIDING_TARGET:

            # Si el encuentro pasa a give-way, se cancela la
            # reducción stand-on y continúa la lógica original
            # de maniobra por rumbo.
            if risk and should_maneuver:
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False

                if target_mmsi != self.active_target_mmsi:
                    previous_target_mmsi = (
                        self.active_target_mmsi
                    )

                    self.active_target_mmsi = target_mmsi
                    self.clear_counter = 0

                    reason = (
                        "Cambió el contacto prioritario durante "
                        "la evasión: "
                        f"{previous_target_mmsi} → "
                        f"{target_mmsi}."
                    )
                else:
                    reason = (
                        "El encuentro requiere maniobra give-way; "
                        "se cancela la reducción stand-on."
                    )

            # La reducción solo se mantiene si el rol continúa
            # siendo stand-on.
            elif (
                risk
                and ownship_role == "stand_on"
                and should_maneuver is False
                and self.stand_on_mode_eligible
                and self.stand_on_emergency_active
            ):
                reason = (
                    "Se mantiene la reducción tardía de velocidad "
                    "del buque stand-on."
                )

            # Si todavía existe riesgo, pero el rol ya no es
            # stand-on ni give-way, se cancela la reducción.
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.stand_on_mode_eligible = False
                self.stand_on_emergency_active = False

                reason = (
                    "El rol dejó de ser stand-on; se cancela "
                    "la reducción de velocidad y se vuelve "
                    "a evaluación."
                )

            elif target_clear:
                self.state = NavigationState.CLEARING_TARGET
                self.clear_counter = 1
                self.stand_on_emergency_active = False

                reason = "El blanco comienza a quedar claro."

            else:
                reason = "Se mantiene estado evasivo."

        elif self.state == NavigationState.CLEARING_TARGET:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.stand_on_emergency_active = False
                reason = (
                    "El contacto continúa en riesgo; volver a evasión."
                )

            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.stand_on_emergency_active = False
                reason = (
                    "El contacto continúa en riesgo; volver a evaluación."
                )

            elif target_clear:
                self.clear_counter += 1

                if (
                    self.clear_counter
                    >= self.config.clear_samples_required
                ):
                    self.state = NavigationState.RETURNING_TO_TRACK
                    reason = (
                        "Blanco claro durante tres actualizaciones "
                        "consecutivas."
                    )
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
                self.stand_on_emergency_active = False
                reason = "Nuevo riesgo durante retorno al track."
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.stand_on_emergency_active = False
                reason = "Nuevo blanco detectado durante retorno."
            elif route_recovered:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                self.risk_detected_at_s = None
                self.stand_on_emergency_active = False
                reason = "Track recuperado; navegación normal."
            else:
                reason = "Retornando al track o waypoint."

        # Variables mantenidas para conservar trazabilidad con la versión
        # original, aunque la condición de despeje sigue usando target_clear.
        _ = cpa_safe, target_passed_cpa

        return self._build_result(
            previous_state,
            reason,
            current_time_s,
        )

    def _is_distance_increasing(
        self,
        target_mmsi: int | None,
        distance_m: float,
    ) -> bool:
        """Verifica si la distancia al blanco está aumentando."""

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

    def _build_result(
        self,
        previous_state: NavigationState,
        reason: str,
        current_time_s: float,
    ) -> dict[str, Any]:
        """Construye una salida estándar para los demás módulos."""

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
            "decision_delay_remaining_s": (
                decision_delay_remaining_s
            ),
            "stand_on_action_delay_s": (
                self.config.stand_on_action_delay_s
            ),
            "stand_on_critical_tcpa_s": (
                self.config.stand_on_critical_tcpa_s
            ),
            "stand_on_emergency_active": (
                self.stand_on_emergency_active
            ),
            "stand_on_mode_eligible": (
                self.stand_on_mode_eligible
            ),
        }
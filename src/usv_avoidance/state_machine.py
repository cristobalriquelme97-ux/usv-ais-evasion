from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import inf
from typing import Any, Mapping
from usv_avoidance.target_priority import (
    select_most_critical_assessment,
)

class NavigationState(str, Enum):
    """
    Estados principales del comportamiento del USV.
    """

    TRACKING_ROUTE = "TRACKING_ROUTE"
    ASSESSING_TARGET = "ASSESSING_TARGET"
    AVOIDING_TARGET = "AVOIDING_TARGET"
    CLEARING_TARGET = "CLEARING_TARGET"
    RETURNING_TO_TRACK = "RETURNING_TO_TRACK"


@dataclass
class StateMachineConfig:
    """
    Configuración de la máquina de estados.

    clear_samples_required:
        Cantidad de actualizaciones seguras consecutivas necesarias
        para considerar que el blanco ya quedó claro.

    min_distance_increase_m:
        Incremento mínimo de distancia para considerar que el blanco
        se está alejando.
    """

    clear_samples_required: int = 3
    min_distance_increase_m: float = 1.0

    # Tiempo mínimo de observación desde la primera detección
    # de riesgo hasta la entrada a AVOIDING_TARGET.
    maneuver_decision_delay_s: float = 0.0

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


@dataclass
class NavigationStateMachine:
    """
    Máquina de estados del algoritmo de navegación evasiva.

    Esta clase no calcula CPA/TCPA.
    Esta clase no clasifica encuentros.
    Esta clase no decide cuántos grados caer.

    Su función es decidir en qué etapa del comportamiento está el USV
    usando los resultados ya calculados por:
    - cpa_tcpa.py
    - encounter_geometry.py
    - encounter_classifier.py
    """

    config: StateMachineConfig = field(default_factory=StateMachineConfig)
    state: NavigationState = NavigationState.TRACKING_ROUTE
    active_target_mmsi: int | None = None
    clear_counter: int = 0
    last_distance_by_mmsi: dict[int, float] = field(default_factory=dict)
    risk_detected_at_s: float | None = None

    def update(
        self,
        assessment: Mapping[str, Any] | None,
        route_recovered: bool = False,
        current_time_s: float = 0.0,
    ) -> dict[str, Any]:
        """
        Actualiza el estado del algoritmo.

        Parámetros:
        - assessment:
            Diccionario con target, cpa_result, bearing_info y classification.
            Puede ser None si no hay blancos activos.

        - route_recovered:
            Indica si el USV ya retomó el track o waypoint.
            Por ahora lo dejaremos normalmente en False, porque todavía
            no desarrollamos route_manager.py.

        Retorna:
        - Diccionario con estado anterior, estado actual y motivo.
        """

        previous_state = self.state
        current_time_s = float(current_time_s)

        decision_delay_s = float(
            self.config.maneuver_decision_delay_s
        )

        # Caso sin blancos activos.
        if assessment is None:
            self.risk_detected_at_s = None

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

        target_mmsi = target.get("mmsi", cpa_result.get("target_mmsi"))
        target_mmsi = int(target_mmsi) if target_mmsi is not None else None

        risk = bool(classification.get("risk", cpa_result.get("risk", False)))
        should_maneuver = bool(classification.get("should_maneuver", False))

        distance_m = float(cpa_result.get("distance_m", inf))
        tcpa_s = float(cpa_result.get("tcpa_s", inf))

        distance_increasing = self._is_distance_increasing(
            target_mmsi=target_mmsi,
            distance_m=distance_m,
        )

        cpa_m = float(cpa_result.get("cpa_m", inf))
        safety_radius_m = float(cpa_result.get("safety_radius_m", 50.0))
        # El blanco se considera despejado si el CPA es mayor al radio de seguridad o si el TCPA es negativo (ya pasó el punto de máxima aproximación).
        cpa_safe = cpa_m >= safety_radius_m
        target_passed_cpa = tcpa_s < 0.0

        return_cpa_result = assessment.get("return_cpa_result")

        return_course_safe = False

        if return_cpa_result is not None:
            return_cpa_m = float(return_cpa_result.get("cpa_m", 0.0))
            return_safety_radius_m = float(return_cpa_result.get("safety_radius_m", 50.0))

            return_course_safe = return_cpa_m >= return_safety_radius_m

        target_clear = (
            not risk
            and (
                target_passed_cpa
                or return_course_safe
            )
        )

        reason = "Estado mantenido."

        if self.state == NavigationState.TRACKING_ROUTE:
            if risk:
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                self.risk_detected_at_s = current_time_s

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
                    else:
                        reason = (
                            "Riesgo detectado; evaluando el rol "
                            "del USV."
                        )
            else:
                self.risk_detected_at_s = None
                reason = "Sin riesgo; navegación normal."

        elif self.state == NavigationState.ASSESSING_TARGET:
            if not risk:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                self.risk_detected_at_s = None

                reason = (
                    "El riesgo desapareció durante la evaluación."
                )

            elif risk and should_maneuver:
                # El contacto prioritario puede cambiar durante el
                # periodo de observación.
                self.active_target_mmsi = target_mmsi

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

            else:
                self.active_target_mmsi = target_mmsi

                reason = (
                    "Se mantiene evaluación; el USV no tiene "
                    "actualmente obligación de maniobrar."
                )

        elif self.state == NavigationState.AVOIDING_TARGET:
            # Mientras exista riesgo y el USV deba maniobrar,
            # la evasión tiene prioridad sobre el despeje.
            if risk and should_maneuver:
                if target_mmsi != self.active_target_mmsi:
                    previous_target_mmsi = (
                        self.active_target_mmsi
                    )

                    self.active_target_mmsi = target_mmsi
                    self.clear_counter = 0

                    reason = (
                        "Cambió el contacto prioritario durante la "
                        "evasión: "
                        f"{previous_target_mmsi} → "
                        f"{target_mmsi}."
                    )
                else:
                    reason = "Se mantiene estado evasivo."

            elif target_clear:
                self.state = NavigationState.CLEARING_TARGET
                self.clear_counter = 1

                reason = "El blanco comienza a quedar claro."

            else:
                reason = "Se mantiene estado evasivo."

        elif self.state == NavigationState.CLEARING_TARGET:
            # Si todavía existe riesgo, se cancela inmediatamente
            # la confirmación de despeje.
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0

                reason = (
                    "El contacto continúa en riesgo; "
                    "volver a evasión."
                )

            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0

                reason = (
                    "El contacto continúa en riesgo; "
                    "volver a evaluación."
                )

            elif target_clear:
                self.clear_counter += 1

                if (
                    self.clear_counter
                    >= self.config.clear_samples_required
                ):
                    self.state = (
                        NavigationState.RETURNING_TO_TRACK
                    )

                    reason = (
                        "Blanco claro durante tres "
                        "actualizaciones consecutivas."
                    )
                else:
                    reason = (
                        "Confirmando que el blanco quedó claro."
                    )

            else:
                self.clear_counter = 0

                reason = (
                    "Aún no se confirma despeje del blanco."
                )

        elif self.state == NavigationState.RETURNING_TO_TRACK:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "Nuevo riesgo durante retorno al track."
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "Nuevo blanco detectado durante retorno."
            elif route_recovered:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                reason = "Track recuperado; navegación normal."
            else:
                reason = "Retornando al track o waypoint."

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
        """
        Verifica si la distancia al blanco está aumentando.
        """

        if target_mmsi is None:
            return False

        previous_distance = self.last_distance_by_mmsi.get(target_mmsi)

        self.last_distance_by_mmsi[target_mmsi] = distance_m

        if previous_distance is None:
            return False

        return distance_m > previous_distance + self.config.min_distance_increase_m

    def _build_result(
        self,
        previous_state: NavigationState,
        reason: str,
        current_time_s: float,
    ) -> dict[str, Any]:
        """
        Construye una salida estándar para imprimir o utilizar
        en otros módulos.
        """

        observation_elapsed_s = None
        decision_delay_remaining_s = None

        if self.risk_detected_at_s is not None:
            observation_elapsed_s = max(
                0.0,
                float(current_time_s)
                - self.risk_detected_at_s,
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
        }




if __name__ == "__main__":
    machine = NavigationStateMachine()

    fake_target = {
        "mmsi": 725000001,
    }

    sequence = [
        {
            "name": "Navegación normal",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 300.0,
                "cpa_m": 120.0,
                "tcpa_s": 80.0,
                "risk": False,
            },
            "classification": {
                "risk": False,
                "should_maneuver": False,
                "encounter_name": "sin riesgo",
            },
        },
        {
            "name": "Riesgo de cruce",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 220.0,
                "cpa_m": 35.0,
                "tcpa_s": 60.0,
                "risk": True,
            },
            "classification": {
                "risk": True,
                "should_maneuver": True,
                "encounter_name": "cruce",
            },
        },
        {
            "name": "Mantiene evasión",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 160.0,
                "cpa_m": 35.0,
                "tcpa_s": 30.0,
                "risk": True,
            },
            "classification": {
                "risk": True,
                "should_maneuver": True,
                "encounter_name": "cruce",
            },
        },
        {
            "name": "PMA superado",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 170.0,
                "cpa_m": 35.0,
                "tcpa_s": -5.0,
                "risk": False,
            },
            "classification": {
                "risk": False,
                "should_maneuver": False,
                "encounter_name": "sin riesgo",
            },
        },
        {
            "name": "Blanco alejándose",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 190.0,
                "cpa_m": 35.0,
                "tcpa_s": -15.0,
                "risk": False,
            },
            "classification": {
                "risk": False,
                "should_maneuver": False,
                "encounter_name": "sin riesgo",
            },
        },
        {
            "name": "Blanco claro",
            "cpa_result": {
                "target_mmsi": 725000001,
                "distance_m": 220.0,
                "cpa_m": 35.0,
                "tcpa_s": -25.0,
                "risk": False,
            },
            "classification": {
                "risk": False,
                "should_maneuver": False,
                "encounter_name": "sin riesgo",
            },
        },
    ]

    for item in sequence:
        assessment = {
            "target": fake_target,
            "cpa_result": item["cpa_result"],
            "bearing_info": {},
            "classification": item["classification"],
        }

        state_info = machine.update(
            assessment=assessment,
            route_recovered=False,
        )

        print("=" * 70)
        print(item["name"])
        print(state_info)
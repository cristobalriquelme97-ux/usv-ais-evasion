from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import inf
from typing import Any, Mapping


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

    def update(
        self,
        assessment: Mapping[str, Any] | None,
        route_recovered: bool = False,
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

        # Caso sin blancos activos.
        if assessment is None:
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

            return self._build_result(previous_state, reason)

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

        target_clear = target_passed_cpa or return_course_safe

        reason = "Estado mantenido."

        if self.state == NavigationState.TRACKING_ROUTE:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "Riesgo detectado y el USV debe maniobrar."
            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "Riesgo detectado; evaluando rol del USV."
            else:
                reason = "Sin riesgo; navegación normal."

        elif self.state == NavigationState.ASSESSING_TARGET:
            if risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.active_target_mmsi = target_mmsi
                self.clear_counter = 0
                reason = "El encuentro requiere maniobra evasiva."
            elif not risk:
                self.state = NavigationState.TRACKING_ROUTE
                self.active_target_mmsi = None
                self.clear_counter = 0
                reason = "El riesgo desapareció durante la evaluación."
            else:
                reason = "Se mantiene evaluación del blanco."

        elif self.state == NavigationState.AVOIDING_TARGET:
            if target_clear:
                self.state = NavigationState.CLEARING_TARGET
                self.clear_counter = 1
                reason = "El blanco comienza a quedar claro."
            else:
                reason = "Se mantiene estado evasivo."

        elif self.state == NavigationState.CLEARING_TARGET:
            if target_clear:
                self.clear_counter += 1

                if self.clear_counter >= self.config.clear_samples_required:
                    self.state = NavigationState.RETURNING_TO_TRACK
                    reason = "Blanco claro durante tres actualizaciones consecutivas."
                else:
                    reason = "Confirmando que el blanco quedó claro."

            elif risk and should_maneuver:
                self.state = NavigationState.AVOIDING_TARGET
                self.clear_counter = 0
                reason = "El riesgo reapareció; volver a evasión."

            elif risk:
                self.state = NavigationState.ASSESSING_TARGET
                self.clear_counter = 0
                reason = "Riesgo reaparece; volver a evaluación."

            else:
                self.clear_counter = 0
                reason = "Aún no se confirma despeje del blanco."

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

        return self._build_result(previous_state, reason)

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
    ) -> dict[str, Any]:
        """
        Construye una salida estándar para imprimir o usar en otros módulos.
        """

        return {
            "previous_state": previous_state.value,
            "current_state": self.state.value,
            "active_target_mmsi": self.active_target_mmsi,
            "clear_counter": self.clear_counter,
            "reason": reason,
        }


def select_most_critical_assessment(
    assessments: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """
    Selecciona el blanco más crítico entre varios blancos activos.

    Criterio:
    1. Prioriza blancos con riesgo.
    2. Prioriza blancos donde el USV debe maniobrar.
    3. Prioriza menor TCPA positivo.
    4. Prioriza menor CPA.
    """

    if not assessments:
        return None

    def score(assessment: Mapping[str, Any]) -> tuple[float, float, float, float]:
        cpa_result = assessment["cpa_result"]
        classification = assessment["classification"]

        risk = bool(classification.get("risk", cpa_result.get("risk", False)))
        should_maneuver = bool(classification.get("should_maneuver", False))

        cpa_m = float(cpa_result.get("cpa_m", inf))
        tcpa_s = float(cpa_result.get("tcpa_s", inf))

        # Si TCPA es negativo, el punto de máxima aproximación ya pasó.
        # Por eso se manda al final de la prioridad temporal.
        tcpa_priority = tcpa_s if tcpa_s >= 0.0 else inf

        risk_priority = 0.0 if risk else 1.0
        maneuver_priority = 0.0 if should_maneuver else 1.0

        return (
            risk_priority,
            maneuver_priority,
            tcpa_priority,
            cpa_m,
        )

    return min(assessments, key=score)


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
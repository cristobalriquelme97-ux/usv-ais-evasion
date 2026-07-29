from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmConfig:
    """
    Parámetros utilizados por el algoritmo de evasión.

    Esta configuración no describe las posiciones, velocidades
    ni rumbos iniciales de un escenario. Solamente contiene los
    criterios internos utilizados para analizar el riesgo y
    seleccionar las maniobras.
    """

    # Distancia mínima que debe conservar el USV respecto
    # de cualquier contacto.
    safety_radius_m: float = 50.0

    # Tiempo futuro considerado en los cálculos de CPA/TCPA
    # y en la evaluación de las maniobras candidatas.
    time_horizon_s: float = 200.0

    # Tiempo máximo durante el cual un contacto AIS puede
    # permanecer sin actualización antes de eliminarse.
    tracker_max_age_s: float = 60.0

    # Diferencia máxima respecto del rumbo original para
    # considerar que el USV recuperó su trayectoria.
    route_recovery_tolerance_deg: float = 3.0

    # Tiempo durante el cual el algoritmo observa el encuentro
    # antes de ordenar la primera maniobra evasiva.
    maneuver_decision_delay_s: float = 20.0

    def __post_init__(self) -> None:
        """
        Valida los valores al crear la configuración.
        """

        if self.safety_radius_m <= 0.0:
            raise ValueError(
                "safety_radius_m debe ser mayor que cero."
            )

        if self.time_horizon_s <= 0.0:
            raise ValueError(
                "time_horizon_s debe ser mayor que cero."
            )

        if self.tracker_max_age_s <= 0.0:
            raise ValueError(
                "tracker_max_age_s debe ser mayor que cero."
            )

        if self.route_recovery_tolerance_deg < 0.0:
            raise ValueError(
                "route_recovery_tolerance_deg no puede ser negativo."
            )

        if self.maneuver_decision_delay_s < 0.0:
            raise ValueError(
                "maneuver_decision_delay_s no puede ser negativo."
            )


DEFAULT_ALGORITHM_CONFIG = AlgorithmConfig()
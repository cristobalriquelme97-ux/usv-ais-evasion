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

    # Tiempo durante el cual el algoritmo observa un encuentro
    # give-way antes de ordenar la primera maniobra evasiva.
    maneuver_decision_delay_s: float = 20.0

    # Tiempo mínimo durante el cual un USV stand-on conserva
    # rumbo y velocidad antes de considerar una acción tardía.
    stand_on_action_delay_s: float = 20.0

    # La reducción de velocidad stand-on solo se activa cuando
    # el riesgo persiste y el TCPA entra en esta ventana crítica.
    stand_on_critical_tcpa_s: float = 60.0

    # Fracciones de la velocidad actual evaluadas, desde la opción
    # menos intrusiva hasta la reducción más intensa.
    stand_on_speed_factors: tuple[float, ...] = (
        0.75,
        0.50,
        0.25,
    )

    # Razón máxima de variación de velocidad simulada.
    # Por ejemplo, 0.10 kn/s permite variar 0.5 kn en un paso de 5 s.
    speed_change_rate_kn_s: float = 0.10

    def __post_init__(self) -> None:
        """Valida los valores al crear la configuración."""

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

        if self.stand_on_action_delay_s < 0.0:
            raise ValueError(
                "stand_on_action_delay_s no puede ser negativo."
            )

        if self.stand_on_critical_tcpa_s <= 0.0:
            raise ValueError(
                "stand_on_critical_tcpa_s debe ser mayor que cero."
            )

        if not self.stand_on_speed_factors:
            raise ValueError(
                "stand_on_speed_factors debe contener al menos un valor."
            )

        if any(
            factor <= 0.0 or factor >= 1.0
            for factor in self.stand_on_speed_factors
        ):
            raise ValueError(
                "Cada factor de velocidad stand-on debe estar entre 0 y 1."
            )

        if self.speed_change_rate_kn_s <= 0.0:
            raise ValueError(
                "speed_change_rate_kn_s debe ser mayor que cero."
            )


DEFAULT_ALGORITHM_CONFIG = AlgorithmConfig()
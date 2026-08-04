from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AlgorithmConfig:
    """Parámetros internos utilizados por el algoritmo de evasión."""

    # Radio mínimo exigido para considerar una ejecución segura.
    safety_radius_m: float = 50.0

    # Horizonte empleado por CPA/TCPA y por las simulaciones candidatas.
    time_horizon_s: float = 200.0

    # Antigüedad máxima de un contacto AIS antes de eliminarlo.
    tracker_max_age_s: float = 60.0

    # Tolerancia para considerar recuperado el rumbo original.
    route_recovery_tolerance_deg: float = 3.0

    # Las maniobras give-way se ejecutan sin retardo artificial.
    maneuver_decision_delay_s: float = 0.0

    # Tiempo mínimo para confirmar que el blanco obligado a maniobrar
    # no ha cambiado apreciablemente su COG/SOG. Con AIS cada 5 s,
    # 10 s permiten observar las muestras de t=0, t=5 y t=10 s.
    stand_on_action_delay_s: float = 10.0

    # Ventana en la que se autoriza la acción tardía del stand-on.
    stand_on_critical_tcpa_s: float = 90.0

    # Número de muestras consecutivas requeridas para considerar que
    # el contacto no está adoptando una acción efectiva.
    stand_on_confirmation_samples_required: int = 3

    # Variaciones mínimas consideradas como maniobra del contacto.
    stand_on_course_change_threshold_deg: float = 5.0
    stand_on_speed_change_threshold_kn: float = 0.5

    # La velocidad reducida se conserva hasta que el contacto haya
    # pasado el CPA, se aleje y supere esta distancia durante tres muestras.
    stand_on_recovery_distance_m: float = 100.0

    # Reducciones candidatas. Se conserva el 10 % que agregaste.
    stand_on_speed_factors: tuple[float, ...] = (
        0.75,
        0.50,
        0.25,
        0.10,
    )

    # La disminución de velocidad es instantánea en motion_model.py.
    # Este valor controla la recuperación gradual de velocidad.
    speed_change_rate_kn_s: float = 0.10

    def __post_init__(self) -> None:
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

        if not self.stand_on_speed_factors:
            raise ValueError(
                "stand_on_speed_factors debe contener al menos un valor."
            )

        if any(
            factor <= 0.0 or factor >= 1.0
            for factor in self.stand_on_speed_factors
        ):
            raise ValueError(
                "Cada factor stand-on debe estar entre 0 y 1."
            )

        if self.speed_change_rate_kn_s <= 0.0:
            raise ValueError(
                "speed_change_rate_kn_s debe ser mayor que cero."
            )


DEFAULT_ALGORITHM_CONFIG = AlgorithmConfig()
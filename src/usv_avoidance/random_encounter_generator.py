from __future__ import annotations

import math
import random
from dataclasses import dataclass


KNOT_TO_MPS = 0.514444
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class RandomEncounterConfig:
    """Configuración del generador cinemático independiente."""

    area_radius_m: float = 1000.0
    min_initial_distance_m: float = 100.0
    safety_radius_m: float = 50.0

    usv_speed_min_kn: float = 4.0
    usv_speed_max_kn: float = 8.0
    target_speed_min_kn: float = 2.0
    target_speed_max_kn: float = 10.0

    duration_s: float = 200.0
    propagation_step_s: float = 0.5

    def __post_init__(self) -> None:
        if self.area_radius_m <= 0.0:
            raise ValueError("area_radius_m debe ser mayor que cero.")
        if self.min_initial_distance_m < 0.0:
            raise ValueError(
                "min_initial_distance_m no puede ser negativo."
            )
        if self.min_initial_distance_m >= self.area_radius_m:
            raise ValueError(
                "min_initial_distance_m debe ser menor que area_radius_m."
            )
        if self.safety_radius_m <= 0.0:
            raise ValueError("safety_radius_m debe ser mayor que cero.")
        if self.min_initial_distance_m <= self.safety_radius_m:
            raise ValueError(
                "min_initial_distance_m debe ser mayor que "
                "safety_radius_m para evitar casos inicialmente violados."
            )
        if self.usv_speed_min_kn < 0.0:
            raise ValueError("usv_speed_min_kn no puede ser negativo.")
        if self.usv_speed_max_kn <= self.usv_speed_min_kn:
            raise ValueError(
                "usv_speed_max_kn debe superar a usv_speed_min_kn."
            )
        if self.target_speed_min_kn < 0.0:
            raise ValueError("target_speed_min_kn no puede ser negativo.")
        if self.target_speed_max_kn <= self.target_speed_min_kn:
            raise ValueError(
                "target_speed_max_kn debe superar a target_speed_min_kn."
            )
        if self.duration_s <= 0.0:
            raise ValueError("duration_s debe ser mayor que cero.")
        if self.propagation_step_s <= 0.0:
            raise ValueError(
                "propagation_step_s debe ser mayor que cero."
            )


@dataclass(frozen=True)
class RandomEncounterCandidate:
    """Condiciones iniciales completamente aleatorias de un encuentro."""

    usv_sog_kn: float
    usv_cog_deg: float

    target_x0_m: float
    target_y0_m: float
    target_sog_kn: float
    target_cog_deg: float

    initial_distance_m: float
    initial_true_bearing_deg: float
    initial_relative_bearing_deg: float


@dataclass(frozen=True)
class BaselineResult:
    """Resultado de propagar ambas embarcaciones sin evasión."""

    minimum_distance_m: float
    time_at_minimum_s: float
    safety_radius_violated: bool


def normalize_angle_360(angle_deg: float) -> float:
    return angle_deg % 360.0


def normalize_angle_signed(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


def velocity_xy_mps(
    speed_kn: float,
    course_deg: float,
) -> tuple[float, float]:
    """
    Convierte SOG/COG en componentes Este-Norte.

    Convención náutica:
    0° norte, 90° este, 180° sur y 270° oeste.
    """

    speed_mps = float(speed_kn) * KNOT_TO_MPS
    course_rad = math.radians(float(course_deg))

    east_mps = speed_mps * math.sin(course_rad)
    north_mps = speed_mps * math.cos(course_rad)

    return east_mps, north_mps


def generate_random_candidate(
    rng: random.Random,
    config: RandomEncounterConfig,
) -> RandomEncounterCandidate:
    """
    Genera una configuración sin imponer CPA, TCPA o familia RIPA.

    El blanco se distribuye uniformemente por área dentro de un anillo
    circular. El USV permanece en el origen, pero su rumbo y velocidad
    también se generan aleatoriamente.
    """

    usv_sog_kn = rng.uniform(
        config.usv_speed_min_kn,
        config.usv_speed_max_kn,
    )
    usv_cog_deg = rng.uniform(0.0, 360.0)

    target_sog_kn = rng.uniform(
        config.target_speed_min_kn,
        config.target_speed_max_kn,
    )
    target_cog_deg = rng.uniform(0.0, 360.0)

    angle_rad = rng.uniform(0.0, 2.0 * math.pi)

    # Muestreo uniforme por área dentro de un anillo circular.
    radius_squared = rng.uniform(
        config.min_initial_distance_m**2,
        config.area_radius_m**2,
    )
    radius_m = math.sqrt(radius_squared)

    target_x0_m = radius_m * math.sin(angle_rad)
    target_y0_m = radius_m * math.cos(angle_rad)

    true_bearing_deg = normalize_angle_360(
        math.degrees(math.atan2(target_x0_m, target_y0_m))
    )
    relative_bearing_deg = normalize_angle_signed(
        true_bearing_deg - usv_cog_deg
    )

    return RandomEncounterCandidate(
        usv_sog_kn=usv_sog_kn,
        usv_cog_deg=usv_cog_deg,
        target_x0_m=target_x0_m,
        target_y0_m=target_y0_m,
        target_sog_kn=target_sog_kn,
        target_cog_deg=target_cog_deg,
        initial_distance_m=radius_m,
        initial_true_bearing_deg=true_bearing_deg,
        initial_relative_bearing_deg=relative_bearing_deg,
    )


def simulate_independent_baseline(
    candidate: RandomEncounterCandidate,
    config: RandomEncounterConfig,
) -> BaselineResult:
    """
    Propaga directamente las posiciones sin utilizar CPA/TCPA.

    Ningún módulo matemático o clasificador del algoritmo evaluado
    interviene en esta comprobación.
    """

    own_vx, own_vy = velocity_xy_mps(
        candidate.usv_sog_kn,
        candidate.usv_cog_deg,
    )
    target_vx, target_vy = velocity_xy_mps(
        candidate.target_sog_kn,
        candidate.target_cog_deg,
    )

    minimum_distance_m = candidate.initial_distance_m
    time_at_minimum_s = 0.0

    total_steps = int(
        math.ceil(config.duration_s / config.propagation_step_s)
    )

    for step in range(total_steps + 1):
        time_s = min(
            step * config.propagation_step_s,
            config.duration_s,
        )

        own_x_m = own_vx * time_s
        own_y_m = own_vy * time_s

        target_x_m = candidate.target_x0_m + target_vx * time_s
        target_y_m = candidate.target_y0_m + target_vy * time_s

        distance_m = math.hypot(
            target_x_m - own_x_m,
            target_y_m - own_y_m,
        )

        if distance_m < minimum_distance_m:
            minimum_distance_m = distance_m
            time_at_minimum_s = time_s

    return BaselineResult(
        minimum_distance_m=minimum_distance_m,
        time_at_minimum_s=time_at_minimum_s,
        safety_radius_violated=(
            minimum_distance_m < config.safety_radius_m
        ),
    )


def xy_to_latlon(
    x_east_m: float,
    y_north_m: float,
    ref_lat_deg: float,
    ref_lon_deg: float,
) -> tuple[float, float]:
    """Convierte coordenadas locales Este-Norte a latitud y longitud."""

    ref_lat_rad = math.radians(ref_lat_deg)
    cos_lat = math.cos(ref_lat_rad)

    if abs(cos_lat) < 1e-12:
        raise ValueError("La latitud de referencia no es válida.")

    lat_deg = ref_lat_deg + math.degrees(
        y_north_m / EARTH_RADIUS_M
    )
    lon_deg = ref_lon_deg + math.degrees(
        x_east_m / (EARTH_RADIUS_M * cos_lat)
    )

    return lat_deg, lon_deg
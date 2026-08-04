from __future__ import annotations

import math
import random
from dataclasses import dataclass

KNOT_TO_MPS = 0.514444
EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class MultishipGenerationConfig:
    area_radius_m: float = 1000.0
    min_initial_distance_m: float = 100.0
    min_intertarget_distance_m: float = 75.0
    safety_radius_m: float = 50.0
    usv_speed_min_kn: float = 4.0
    usv_speed_max_kn: float = 8.0
    target_speed_min_kn: float = 2.0
    target_speed_max_kn: float = 10.0
    duration_s: float = 200.0
    propagation_step_s: float = 0.5
    simultaneity_window_s: float = 60.0
    max_attempts_per_target: int = 20_000

    def __post_init__(self) -> None:
        if not 2 <= self.min_initial_distance_m < self.area_radius_m:
            raise ValueError("Distancias iniciales no válidas.")
        if self.safety_radius_m <= 0.0:
            raise ValueError("safety_radius_m debe ser positivo.")
        if self.min_initial_distance_m <= self.safety_radius_m:
            raise ValueError(
                "min_initial_distance_m debe superar safety_radius_m."
            )
        if self.duration_s <= 0.0 or self.propagation_step_s <= 0.0:
            raise ValueError("Duración y paso deben ser positivos.")
        if self.simultaneity_window_s <= 0.0:
            raise ValueError("simultaneity_window_s debe ser positiva.")
        if self.max_attempts_per_target <= 0:
            raise ValueError("max_attempts_per_target debe ser positivo.")


@dataclass(frozen=True)
class OwnshipInitialState:
    sog_kn: float
    cog_deg: float


@dataclass(frozen=True)
class TargetCandidate:
    target_index: int
    x0_m: float
    y0_m: float
    sog_kn: float
    cog_deg: float
    initial_distance_m: float
    true_bearing_deg: float
    relative_bearing_deg: float


@dataclass(frozen=True)
class TargetBaseline:
    minimum_distance_m: float
    time_at_minimum_s: float
    safety_radius_violated: bool


@dataclass(frozen=True)
class RipaTargetReference:
    evaluable: bool
    encounter: str
    ownship_role: str
    expected_action: str | None
    reason: str


@dataclass(frozen=True)
class MultishipCandidate:
    ownship: OwnshipInitialState
    targets: tuple[TargetCandidate, ...]
    baselines: tuple[TargetBaseline, ...]
    anchor_time_s: float
    attempts_used: int


def normalize_360(angle_deg: float) -> float:
    return angle_deg % 360.0


def normalize_signed(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


def velocity_xy_mps(speed_kn: float, course_deg: float) -> tuple[float, float]:
    speed_mps = float(speed_kn) * KNOT_TO_MPS
    course_rad = math.radians(float(course_deg))
    return (
        speed_mps * math.sin(course_rad),
        speed_mps * math.cos(course_rad),
    )


def _bearing_deg(x_m: float, y_m: float) -> float:
    return normalize_360(math.degrees(math.atan2(x_m, y_m)))


def generate_raw_target(
    rng: random.Random,
    config: MultishipGenerationConfig,
    ownship: OwnshipInitialState,
    target_index: int,
) -> TargetCandidate:
    angle_rad = rng.uniform(0.0, 2.0 * math.pi)
    radius_m = math.sqrt(
        rng.uniform(
            config.min_initial_distance_m**2,
            config.area_radius_m**2,
        )
    )
    x0_m = radius_m * math.sin(angle_rad)
    y0_m = radius_m * math.cos(angle_rad)
    true_bearing_deg = _bearing_deg(x0_m, y0_m)

    return TargetCandidate(
        target_index=target_index,
        x0_m=x0_m,
        y0_m=y0_m,
        sog_kn=rng.uniform(
            config.target_speed_min_kn,
            config.target_speed_max_kn,
        ),
        cog_deg=rng.uniform(0.0, 360.0),
        initial_distance_m=radius_m,
        true_bearing_deg=true_bearing_deg,
        relative_bearing_deg=normalize_signed(
            true_bearing_deg - ownship.cog_deg
        ),
    )


def simulate_target_baseline(
    ownship: OwnshipInitialState,
    target: TargetCandidate,
    config: MultishipGenerationConfig,
) -> TargetBaseline:
    """Propagación directa; no usa CPA/TCPA del algoritmo."""

    own_vx, own_vy = velocity_xy_mps(ownship.sog_kn, ownship.cog_deg)
    target_vx, target_vy = velocity_xy_mps(target.sog_kn, target.cog_deg)

    minimum_distance_m = target.initial_distance_m
    time_at_minimum_s = 0.0
    steps = int(math.ceil(config.duration_s / config.propagation_step_s))

    for index in range(steps + 1):
        time_s = min(index * config.propagation_step_s, config.duration_s)
        own_x_m = own_vx * time_s
        own_y_m = own_vy * time_s
        target_x_m = target.x0_m + target_vx * time_s
        target_y_m = target.y0_m + target_vy * time_s
        distance_m = math.hypot(target_x_m - own_x_m, target_y_m - own_y_m)

        if distance_m < minimum_distance_m:
            minimum_distance_m = distance_m
            time_at_minimum_s = time_s

    return TargetBaseline(
        minimum_distance_m=minimum_distance_m,
        time_at_minimum_s=time_at_minimum_s,
        safety_radius_violated=minimum_distance_m < config.safety_radius_m,
    )


def _far_enough_from_other_targets(
    target: TargetCandidate,
    accepted_targets: list[TargetCandidate],
    minimum_distance_m: float,
) -> bool:
    return all(
        math.hypot(target.x0_m - other.x0_m, target.y0_m - other.y0_m)
        >= minimum_distance_m
        for other in accepted_targets
    )


def generate_multiship_candidate(
    rng: random.Random,
    config: MultishipGenerationConfig,
    target_count: int,
) -> MultishipCandidate:
    """
    Genera 2-4 blancos riesgosos con aproximaciones temporales simultáneas.

    La aceptación se basa exclusivamente en propagación cartesiana directa.
    No importa ni llama CPA/TCPA, geometría o clasificador del algoritmo.
    """

    if target_count < 2 or target_count > 4:
        raise ValueError("target_count debe estar entre 2 y 4.")

    ownship = OwnshipInitialState(
        sog_kn=rng.uniform(config.usv_speed_min_kn, config.usv_speed_max_kn),
        cog_deg=rng.uniform(0.0, 360.0),
    )

    half_window = config.simultaneity_window_s / 2.0
    anchor_min = max(half_window, 30.0)
    anchor_max = min(config.duration_s - half_window, config.duration_s - 10.0)
    if anchor_max <= anchor_min:
        raise ValueError("La ventana de simultaneidad no cabe en la duración.")

    anchor_time_s = rng.uniform(anchor_min, anchor_max)
    accepted_targets: list[TargetCandidate] = []
    accepted_baselines: list[TargetBaseline] = []
    attempts_used = 0

    for target_index in range(1, target_count + 1):
        target_accepted = False

        for _ in range(config.max_attempts_per_target):
            attempts_used += 1
            target = generate_raw_target(rng, config, ownship, target_index)

            if not _far_enough_from_other_targets(
                target,
                accepted_targets,
                config.min_intertarget_distance_m,
            ):
                continue

            baseline = simulate_target_baseline(ownship, target, config)
            simultaneous = abs(baseline.time_at_minimum_s - anchor_time_s) <= half_window

            if baseline.safety_radius_violated and simultaneous:
                accepted_targets.append(target)
                accepted_baselines.append(baseline)
                target_accepted = True
                break

        if not target_accepted:
            raise RuntimeError(
                "No fue posible generar un blanco riesgoso simultáneo. "
                "Aumente --max-attempts-per-target o --simultaneity-window-s."
            )

    return MultishipCandidate(
        ownship=ownship,
        targets=tuple(accepted_targets),
        baselines=tuple(accepted_baselines),
        anchor_time_s=anchor_time_s,
        attempts_used=attempts_used,
    )


def classify_ripa_reference(
    ownship: OwnshipInitialState,
    target: TargetCandidate,
    *,
    boundary_margin_deg: float = 2.5,
) -> RipaTargetReference:
    """Referencia geométrica independiente, aplicada después de generar."""

    own_rel = normalize_signed(target.true_bearing_deg - ownship.cog_deg)
    target_to_own_bearing = normalize_360(target.true_bearing_deg + 180.0)
    target_rel = normalize_signed(target_to_own_bearing - target.cog_deg)
    course_diff = abs(normalize_signed(ownship.cog_deg - target.cog_deg))

    ahead_limit = 10.0
    reciprocal_limit = 165.0
    overtaking_limit = 112.5

    near_boundary = any(
        (
            abs(abs(own_rel) - ahead_limit) <= boundary_margin_deg,
            abs(course_diff - reciprocal_limit) <= boundary_margin_deg,
            abs(abs(own_rel) - overtaking_limit) <= boundary_margin_deg,
            abs(abs(target_rel) - overtaking_limit) <= boundary_margin_deg,
            abs(own_rel) <= boundary_margin_deg,
        )
    )
    if near_boundary:
        return RipaTargetReference(False, "ambiguo", "caution", None, "Límite angular.")

    if abs(own_rel) <= ahead_limit and course_diff >= reciprocal_limit:
        return RipaTargetReference(
            True, "vuelta encontrada", "give_way", "alter_course_starboard", "Cursos recíprocos."
        )

    if abs(target_rel) > overtaking_limit and ownship.sog_kn > target.sog_kn:
        return RipaTargetReference(
            True, "alcance", "give_way", "alter_course_starboard", "USV alcanza al blanco."
        )

    if abs(own_rel) > overtaking_limit and target.sog_kn > ownship.sog_kn:
        return RipaTargetReference(
            True, "alcance por blanco", "stand_on", "maintain_course", "Blanco alcanza al USV."
        )

    if own_rel > 0.0:
        return RipaTargetReference(
            True, "cruce", "give_way", "alter_course_starboard", "Blanco por estribor."
        )

    return RipaTargetReference(
        True, "cruce", "stand_on", "maintain_course", "Blanco por babor."
    )


def xy_to_latlon(
    x_east_m: float,
    y_north_m: float,
    ref_lat_deg: float,
    ref_lon_deg: float,
) -> tuple[float, float]:
    ref_lat_rad = math.radians(ref_lat_deg)
    lat_deg = ref_lat_deg + math.degrees(y_north_m / EARTH_RADIUS_M)
    lon_deg = ref_lon_deg + math.degrees(
        x_east_m / (EARTH_RADIUS_M * math.cos(ref_lat_rad))
    )
    return lat_deg, lon_deg
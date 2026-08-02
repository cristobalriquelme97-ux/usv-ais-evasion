#Ejectuar un escenario de simulación y devolver los resultados en un formato estructurado para la interfaz web.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from usv_avoidance.algorithm_config import (
    AlgorithmConfig,
    DEFAULT_ALGORITHM_CONFIG,
)
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.avoidance import (
    recommend_avoidance_maneuver,
    simulate_course_candidate_against_targets,
)
from usv_avoidance.cpa_tcpa import latlon_to_xy_m
from usv_avoidance.collision_assessment import build_assessments
from usv_avoidance.target_priority import (
    rank_assessments,
    select_most_critical_assessment,
)
from usv_avoidance.motion_model import advance_vessel_state_with_course_command
from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.route_manager import RouteManager
from usv_avoidance.simulation_metrics import SimulationMetrics
from usv_avoidance.state_machine import (
    NavigationStateMachine,
    StateMachineConfig,
)
from usv_avoidance.target_tracker import TargetTracker
from usv_avoidance.replanning import (
    decorate_avoidance_decision,
    determine_replanning_need,
    evaluate_active_evasive_course,
)

from usv_avoidance.scenario_config import (
    DEFAULT_SCENARIO_CONFIG,
    OUTPUT_FILE,
    PROJECT_ROOT,
    SCENARIOS_DIR,
    ScenarioConfig,
)

MANIFEST_PATH = SCENARIOS_DIR / "scenario_manifest.json"


def list_scenarios() -> list[dict[str, Any]]:
    """
    Returns the available scenario metadata for the web interface.
    """

    manifest_scenarios: list[dict[str, Any]] = []

    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("r", encoding="utf-8") as file:
            manifest = json.load(file)

        manifest_scenarios = list(manifest.get("scenarios", []))

    scenarios_by_file = {
        str(item.get("output_file")): dict(item)
        for item in manifest_scenarios
        if item.get("output_file")
    }

    for scenario_file in sorted(SCENARIOS_DIR.glob("*.txt")):
        if scenario_file.name not in scenarios_by_file:
            scenarios_by_file[scenario_file.name] = {
                "name": scenario_file.stem,
                "description": "",
                "output_file": scenario_file.name,
            }

    return sorted(
        scenarios_by_file.values(),
        key=lambda item: str(item.get("name", item.get("output_file", ""))),
    )

def get_scenario_metadata(
    scenario_file: Path,
) -> dict[str, Any]:
    """
    Obtiene los metadatos y resultados esperados de un escenario.

    Si el archivo no se encuentra en el manifiesto, devuelve un
    diccionario vacío. Esto permite ejecutar escenarios de prueba
    o multiblanco que todavía no tengan expectativas definidas.
    """

    for scenario in list_scenarios():
        if scenario.get("output_file") == scenario_file.name:
            return dict(scenario)

    return {}

def resolve_scenario_file(scenario_name: str | None = None) -> Path:
    """
    Resolves a scenario name, stem, or txt filename into an existing file.
    """

    if not scenario_name:
        return Path(OUTPUT_FILE)

    candidate = Path(scenario_name)

    if candidate.suffix != ".txt":
        candidate = candidate.with_suffix(".txt")

    if candidate.parent == Path("."):
        candidate = SCENARIOS_DIR / candidate

    if candidate.exists():
        return candidate

    for item in list_scenarios():
        if scenario_name in {item.get("name"), item.get("output_file")}:
            return SCENARIOS_DIR / str(item["output_file"])

    raise FileNotFoundError(f"No se encontro el escenario: {scenario_name}")


def run_scenario(
    scenario_name: str | None = None,
    save_results: bool = False,
    maneuver_decision_delay_s: float | None = None,
    playback_delay_s: float = 0.0,
    algorithm_config: AlgorithmConfig | None = None,
    scenario_config: ScenarioConfig | None = None,
    expected_encounter: str | None = None,
    expected_ownship_role: str | None = None,
    expected_action: str | None = None,
) -> dict[str, Any]:
    
    """
    Ejecuta el motor principal de simulación del algoritmo.

    Procesa un escenario AIS/NMEA, actualiza los contactos,
    evalúa el riesgo de colisión, administra la máquina de estados,
    calcula las maniobras evasivas y registra las métricas.

    No imprime información directamente en la terminal. Devuelve
    los resultados estructurados para que puedan ser utilizados por
    main.py, la interfaz web, las pruebas o la ejecución batch.
    """

    scenario_file = resolve_scenario_file(scenario_name)
    scenario_stem = scenario_file.stem
    scenario_metadata = get_scenario_metadata(
        scenario_file=scenario_file,
    )

    config = (
        algorithm_config
        if algorithm_config is not None
        else DEFAULT_ALGORITHM_CONFIG
    )

    scenario_cfg = (
        scenario_config
        if scenario_config is not None
        else DEFAULT_SCENARIO_CONFIG
    )

    if maneuver_decision_delay_s is None:
        effective_maneuver_decision_delay_s = (
            config.maneuver_decision_delay_s
        )
    else:
        effective_maneuver_decision_delay_s = float(
            maneuver_decision_delay_s
        )

        if effective_maneuver_decision_delay_s < 0.0:
            raise ValueError(
                "maneuver_decision_delay_s no puede ser negativo."
            )


    source = NmeaFileSource(
        file_path=scenario_file,
        delay_s=max(0.0, playback_delay_s),
    )

    receiver = AisNmeaReceiver(strict_checksum=True)
    tracker = TargetTracker(
    max_age_s=config.tracker_max_age_s,
    )
    state_machine = NavigationStateMachine(
        config=StateMachineConfig(
            maneuver_decision_delay_s=(
                effective_maneuver_decision_delay_s
            ),
        )
    )

    route_manager = RouteManager(
        original_course_deg=scenario_cfg.usv_cog_deg,
        recovery_tolerance_deg=(
            config.route_recovery_tolerance_deg
        ),
    )

    metrics = SimulationMetrics(
        scenario_name=scenario_stem,
        original_course_deg=scenario_cfg.usv_cog_deg,
        safety_radius_m=config.safety_radius_m,
        expected_encounter=(
            expected_encounter
            if expected_encounter is not None
            else scenario_metadata.get("expected_encounter")
        ),
        expected_ownship_role=(
            expected_ownship_role
            if expected_ownship_role is not None
            else scenario_metadata.get("expected_ownship_role")
        ),
        expected_action=(
            expected_action
            if expected_action is not None
            else scenario_metadata.get("expected_action")
        ),
    )

    ownship = {
        "lat": scenario_cfg.usv_lat0,
        "lon": scenario_cfg.usv_lon0,
        "sog_kn": scenario_cfg.usv_sog_kn,
        "cog_deg": scenario_cfg.usv_cog_deg,
        "heading_deg": scenario_cfg.usv_heading_deg,
        "timestamp": 0.0,
    }

    active_evasive_course_deg = None
    active_avoidance_decision = None
    commanded_course_deg = scenario_cfg.usv_cog_deg
    replan_count = 0
    steps: list[dict[str, Any]] = []

    # Se utiliza para calcular el tiempo realmente transcurrido
    # entre dos frames consecutivos.
    previous_timestamp_s: float | None = None


    for frame in source.read_frames(
        default_step_s=scenario_cfg.step_s,
    ):
        # El tiempo de simulación queda determinado por el frame,
        # no por la cantidad de sentencias AIS que contiene.
        ownship["timestamp"] = frame.timestamp_s

        if previous_timestamp_s is None:
            elapsed_s = 0.0
        else:
            elapsed_s = max(
                0.0,
                frame.timestamp_s - previous_timestamp_s,
            )

        previous_timestamp_s = frame.timestamp_s

        # Primero se procesan todas las sentencias correspondientes
        # al mismo instante de simulación.
        for sentence in frame.sentences:
            ais_data = receiver.ingest(sentence)

            if ais_data is None:
                continue

            if not ais_data.get("valid", False):
                continue

            if (
                ais_data.get("lat") is None
                or ais_data.get("lon") is None
            ):
                continue

            tracker.update_from_ais(
                ais_data=ais_data,
                received_at_s=frame.timestamp_s,
            )

        # El mantenimiento del tracker se realiza una sola vez
        # después de actualizar todos los contactos del frame.
        tracker.remove_stale_targets(
            current_time_s=frame.timestamp_s,
        )

        active_targets = tracker.get_active_targets(
            current_time_s=frame.timestamp_s,
        )

        assessments = build_assessments(
            ownship=ownship,
            targets=active_targets,
            return_course_deg=route_manager.get_return_course(),
            safety_radius_m=config.safety_radius_m,
            time_horizon_s=config.time_horizon_s,
        )

        critical_assessment = select_most_critical_assessment(assessments)

        route_recovered = route_manager.is_route_recovered(
            current_course_deg=ownship["cog_deg"],
        )

        return_course_evaluation = None
        global_return_course_safe = False

        if critical_assessment is not None:
            return_course_evaluation = (
                simulate_course_candidate_against_targets(
                    ownship=ownship,
                    primary_target=critical_assessment["target"],
                    targets=active_targets,
                    candidate_course_deg=route_manager.get_return_course(),
                    safety_radius_m=config.safety_radius_m,
                    time_horizon_s=config.time_horizon_s,
                    dt_s=scenario_cfg.step_s,
                    turn_rate_deg_s=scenario_cfg.usv_turn_rate_deg_s,
                )
            )

            global_return_course_safe = bool(
                return_course_evaluation["candidate_is_safe"]
            )

        state_info = state_machine.update(
            assessment=critical_assessment,
            route_recovered=route_recovered,
            current_time_s=frame.timestamp_s,
            global_return_course_safe=global_return_course_safe,
        )

        current_state = state_info["current_state"]
        avoidance_decision = None

        # Se comprueba si el rumbo evasivo actualmente ordenado
        # sigue siendo seguro frente a todos los contactos activos.
        active_course_evaluation = (
            evaluate_active_evasive_course(
                ownship=ownship,
                critical_assessment=critical_assessment,
                targets=active_targets,
                active_evasive_course_deg=(
                    active_evasive_course_deg
                ),
                safety_radius_m=config.safety_radius_m,
                time_horizon_s=config.time_horizon_s,
                dt_s=scenario_cfg.step_s,
                turn_rate_deg_s=(
                    scenario_cfg.usv_turn_rate_deg_s
                ),
            )
        )

        # Se determina si corresponde crear el primer plan,
        # cambiarlo por un nuevo contacto prioritario o recalcularlo
        # porque el rumbo activo dejó de ser seguro.
        replanning_info = determine_replanning_need(
            current_state=current_state,
            critical_assessment=critical_assessment,
            active_evasive_course_deg=(
                active_evasive_course_deg
            ),
            active_avoidance_decision=(
                active_avoidance_decision
            ),
            active_course_evaluation=(
                active_course_evaluation
            ),
        )

        if (
            replanning_info["replan_required"]
            and critical_assessment is not None
        ):
            avoidance_decision = (
                recommend_avoidance_maneuver(
                    ownship=ownship,
                    target=critical_assessment[
                        "target"
                    ],
                    targets=active_targets,
                    classification=(
                        critical_assessment[
                            "classification"
                        ]
                    ),
                    state_info=state_info,
                    safety_radius_m=config.safety_radius_m,
                    time_horizon_s=config.time_horizon_s,
                    dt_s=scenario_cfg.step_s,
                    turn_rate_deg_s=(
                        scenario_cfg.usv_turn_rate_deg_s
                    ),
                )
            )

            if avoidance_decision[
                "maneuver_required"
            ]:
                # El plan inicial no se contabiliza como
                # replanificación. Solo se cuentan los cambios
                # efectuados después de la primera decisión.
                if (
                    replanning_info["trigger"]
                    != "initial_plan"
                ):
                    replan_count += 1

                avoidance_decision = (
                    decorate_avoidance_decision(
                        avoidance_decision,
                        critical_assessment=(
                            critical_assessment
                        ),
                        current_time_s=(
                            frame.timestamp_s
                        ),
                        replanning_info=(
                            replanning_info
                        ),
                        replan_count=replan_count,
                    )
                )

                active_evasive_course_deg = (
                    avoidance_decision[
                        "recommended_course_deg"
                    ]
                )

                active_avoidance_decision = (
                    avoidance_decision
                )

        if current_state == "AVOIDING_TARGET":
            commanded_course_deg = (
                active_evasive_course_deg
                if active_evasive_course_deg is not None
                else ownship["cog_deg"]
            )

        elif current_state == "CLEARING_TARGET":
            if active_evasive_course_deg is not None:
                commanded_course_deg = active_evasive_course_deg

        elif current_state == "RETURNING_TO_TRACK":
            active_evasive_course_deg = None
            active_avoidance_decision = None
            replan_count = 0
            commanded_course_deg = route_manager.get_return_course()

        elif current_state == "TRACKING_ROUTE":
            active_evasive_course_deg = None
            active_avoidance_decision = None
            replan_count = 0
            commanded_course_deg = scenario_cfg.usv_cog_deg

        elif current_state == "ASSESSING_TARGET":
            commanded_course_deg = ownship["cog_deg"]

        metrics.record_step(
            ownship=ownship,
            critical_assessment=critical_assessment,
            assessments=assessments,
            state_info=state_info,
            commanded_course_deg=commanded_course_deg,
            route_recovered=route_recovered,
            dt_s=elapsed_s,
            avoidance_decision=active_avoidance_decision,
            new_avoidance_decision=avoidance_decision,
            replanning_info=replanning_info,
            active_course_evaluation=(
                active_course_evaluation
            ),
        )

        step = _build_step(
            ownship=ownship,
            assessments=assessments,
            ref_lat=scenario_cfg.usv_lat0,
            ref_lon=scenario_cfg.usv_lon0,
            critical_assessment=critical_assessment,
            state_info=state_info,
            commanded_course_deg=commanded_course_deg,
            route_recovered=route_recovered,
            avoidance_decision=(
                active_avoidance_decision
                or avoidance_decision
            ),
            replanning_info=replanning_info,
            active_course_evaluation=(
                active_course_evaluation
            ),
            replan_count=replan_count,
        )
        steps.append(step)

        ownship = advance_vessel_state_with_course_command(
            vessel=ownship,
            commanded_course_deg=commanded_course_deg,
            dt_s=scenario_cfg.step_s,
            turn_rate_deg_s=scenario_cfg.usv_turn_rate_deg_s,
        )

    metric_paths = None

    if save_results:
        results_dir = Path(scenario_file).parent.parent / "results"
        metric_paths = metrics.save(output_dir=results_dir)

    return {
        "scenario": {
            "name": scenario_stem,
            "file": scenario_file.name,
            "path": str(scenario_file),
        },
        "config": {
            "project_root": str(PROJECT_ROOT),
            "safety_radius_m": config.safety_radius_m,
            "time_horizon_s": config.time_horizon_s,
            "tracker_max_age_s": config.tracker_max_age_s,
            "route_recovery_tolerance_deg": (
                config.route_recovery_tolerance_deg
            ),
            "step_s": scenario_cfg.step_s,
            "turn_rate_deg_s": scenario_cfg.usv_turn_rate_deg_s,
            "maneuver_decision_delay_s": (
                effective_maneuver_decision_delay_s
            ),
            "playback_delay_s": max(
                0.0,
                playback_delay_s,
            ),
        },
        "steps": steps,
        "summary": metrics.build_summary(),
        "metric_paths": _stringify_paths(metric_paths),
    }


def _build_step(
    ownship: Mapping[str, Any],
    assessments: list[Mapping[str, Any]],
    ref_lat: float,
    ref_lon: float,
    critical_assessment: Mapping[str, Any] | None,
    state_info: Mapping[str, Any],
    commanded_course_deg: float,
    route_recovered: bool,
    avoidance_decision: Mapping[str, Any] | None,
    replanning_info: Mapping[str, Any],
    active_course_evaluation: Mapping[str, Any] | None,
    replan_count: int,
) -> dict[str, Any]:
    ownship_x_m, ownship_y_m = latlon_to_xy_m(
        lat=float(ownship["lat"]),
        lon=float(ownship["lon"]),
        ref_lat=ref_lat,
        ref_lon=ref_lon,
    )

    targets = []

    ranked_assessments = rank_assessments(
        assessments
    )

    for index, assessment in enumerate(
        ranked_assessments,
        start=1,
    ):
        target = assessment["target"]
        target_x_m, target_y_m = latlon_to_xy_m(
            lat=float(target["lat"]),
            lon=float(target["lon"]),
            ref_lat=ref_lat,
            ref_lon=ref_lon,
        )

        cpa_result = assessment["cpa_result"]
        bearing_info = assessment["bearing_info"]
        classification = assessment["classification"]

        targets.append(
            {
                "priority": index,
                "mmsi": target.get("mmsi"),
                "lat": target.get("lat"),
                "lon": target.get("lon"),
                "x_m": target_x_m,
                "y_m": target_y_m,
                "sog_kn": target.get("sog_kn"),
                "cog_deg": target.get("cog_deg"),
                "heading_deg": target.get("heading_deg"),
                "distance_m": cpa_result.get("distance_m"),
                "cpa_m": cpa_result.get("cpa_m"),
                "tcpa_s": cpa_result.get("tcpa_s"),
                "risk": cpa_result.get("risk"),
                "true_bearing_deg": bearing_info.get("true_bearing_deg"),
                "relative_bearing_deg": bearing_info.get("relative_bearing_deg"),
                "side": bearing_info.get("side"),
                "encounter_type": classification.get("encounter_type"),
                "encounter_name": classification.get("encounter_name"),
                "ownship_role": classification.get("ownship_role"),
                "should_maneuver": classification.get("should_maneuver"),
                "reason": classification.get("reason"),
            }
        )

    critical_mmsi = None

    if critical_assessment is not None:
        critical_mmsi = critical_assessment["target"].get("mmsi")

    active_course_status = None

    if active_course_evaluation is not None:
        active_course_status = {
            "candidate_is_safe": (
                active_course_evaluation[
                    "candidate_is_safe"
                ]
            ),
            "global_min_distance_m": (
                active_course_evaluation[
                    "global_min_distance_m"
                ]
            ),
            "blocking_target_mmsi": (
                active_course_evaluation[
                    "blocking_target_mmsi"
                ]
            ),
            "unsafe_target_mmsi": list(
                active_course_evaluation[
                    "unsafe_target_mmsi"
                ]
            ),
        }    

    return {
        "time_s": ownship.get("timestamp", 0.0),
        "ownship": {
            "lat": ownship.get("lat"),
            "lon": ownship.get("lon"),
            "x_m": ownship_x_m,
            "y_m": ownship_y_m,
            "sog_kn": ownship.get("sog_kn"),
            "cog_deg": ownship.get("cog_deg"),
            "heading_deg": ownship.get("heading_deg"),
        },
        "targets": targets,
        "critical_target_mmsi": critical_mmsi,
        "state": state_info,    
        "commanded_course_deg": commanded_course_deg,
        "route_recovered": route_recovered,
        "avoidance_decision": dict(avoidance_decision)
        if avoidance_decision is not None
        else None,   
        "replanning": dict(replanning_info),
        "replan_count": replan_count,
        "active_course_evaluation": active_course_status,
    }


def _stringify_paths(paths: Mapping[str, Path] | None) -> dict[str, str] | None:
    if paths is None:
        return None

    return {
        key: str(value)
        for key, value in paths.items()
    }

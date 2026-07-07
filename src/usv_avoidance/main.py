import argparse
from pathlib import Path

from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import calculate_bearing_info
from usv_avoidance.encounter_classifier import classify_encounter
from usv_avoidance.target_tracker import TargetTracker
from usv_avoidance.avoidance import recommend_avoidance_maneuver
from usv_avoidance.route_manager import RouteManager
from usv_avoidance.simulation_metrics import SimulationMetrics
from usv_avoidance.motion_model import (
    advance_vessel_state,
    advance_vessel_state_with_course_command,
)

from usv_avoidance.scenario_config import (
    OUTPUT_FILE,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
    USV_COG_DEG,
    USV_HEADING_DEG,
    STEP_S,
    DELAY_S,
    USV_TURN_RATE_DEG_S,
)

from usv_avoidance.state_machine import (
    NavigationStateMachine,
    select_most_critical_assessment,
)


SCENARIOS_DIR = Path(OUTPUT_FILE).parent


def parse_args():
    """
    Lee argumentos desde la terminal.

    Permite ejecutar:
        python -m usv_avoidance.main

        python -m usv_avoidance.main --list-scenarios

        python -m usv_avoidance.main --scenario crossing_starboard_risk_nmea.txt, por ejemplo, para ejecutar un escenario específico.
    """

    parser = argparse.ArgumentParser(
        description="Ejecuta un escenario AIS/NMEA guardado en data/scenarios."
    )

    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Nombre del archivo .txt dentro de data/scenarios.",
    )

    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Lista los escenarios disponibles en data/scenarios.",
    )

    parser.add_argument(
    "--visualize",
    action="store_true",
    help="Muestra una visualización del escenario procesado por main.py.",
    )

    return parser.parse_args()


def list_available_scenarios():
    """
    Muestra en pantalla todos los escenarios .txt disponibles
    dentro de data/scenarios.
    """

    print("\nEscenarios disponibles en data/scenarios:\n")

    scenario_files = sorted(SCENARIOS_DIR.glob("*.txt"))

    if not scenario_files:
        print("No se encontraron archivos .txt en data/scenarios.")
        return

    for scenario_file in scenario_files:
        print(f" - {scenario_file.name}")

    print()


def resolve_scenario_file(scenario_name: str | None) -> Path:
    """
    Determina qué archivo de escenario se va a ejecutar.

    Si no se entrega --scenario, se usa OUTPUT_FILE desde scenario_config.py.

    Si se entrega solo el nombre del archivo, se busca dentro de data/scenarios.
    """

    if scenario_name is None:
        return Path(OUTPUT_FILE)

    scenario_path = Path(scenario_name)

    if scenario_path.parent == Path("."):
        scenario_path = SCENARIOS_DIR / scenario_path

    return scenario_path

def visualize_processed_scenario(usv_history, target_history, scenario_file):
    """
    Visualiza el escenario que ya fue procesado por main.py.

    No genera archivos nuevos.
    No modifica scenario_config.py.
    No sobrescribe OUTPUT_FILE.

    Solo grafica las posiciones que main.py ya calculó y decodificó.
    """

    if not usv_history or not target_history:
        print("No hay datos suficientes para visualizar.")
        return

    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    frames = min(len(usv_history), len(target_history))

    usv_lats = [item["lat"] for item in usv_history[:frames]]
    usv_lons = [item["lon"] for item in usv_history[:frames]]

    target_lats = [item["lat"] for item in target_history[:frames]]
    target_lons = [item["lon"] for item in target_history[:frames]]

    fig, ax = plt.subplots()

    ax.set_title(f"Escenario AIS: {scenario_file.name}")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")

    ax.plot(
        usv_lons,
        usv_lats,
        marker="o",
        label="Trayectoria USV",
    )

    ax.plot(
        target_lons,
        target_lats,
        marker="x",
        label="Trayectoria blanco AIS",
    )

    usv_point, = ax.plot(
        [],
        [],
        marker="o",
        markersize=10,
        label="USV propio",
    )

    target_point, = ax.plot(
        [],
        [],
        marker="x",
        markersize=10,
        label="Blanco AIS",
    )

    time_text = ax.text(
        0.02,
        0.95,
        "",
        transform=ax.transAxes,
    )

    info_text = ax.text(
        0.02,
        0.90,
        "",
        transform=ax.transAxes,
    )

    all_lons = usv_lons + target_lons
    all_lats = usv_lats + target_lats

    lon_margin = (max(all_lons) - min(all_lons)) * 0.2
    lat_margin = (max(all_lats) - min(all_lats)) * 0.2

    if lon_margin == 0:
        lon_margin = 0.001

    if lat_margin == 0:
        lat_margin = 0.001

    ax.set_xlim(min(all_lons) - lon_margin, max(all_lons) + lon_margin)
    ax.set_ylim(min(all_lats) - lat_margin, max(all_lats) + lat_margin)

    ax.grid(True)
    ax.legend()

    def update(frame):
        usv = usv_history[frame]
        target = target_history[frame]

        usv_point.set_data(
            [usv["lon"]],
            [usv["lat"]],
        )

        target_point.set_data(
            [target["lon"]],
            [target["lat"]],
        )

        time_text.set_text(
            f"t = {usv['timestamp']:.1f} s"
        )

        info_text.set_text(
            f"MMSI: {target['mmsi']} | "
            f"CPA: {target['cpa_m']:.2f} m | "
            f"TCPA: {target['tcpa_s']:.2f} s | "
            f"Encuentro: {target['encounter_name']}"
        )

        return usv_point, target_point, time_text, info_text

    animation = FuncAnimation(
        fig,
        update,
        frames=frames,
        interval=500,
        repeat=True,
    )

    plt.show()

def main():
    args = parse_args()

    if args.list_scenarios:
        list_available_scenarios()
        return

    scenario_file = resolve_scenario_file(args.scenario)

    results_dir = Path(scenario_file).parent.parent / "results"

    metrics = SimulationMetrics(
        scenario_name=Path(scenario_file).stem,
        original_course_deg=USV_COG_DEG,
        safety_radius_m=50.0,
    )

    print("=" * 70)
    print(f"Escenario seleccionado: {scenario_file}")
    print("=" * 70)

    source = NmeaFileSource(
        file_path=scenario_file,
        delay_s=DELAY_S,
    )

    receiver = AisNmeaReceiver(strict_checksum=True)
    tracker = TargetTracker(max_age_s=60.0) # Si un blanco no se actualiza en 60 segundos, se considera "stale" y se elimina.
    state_machine = NavigationStateMachine() # Se encarga de evaluar la situación de navegación y decidir si el USV debe maniobrar.

    ownship = {
        "lat": USV_LAT0,
        "lon": USV_LON0,
        "sog_kn": USV_SOG_KN,
        "cog_deg": USV_COG_DEG,
        "heading_deg": USV_HEADING_DEG,
        "timestamp": 0.0,
    }

    route_manager = RouteManager(
        original_course_deg=USV_COG_DEG,
        recovery_tolerance_deg=3.0,
    )

    usv_history = []
    target_history = [] 

    active_evasive_course_deg = None
    active_avoidance_decision = None
    commanded_course_deg = USV_COG_DEG #Rumbo inicial del USV, que se puede modificar si el algoritmo decide maniobrar.

    for sentence in source.read_sentences():
        ais_data = receiver.ingest(sentence)

        if ais_data is None:
            continue

        if not ais_data.get("valid", False):
            print("Sentencia inválida:", ais_data.get("error"))
            continue

        if ais_data.get("lat") is None or ais_data.get("lon") is None:
            print("Mensaje AIS sin posición válida")
            continue

        updated_target = tracker.update_from_ais(
            ais_data=ais_data,
            received_at_s=ownship["timestamp"],
        )

        if updated_target is None:
            print("Mensaje AIS válido, pero sin datos cinemáticos suficientes.")
            continue

        active_targets = tracker.get_active_targets(
            current_time_s=ownship["timestamp"],
        )

        tracker.remove_stale_targets(
            current_time_s=ownship["timestamp"],
        )
        
        assessments = []

        for target in active_targets:
            cpa_result = calculate_cpa_tcpa(
                ownship=ownship,
                target=target,
                safety_radius_m=50.0,
                time_horizon_s=300.0,
            )
        
            bearing_info = calculate_bearing_info(
                ownship=ownship,
                target=target,
            )
        
            classification = classify_encounter(
                ownship=ownship,
                target=target,
                cpa_result=cpa_result,
                bearing_info=bearing_info,
            )

            assessment = {
                "target": target,
                "cpa_result": cpa_result,
                "bearing_info": bearing_info,
                "classification": classification,
            }

            assessments.append(assessment)

            usv_history.append(
                {
                    "lat": ownship["lat"],
                    "lon": ownship["lon"],
                    "sog_kn": ownship["sog_kn"],
                    "cog_deg": ownship["cog_deg"],
                    "heading_deg": ownship["heading_deg"],
                    "timestamp": ownship["timestamp"],
                }
            )

            target_history.append(
                {
                    "mmsi": target["mmsi"],
                    "lat": target["lat"],
                    "lon": target["lon"],
                    "sog_kn": target["sog_kn"],
                    "cog_deg": target["cog_deg"],
                    "heading_deg": target["heading_deg"],
                    "cpa_m": cpa_result["cpa_m"],
                    "tcpa_s": cpa_result["tcpa_s"],
                    "risk": cpa_result["risk"],
                    "encounter_name": classification["encounter_name"],
                }
            )

            print("=" * 70)

            print(
                f"USV | "
                f"t={ownship['timestamp']:.1f} s | "
                f"Lat={ownship['lat']:.6f} | "
                f"Lon={ownship['lon']:.6f} | "
                f"SOG={ownship['sog_kn']} kn | "
                f"COG={ownship['cog_deg']}° | "
                f"HDG={ownship['heading_deg']}°"
            )

            print(
                f"MMSI={target['mmsi']} | "
                f"Lat={target['lat']:.6f} | "
                f"Lon={target['lon']:.6f} | "
                f"SOG={target['sog_kn']} kn | "
                f"COG={target['cog_deg']}°"
            )

            print(
                f"Distancia actual: {cpa_result['distance_m']:.2f} m | "
                f"CPA: {cpa_result['cpa_m']:.2f} m | "
                f"TCPA: {cpa_result['tcpa_s']:.2f} s | "
                f"Riesgo: {cpa_result['risk']}"
            )

            print(
                f"Demarcación verdadera: {bearing_info['true_bearing_deg']:.2f}° | "
                f"Demarcación relativa: {bearing_info['relative_bearing_deg']:.2f}° | "
                f"Sector: {bearing_info['side']}"
            )

            print(
                f"Encuentro: {classification['encounter_name']} | "
                f"Rol USV: {classification['ownship_role']} | "
                f"Debe maniobrar: {classification['should_maneuver']} | "
                f"Motivo: {classification['reason']}"
            )

        critical_assessment = select_most_critical_assessment(assessments)

        route_recovered = route_manager.is_route_recovered(
            current_course_deg=ownship["cog_deg"],
        )

        state_info = state_machine.update(
            assessment=critical_assessment,
            route_recovered=route_recovered,
        )

        current_state = state_info["current_state"]
        avoidance_decision = None

        print("-" * 70)
        print(
            f"Estado algoritmo: {current_state} | "
            f"Blanco activo: {state_info['active_target_mmsi']} | "
            f"Motivo: {state_info['reason']}"
        )

# ------------------------------------------------------------
# 1. Calcular nueva decisión evasiva solo al iniciar evasión
# ------------------------------------------------------------
        if (
            critical_assessment is not None
            and current_state == "AVOIDING_TARGET"
            and active_evasive_course_deg is None
        ):
            avoidance_decision = recommend_avoidance_maneuver(
                ownship=ownship,
                target=critical_assessment["target"],
                classification=critical_assessment["classification"],
                state_info=state_info,
                safety_radius_m=50.0,
                time_horizon_s=300.0,
                dt_s=STEP_S,
                turn_rate_deg_s=USV_TURN_RATE_DEG_S,
            )

            if avoidance_decision["maneuver_required"]:
                active_evasive_course_deg = avoidance_decision["recommended_course_deg"]
                active_avoidance_decision = avoidance_decision

# ------------------------------------------------------------
# 2. Imprimir decisión evasiva solo si fue calculada ahora
# ------------------------------------------------------------
        if avoidance_decision is not None:
            print(
                f"Decisión evasiva: {avoidance_decision['action']} | "
                f"Rumbo recomendado: {avoidance_decision['recommended_course_deg']:.1f}° | "
                f"Caída: {avoidance_decision['course_change_deg']:.1f}° | "
                f"Motivo: {avoidance_decision['reason']}"
            )

# ------------------------------------------------------------
# 3. Definir orden de gobierno según estado del algoritmo
# ------------------------------------------------------------
        if current_state == "AVOIDING_TARGET":
            if active_evasive_course_deg is not None:
                commanded_course_deg = active_evasive_course_deg

                print(
                    f"Orden de gobierno: EVASIÓN | "
                    f"Rumbo ordenado: {commanded_course_deg:.1f}°"
                )
            else:
                commanded_course_deg = ownship["cog_deg"]

                print(
                    f"Orden de gobierno: MANTENER | "
                    f"Rumbo ordenado: {commanded_course_deg:.1f}°"
                )

        elif current_state == "CLEARING_TARGET":
            if active_evasive_course_deg is not None:
                commanded_course_deg = active_evasive_course_deg

                print(
                    f"Orden de gobierno: CONFIRMAR DESPEJE | "
                    f"manteniendo rumbo evasivo: {commanded_course_deg:.1f}°"
                )

        elif current_state == "RETURNING_TO_TRACK":
            active_evasive_course_deg = None
            active_avoidance_decision = None
            commanded_course_deg = route_manager.get_return_course()

            print(
                f"Orden de gobierno: RETORNO A RUTA | "
                f"Rumbo ordenado: {commanded_course_deg:.1f}°"
            )

        elif current_state == "TRACKING_ROUTE":
            active_evasive_course_deg = None
            active_avoidance_decision = None
            commanded_course_deg = USV_COG_DEG

            print(
                f"Orden de gobierno: RUTA NORMAL | "
                f"Rumbo ordenado: {commanded_course_deg:.1f}°"
            )

        elif current_state == "ASSESSING_TARGET":
            commanded_course_deg = ownship["cog_deg"]

            print(
                f"Orden de gobierno: EVALUACIÓN | "
                f"mantener rumbo actual: {commanded_course_deg:.1f}°"
            )

        metrics.record_step(
            ownship=ownship,
            critical_assessment=critical_assessment,
            state_info=state_info,
            commanded_course_deg=commanded_course_deg,
            route_recovered=route_recovered,
            dt_s=STEP_S,
            avoidance_decision=active_avoidance_decision,
        )

        ownship = advance_vessel_state_with_course_command(
            vessel=ownship,
            commanded_course_deg=commanded_course_deg,
            dt_s=STEP_S,
            turn_rate_deg_s=USV_TURN_RATE_DEG_S,
        )

    metric_paths = metrics.save(output_dir=results_dir)

    summary = metrics.build_summary()

    min_distance_text = (
        f"{summary['distancia_minima_m']:.2f} m"
        if summary["distancia_minima_m"] is not None
        else "sin datos"
    )

    min_cpa_text = (
        f"{summary['cpa_minimo_m']:.2f} m"
        if summary["cpa_minimo_m"] is not None
        else "sin datos"
    )

    margen_seguridad_text = (
        f"{summary['margen_seguridad_minimo_m']:.2f} m"
        if summary["margen_seguridad_minimo_m"] is not None
        else "sin datos"
    )

    tiempo_reaccion_text = (
        f"{summary['tiempo_reaccion_s']:.1f} s"
        if summary["tiempo_reaccion_s"] is not None
        else "sin datos"
    )

    print("-" * 70)
    print("Resumen de métricas de simulación:")
    print(f"Escenario: {summary['nombre_escenario']}")
    print(f"Estado final: {summary['estado_final']}")
    print(f"Escenario exitoso: {summary['escenario_exitoso']}")
    print(f"Maniobra seleccionada: {summary['accion_seleccionada']}")
    print(f"Caída seleccionada: {summary['caida_seleccionada_deg']}°")
    print(f"Distancia mínima real: {min_distance_text}")
    print(f"CPA mínimo calculado: {min_cpa_text}")
    print(f"Margen mínimo de seguridad: {margen_seguridad_text}")
    print(f"Violó radio de seguridad: {summary['violo_radio_seguridad']}")
    print(f"Tiempo de reacción: {tiempo_reaccion_text}")
    print(f"Tiempo en evasión: {summary['tiempo_total_evasion_s']:.1f} s")
    print(f"Tiempo en despeje: {summary['tiempo_total_despeje_s']:.1f} s")
    print(f"Tiempo retornando a ruta: {summary['tiempo_total_retorno_ruta_s']:.1f} s")
    print(f"Ruta recuperada después de evasión: {summary['ruta_recuperada_despues_evasion']}")
    print(f"Cambios de estado: {summary['cantidad_cambios_estado']}")
    print(f"Cambios de rumbo ordenado: {summary['cantidad_cambios_rumbo_ordenado']}")
    print(
        "Variación total de rumbo ordenado: "
        f"{summary['variacion_total_rumbo_ordenado_deg']:.1f}°"
    )
    print(f"Historial CSV: {metric_paths['steps_path']}")
    print(f"Resumen JSON: {metric_paths['summary_path']}")

    if args.visualize:
        visualize_processed_scenario(
        usv_history=usv_history,
        target_history=target_history,
        scenario_file=scenario_file,
        )

if __name__ == "__main__":
    main()
import argparse
from pathlib import Path

from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import calculate_bearing_info
from usv_avoidance.encounter_classifier import classify_encounter
from usv_avoidance.motion_model import advance_vessel_state

from usv_avoidance.scenario_config import (
    OUTPUT_FILE,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
    USV_COG_DEG,
    USV_HEADING_DEG,
    STEP_S,
    DELAY_S,
)

SCENARIOS_DIR = Path(OUTPUT_FILE).parent


def parse_args():
    """
    Lee argumentos desde la terminal.

    Permite ejecutar:
        python -m usv_avoidance.main

        python -m usv_avoidance.main --list-scenarios

        python -m usv_avoidance.main --scenario crossing_starboard_risk_nmea.txt
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

    print("=" * 70)
    print(f"Escenario seleccionado: {scenario_file}")
    print("=" * 70)

    source = NmeaFileSource(
        file_path=scenario_file,
        delay_s=DELAY_S,
    )

    receiver = AisNmeaReceiver(strict_checksum=True)

    ownship = {
        "lat": USV_LAT0,
        "lon": USV_LON0,
        "sog_kn": USV_SOG_KN,
        "cog_deg": USV_COG_DEG,
        "heading_deg": USV_HEADING_DEG,
        "timestamp": 0.0,
    }

    usv_history = []
    target_history = [] 

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

        target = {
            "mmsi": ais_data.get("mmsi"),
            "lat": ais_data.get("lat"),
            "lon": ais_data.get("lon"),
            "sog_kn": ais_data.get("sog_kn"),
            "cog_deg": ais_data.get("cog_deg"),
            "heading_deg": ais_data.get("heading_deg"),
        }

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

        ownship = advance_vessel_state(
            vessel=ownship,
            dt_s=STEP_S,
        )

    if args.visualize:
        visualize_processed_scenario(
        usv_history=usv_history,
        target_history=target_history,
        scenario_file=scenario_file,
        )

if __name__ == "__main__":
    main()
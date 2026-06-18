from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.cpa_tcpa import calculate_cpa_tcpa
from usv_avoidance.encounter_geometry import calculate_bearing_info

from usv_avoidance.scenario_config import (
    OUTPUT_FILE,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
    USV_COG_DEG,
    USV_HEADING_DEG,
)


def main():
    source = NmeaFileSource(
        file_path=OUTPUT_FILE,
        delay_s=0.5,
    )

    receiver = AisNmeaReceiver(strict_checksum=True)

    ownship = {
        "lat": USV_LAT0,
        "lon": USV_LON0,
        "sog_kn": USV_SOG_KN,
        "cog_deg": USV_COG_DEG,
        "heading_deg": USV_HEADING_DEG,
    }

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
        
        print("=" * 70)
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
            f"Demarcación relativa: {bearing_info['relative_bearing_360_deg']:.2f}° | "
            f"Sector: {bearing_info['side']}"
        )


if __name__ == "__main__":
    main()
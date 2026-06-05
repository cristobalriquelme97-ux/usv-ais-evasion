from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.ais_adapter import AisNmeaReceiver


def main():
    source = NmeaFileSource(
        file_path="data/scenarios/crossing_scenario_nmea.txt",
        delay_s=0.5
    )

    receiver = AisNmeaReceiver(strict_checksum=True)

    for sentence in source.read_sentences():
        ais_data = receiver.ingest(sentence)

        if ais_data is None:
            continue

        if not ais_data.get("valid", False):
            print("Sentencia inválida")
            continue

        print(
            f"MMSI={ais_data['mmsi']} | "
            f"Lat={ais_data['lat']} | "
            f"Lon={ais_data['lon']} | "
            f"SOG={ais_data['sog_kn']} kn | "
            f"COG={ais_data['cog_deg']}°"
        )


if __name__ == "__main__":
    main()
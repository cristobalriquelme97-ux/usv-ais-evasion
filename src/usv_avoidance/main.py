from usv_avoidance.ais_adapter import AisNmeaReceiver


def main():
    receiver = AisNmeaReceiver(strict_checksum=True)

    with open("data/sample_nmea.txt", "r", encoding="utf-8") as file:
        for line in file:
            result = receiver.ingest(line)

            if result is None:
                continue

            print(result)


if __name__ == "__main__":
    main()
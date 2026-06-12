import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from usv_avoidance.ais_type1_generator import generate_moving_target_scenario, move_position
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.nmea_file_source import NmeaFileSource

from usv_avoidance.scenario_config import (
    OUTPUT_FILE,
    TARGET_MMSI,
    TARGET_LAT0,
    TARGET_LON0,
    TARGET_SOG_KN,
    TARGET_COG_DEG,
    TARGET_HEADING_DEG,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
    USV_COG_DEG,
    DURATION_S,
    STEP_S,
)


def generate_ais_file() -> None:
    """
    Genera el archivo de sentencias AIS/NMEA del blanco móvil.

    De esta forma, cada vez que ejecutes el visualizador,
    se genera nuevamente el archivo crossing_scenario_nmea.txt
    usando los datos de scenario_config.py.
    """

    generate_moving_target_scenario(
        output_file=OUTPUT_FILE,
        mmsi=TARGET_MMSI,
        lat0=TARGET_LAT0,
        lon0=TARGET_LON0,
        sog_kn=TARGET_SOG_KN,
        cog_deg=TARGET_COG_DEG,
        heading_deg=TARGET_HEADING_DEG,
        duration_s=DURATION_S,
        step_s=STEP_S,
    )


def read_target_positions_from_nmea(file_path):
    """
     Lee el archivo AIS/NMEA generado y decodifica cada sentencia
    usando el adaptador AIS existente.

    Este método utiliza AisNmeaReceiver, por lo tanto no queda limitado
    exclusivamente a una función llamada decode_aivdm_type1.

    Retorna:
    - tiempos
    - latitudes del blanco
    - longitudes del blanco
    - datos decodificados completos
    """
    source = NmeaFileSource(
        file_path=file_path,
        delay_s=0.0,
    )

    receiver = AisNmeaReceiver(strict_checksum=True)

    times = []
    lats = []
    lons = []
    decoded_messages = []

    for index, sentence in enumerate(source.read_sentences()):

            decoded = receiver.ingest(sentence)

            # Si el mensaje es multifragmento, puede retornar None
            # hasta que tenga todos los fragmentos.
            if decoded is None:
                continue

            # Si el adaptador detecta un error, se muestra y se omite.
            if not decoded.get("valid", False):
                print("Mensaje AIS inválido:", decoded.get("error"))
                continue

            # El visualizador necesita posición.
            # Por ahora graficamos solo mensajes que traigan lat/lon.
            lat = decoded.get("lat")
            lon = decoded.get("lon")

            if lat is None or lon is None:
                continue

            decoded_messages.append(decoded)
            times.append(index * STEP_S)
            lats.append(lat)
            lons.append(lon)

    return times, lats, lons, decoded_messages
    #Con eso, el visualizador ya no abre directamente el archivo, 
    #sino que consume una fuente NMEA. Eso se parece más a una recepción real.

def simulate_usv_positions(
    lat0: float,
    lon0: float,
    sog_kn: float,
    cog_deg: float,
    duration_s: int,
    step_s: int,
):
    """
    Simula el movimiento del USV propio.

    Por ahora el USV se define con posición inicial, velocidad y curso.
    Más adelante, estos datos deberían venir desde el GPS, CubePilot,
    Mission Planner o telemetría real del prototipo.
    """

    times = []
    lats = []
    lons = []

    lat = lat0
    lon = lon0

    for t in range(0, duration_s + 1, step_s):
        times.append(t)
        lats.append(lat)
        lons.append(lon)

        lat, lon = move_position(
            lat=lat,
            lon=lon,
            sog_kn=sog_kn,
            cog_deg=cog_deg,
            delta_t_s=step_s,
        )

    return times, lats, lons


def main():
    """
    Función principal del visualizador.

    Flujo:
    1. Genera sentencias AIS simuladas del blanco móvil.
    2. Usa NmeaFileSource para leerlas secuencialmente.
    3. Usa AisNmeaReceiver para decodificarlas.
    4. Simula la trayectoria del USV propio.
    5. Muestra ambos movimientos en una animación.
    """

    generate_ais_file()

    target_times, target_lats, target_lons, decoded_messages = read_target_positions_from_nmea(
        OUTPUT_FILE
    )

    usv_times, usv_lats, usv_lons = simulate_usv_positions(
        lat0=USV_LAT0,
        lon0=USV_LON0,
        sog_kn=USV_SOG_KN,
        cog_deg=USV_COG_DEG,
        duration_s=DURATION_S,
        step_s=STEP_S,
    )

    frames = min(len(usv_times), len(target_times))

    fig, ax = plt.subplots()

    ax.set_title("Visualizador AIS: USV propio y blanco móvil")
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
        label="Trayectoria blanco AIS decodificado",
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
        """
        Actualiza la posición del USV y del blanco AIS en cada instante.
        """

        usv_point.set_data(
            [usv_lons[frame]],
            [usv_lats[frame]],
        )

        target_point.set_data(
            [target_lons[frame]],
            [target_lats[frame]],
        )

        decoded = decoded_messages[frame]

        time_text.set_text(f"t = {target_times[frame]} s")

        info_text.set_text(
            f"MMSI: {decoded['mmsi']} | "
            f"SOG: {decoded['sog_kn']} kn | "
            f"COG: {decoded['cog_deg']}°"
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


if __name__ == "__main__":
    main()
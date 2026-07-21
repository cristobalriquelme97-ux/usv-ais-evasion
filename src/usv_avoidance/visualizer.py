"""
Visualizador temporal para generar una figura académica del movimiento
del USV YAGAN y un blanco AIS decodificado.

Ejecución recomendada desde la raíz del repositorio:
    python -m usv_avoidance.visualizer_thesis

Controles:
    Espacio : pausar/reanudar la animación
    S       : guardar el cuadro actual en PNG a 300 dpi
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.ais_type1_generator import generate_moving_target_scenario
from usv_avoidance.motion_model import advance_position
from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.scenario_config import (
    DURATION_S,
    OUTPUT_FILE,
    STEP_S,
    TARGET_COG_DEG,
    TARGET_HEADING_DEG,
    TARGET_LAT0,
    TARGET_LON0,
    TARGET_MMSI,
    TARGET_SOG_KN,
    USV_COG_DEG,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIGURES_DIR = PROJECT_ROOT / "data" / "figures"
CAPTURE_TIME_S = 100


def generate_ais_file() -> None:
    """Genera las sentencias AIS/NMEA del blanco móvil."""
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


def read_target_positions(file_path: Path):
    """Lee y decodifica las sentencias del blanco AIS."""
    source = NmeaFileSource(file_path=file_path, delay_s=0.0)
    receiver = AisNmeaReceiver(strict_checksum=True)

    times: list[float] = []
    lats: list[float] = []
    lons: list[float] = []
    decoded_messages: list[dict] = []

    for index, sentence in enumerate(source.read_sentences()):
        decoded = receiver.ingest(sentence)

        if decoded is None or not decoded.get("valid", False):
            continue

        lat = decoded.get("lat")
        lon = decoded.get("lon")
        if lat is None or lon is None:
            continue

        times.append(index * STEP_S)
        lats.append(float(lat))
        lons.append(float(lon))
        decoded_messages.append(decoded)

    if not decoded_messages:
        raise RuntimeError("No se obtuvieron mensajes AIS válidos con posición.")

    return times, lats, lons, decoded_messages


def simulate_usv_positions():
    """Simula el movimiento rectilíneo del USV propio."""
    times: list[float] = []
    lats: list[float] = []
    lons: list[float] = []

    lat = USV_LAT0
    lon = USV_LON0

    for t in range(0, DURATION_S + 1, STEP_S):
        times.append(t)
        lats.append(lat)
        lons.append(lon)

        lat, lon = advance_position(
            lat=lat,
            lon=lon,
            sog_kn=USV_SOG_KN,
            cog_deg=USV_COG_DEG,
            dt_s=STEP_S,
        )

    return times, lats, lons


def add_margin(
    values: list[float],
    proportion: float = 0.08,
) -> tuple[float, float]:
    """Agrega un margen proporcional a un conjunto de coordenadas."""
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum

    # Margen mínimo en grados para evitar límites idénticos.
    margin = max(span * proportion, 0.00005)
    return minimum - margin, maximum + margin


def main() -> None:
    generate_ais_file()

    target_times, target_lats, target_lons, decoded_messages = (
        read_target_positions(OUTPUT_FILE)
    )
    usv_times, usv_lats, usv_lons = simulate_usv_positions()

    frames = min(len(target_times), len(usv_times))
    target_times = target_times[:frames]
    target_lats = target_lats[:frames]
    target_lons = target_lons[:frames]
    decoded_messages = decoded_messages[:frames]
    usv_times = usv_times[:frames]
    usv_lats = usv_lats[:frames]
    usv_lons = usv_lons[:frames]

    # Para esta visualización se emplean directamente las coordenadas
    # geográficas decodificadas: longitud en el eje X y latitud en el eje Y.
    usv_x = usv_lons
    usv_y = usv_lats
    target_x = target_lons
    target_y = target_lats

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FIGURES_DIR / "figura_6_3_movimiento_usv_blanco_ais.png"

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.canvas.manager.set_window_title(
        "Verificación visual del adaptador AIS/NMEA"
    )

    ax.set_title(
        "Trayectoria del USV YAGAN y blanco AIS",
        pad=14,
    )
    ax.set_xlabel("Longitud [°]")
    ax.set_ylabel("Latitud [°]")
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.ticklabel_format(
        axis="both",
        style="plain",
        useOffset=False,
    )

    all_x = usv_x + target_x
    all_y = usv_y + target_y
    ax.set_xlim(*add_margin(all_x, proportion=0.08))
    ax.set_ylim(*add_margin(all_y, proportion=0.08))

    # Trayectorias completas de referencia.
    ax.plot(
        usv_x,
        usv_y,
        linestyle=":",
        linewidth=1.2,
        label="Trayectoria prevista del USV YAGAN",
    )
    ax.plot(
        target_x,
        target_y,
        linestyle=":",
        linewidth=1.2,
        label=f"Trayectoria AIS decodificada (MMSI {TARGET_MMSI})",
    )

    # Puntos iniciales.
    ax.plot(usv_x[0], usv_y[0], marker="s", markersize=7)
    ax.annotate(
        "Inicio USV",
        (usv_x[0], usv_y[0]),
        xytext=(7, 7),
        textcoords="offset points",
    )

    ax.plot(target_x[0], target_y[0], marker="s", markersize=7)
    ax.annotate(
        "Inicio blanco",
        (target_x[0], target_y[0]),
        xytext=(-25, -20),
        textcoords="offset points",
    )

    # Elementos animados.
    usv_trace, = ax.plot([], [], linewidth=2.2, label="Recorrido USV")
    target_trace, = ax.plot([], [], linewidth=2.2, label="Recorrido blanco AIS")
    usv_point, = ax.plot([], [], marker="^", markersize=11)
    target_point, = ax.plot([], [], marker="X", markersize=10)

    info_text = ax.text(
        0.02,
        0.98,
        "",
        transform=ax.transAxes,
        va="top",
        family="monospace",
    )

    ax.legend(loc="best")
    fig.tight_layout()

    state = {"frame": 0, "paused": False}

    def update(frame: int):
        state["frame"] = frame

        usv_trace.set_data(usv_x[: frame + 1], usv_y[: frame + 1])
        target_trace.set_data(
            target_x[: frame + 1], target_y[: frame + 1]
        )

        usv_point.set_data([usv_x[frame]], [usv_y[frame]])
        target_point.set_data([target_x[frame]], [target_y[frame]])

        decoded = decoded_messages[frame]
        info_text.set_text(
            f"t = {target_times[frame]:.0f} s\n"
            f"USV YAGAN: SOG {USV_SOG_KN:.1f} kn | "
            f"COG {USV_COG_DEG:.1f}°\n"
            f"Blanco AIS: SOG {decoded['sog_kn']:.1f} kn | "
            f"COG {decoded['cog_deg']:.1f}°"
        )

        return usv_trace, target_trace, usv_point, target_point, info_text

    animation = FuncAnimation(
        fig,
        update,
        frames=frames,
        interval=350,
        repeat=True,
        blit=False,
    )

    def save_current_frame() -> None:
        fig.savefig(output_path, dpi=300, bbox_inches="tight")
        print(f"Figura guardada en: {output_path}")

    def on_key(event) -> None:
        if event.key == " ":
            if state["paused"]:
                animation.event_source.start()
            else:
                animation.event_source.stop()
            state["paused"] = not state["paused"]

        elif event.key and event.key.lower() == "s":
            save_current_frame()

    fig.canvas.mpl_connect("key_press_event", on_key)

    # Genera automáticamente una captura limpia en el instante seleccionado.
    capture_index = min(
        range(frames),
        key=lambda index: abs(target_times[index] - CAPTURE_TIME_S),
    )
    update(capture_index)
    save_current_frame()

    # La ventana comienza desde el primer instante.
    update(0)
    plt.show()


if __name__ == "__main__":
    main()
"""
Genera una figura estática para el apartado 9.2 del Capítulo IX.

La figura representa la configuración inicial y las trayectorias nominales
proyectadas de un escenario RIPA, sin mostrar todavía la maniobra evasiva.

Ejecución desde la raíz del repositorio:
    python -m usv_avoidance.visualizer_figure_9_2

También puede seleccionarse otro escenario representativo:
    python -m usv_avoidance.visualizer_figure_9_2 --scenario crossing_starboard_risk
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from usv_avoidance.algorithm_config import DEFAULT_ALGORITHM_CONFIG
from usv_avoidance.ais_adapter import AisNmeaReceiver
from usv_avoidance.cpa_tcpa import (
    calculate_cpa_tcpa,
    latlon_to_xy_m,
    velocity_components,
)
from usv_avoidance.generate_representative_scenarios import (
    REPRESENTATIVE_SCENARIOS,
    generate_all_representative_scenarios,
)
from usv_avoidance.nmea_file_source import NmeaFileSource
from usv_avoidance.scenario_config import (
    DURATION_S,
    PROJECT_ROOT,
    SCENARIOS_DIR,
    STEP_S,
    USV_COG_DEG,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
)

FIGURES_DIR = PROJECT_ROOT / "data" / "figures"
DEFAULT_SCENARIO_NAME = "head_on_risk"
MB2_SCENARIO_NAME = "MB-2"

MB2_SCENARIO_FILE = (
    SCENARIOS_DIR / "multitarget_MB2_TCPA_priority.txt"
)


def get_scenario(name: str):
    """Busca un escenario representativo por su nombre interno."""
    for scenario in REPRESENTATIVE_SCENARIOS:
        if scenario.name == name:
            return scenario

    available = ", ".join(item.name for item in REPRESENTATIVE_SCENARIOS)
    raise ValueError(
        f"Escenario desconocido: {name}. Disponibles: {available}"
    )


def read_initial_target_state(scenario) -> dict:
    """Obtiene el primer estado válido desde el archivo AIS/NMEA decodificado."""
    scenario_file = SCENARIOS_DIR / f"{scenario.name}_nmea.txt"

    if not scenario_file.exists():
        generate_all_representative_scenarios()

    source = NmeaFileSource(file_path=scenario_file, delay_s=0.0)
    receiver = AisNmeaReceiver(strict_checksum=True)

    for sentence in source.read_sentences():
        decoded = receiver.ingest(sentence)
        if decoded is None or not decoded.get("valid", False):
            continue
        if decoded.get("lat") is None or decoded.get("lon") is None:
            continue
        if decoded.get("sog_kn") is None or decoded.get("cog_deg") is None:
            continue
        return {
            "mmsi": int(decoded["mmsi"]),
            "lat": float(decoded["lat"]),
            "lon": float(decoded["lon"]),
            "sog_kn": float(decoded["sog_kn"]),
            "cog_deg": float(decoded["cog_deg"]),
        }

    raise RuntimeError(
        f"No se obtuvo un estado AIS válido desde {scenario_file}."
    )

def read_initial_target_states(
    scenario_file: Path,
) -> list[dict]:
    """
    Decodifica todos los contactos AIS contenidos en el primer frame.

    Esta función se utiliza para escenarios multibuque.
    """

    if not scenario_file.exists():
        raise FileNotFoundError(
            f"No existe el escenario multibuque: {scenario_file}\n"
            "Ejecute primero:\n"
            "python -m "
            "usv_avoidance.generate_multitarget_mb2_sources"
        )

    source = NmeaFileSource(
        file_path=scenario_file,
        delay_s=0.0,
    )

    receiver = AisNmeaReceiver(
        strict_checksum=True,
    )

    first_frame = next(
        source.read_frames(default_step_s=STEP_S),
        None,
    )

    if first_frame is None:
        raise RuntimeError(
            f"El archivo no contiene frames AIS: {scenario_file}"
        )

    targets_by_mmsi: dict[int, dict] = {}

    for sentence in first_frame.sentences:
        decoded = receiver.ingest(sentence)

        if decoded is None:
            continue

        if not decoded.get("valid", False):
            continue

        required_values = (
            decoded.get("mmsi"),
            decoded.get("lat"),
            decoded.get("lon"),
            decoded.get("sog_kn"),
            decoded.get("cog_deg"),
        )

        if any(value is None for value in required_values):
            continue

        mmsi = int(decoded["mmsi"])

        targets_by_mmsi[mmsi] = {
            "mmsi": mmsi,
            "lat": float(decoded["lat"]),
            "lon": float(decoded["lon"]),
            "sog_kn": float(decoded["sog_kn"]),
            "cog_deg": float(decoded["cog_deg"]),
        }

    targets = list(targets_by_mmsi.values())
    targets.sort(key=lambda item: item["mmsi"])

    if len(targets) < 2:
        raise RuntimeError(
            "El escenario MB-2 debe contener al menos dos "
            f"contactos en el primer frame. Detectados: {len(targets)}"
        )

    return targets

def build_states(scenario):
    """Construye el estado del USV y decodifica el estado inicial del contacto."""
    ownship = {
        "lat": USV_LAT0,
        "lon": USV_LON0,
        "sog_kn": USV_SOG_KN,
        "cog_deg": USV_COG_DEG,
    }
    target = read_initial_target_state(scenario)
    return ownship, target


def projected_position(
    x0: float,
    y0: float,
    sog_kn: float,
    cog_deg: float,
    time_s: float,
) -> tuple[float, float]:
    """Proyecta una posición local usando movimiento rectilíneo uniforme."""
    vx, vy = velocity_components(sog_kn=sog_kn, cog_deg=cog_deg)
    return x0 + vx * time_s, y0 + vy * time_s


def add_heading_arrow(
    ax,
    x: float,
    y: float,
    sog_kn: float,
    cog_deg: float,
    line,
    scale_s: float = 25.0,
) -> None:
    """Dibuja una flecha de COG usando el mismo color de la trayectoria."""
    vx, vy = velocity_components(sog_kn=sog_kn, cog_deg=cog_deg)
    ax.annotate(
        "",
        xy=(x + vx * scale_s, y + vy * scale_s),
        xytext=(x, y),
        arrowprops={
            "arrowstyle": "-|>",
            "linewidth": 2.0,
            "color": line.get_color(),
        },
    )

def make_mb2_figure(
    output_path: Path | None = None,
) -> Path:
    """
    Genera la configuración geométrica inicial del escenario MB-2.

    Se muestran:
    - USV;
    - dos contactos AIS;
    - trayectorias nominales;
    - CPA y TCPA inicial de cada contacto;
    - contacto prioritario por menor TCPA positivo;
    - radio de seguridad.
    """

    ownship = {
        "lat": USV_LAT0,
        "lon": USV_LON0,
        "sog_kn": USV_SOG_KN,
        "cog_deg": USV_COG_DEG,
    }

    targets = read_initial_target_states(
        MB2_SCENARIO_FILE
    )

    config = DEFAULT_ALGORITHM_CONFIG

    contacts: list[dict] = []

    for target in targets:
        cpa = calculate_cpa_tcpa(
            ownship=ownship,
            target=target,
            safety_radius_m=config.safety_radius_m,
            time_horizon_s=config.time_horizon_s,
        )

        target_x0, target_y0 = latlon_to_xy_m(
            lat=target["lat"],
            lon=target["lon"],
            ref_lat=ownship["lat"],
            ref_lon=ownship["lon"],
        )

        contacts.append(
            {
                "target": target,
                "cpa": cpa,
                "x0": target_x0,
                "y0": target_y0,
            }
        )

    risk_contacts = [
        contact
        for contact in contacts
        if contact["cpa"]["tcpa_s"] > 0.0
        and contact["cpa"]["risk"]
    ]

    if len(risk_contacts) < 2:
        raise RuntimeError(
            "MB-2 requiere dos contactos de riesgo con TCPA positivo. "
            f"Contactos válidos detectados: {len(risk_contacts)}"
        )

    priority_contact = min(
        risk_contacts,
        key=lambda item: item["cpa"]["tcpa_s"],
    )

    maximum_tcpa_s = max(
        float(contact["cpa"]["tcpa_s"])
        for contact in risk_contacts
    )

    projection_time_s = min(
        300.0,
        max(60.0, maximum_tcpa_s + 35.0),
    )

    own_x0 = 0.0
    own_y0 = 0.0

    own_x1, own_y1 = projected_position(
        own_x0,
        own_y0,
        ownship["sog_kn"],
        ownship["cog_deg"],
        projection_time_s,
    )

    fig = plt.figure(
        figsize=(12.5, 8.6),
        constrained_layout=True,
    )

    grid = fig.add_gridspec(
        nrows=1,
        ncols=2,
        width_ratios=[3.7, 1.55],
    )

    ax = fig.add_subplot(grid[0, 0])

    # Panel lateral exclusivo para información y leyenda.
    side_ax = fig.add_subplot(grid[0, 1])
    side_ax.set_axis_off()

    fig.canvas.manager.set_window_title(
        "Escenario MB-2"
    )

    own_line, = ax.plot(
        [own_x0, own_x1],
        [own_y0, own_y1],
        linestyle="--",
        linewidth=2.0,
        label="Trayectoria nominal del USV",
    )

    ax.scatter(
        [own_x0],
        [own_y0],
        marker="^",
        s=120,
        label="Posición inicial del USV",
    )

    add_heading_arrow(
        ax,
        own_x0,
        own_y0,
        ownship["sog_kn"],
        ownship["cog_deg"],
        own_line,
    )

    safety_circle = Circle(
        (own_x0, own_y0),
        radius=config.safety_radius_m,
        fill=False,
        linestyle="-.",
        linewidth=1.5,
        label=(
            "Radio de seguridad del USV = "
            f"{config.safety_radius_m:.0f} m"
        ),
    )

    ax.add_patch(safety_circle)

    all_x = [
        own_x0 - config.safety_radius_m,
        own_x0 + config.safety_radius_m,
        own_x1,
    ]

    all_y = [
        own_y0 - config.safety_radius_m,
        own_y0 + config.safety_radius_m,
        own_y1,
    ]

    for index, contact in enumerate(contacts):
        target = contact["target"]
        cpa = contact["cpa"]

        target_x0 = contact["x0"]
        target_y0 = contact["y0"]

        target_x1, target_y1 = projected_position(
            target_x0,
            target_y0,
            target["sog_kn"],
            target["cog_deg"],
            projection_time_s,
        )

        target_line, = ax.plot(
            [target_x0, target_x1],
            [target_y0, target_y1],
            linestyle="--",
            linewidth=1.8,
            label=(
                "Trayectoria contacto "
                f"{target['mmsi']}"
            ),
        )

        ax.scatter(
            [target_x0],
            [target_y0],
            marker="v",
            s=115,
            label=(
                "Posición inicial contacto "
                f"{target['mmsi']}"
            ),
        )

        add_heading_arrow(
            ax,
            target_x0,
            target_y0,
            target["sog_kn"],
            target["cog_deg"],
            target_line,
        )

        tcpa_for_plot = max(
            0.0,
            float(cpa["tcpa_s"]),
        )

        own_cpa_x, own_cpa_y = projected_position(
            own_x0,
            own_y0,
            ownship["sog_kn"],
            ownship["cog_deg"],
            tcpa_for_plot,
        )

        target_cpa_x, target_cpa_y = projected_position(
            target_x0,
            target_y0,
            target["sog_kn"],
            target["cog_deg"],
            tcpa_for_plot,
        )

        ax.scatter(
            [own_cpa_x],
            [own_cpa_y],
            marker="o",
            s=48,
            label=(
                "Posición proyectada del USV en los CPA"
                if index == 0
                else "_nolegend_"
            ),
        )

        ax.plot(
            [own_cpa_x, target_cpa_x],
            [own_cpa_y, target_cpa_y],
            linestyle=":",
            linewidth=1.6,
            label=(
                f"CPA MMSI {target['mmsi']} = "
                f"{cpa['cpa_m']:.1f} m"
            ),
        )

        is_priority = (
            target["mmsi"]
            == priority_contact["target"]["mmsi"]
        )

        contact_label = (
            f"MMSI {target['mmsi']}\n"
            f"TCPA = {cpa['tcpa_s']:.1f} s"
        )

        if is_priority:
            contact_label += "\nPRIORITARIO"

        # La etiqueta termina antes de la posición inicial del contacto,
        # evitando que invada el panel lateral.
        ax.annotate(
            contact_label,
            xy=(target_x0, target_y0),
            xytext=(-12, 10),
            textcoords="offset points",
            ha="right",
            va="bottom",
            fontsize=8.7,
            linespacing=1.1,
            bbox={
                "boxstyle": "round,pad=0.30",
                "facecolor": "white",
                "edgecolor": "black",
                "alpha": 0.92,
            },
            arrowprops={
                "arrowstyle": "-",
                "linewidth": 0.8,
            },
            zorder=10,
        )

        all_x.extend(
            [
                target_x0,
                target_x1,
                own_cpa_x,
                target_cpa_x,
            ]
        )

        all_y.extend(
            [
                target_y0,
                target_y1,
                own_cpa_y,
                target_cpa_y,
            ]
        )

    ax.annotate(
        "Inicio USV",
        (own_x0, own_y0),
        xytext=(8, -20),
        textcoords="offset points",
    )

    contact_information = "\n".join(
        (
            f"MMSI {contact['target']['mmsi']}: "
            f"CPA={contact['cpa']['cpa_m']:.1f} m | "
            f"TCPA={contact['cpa']['tcpa_s']:.1f} s"
        )
        for contact in contacts
    )

    priority_mmsi = priority_contact["target"]["mmsi"]

    ordered_contacts = sorted(
        contacts,
        key=lambda item: item["cpa"]["tcpa_s"],
    )

    contact_information = "\n\n".join(
        (
            f"MMSI {contact['target']['mmsi']}\n"
            f"  CPA = {contact['cpa']['cpa_m']:.1f} m\n"
            f"  TCPA = {contact['cpa']['tcpa_s']:.1f} s"
        )
        for contact in ordered_contacts
    )

    info = (
        "CONDICIONES INICIALES\n\n"
        "USV\n"
        f"  SOG = {ownship['sog_kn']:.1f} kn\n"
        f"  COG = {ownship['cog_deg']:.0f}°\n\n"
        f"{contact_information}\n\n"
        "ROL ESPERADO DEL USV\n"
        "Maniobrar frente a ambos\n"
        "contactos\n\n"
        "PRIORIDAD ESPERADA\n"
        f"MMSI {priority_mmsi}"
    )

    side_ax.text(
        0.02,
        0.98,
        info,
        transform=side_ax.transAxes,
        va="top",
        ha="left",
        fontsize=9.0,
        linespacing=1.15,
        bbox={
            "boxstyle": "round,pad=0.45",
            "facecolor": "white",
            "edgecolor": "black",
            "alpha": 0.95,
        },
    )

    ax.set_title(
        "Configuración inicial del escenario MB-2: "
        "dos contactos con diferente TCPA",
        pad=14,
    )

    ax.set_xlabel("Posición Este [m]")
    ax.set_ylabel("Posición Norte [m]")
    ax.grid(True, linestyle=":", alpha=0.55)

    handles, labels = ax.get_legend_handles_labels()

    side_ax.legend(
        handles,
        labels,
        loc="upper left",
        bbox_to_anchor=(0.0, 0.48),
        fontsize=7.7,
        frameon=True,
        borderaxespad=0.0,
        handlelength=2.5,
    )

    x_min_data = min(all_x)
    x_max_data = max(all_x)
    y_min_data = min(all_y)
    y_max_data = max(all_y)

    x_span = max(
        x_max_data - x_min_data,
        1.0,
    )

    y_span = max(
        y_max_data - y_min_data,
        1.0,
    )

    x_margin = max(40.0, 0.10 * x_span)
    y_margin = max(40.0, 0.08 * y_span)

    ax.set_xlim(
        x_min_data - x_margin,
        x_max_data + x_margin,
    )

    ax.set_ylim(
        y_min_data - y_margin,
        y_max_data + y_margin,
    )

    ax.set_aspect(
        "equal",
        adjustable="box",
    )

    FIGURES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path is None:
        output_path = (
            FIGURES_DIR
            / "figura_9_3_MB2_configuracion_inicial.png"
        )

    fig.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    print(f"Figura guardada en: {output_path}")
    print(
        "Contacto prioritario esperado: "
        f"MMSI {priority_mmsi}"
    )

    for contact in contacts:
        print(
            f"MMSI={contact['target']['mmsi']} | "
            f"CPA={contact['cpa']['cpa_m']:.2f} m | "
            f"TCPA={contact['cpa']['tcpa_s']:.2f} s | "
            f"Riesgo={contact['cpa']['risk']}"
        )

    plt.show()

    return output_path

def make_figure(scenario_name: str, output_path: Path | None = None) -> Path:
    """Genera y guarda la figura académica del escenario seleccionado."""
    scenario = get_scenario(scenario_name)
    ownship, target = build_states(scenario)

    config = DEFAULT_ALGORITHM_CONFIG
    cpa = calculate_cpa_tcpa(
        ownship=ownship,
        target=target,
        safety_radius_m=config.safety_radius_m,
        time_horizon_s=config.time_horizon_s,
    )

    # La proyección se extiende algo más allá del TCPA para mostrar
    # visualmente la evolución nominal completa del encuentro.
    if cpa["tcpa_s"] > 0.0:
        projection_time_s = min(
            float(DURATION_S),
            max(60.0, cpa["tcpa_s"] + 35.0),
        )
    else:
        projection_time_s = float(DURATION_S)

    own_x0, own_y0 = 0.0, 0.0
    target_x0, target_y0 = latlon_to_xy_m(
        lat=target["lat"],
        lon=target["lon"],
        ref_lat=ownship["lat"],
        ref_lon=ownship["lon"],
    )

    own_x1, own_y1 = projected_position(
        own_x0,
        own_y0,
        ownship["sog_kn"],
        ownship["cog_deg"],
        projection_time_s,
    )
    target_x1, target_y1 = projected_position(
        target_x0,
        target_y0,
        target["sog_kn"],
        target["cog_deg"],
        projection_time_s,
    )

    tcpa_for_plot = max(0.0, float(cpa["tcpa_s"]))
    own_cpa_x, own_cpa_y = projected_position(
        own_x0,
        own_y0,
        ownship["sog_kn"],
        ownship["cog_deg"],
        tcpa_for_plot,
    )
    target_cpa_x, target_cpa_y = projected_position(
        target_x0,
        target_y0,
        target["sog_kn"],
        target["cog_deg"],
        tcpa_for_plot,
    )

    # La vuelta encontrada es casi vertical: se utiliza un formato retrato
    # para evitar un eje Este excesivamente ancho y grandes espacios vacíos.
    fig, ax = plt.subplots(figsize=(9.5, 10.0), constrained_layout=True)
    fig.canvas.manager.set_window_title("Figura 9-2: diseño del escenario")

    own_line, = ax.plot(
        [own_x0, own_x1],
        [own_y0, own_y1],
        linestyle="--",
        linewidth=1.8,
        label="Trayectoria nominal del USV",
    )
    target_line, = ax.plot(
        [target_x0, target_x1],
        [target_y0, target_y1],
        linestyle="--",
        linewidth=1.8,
        label=f"Trayectoria nominal del contacto {scenario.mmsi}",
    )

    ax.scatter(
        [own_x0],
        [own_y0],
        marker="^",
        s=110,
        label="Posición inicial del USV",
    )
    ax.scatter(
        [target_x0],
        [target_y0],
        marker="v",
        s=110,
        label="Posición inicial del contacto",
    )

    add_heading_arrow(
        ax,
        own_x0,
        own_y0,
        ownship["sog_kn"],
        ownship["cog_deg"],
        own_line,
    )
    add_heading_arrow(
        ax,
        target_x0,
        target_y0,
        target["sog_kn"],
        target["cog_deg"],
        target_line,
    )

    # Punto y separación nominal de CPA.
    ax.scatter(
        [own_cpa_x],
        [own_cpa_y],
        marker="o",
        s=55,
        label="Posición proyectada del USV en el CPA",
    )
    ax.plot(
        [own_cpa_x, target_cpa_x],
        [own_cpa_y, target_cpa_y],
        linestyle=":",
        linewidth=1.6,
        label=f"CPA inicial = {cpa['cpa_m']:.1f} m",
    )

    safety_circle = Circle(
        (own_x0, own_y0),
        radius=config.safety_radius_m,
        fill=False,
        linestyle="-.",
        linewidth=1.4,
        label=f"Radio de seguridad del USV = {config.safety_radius_m:.0f} m",
    )
    ax.add_patch(safety_circle)

    ax.annotate(
        "Inicio USV",
        (own_x0, own_y0),
        xytext=(8, -20),
        textcoords="offset points",
    )
    ax.annotate(
        f"Inicio contacto\nMMSI {scenario.mmsi}",
        (target_x0, target_y0),
        xytext=(10, -18),
        textcoords="offset points",
    )
    ax.annotate(
        f"TCPA inicial = {cpa['tcpa_s']:.1f} s",
        (own_cpa_x, own_cpa_y),
        xytext=(12, 12),
        textcoords="offset points",
    )

    info = (
        f"USV: SOG = {ownship['sog_kn']:.1f} kn | "
        f"COG = {ownship['cog_deg']:.0f}°\n"
        f"Contacto: SOG = {target['sog_kn']:.1f} kn | "
        f"COG = {target['cog_deg']:.0f}°\n"
        f"Encuentro esperado: {scenario.expected_encounter}\n"
        f"Rol esperado del USV: Debe maniobrar"
    )
    ax.text(
        1.03,
        0.98,
        info,
        transform=ax.transAxes,
        va="top",
        ha="left",
        bbox={"boxstyle": "round", "alpha": 0.85},
    )

    fig.suptitle(
        "Configuración inicial del escenario MB-2: "
        "dos contactos con diferente TCPA",
        fontsize=14,
    )

    ax.set_title(
        "Trayectorias nominales y condiciones iniciales",
        fontsize=10,
        pad=10,
    )
    ax.set_xlabel("Posición Este [m]")
    ax.set_ylabel("Posición Norte [m]")
    ax.grid(True, linestyle=":", alpha=0.55)
    ax.legend(loc="lower left", bbox_to_anchor=(1.03, 0.0), fontsize=8.5)

    # Ajuste de límites. Se garantiza que el círculo de seguridad del USV
    # quede completamente visible y que exista algo de espacio lateral para
    # evitar una figura demasiado angosta.
    all_x = [
        own_x0 - config.safety_radius_m,
        own_x0 + config.safety_radius_m,
        own_x1,
        target_x0,
        target_x1,
        own_cpa_x,
        target_cpa_x,
    ]
    all_y = [
        own_y0 - config.safety_radius_m,
        own_y0 + config.safety_radius_m,
        own_y1,
        target_y0,
        target_y1,
        own_cpa_y,
        target_cpa_y,
    ]

    x_min_data = min(all_x)
    x_max_data = max(all_x)
    y_min_data = min(all_y)
    y_max_data = max(all_y)

    x_span_data = max(x_max_data - x_min_data, 1.0)
    y_span_data = max(y_max_data - y_min_data, 1.0)

    x_margin = max(35.0, 0.12 * x_span_data)
    y_margin = max(35.0, 0.05 * y_span_data)

    x_min = x_min_data - x_margin
    x_max = x_max_data + x_margin
    y_min = y_min_data - y_margin
    y_max = y_max_data + y_margin

    # Para la figura de diseño del escenario de vuelta encontrada se amplía
    # deliberadamente el eje horizontal para que la composición visual sea
    # más cómoda de leer en la tesis.
    if scenario.name == "head_on_risk":
        x_min = -350.0
        x_max = 350.0
    else:
        min_x_span = max(220.0, 2.4 * config.safety_radius_m)
        current_x_span = x_max - x_min
        if current_x_span < min_x_span:
            x_center = 0.5 * (x_min + x_max)
            x_min = x_center - min_x_span / 2.0
            x_max = x_center + min_x_span / 2.0

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal", adjustable="box")

    fig.tight_layout()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = (
            FIGURES_DIR
            / f"figura_9_2_{scenario.name}_configuracion_inicial.png"
        )

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Figura guardada en: {output_path}")
    print(
        f"CPA inicial: {cpa['cpa_m']:.2f} m | "
        f"TCPA inicial: {cpa['tcpa_s']:.2f} s | "
        f"Riesgo: {cpa['risk']}"
    )

    plt.show()
    return output_path


def parse_args() -> argparse.Namespace:
    available = [
        item.name
        for item in REPRESENTATIVE_SCENARIOS
    ]

    available.append(MB2_SCENARIO_NAME)
    parser = argparse.ArgumentParser(
        description="Genera la figura estática de diseño de un escenario RIPA."
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO_NAME,
        choices=available,
        help="Escenario representativo que se desea dibujar.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.scenario == MB2_SCENARIO_NAME:
        make_mb2_figure()
        return

    make_figure(args.scenario)


if __name__ == "__main__":
    main()

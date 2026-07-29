from __future__ import annotations
import math
import argparse
from typing import Any

from usv_avoidance.scenario_config import (
    MANEUVER_DECISION_DELAY_S,
)
from usv_avoidance.simulation_runner import (
    list_scenarios,
    run_scenario,
)


def parse_args() -> argparse.Namespace:
    """
    Lee los argumentos entregados desde la terminal.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta un escenario AIS/NMEA almacenado "
            "en data/scenarios."
        )
    )

    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help=(
            "Nombre del escenario o archivo .txt ubicado "
            "en data/scenarios."
        ),
    )

    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Muestra los escenarios disponibles.",
    )

    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Muestra la trayectoria obtenida en la simulación.",
    )

    parser.add_argument(
        "--decision-delay-s",
        type=float,
        default=MANEUVER_DECISION_DELAY_S,
        help=(
            "Tiempo de observación previo a ordenar "
            "la primera maniobra evasiva."
        ),
    )

    return parser.parse_args()


def print_available_scenarios() -> None:
    """
    Muestra los escenarios disponibles en data/scenarios.
    """

    scenarios = list_scenarios()

    print("\nEscenarios disponibles:\n")

    if not scenarios:
        print("No se encontraron escenarios.")
        return

    for scenario in scenarios:
        file_name = (
            scenario.get("output_file")
            or scenario.get("name")
            or "sin_nombre"
        )

        description = scenario.get("description", "")

        if description:
            print(f" - {file_name}: {description}")
        else:
            print(f" - {file_name}")

    print()


def format_value(
    value: Any,
    decimals: int = 2,
    suffix: str = "",
) -> str:
    """
    Formatea valores numéricos que podrían ser None.
    """

    if value is None:
        return "sin datos"

    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}{suffix}"

    return str(value)


def print_step(step: dict[str, Any]) -> None:
    """
    Imprime un paso de simulación entregado por run_scenario().
    """

    time_s = step.get("time_s", 0.0)
    ownship = step.get("ownship", {})
    targets = step.get("targets", [])
    state_info = step.get("state", {})

    print("\n" + "#" * 70)
    print(
        f"FRAME | "
        f"t={format_value(time_s, 1, ' s')} | "
        f"Contactos activos={len(targets)}"
    )
    print("#" * 70)

    print(
        "USV | "
        f"Lat={format_value(ownship.get('lat'), 6)} | "
        f"Lon={format_value(ownship.get('lon'), 6)} | "
        f"SOG={format_value(ownship.get('sog_kn'), 1, ' kn')} | "
        f"COG={format_value(ownship.get('cog_deg'), 1, '°')} | "
        f"HDG={format_value(ownship.get('heading_deg'), 1, '°')}"
    )

    if not targets:
        print("Sin contactos AIS activos.")

    for target in targets:
        print("-" * 70)

        print(
            f"Prioridad={target.get('priority')} | "
            f"MMSI={target.get('mmsi')} | "
            f"Lat={format_value(target.get('lat'), 6)} | "
            f"Lon={format_value(target.get('lon'), 6)}"
        )

        print(
            f"SOG={format_value(target.get('sog_kn'), 1, ' kn')} | "
            f"COG={format_value(target.get('cog_deg'), 1, '°')} | "
            f"Distancia={format_value(target.get('distance_m'), 2, ' m')} | "
            f"CPA={format_value(target.get('cpa_m'), 2, ' m')} | "
            f"TCPA={format_value(target.get('tcpa_s'), 1, ' s')}"
        )

        print(
            f"Riesgo={target.get('risk')} | "
            f"Encuentro={target.get('encounter_name')} | "
            f"Rol USV={target.get('ownship_role')} | "
            f"Debe maniobrar={target.get('should_maneuver')}"
        )

    print("-" * 70)

    print(
        f"Estado algoritmo: "
        f"{state_info.get('current_state')} | "
        f"Contacto crítico: "
        f"{step.get('critical_target_mmsi')} | "
        f"Rumbo ordenado: "
        f"{format_value(step.get('commanded_course_deg'), 1, '°')}"
    )

    avoidance_decision = step.get("avoidance_decision")

    if avoidance_decision:
        recommended_course = format_value(
            avoidance_decision.get(
                "recommended_course_deg"
            ),
            1,
            "°",
        )

        course_change = format_value(
            avoidance_decision.get(
                "course_change_deg"
            ),
            1,
            "°",
        )

        print(
            "Decisión evasiva | "
            f"Acción={avoidance_decision.get('action')} | "
            f"Rumbo recomendado={recommended_course} | "
            f"Caída={course_change}"
        )

        reason = avoidance_decision.get(
            "reason",
            "sin información",
        )

        print(f"Motivo: {reason}")

    active_course = step.get("active_course_evaluation")

    if active_course:
        candidate_is_safe = active_course.get(
            "candidate_is_safe"
        )

        global_min_distance = format_value(
            active_course.get("global_min_distance_m"),
            2,
            " m",
        )

        blocking_target = active_course.get(
            "blocking_target_mmsi"
        )

        print(
            "Evaluación rumbo activo | "
            f"Seguro={candidate_is_safe} | "
            f"Distancia mínima global={global_min_distance} | "
            f"Contacto limitante={blocking_target}"
        )


def print_summary(result: dict[str, Any]) -> None:
    """
    Imprime el resumen final y las rutas de los archivos generados.
    """

    summary = result.get("summary", {})
    metric_paths = result.get("metric_paths")

    scenario_name = summary.get(
        "nombre_escenario",
        "sin nombre",
    )

    final_state = summary.get(
        "estado_final",
        "sin datos",
    )

    selected_course_change = format_value(
        summary.get("caida_seleccionada_deg"),
        1,
        "°",
    )

    selected_course = format_value(
        summary.get("rumbo_seleccionado_deg"),
        1,
        "°",
    )

    minimum_distance = format_value(
        summary.get("distancia_minima_m"),
        2,
        " m",
    )

    minimum_cpa = format_value(
        summary.get("cpa_minimo_m"),
        2,
        " m",
    )

    minimum_safety_margin = format_value(
        summary.get("margen_seguridad_minimo_m"),
        2,
        " m",
    )

    reaction_time = format_value(
        summary.get("tiempo_reaccion_s"),
        1,
        " s",
    )

    avoidance_time = format_value(
        summary.get("tiempo_total_evasion_s"),
        1,
        " s",
    )

    print("\n" + "=" * 70)
    print("RESUMEN DE LA SIMULACIÓN")
    print("=" * 70)

    print(f"Escenario: {scenario_name}")
    print(f"Estado final: {final_state}")

    print(
        "Escenario exitoso: "
        f"{summary.get('escenario_exitoso')}"
    )

    print(
        "Riesgo detectado: "
        f"{summary.get('riesgo_detectado')}"
    )

    print(
        "Violó radio de seguridad: "
        f"{summary.get('violo_radio_seguridad')}"
    )

    print(
        "Acción seleccionada: "
        f"{summary.get('accion_seleccionada')}"
    )

    print(
        f"Caída seleccionada: {selected_course_change}"
    )

    print(
        f"Rumbo seleccionado: {selected_course}"
    )

    print(
        f"Distancia mínima: {minimum_distance}"
    )

    print(
        f"CPA mínimo: {minimum_cpa}"
    )

    print(
        "Margen mínimo de seguridad: "
        f"{minimum_safety_margin}"
    )

    print(
        f"Tiempo de reacción: {reaction_time}"
    )

    print(
        f"Tiempo total en evasión: {avoidance_time}"
    )

    print(
        "Cambios de estado: "
        f"{summary.get('cantidad_cambios_estado')}"
    )

    print(
        "Replanificaciones: "
        f"{summary.get('cantidad_replanificaciones', 0)}"
    )

    if metric_paths:
        print("\nArchivos generados:")

        for name, path in metric_paths.items():
            print(f" - {name}: {path}")


def heading_to_vector(heading_deg: float, scale: float = 25.0):
    """
    Convierte un rumbo náutico en grados
    (0° = Norte, 90° = Este)
    a un vector (dx, dy) para graficar.
    """
    heading_rad = math.radians(heading_deg)
    dx = scale * math.sin(heading_rad)
    dy = scale * math.cos(heading_rad)
    return dx, dy

def visualize_result(result: dict[str, Any]) -> None:
    """
    Visualiza las trayectorias utilizando result['steps'].
    """

    steps = result.get("steps", [])

    if not steps:
        print("No existen pasos para visualizar.")
        return

    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    ownship_x = []
    ownship_y = []
    target_tracks: dict[str, dict[str, list[float]]] = {}

    for step in steps:
        ownship = step.get("ownship", {})

        if (
            ownship.get("x_m") is not None
            and ownship.get("y_m") is not None
        ):
            ownship_x.append(float(ownship["x_m"]))
            ownship_y.append(float(ownship["y_m"]))

        for target in step.get("targets", []):
            if (
                target.get("x_m") is None
                or target.get("y_m") is None
            ):
                continue

            mmsi = str(target.get("mmsi", "desconocido"))

            if mmsi not in target_tracks:
                target_tracks[mmsi] = {
                    "x": [],
                    "y": [],
                }

            target_tracks[mmsi]["x"].append(
                float(target["x_m"])
            )
            target_tracks[mmsi]["y"].append(
                float(target["y_m"])
            )

    if not ownship_x:
        print("No existen posiciones válidas para visualizar.")
        return

    fig, ax = plt.subplots(figsize=(9, 7))

    scenario = result.get("scenario", {})
    scenario_name = scenario.get("name", "sin nombre")

    ax.set_title(f"Simulación AIS: {scenario_name}")
    ax.set_xlabel("Posición Este [m]")
    ax.set_ylabel("Posición Norte [m]")

    ax.plot(
        ownship_x,
        ownship_y,
        label="Trayectoria USV",
        zorder=1,
    )

    for mmsi, track in target_tracks.items():
        ax.plot(
            track["x"],
            track["y"],
            label=f"Contacto {mmsi}",
            zorder=1,
        )

    ownship_arrow = ax.quiver(
        [0.0],
        [0.0],
        [0.0],
        [1.0],
        angles="xy",
        scale_units="xy",
        scale=1,
        width=0.010,
        pivot="mid",
        color="blue",
        label="USV actual",
        zorder=7,
    )

    target_arrows = {
        mmsi: ax.quiver(
            [0.0],
            [0.0],
            [0.0],
            [1.0],
            angles="xy",
            scale_units="xy",
            scale=1,
            width=0.008,
            pivot="mid",
            color="black",
            zorder=6,
        )
        for mmsi in target_tracks
    }

    time_text = fig.text(
        0.5,
        0.92,
        "",
        ha="center",
        va="top",
        fontsize=10,
    )

    all_x = list(ownship_x)
    all_y = list(ownship_y)

    for track in target_tracks.values():
        all_x.extend(track["x"])
        all_y.extend(track["y"])

    x_range = max(all_x) - min(all_x)
    y_range = max(all_y) - min(all_y)

    x_margin = x_range * 0.15 if x_range > 0 else 10.0
    y_margin = y_range * 0.15 if y_range > 0 else 10.0

    ax.set_xlim(
        min(all_x) - x_margin,
        max(all_x) + x_margin,
    )
    ax.set_ylim(
        min(all_y) - y_margin,
        max(all_y) + y_margin,
    )

    ax.grid(True)
    ax.legend()
    ax.set_aspect("equal", adjustable="datalim")

    fig.subplots_adjust(
        top=0.84,
        bottom=0.12,
        left=0.12,
        right=0.95,
    )
    
    def update(frame_index: int):
        step = steps[frame_index]
        ownship = step.get("ownship", {})

        own_x = ownship.get("x_m")
        own_y = ownship.get("y_m")

        critical_target_mmsi = step.get("critical_target_mmsi")

        if critical_target_mmsi is not None:
            critical_target_mmsi = str(critical_target_mmsi)

        own_heading = ownship.get("heading_deg")

        if own_heading is None:
            own_heading = ownship.get("cog_deg", 0.0)

        if own_x is not None and own_y is not None:
            own_dx, own_dy = heading_to_vector(
                float(own_heading),
                scale=40.0,
            )

            ownship_arrow.set_offsets(
                [[float(own_x), float(own_y)]]
            )

            ownship_arrow.set_UVC(
                [own_dx],
                [own_dy],
            )

            ownship_arrow.set_visible(True)

        else:
            ownship_arrow.set_visible(False)

        # Ocultar primero todos los contactos.
        for arrow in target_arrows.values():
            arrow.set_visible(False)

        # Mostrar solamente los contactos presentes en este frame.
        for target in step.get("targets", []):
            mmsi = str(target.get("mmsi", "desconocido"))
            arrow = target_arrows.get(mmsi)

            if arrow is None:
                continue

            target_x = target.get("x_m")
            target_y = target.get("y_m")

            if target_x is None or target_y is None:
                continue

            target_heading = target.get("heading_deg")

            if target_heading is None:
                target_heading = target.get("cog_deg", 0.0)

            is_priority = (
                critical_target_mmsi is not None
                and mmsi == critical_target_mmsi
            )

            if is_priority:
                scale_used = 45.0
                arrow.set(color="red")
                arrow.set_linewidth(1.8)
                arrow.set_zorder(8)
            else:
                scale_used = 35.0
                arrow.set(color="black")
                arrow.set_linewidth(1.0)
                arrow.set_zorder(6)

            target_dx, target_dy = heading_to_vector(
                float(target_heading),
                scale=scale_used,
            )

            arrow.set_offsets(
                [[float(target_x), float(target_y)]]
            )

            arrow.set_UVC(
                [target_dx],
                [target_dy],
            )

            arrow.set_visible(True)

        current_state = step.get(
            "state",
            {},
        ).get(
            "current_state",
            "sin estado",
        )

        critical_target = step.get(
            "critical_target_mmsi"
        )

        time_s = step.get("time_s", 0.0)

        time_text.set_text(
            f"t = {time_s:.1f} s | "
            f"Estado = {current_state} | "
            f"Contacto crítico = {critical_target}"
        )

        return (
            ownship_arrow,
            time_text,
            *target_arrows.values(),
        )

    animation = FuncAnimation(
        fig,
        update,
        frames=len(steps),
        interval=400,
        repeat=True,
    )

    # Mantiene viva la referencia mientras se muestra la ventana.
    _ = animation

    plt.show()


def main() -> None:
    args = parse_args()

    if args.list_scenarios:
        print_available_scenarios()
        return

    try:
        result = run_scenario(
            scenario_name=args.scenario,
            save_results=True,
            maneuver_decision_delay_s=(
                args.decision_delay_s
            ),
            playback_delay_s=0.0,
        )

    except FileNotFoundError as error:
        raise SystemExit(str(error)) from error

    for step in result.get("steps", []):
        print_step(step)

    print_summary(result)

    if args.visualize:
        visualize_result(result)


if __name__ == "__main__":
    main()
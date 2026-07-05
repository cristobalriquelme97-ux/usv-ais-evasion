## Modulo para guardar por escenario las métricas de simulación de la maniobra de evasión del USV como: 

# -CPA mínimo real alcanzado
# -distancia mínima real
# -tiempo de inicio de evasión
# -tiempo total en evasión
# -rumbo máximo ordenado
# -maniobra seleccionada
# -estado final
# -si recuperó o no la ruta

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping

from usv_avoidance.motion_model import shortest_angle_difference_deg


class SimulationMetrics:
    """
    Registra métricas de desempeño del algoritmo de evasión.

    Este módulo no decide maniobras.
    Solo observa lo que ocurre durante la simulación y guarda resultados.
    """

    def __init__(
        self,
        scenario_name: str,
        original_course_deg: float,
        safety_radius_m: float,
    ):
        self.scenario_name = scenario_name
        self.original_course_deg = float(original_course_deg)
        self.safety_radius_m = float(safety_radius_m)

        self.rows: list[dict[str, Any]] = []

        self.min_distance_m = math.inf
        self.time_at_min_distance_s = None

        self.min_cpa_m = math.inf
        self.time_at_min_cpa_s = None

        self.first_avoidance_time_s = None
        self.last_avoidance_time_s = None

        self.time_in_avoidance_s = 0.0
        self.time_in_clearing_s = 0.0
        self.time_returning_to_track_s = 0.0

        self.max_abs_course_deviation_deg = 0.0

        self.selected_action = None
        self.selected_course_change_deg = None
        self.selected_course_deg = None

        self.route_recovered_ever = False
        self.final_state = None

    def record_step(
        self,
        ownship: Mapping[str, Any],
        critical_assessment: Mapping[str, Any] | None,
        state_info: Mapping[str, Any],
        commanded_course_deg: float,
        route_recovered: bool,
        dt_s: float,
        avoidance_decision: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Registra una muestra de la simulación.

        Se recomienda llamarla una vez por iteración del bucle principal,
        después de decidir el rumbo ordenado y antes de avanzar el USV.
        """

        timestamp_s = float(ownship.get("timestamp", 0.0))
        current_state = str(state_info.get("current_state"))

        self.final_state = current_state

        if route_recovered:
            self.route_recovered_ever = True

        if current_state == "AVOIDING_TARGET":
            self.time_in_avoidance_s += dt_s

            if self.first_avoidance_time_s is None:
                self.first_avoidance_time_s = timestamp_s

            self.last_avoidance_time_s = timestamp_s

        elif current_state == "CLEARING_TARGET":
            self.time_in_clearing_s += dt_s

        elif current_state == "RETURNING_TO_TRACK":
            self.time_returning_to_track_s += dt_s

        course_deviation_deg = abs(
            shortest_angle_difference_deg(
                target_deg=self.original_course_deg,
                current_deg=float(ownship["cog_deg"]),
            )
        )

        if course_deviation_deg > self.max_abs_course_deviation_deg:
            self.max_abs_course_deviation_deg = course_deviation_deg

        target_mmsi = None
        distance_m = None
        cpa_m = None
        tcpa_s = None
        risk = None
        encounter_name = None
        ownship_role = None
        should_maneuver = None

        if critical_assessment is not None:
            target = critical_assessment["target"]
            cpa_result = critical_assessment["cpa_result"]
            classification = critical_assessment["classification"]

            target_mmsi = target.get("mmsi")
            distance_m = float(cpa_result["distance_m"])
            cpa_m = float(cpa_result["cpa_m"])
            tcpa_s = float(cpa_result["tcpa_s"])
            risk = bool(cpa_result["risk"])
            encounter_name = classification.get("encounter_name")
            ownship_role = classification.get("ownship_role")
            should_maneuver = classification.get("should_maneuver")

            if distance_m < self.min_distance_m:
                self.min_distance_m = distance_m
                self.time_at_min_distance_s = timestamp_s

            if cpa_m < self.min_cpa_m:
                self.min_cpa_m = cpa_m
                self.time_at_min_cpa_s = timestamp_s

        action = None
        recommended_course_deg = None
        course_change_deg = None
        maneuver_required = None

        if avoidance_decision is not None:
            action = avoidance_decision.get("action")
            recommended_course_deg = avoidance_decision.get("recommended_course_deg")
            course_change_deg = avoidance_decision.get("course_change_deg")
            maneuver_required = avoidance_decision.get("maneuver_required")

            if (
                self.selected_action is None
                and bool(maneuver_required)
            ):
                self.selected_action = action
                self.selected_course_change_deg = course_change_deg
                self.selected_course_deg = recommended_course_deg

        row = {
            "scenario_name": self.scenario_name,
            "timestamp_s": timestamp_s,
            "state": current_state,
            "target_mmsi": target_mmsi,
            "ownship_lat": ownship.get("lat"),
            "ownship_lon": ownship.get("lon"),
            "ownship_sog_kn": ownship.get("sog_kn"),
            "ownship_cog_deg": ownship.get("cog_deg"),
            "commanded_course_deg": commanded_course_deg,
            "distance_m": distance_m,
            "cpa_m": cpa_m,
            "tcpa_s": tcpa_s,
            "risk": risk,
            "encounter_name": encounter_name,
            "ownship_role": ownship_role,
            "should_maneuver": should_maneuver,
            "avoidance_action": action,
            "maneuver_required": maneuver_required,
            "recommended_course_deg": recommended_course_deg,
            "course_change_deg": course_change_deg,
            "route_recovered": route_recovered,
        }

        self.rows.append(row)

    def build_summary(self) -> dict[str, Any]:
        """
        Construye un resumen final de la simulación.
        """

        if self.min_distance_m == math.inf:
            min_distance_m = None
        else:
            min_distance_m = self.min_distance_m

        if self.min_cpa_m == math.inf:
            min_cpa_m = None
        else:
            min_cpa_m = self.min_cpa_m

        safety_radius_violated = (
            min_distance_m is not None
            and min_distance_m < self.safety_radius_m
        )

        return {
            "scenario_name": self.scenario_name,
            "safety_radius_m": self.safety_radius_m,
            "final_state": self.final_state,
            "route_recovered_ever": self.route_recovered_ever,
            "selected_action": self.selected_action,
            "selected_course_change_deg": self.selected_course_change_deg,
            "selected_course_deg": self.selected_course_deg,
            "min_distance_m": min_distance_m,
            "time_at_min_distance_s": self.time_at_min_distance_s,
            "min_cpa_m": min_cpa_m,
            "time_at_min_cpa_s": self.time_at_min_cpa_s,
            "safety_radius_violated": safety_radius_violated,
            "first_avoidance_time_s": self.first_avoidance_time_s,
            "last_avoidance_time_s": self.last_avoidance_time_s,
            "time_in_avoidance_s": self.time_in_avoidance_s,
            "time_in_clearing_s": self.time_in_clearing_s,
            "time_returning_to_track_s": self.time_returning_to_track_s,
            "max_abs_course_deviation_deg": self.max_abs_course_deviation_deg,
            "total_samples": len(self.rows),
        }

    def save(self, output_dir: Path) -> dict[str, Path]:
        """
        Guarda el historial paso a paso y el resumen final.
        """

        output_dir.mkdir(parents=True, exist_ok=True)

        steps_path = output_dir / f"{self.scenario_name}_steps.csv"
        summary_path = output_dir / f"{self.scenario_name}_summary.json"

        self._save_steps_csv(steps_path)
        self._save_summary_json(summary_path)

        return {
            "steps_path": steps_path,
            "summary_path": summary_path,
        }

    def _save_steps_csv(self, path: Path) -> None:
        """
        Guarda las muestras de simulación en formato CSV.
        """

        if not self.rows:
            return

        fieldnames = list(self.rows[0].keys())

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.rows)

    def _save_summary_json(self, path: Path) -> None:
        """
        Guarda el resumen final en formato JSON.
        """

        summary = self.build_summary()

        with path.open("w", encoding="utf-8") as file:
            json.dump(
                summary,
                file,
                indent=4,
                ensure_ascii=False,
            )
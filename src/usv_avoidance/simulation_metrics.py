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

        # Métricas de seguridad
        self.first_risk_time_s = None
        self.safety_violation_time_s = None
        self.risk_detected_ever = False

        # Métricas de eficiencia
        self.reaction_time_s = None
        self.avoidance_started_ever = False
        self.route_recovered_after_avoidance = False

        # Métricas de estabilidad lógica y de mando
        self.previous_state = None
        self.state_transition_count = 0

        self.previous_commanded_course_deg = None
        self.commanded_course_change_count = 0
        self.total_commanded_course_variation_deg = 0.0
        self.max_commanded_course_step_deg = 0.0

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

        # Conteo de cambios de estado del algoritmo.
        # Esto permite evaluar estabilidad lógica:
        # mientras menos cambios innecesarios existan, más estable es la decisión.
        if self.previous_state is not None and current_state != self.previous_state:
            self.state_transition_count += 1

        self.previous_state = current_state

        if route_recovered:
            self.route_recovered_ever = True

            if self.avoidance_started_ever and current_state in (
                    "RETURNING_TO_TRACK",
                    "TRACKING_ROUTE",
                ):
                    self.route_recovered_after_avoidance = True

        if current_state == "AVOIDING_TARGET":
            self.time_in_avoidance_s += dt_s
            self.avoidance_started_ever = True

            if self.first_avoidance_time_s is None:
                self.first_avoidance_time_s = timestamp_s

                if self.first_risk_time_s is not None:
                    self.reaction_time_s = (
                        self.first_avoidance_time_s - self.first_risk_time_s
                    )

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

        # Variación del rumbo ordenado entre una muestra y la siguiente.
        # Esto permite evaluar estabilidad de mando.
        # Mientras menos cambios bruscos de rumbo ordenado existan, más estable es la maniobra.
        if self.previous_commanded_course_deg is not None:
            commanded_course_step_deg = abs(
                shortest_angle_difference_deg(
                    target_deg=self.previous_commanded_course_deg,
                    current_deg=float(commanded_course_deg),
                )
            )

            if commanded_course_step_deg > 1e-6:
                self.commanded_course_change_count += 1
                self.total_commanded_course_variation_deg += commanded_course_step_deg

                if commanded_course_step_deg > self.max_commanded_course_step_deg:
                    self.max_commanded_course_step_deg = commanded_course_step_deg

        self.previous_commanded_course_deg = float(commanded_course_deg)

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
            if risk:
                self.risk_detected_ever = True
                if self.first_risk_time_s is None:
                    self.first_risk_time_s = timestamp_s
            encounter_name = classification.get("encounter_name")
            ownship_role = classification.get("ownship_role")
            should_maneuver = classification.get("should_maneuver")

            if distance_m < self.min_distance_m:
                self.min_distance_m = distance_m
                self.time_at_min_distance_s = timestamp_s
            if (
                distance_m < self.safety_radius_m
                and self.safety_violation_time_s is None
            ):
                self.safety_violation_time_s = timestamp_s
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
            "nombre_escenario": self.scenario_name,
            "tiempo_s": timestamp_s,
            "estado_algoritmo": current_state,
            "mmsi_blanco": target_mmsi,
            "latitud_usv": ownship.get("lat"),
            "longitud_usv": ownship.get("lon"),
            "velocidad_usv_kn": ownship.get("sog_kn"),
            "rumbo_usv_deg": ownship.get("cog_deg"),
            "rumbo_ordenado_deg": commanded_course_deg,
            "distancia_actual_m": distance_m,
            "cpa_m": cpa_m,
            "tcpa_s": tcpa_s,
            "riesgo_colision": risk,
            "tipo_encuentro": encounter_name,
            "rol_usv": ownship_role,
            "debe_maniobrar": should_maneuver,
            "accion_evasiva": action,
            "maniobra_requerida": maneuver_required,
            "rumbo_recomendado_deg": recommended_course_deg,
            "caida_rumbo_deg": course_change_deg,
            "ruta_recuperada": route_recovered,
        }

        self.rows.append(row)

    def build_summary(self) -> dict[str, Any]:
        """
        Construye un resumen final de la simulación con nombres en español.
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

        if min_distance_m is None:
            safety_margin_m = None
        else:
            safety_margin_m = min_distance_m - self.safety_radius_m

        scenario_success = (
            not safety_radius_violated
            and (
                not self.risk_detected_ever
                or self.route_recovered_after_avoidance
                or self.time_in_avoidance_s == 0.0
            )
        )

        return {
            "nombre_escenario": self.scenario_name,
            "radio_seguridad_m": self.safety_radius_m,
            "estado_final": self.final_state,

            # Resultado global
            "escenario_exitoso": scenario_success,
            "riesgo_detectado": self.risk_detected_ever,
            "violo_radio_seguridad": safety_radius_violated,
            "ruta_recuperada_alguna_vez": self.route_recovered_ever,
            "ruta_recuperada_despues_evasion": self.route_recovered_after_avoidance, #El usv maniobró y luego volvió a su rumbo original.

            # Maniobra seleccionada
            "accion_seleccionada": self.selected_action,
            "caida_seleccionada_deg": self.selected_course_change_deg,
            "rumbo_seleccionado_deg": self.selected_course_deg,

            # Seguridad
            "distancia_minima_m": min_distance_m,
            "tiempo_distancia_minima_s": self.time_at_min_distance_s,
            "cpa_minimo_m": min_cpa_m,
            "tiempo_cpa_minimo_s": self.time_at_min_cpa_s,
            "margen_seguridad_minimo_m": safety_margin_m,
            "1era_deteccion_riesgo_s": self.first_risk_time_s,
            "1era_violacion_seguridad_s": self.safety_violation_time_s, #Si nunca entra en violación, queda None

            # Eficiencia
            "1era_evasion_s": self.first_avoidance_time_s,
            "ultima_evasion_s": self.last_avoidance_time_s,
            "tiempo_reaccion_s": self.reaction_time_s,
            "tiempo_total_evasion_s": self.time_in_avoidance_s,
            "tiempo_total_despeje_s": self.time_in_clearing_s,
            "tiempo_total_retorno_ruta_s": self.time_returning_to_track_s,

            # Estabilidad
            "desviacion_maxima_rumbo_usv_deg": self.max_abs_course_deviation_deg,
            "cantidad_cambios_estado": self.state_transition_count,
            "cantidad_cambios_rumbo_ordenado": self.commanded_course_change_count,
            "variacion_total_rumbo_ordenado_deg": (
                self.total_commanded_course_variation_deg
            ),
            "max_cambio_rumbo_ordenado_deg": self.max_commanded_course_step_deg,

            # Datos generales
            "total_muestras": len(self.rows),
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
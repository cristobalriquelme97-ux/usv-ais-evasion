# Generador de escenarios representativos para pruebas de evasión de colisiones de USV.

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from usv_avoidance.ais_type1_generator import generate_moving_target_scenario
from usv_avoidance.scenario_config import (
    SCENARIOS_DIR,
    USV_LAT0,
    USV_LON0,
    USV_SOG_KN,
    USV_COG_DEG,
    USV_HEADING_DEG,
    USV_TURN_RATE_DEG_S,
    DURATION_S,
    STEP_S,
)


EARTH_RADIUS_M = 6371000.0
SAFETY_RADIUS_M = 50.0
TIME_HORIZON_S = 300.0


@dataclass(frozen=True)
class TargetScenario:
    """
    Define un escenario AIS representativo usando coordenadas relativas
    al USV propio.

    offset_east_m:
        Distancia inicial del blanco hacia el Este respecto al USV.

    offset_north_m:
        Distancia inicial del blanco hacia el Norte respecto al USV.

    Los parámetros del USV no se modifican en este archivo.
    Solo se modifica el blanco AIS.
    """

    name: str
    description: str
    mmsi: int
    offset_east_m: float
    offset_north_m: float
    target_sog_kn: float
    target_cog_deg: float
    expected_encounter: str
    expected_ownship_role: str
    expected_action: str


def offset_m_to_latlon(
    ref_lat: float,
    ref_lon: float,
    east_m: float,
    north_m: float,
) -> tuple[float, float]:
    """
    Convierte un desplazamiento local Este/Norte en latitud/longitud.

    Esta aproximación es válida para escenarios locales de simulación,
    donde las distancias son pequeñas.
    """

    delta_lat = (north_m / EARTH_RADIUS_M) * (180.0 / math.pi)

    delta_lon = (
        east_m
        / (EARTH_RADIUS_M * math.cos(math.radians(ref_lat)))
    ) * (180.0 / math.pi)

    return ref_lat + delta_lat, ref_lon + delta_lon


FROZEN_OWNSHIP = {
    "lat0": USV_LAT0,
    "lon0": USV_LON0,
    "sog_kn": USV_SOG_KN,
    "cog_deg": USV_COG_DEG,
    "heading_deg": USV_HEADING_DEG,
    "turn_rate_deg_s": USV_TURN_RATE_DEG_S,
}


REPRESENTATIVE_SCENARIOS = [
    TargetScenario(
        name="crossing_starboard_risk",
        description="Cruce con blanco por estribor. El USV debe mantenerse apartado.",
        mmsi=725000001,
        offset_east_m=450.0,
        offset_north_m=450.0,
        target_sog_kn=6.0,
        target_cog_deg=270.0,
        expected_encounter="cruce",
        expected_ownship_role="give_way",
        expected_action="alter_course_starboard",
    ),
    TargetScenario(
        name="crossing_port_risk",
        description="Cruce con blanco por babor. El USV se comporta como buque con preferencia.",
        mmsi=725000002,
        offset_east_m=-450.0,
        offset_north_m=450.0,
        target_sog_kn=6.0,
        target_cog_deg=90.0,
        expected_encounter="cruce",
        expected_ownship_role="stand_on",
        expected_action="maintain_course",
    ),
    TargetScenario(
        name="head_on_risk",
        description="Vuelta encontrada con cursos opuestos.",
        mmsi=725000003,
        offset_east_m=0.0,
        offset_north_m=900.0,
        target_sog_kn=6.0,
        target_cog_deg=180.0,
        expected_encounter="vuelta encontrada",
        expected_ownship_role="give_way",
        expected_action="alter_course_starboard",
    ),
    TargetScenario(
        name="overtaking_ownship_give_way",
        description="El USV alcanza a un blanco más lento por la popa.",
        mmsi=725000004,
        offset_east_m=0.0,
        offset_north_m=250.0,
        target_sog_kn=3.0,
        target_cog_deg=0.0,
        expected_encounter="alcance",
        expected_ownship_role="give_way",
        expected_action="keep_clear",
    ),
    TargetScenario(
        name="being_overtaken_stand_on",
        description="El blanco alcanza al USV desde popa.",
        mmsi=725000005,
        offset_east_m=0.0,
        offset_north_m=-250.0,
        target_sog_kn=9.0,
        target_cog_deg=0.0,
        expected_encounter="alcance por blanco",
        expected_ownship_role="stand_on",
        expected_action="maintain_course",
    ),
    TargetScenario(
        name="parallel_no_risk",
        description="Blanco paralelo al USV sin riesgo de colisión.",
        mmsi=725000006,
        offset_east_m=150.0,
        offset_north_m=0.0,
        target_sog_kn=6.0,
        target_cog_deg=0.0,
        expected_encounter="sin riesgo",
        expected_ownship_role="none",
        expected_action="maintain_course",
    ),
    TargetScenario(
        name="late_crossing_starboard_risk",
        description="Cruce por estribor con menor tiempo disponible para reaccionar.",
        mmsi=725000007,
        offset_east_m=160.0,
        offset_north_m=160.0,
        target_sog_kn=6.0,
        target_cog_deg=270.0,
        expected_encounter="cruce",
        expected_ownship_role="give_way",
        expected_action="alter_course_starboard",
    ),
    TargetScenario(
        name="close_crossing_starboard_risk",
        description="Cruce por estribor con aproximación más cercana que el caso base.",
        mmsi=725000008,
        offset_east_m=300.0,
        offset_north_m=300.0,
        target_sog_kn=6.0,
        target_cog_deg=270.0,
        expected_encounter="cruce",
        expected_ownship_role="give_way",
        expected_action="alter_course_starboard",
    ),
]


def generate_all_representative_scenarios() -> None:
    """
    Genera todos los escenarios AIS/NMEA representativos.

    Los archivos generados quedan en:
        data/scenarios/

    También se genera un manifest JSON con:
    - parámetros congelados del USV
    - parámetros generales de simulación
    - descripción y resultado esperado de cada escenario
    """

    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "ownship_frozen": FROZEN_OWNSHIP,
        "simulation": {
            "duration_s": DURATION_S,
            "step_s": STEP_S,
            "safety_radius_m": SAFETY_RADIUS_M,
            "time_horizon_s": TIME_HORIZON_S,
        },
        "scenarios": [],
    }

    for scenario in REPRESENTATIVE_SCENARIOS:
        target_lat0, target_lon0 = offset_m_to_latlon(
            ref_lat=USV_LAT0,
            ref_lon=USV_LON0,
            east_m=scenario.offset_east_m,
            north_m=scenario.offset_north_m,
        )

        output_file = SCENARIOS_DIR / f"{scenario.name}_nmea.txt"

        generate_moving_target_scenario(
            output_file=str(output_file),
            mmsi=scenario.mmsi,
            lat0=target_lat0,
            lon0=target_lon0,
            sog_kn=scenario.target_sog_kn,
            cog_deg=scenario.target_cog_deg,
            heading_deg=int(round(scenario.target_cog_deg)) % 360,
            duration_s=DURATION_S,
            step_s=STEP_S,
        )

        scenario_info = asdict(scenario)
        scenario_info["output_file"] = output_file.name
        scenario_info["target_lat0"] = target_lat0
        scenario_info["target_lon0"] = target_lon0

        manifest["scenarios"].append(scenario_info)

        print(f"Escenario generado: {output_file.name}")

    manifest_file = SCENARIOS_DIR / "scenario_manifest.json"

    with manifest_file.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            indent=4,
            ensure_ascii=False,
        )

    print(f"\nManifest generado: {manifest_file}")


if __name__ == "__main__":
    generate_all_representative_scenarios()
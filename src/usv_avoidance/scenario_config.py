from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# ============================================================
# RUTAS DEL PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"


# ============================================================
# ARCHIVO DE SALIDA AIS/NMEA PARA GENERACIÓN MANUAL
# ============================================================

OUTPUT_FILE = SCENARIOS_DIR / "mc_crossing_starboard_run14.txt"
DELAY_S = 0.5


# ============================================================
# CONFIGURACIÓN MANUAL DEL BLANCO AIS
# ============================================================

TARGET_MMSI = 725100014

TARGET_LAT0 = -33.0249508015
TARGET_LON0 = -71.6224856243
TARGET_SOG_KN = 6.8083284678
TARGET_COG_DEG = 298.0687330349
TARGET_HEADING_DEG = TARGET_COG_DEG


# ============================================================
# CONFIGURACIÓN PARAMETRIZABLE DEL ESCENARIO
# ============================================================

@dataclass(frozen=True)
class ScenarioConfig:
    """
    Condiciones físicas y temporales de una simulación.

    No contiene parámetros de decisión del algoritmo. Esos valores
    pertenecen a AlgorithmConfig.
    """

    usv_lat0: float = -33.025000
    usv_lon0: float = -71.625000
    usv_sog_kn: float = 6.0
    usv_cog_deg: float = 0.0
    usv_heading_deg: float = 0.0
    usv_turn_rate_deg_s: float = 10.0

    duration_s: int = 200
    step_s: int = 5

    def __post_init__(self) -> None:
        if self.usv_sog_kn < 0.0:
            raise ValueError("usv_sog_kn no puede ser negativo.")

        if self.usv_turn_rate_deg_s <= 0.0:
            raise ValueError(
                "usv_turn_rate_deg_s debe ser mayor que cero."
            )

        if self.duration_s <= 0:
            raise ValueError("duration_s debe ser mayor que cero.")

        if self.step_s <= 0:
            raise ValueError("step_s debe ser mayor que cero.")

        if self.step_s > self.duration_s:
            raise ValueError(
                "step_s no puede ser mayor que duration_s."
            )


DEFAULT_SCENARIO_CONFIG = ScenarioConfig()


# ============================================================
# ALIAS DE COMPATIBILIDAD
# ============================================================
# Se mantienen temporalmente para no romper generadores o módulos
# antiguos. El simulation_runner deberá usar ScenarioConfig.

USV_LAT0 = DEFAULT_SCENARIO_CONFIG.usv_lat0
USV_LON0 = DEFAULT_SCENARIO_CONFIG.usv_lon0
USV_SOG_KN = DEFAULT_SCENARIO_CONFIG.usv_sog_kn
USV_COG_DEG = DEFAULT_SCENARIO_CONFIG.usv_cog_deg
USV_HEADING_DEG = DEFAULT_SCENARIO_CONFIG.usv_heading_deg
USV_TURN_RATE_DEG_S = DEFAULT_SCENARIO_CONFIG.usv_turn_rate_deg_s
DURATION_S = DEFAULT_SCENARIO_CONFIG.duration_s
STEP_S = DEFAULT_SCENARIO_CONFIG.step_s
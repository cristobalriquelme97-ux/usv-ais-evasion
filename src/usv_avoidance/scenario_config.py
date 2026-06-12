from pathlib import Path


# ============================================================
# RUTA BASE DEL PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ============================================================
# ARCHIVO DE SALIDA AIS/NMEA
# ============================================================

OUTPUT_FILE = PROJECT_ROOT / "data" / "scenarios" / "crossing_scenario_nmea.txt"


# ============================================================
# CONFIGURACIÓN DEL BLANCO AIS
# ============================================================

TARGET_MMSI = 725000001

TARGET_LAT0 = -33.020000
TARGET_LON0 = -71.620000

TARGET_SOG_KN = 8.5
TARGET_COG_DEG = 225.0
TARGET_HEADING_DEG = 45


# ============================================================
# CONFIGURACIÓN DEL USV PROPIO
# ============================================================

USV_LAT0 = -33.025000
USV_LON0 = -71.625000

USV_SOG_KN = 6.0
USV_COG_DEG = 45.0
USV_HEADING_DEG = 20


# ============================================================
# CONFIGURACIÓN GENERAL DEL ESCENARIO
# ============================================================

DURATION_S = 150
STEP_S = 5
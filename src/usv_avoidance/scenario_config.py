from pathlib import Path


# ============================================================
# RUTA BASE DEL PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"
    
# ============================================================
# ARCHIVO DE SALIDA AIS/NMEA
# ============================================================

# Archivo de salida para CREAR un nuevo escenario AIS/NMEA.
OUTPUT_FILE = SCENARIOS_DIR / "crossing_starboard_risk_nmea.txt"

# Parámetros de simulación
DELAY_S = 0.5

# ============================================================
# CONFIGURACIÓN DEL BLANCO AIS
# ============================================================

TARGET_MMSI = 725000001
TARGET_LAT0 = -33.020503
TARGET_LON0 = -71.619637
TARGET_SOG_KN = 6.0
TARGET_COG_DEG = 270.0
#TARGET_HEADING_DEG = 45
TARGET_HEADING_DEG = TARGET_COG_DEG # Para simplificar, el blanco siempre apunta hacia su rumbo.

# ============================================================
# CONFIGURACIÓN DEL USV PROPIO
# ============================================================

USV_LAT0 = -33.025000
USV_LON0 = -71.625000
USV_SOG_KN = 6.0
USV_COG_DEG = 0.0
USV_HEADING_DEG = 0.0
USV_TURN_RATE_DEG_S = 1.0


# ============================================================
# CONFIGURACIÓN GENERAL DEL ESCENARIO
# ============================================================

DURATION_S = 200
STEP_S = 5
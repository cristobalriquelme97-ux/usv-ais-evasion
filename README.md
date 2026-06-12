# USV AIS Avoidance

Repositorio para el desarrollo de un algoritmo de gobierno autónomo para un USV orientado a la evasión de blancos móviles utilizando información AIS.

## Objetivo

Procesar sentencias AIS/NMEA, extraer variables cinemáticas de blancos móviles, alimentar el algoritmo de evasión de colisiones, tomar la maniobra adecuada y recomendar un rumbo a navegar al auto-piloto

## Estructura del proyecto

# ============================================================
# ADAPTADOR AIS
# ============================================================
- `scenario_config.py`: configuración blanco AIS y USV Yagán.
- `ais_type1_generator.py`: generación de sentencias AIS/NMEA según escenario creado.
- `nmea_file_source.py`: recepción secuencial de sentencias AIS/NMEA.
- `visualizer.ais.py`:simulación trayectorias blanco AIS y USV Yagán.
- `ais_adapter.py`: recepción y decodificación de sentencias AIS/NMEA.
# ============================================================
# CÁLCULOS CINEMÁTICOS
# ============================================================
- `cpa_tcpa.py`: cálculo de CPA y TCPA.
# ============================================================
# MÓDULO EVASIÓN 
# ============================================================
- `target_tracker.py`: seguimiento de blancos móviles.
- `avoidance.py`: lógica de decisión de maniobra.
- `main.py`: integración general.
- `data/`: datos AIS de prueba.
- `tests/`: pruebas unitarias.
- `docs/`: documentación técnica del proyecto.
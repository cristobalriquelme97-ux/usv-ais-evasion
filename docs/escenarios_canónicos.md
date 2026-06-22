# Escenario: crossing_starboard_risk

## Descripción

El USV navega al norte y un blanco AIS ubicado por estribor navega hacia el oeste.
Ambas trayectorias se cruzan dentro del radio de seguridad.

## Configuración

- USV:
  - lat: -33.025000
  - lon: -71.625000
  - SOG: 6.0 kn
  - COG: 0.0 deg

- Blanco AIS:
  - lat: -33.020503
  - lon: -71.619637
  - SOG: 6.0 kn
  - COG: 270.0 deg

## Resultado esperado

- Riesgo: True
- CPA: cercano a 0 m
- TCPA: positivo, cercano a 162 s
- Demarcación relativa: cercana a 45 deg
- Sector: estribor
- Encuentro: cruce
- Rol USV: give_way
- Debe maniobrar: True
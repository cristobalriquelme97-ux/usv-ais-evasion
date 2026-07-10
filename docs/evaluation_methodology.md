1. Propósito de la evaluación
El propósito de la evaluación es analizar el desempeño del algoritmo de evasión de blancos móviles mediante simulación cinemática, considerando escenarios representativos de navegación marítima. La evaluación busca determinar si el algoritmo identifica situaciones de riesgo, clasifica el tipo de encuentro, selecciona una maniobra evasiva coherente y mantiene márgenes mínimos de seguridad.
2. Alcance de la evaluación
La evaluación se limita al comportamiento lógico y cinemático del algoritmo. No se considera la validación experimental sobre el USV físico, debido a la no disponibilidad de la plataforma durante el desarrollo. Tampoco se modelan perturbaciones externas como viento, corriente, oleaje, retardos reales de comunicación, dinámica de actuadores o errores de sensores.
3. Arquitectura evaluada
AIS/NMEA → Adaptador AIS → Tracker de blancos → CPA/TCPA → Clasificador de encuentro → Máquina de estados → Módulo de evasión → Modelo cinemático → Métricas
4. Escenarios simulados
- Cruce por estribor con riesgo.
- Cruce cercano por estribor.
- Vuelta encontrada.
- Alcance con USV como buque que alcanza.
- Escenario sin riesgo.
- Escenario de bajo margen de seguridad.

| Escenario                   | Tipo de encuentro | Riesgo esperado | Rol esperado del USV | Acción esperada  |
| --------------------------- | ----------------- | --------------- | -------------------- | ---------------- |
| crossing_starboard_risk     | Cruce             | Sí              | Give-way             | Caer a estribor  |
| head_on_risk                | Vuelta encontrada | Sí              | Give-way             | Caer a estribor  |
| overtaking_ownship_give_way | Alcance           | Sí              | Give-way             | Maniobra evasiva |
| no_risk                     | Sin riesgo        | No              | Mantener             | Mantener rumbo   |
5. Variables registradas
- tiempo de simulación;
- posición del USV;
- rumbo actual del USV;
- rumbo ordenado;
- distancia al blanco;
- CPA;
- TCPA;
- tipo de encuentro;
- rol del USV;
- estado del algoritmo;
- acción evasiva seleccionada;
- recuperación de ruta.
6. Métricas de evaluación
   6.1 Métricas de seguridad
   - Distancia mínima real.
- CPA mínimo.
- Margen mínimo de seguridad.
- Violación del radio de seguridad.
   6.2 Métricas de eficiencia
   - Tiempo de reacción.
- Tiempo total en evasión.
- Tiempo total en despeje.
- Tiempo total retornando a ruta.
- Caída seleccionada.
   6.3 Métricas de estabilidad
   - Cantidad de cambios de estado.
- Cantidad de cambios de rumbo ordenado.
- Variación total del rumbo ordenado.
- Máximo cambio de rumbo ordenado.
- Recuperación de ruta después de evasión.
7. Criterios de éxito
Un escenario se considera exitoso si:
7.1. No se viola el radio de seguridad.
7.2. Si existe riesgo, el algoritmo detecta la condición de riesgo.
7.3. Si el USV tiene rol de maniobra, se genera una acción evasiva.
7.4. Luego de la evasión, el USV retorna al rumbo nominal.
7.5. No se presentan cambios excesivos de estado o rumbo ordenado.
8. Procedimiento de ejecución
python -m usv_avoidance.batch_simulation
python -m usv_avoidance.evaluation_report
9. Formato de resultados
10. Limitaciones de la evaluación
La evaluación no constituye una validación física del algoritmo sobre el USV real. Los resultados corresponden a simulaciones cinemáticas bajo escenarios controlados, por lo que no incorporan perturbaciones ambientales, errores reales de sensores, retardos de comunicación, dinámica completa de actuadores ni respuesta hidrodinámica de la plataforma.

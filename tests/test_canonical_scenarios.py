from __future__ import annotations

import pytest

from usv_avoidance.simulation_runner import run_scenario


CANONICAL_SCENARIOS = (
    "crossing_starboard_risk_nmea.txt",
    "crossing_port_risk_nmea.txt",
    "head_on_risk_nmea.txt",
    "overtaking_ownship_give_way_nmea.txt",
    "being_overtaken_stand_on_nmea.txt",
    "parallel_no_risk_nmea.txt",
)


@pytest.mark.parametrize(
    "scenario_file",
    CANONICAL_SCENARIOS,
)
def test_canonical_scenario_matches_expected_behavior(
    scenario_file: str,
) -> None:
    """
    Comprueba que cada escenario canónico:

    1. Sea clasificado correctamente.
    2. Asigne correctamente el rol RIPA del USV.
    3. Ejecute la acción esperada.
    4. Mantenga la separación de seguridad.
    """

    result = run_scenario(
        scenario_name=scenario_file,
        save_results=False,
        playback_delay_s=0.0,
    )

    summary = result["summary"]

    assert summary["encuentro_correcto"] is True, (
        f"Clasificación incorrecta en {scenario_file}: "
        f"esperado={summary['encuentro_esperado']}, "
        f"observado={summary['encuentro_observado']}"
    )

    assert summary["rol_correcto"] is True, (
        f"Rol incorrecto en {scenario_file}: "
        f"esperado={summary['rol_esperado']}, "
        f"observado={summary['rol_observado']}"
    )

    assert summary["accion_correcta"] is True, (
        f"Acción incorrecta en {scenario_file}: "
        f"esperada={summary['accion_esperada']}, "
        f"observada={summary['accion_observada']}"
    )

    assert summary["resultado_seguro"] is True, (
        f"Se vulneró el radio de seguridad en {scenario_file}. "
        f"Distancia mínima: {summary['distancia_minima_m']} m"
    )

    assert summary["comportamiento_esperado"] is True
    assert summary["escenario_exitoso"] is True


@pytest.mark.parametrize(
    "scenario_file",
    CANONICAL_SCENARIOS,
)
def test_accumulated_state_times_do_not_exceed_simulation_time(
    scenario_file: str,
) -> None:
    """
    Comprueba que las duraciones acumuladas no incluyan
    intervalos ficticios adicionales.
    """

    result = run_scenario(
        scenario_name=scenario_file,
        save_results=False,
        playback_delay_s=0.0,
    )

    steps = result["steps"]
    summary = result["summary"]

    assert steps

    final_time_s = float(steps[-1]["time_s"])

    accumulated_time_s = sum(
        float(summary.get(field, 0.0) or 0.0)
        for field in (
            "tiempo_total_evasion_s",
            "tiempo_total_despeje_s",
            "tiempo_total_retorno_ruta_s",
        )
    )

    assert accumulated_time_s <= final_time_s + 1e-9, (
        f"Tiempo acumulado inválido en {scenario_file}: "
        f"{accumulated_time_s} > {final_time_s}"
    )


@pytest.mark.parametrize(
    "scenario_file",
    (
        "late_crossing_starboard_risk_nmea.txt",
        "close_crossing_starboard_risk_nmea.txt",
    ),
)
def test_stress_crossing_scenarios_produce_complete_results(
    scenario_file: str,
) -> None:
    """
    Los casos exigentes deben producir una evaluación completa.

    No se exige inicialmente que sean exitosos: su propósito es
    detectar los límites operacionales del algoritmo.
    """

    result = run_scenario(
        scenario_name=scenario_file,
        save_results=False,
        playback_delay_s=0.0,
    )

    summary = result["summary"]

    assert result["steps"]
    assert summary["encuentro_observado"] is not None
    assert summary["rol_observado"] is not None
    assert summary["accion_observada"] is not None
    assert summary["distancia_minima_m"] is not None
from __future__ import annotations

from usv_avoidance.simulation_runner import (
    list_scenarios,
    run_scenario,
)


SCENARIO_FILE = "multitarget_priority_test.txt"


def test_list_scenarios_includes_multitarget_scenario() -> None:
    scenario_files = {
        item.get("output_file")
        for item in list_scenarios()
    }

    assert SCENARIO_FILE in scenario_files


def test_run_scenario_returns_structured_result() -> None:
    result = run_scenario(
        scenario_name=SCENARIO_FILE,
        save_results=False,
        playback_delay_s=0.0,
    )

    assert result["scenario"]["file"] == SCENARIO_FILE
    assert result["config"]["playback_delay_s"] == 0.0
    assert result["steps"]
    assert result["summary"]
    assert result["metric_paths"] is None


def test_multitarget_scenario_contains_two_contacts() -> None:
    result = run_scenario(
        scenario_name=SCENARIO_FILE,
        save_results=False,
        playback_delay_s=0.0,
    )

    assert any(
        len(step.get("targets", [])) >= 2
        for step in result["steps"]
    )


def test_each_step_contains_navigation_output() -> None:
    result = run_scenario(
        scenario_name=SCENARIO_FILE,
        save_results=False,
        playback_delay_s=0.0,
    )

    required_keys = {
        "time_s",
        "ownship",
        "targets",
        "critical_target_mmsi",
        "state",
        "commanded_course_deg",
        "route_recovered",
        "avoidance_decision",
        "replanning",
        "replan_count",
        "active_course_evaluation",
    }

    assert all(
        required_keys.issubset(step)
        for step in result["steps"]
    )
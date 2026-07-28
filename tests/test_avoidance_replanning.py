import math
import unittest

from usv_avoidance.cpa_tcpa import EARTH_RADIUS_M
from usv_avoidance.replanning import (
    determine_replanning_need,
    evaluate_active_evasive_course,
)


PRIMARY_MMSI = 725000201
SECONDARY_MMSI = 725000202


def offset_m_to_latlon(
    *,
    ref_lat: float,
    ref_lon: float,
    east_m: float,
    north_m: float,
) -> tuple[float, float]:
    lat = ref_lat + math.degrees(
        north_m / EARTH_RADIUS_M
    )

    lon = ref_lon + math.degrees(
        east_m
        / (
            EARTH_RADIUS_M
            * math.cos(math.radians(ref_lat))
        )
    )

    return lat, lon


def make_assessment(
    mmsi: int,
) -> dict:
    return {
        "target": {
            "mmsi": mmsi,
        },
        "cpa_result": {
            "target_mmsi": mmsi,
        },
        "classification": {
            "risk": True,
            "should_maneuver": True,
        },
    }


class AvoidanceReplanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.primary_assessment = make_assessment(
            PRIMARY_MMSI
        )

    def test_initial_plan_is_required(self):
        replanning = determine_replanning_need(
            current_state="AVOIDING_TARGET",
            critical_assessment=(
                self.primary_assessment
            ),
            active_evasive_course_deg=None,
            active_avoidance_decision=None,
            active_course_evaluation=None,
        )

        self.assertTrue(
            replanning["replan_required"]
        )

        self.assertEqual(
            replanning["trigger"],
            "initial_plan",
        )

    def test_replan_is_required_when_priority_changes(
        self,
    ):
        new_assessment = make_assessment(
            SECONDARY_MMSI
        )

        active_decision = {
            "priority_target_mmsi": PRIMARY_MMSI,
            "candidate_is_safe": True,
        }

        active_course_evaluation = {
            "candidate_is_safe": True,
        }

        replanning = determine_replanning_need(
            current_state="AVOIDING_TARGET",
            critical_assessment=new_assessment,
            active_evasive_course_deg=20.0,
            active_avoidance_decision=active_decision,
            active_course_evaluation=(
                active_course_evaluation
            ),
        )

        self.assertTrue(
            replanning["replan_required"]
        )

        self.assertTrue(
            replanning["priority_changed"]
        )

        self.assertEqual(
            replanning["trigger"],
            "priority_changed",
        )

    def test_no_replan_when_plan_remains_safe(self):
        active_decision = {
            "priority_target_mmsi": PRIMARY_MMSI,
            "candidate_is_safe": True,
        }

        active_course_evaluation = {
            "candidate_is_safe": True,
        }

        replanning = determine_replanning_need(
            current_state="AVOIDING_TARGET",
            critical_assessment=(
                self.primary_assessment
            ),
            active_evasive_course_deg=20.0,
            active_avoidance_decision=active_decision,
            active_course_evaluation=(
                active_course_evaluation
            ),
        )

        self.assertFalse(
            replanning["replan_required"]
        )

        self.assertEqual(
            replanning["trigger"],
            "none",
        )

    def test_replan_when_active_course_becomes_unsafe(
        self,
    ):
        ownship = {
            "lat": -33.025000,
            "lon": -71.625000,
            "sog_kn": 6.0,
            "cog_deg": 0.0,
            "heading_deg": 0.0,
            "timestamp": 0.0,
        }

        primary_lat, primary_lon = (
            offset_m_to_latlon(
                ref_lat=ownship["lat"],
                ref_lon=ownship["lon"],
                east_m=300.0,
                north_m=300.0,
            )
        )

        primary_target = {
            "mmsi": PRIMARY_MMSI,
            "lat": primary_lat,
            "lon": primary_lon,
            "sog_kn": 6.0,
            "cog_deg": 270.0,
            "heading_deg": 270.0,
        }

        secondary_lat, secondary_lon = (
            offset_m_to_latlon(
                ref_lat=ownship["lat"],
                ref_lon=ownship["lon"],
                east_m=100.0,
                north_m=388.0,
            )
        )

        secondary_target = {
            "mmsi": SECONDARY_MMSI,
            "lat": secondary_lat,
            "lon": secondary_lon,
            "sog_kn": 0.0,
            "cog_deg": 0.0,
            "heading_deg": 0.0,
        }

        critical_assessment = {
            "target": primary_target,
            "cpa_result": {
                "target_mmsi": PRIMARY_MMSI,
            },
            "classification": {
                "risk": True,
                "should_maneuver": True,
            },
        }

        evaluation = evaluate_active_evasive_course(
            ownship=ownship,
            critical_assessment=(
                critical_assessment
            ),
            targets=[
                primary_target,
                secondary_target,
            ],
            active_evasive_course_deg=15.0,
            safety_radius_m=50.0,
            time_horizon_s=300.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
        )

        self.assertIsNotNone(evaluation)

        self.assertFalse(
            evaluation["candidate_is_safe"]
        )

        self.assertEqual(
            evaluation["blocking_target_mmsi"],
            SECONDARY_MMSI,
        )

        active_decision = {
            "priority_target_mmsi": PRIMARY_MMSI,
            # La maniobra había sido considerada segura cuando
            # fue creada.
            "candidate_is_safe": True,
        }

        replanning = determine_replanning_need(
            current_state="AVOIDING_TARGET",
            critical_assessment=(
                critical_assessment
            ),
            active_evasive_course_deg=15.0,
            active_avoidance_decision=active_decision,
            active_course_evaluation=evaluation,
        )

        self.assertTrue(
            replanning["replan_required"]
        )

        self.assertTrue(
            replanning[
                "active_course_became_unsafe"
            ]
        )

        self.assertEqual(
            replanning["trigger"],
            "active_course_became_unsafe",
        )


if __name__ == "__main__":
    unittest.main()
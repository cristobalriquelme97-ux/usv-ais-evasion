import unittest

from usv_avoidance.simulation_runner import run_scenario


SCENARIO_NAME = "multitarget_priority_test.txt"
EXPECTED_PRIORITY_MMSI = 725000102


class ManeuverDecisionDelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = run_scenario(
            SCENARIO_NAME,
            maneuver_decision_delay_s=20.0,
        )

        cls.steps_by_time = {
            step["time_s"]: step
            for step in result["steps"]
        }

    def test_usv_observes_before_maneuvering(self):
        for time_s in (
            0.0,
            5.0,
            10.0,
            15.0,
        ):
            with self.subTest(time_s=time_s):
                step = self.steps_by_time[time_s]

                self.assertEqual(
                    step["state"]["current_state"],
                    "ASSESSING_TARGET",
                )

                self.assertEqual(
                    step["commanded_course_deg"],
                    0.0,
                )

                self.assertIsNone(
                    step["avoidance_decision"]
                )

                self.assertEqual(
                    step["critical_target_mmsi"],
                    EXPECTED_PRIORITY_MMSI,
                )

    def test_maneuver_begins_at_twenty_seconds(self):
        step = self.steps_by_time[20.0]

        self.assertEqual(
            step["state"]["current_state"],
            "AVOIDING_TARGET",
        )

        self.assertEqual(
            step["state"]["active_target_mmsi"],
            EXPECTED_PRIORITY_MMSI,
        )

        self.assertEqual(
            step["state"][
                "decision_delay_remaining_s"
            ],
            0.0,
        )

        self.assertIsNotNone(
            step["avoidance_decision"]
        )

        self.assertNotEqual(
            step["commanded_course_deg"],
            0.0,
        )

    def test_usv_starts_turning_after_command(self):
        step_at_20 = self.steps_by_time[20.0]
        step_at_25 = self.steps_by_time[25.0]

        # El paso se registra antes del avance del USV.
        self.assertEqual(
            step_at_20["ownship"]["cog_deg"],
            0.0,
        )

        # Entre t=20 y t=25 se aplica la razón de giro.
        self.assertGreater(
            step_at_25["ownship"]["cog_deg"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
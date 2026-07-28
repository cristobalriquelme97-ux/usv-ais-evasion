import unittest

from usv_avoidance.simulation_runner import run_scenario


SCENARIO_NAME = "multitarget_priority_test.txt"

FAR_TARGET_MMSI = 725000101
NEAR_TARGET_MMSI = 725000102

EXPECTED_PRIORITY_MMSI = NEAR_TARGET_MMSI


class MultitargetPriorityScenarioTests(unittest.TestCase):
    """
    Prueba integrada del escenario multiblanco.

    Verifica que:

    1. Los dos contactos estén activos en el mismo frame.
    2. Ambos presenten riesgo y obligación de maniobra.
    3. El contacto cercano tenga menor TCPA.
    4. El algoritmo seleccione el MMSI con menor TCPA.
    5. La salida estructurada refleje el orden de prioridad.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_scenario(
            SCENARIO_NAME
        )

        cls.steps = cls.result["steps"]

        if not cls.steps:
            raise AssertionError(
                "El escenario no produjo pasos de simulación."
            )

        cls.first_step = cls.steps[0]

        cls.targets_by_mmsi = {
            target["mmsi"]: target
            for target in cls.first_step["targets"]
        }

    def test_scenario_contains_expected_number_of_frames(self):
        self.assertEqual(
            len(self.steps),
            41,
        )

        self.assertEqual(
            self.steps[0]["time_s"],
            0.0,
        )

        self.assertEqual(
            self.steps[-1]["time_s"],
            200.0,
        )

    def test_first_frame_contains_both_mmsi(self):
        active_mmsi = set(
            self.targets_by_mmsi
        )

        self.assertEqual(
            active_mmsi,
            {
                FAR_TARGET_MMSI,
                NEAR_TARGET_MMSI,
            },
        )

        self.assertEqual(
            len(self.first_step["targets"]),
            2,
        )

    def test_both_contacts_require_avoidance(self):
        for mmsi in (
            FAR_TARGET_MMSI,
            NEAR_TARGET_MMSI,
        ):
            target = self.targets_by_mmsi[mmsi]

            with self.subTest(mmsi=mmsi):
                self.assertTrue(
                    target["risk"]
                )

                self.assertTrue(
                    target["should_maneuver"]
                )

                self.assertEqual(
                    target["encounter_name"],
                    "cruce",
                )

                self.assertEqual(
                    target["ownship_role"],
                    "give_way",
                )

    def test_near_contact_has_smaller_tcpa(self):
        far_target = self.targets_by_mmsi[
            FAR_TARGET_MMSI
        ]

        near_target = self.targets_by_mmsi[
            NEAR_TARGET_MMSI
        ]

        self.assertGreater(
            far_target["tcpa_s"],
            near_target["tcpa_s"],
        )

        self.assertGreater(
            far_target["tcpa_s"],
            0.0,
        )

        self.assertGreater(
            near_target["tcpa_s"],
            0.0,
        )

    def test_contact_with_smaller_tcpa_is_selected(self):
        self.assertEqual(
            self.first_step["critical_target_mmsi"],
            EXPECTED_PRIORITY_MMSI,
        )

    def test_target_output_is_sorted_by_priority(self):
        ranked_targets = self.first_step[
            "targets"
        ]

        self.assertEqual(
            ranked_targets[0]["priority"],
            1,
        )

        self.assertEqual(
            ranked_targets[0]["mmsi"],
            EXPECTED_PRIORITY_MMSI,
        )

        self.assertEqual(
            ranked_targets[1]["priority"],
            2,
        )

        self.assertEqual(
            ranked_targets[1]["mmsi"],
            FAR_TARGET_MMSI,
        )


if __name__ == "__main__":
    unittest.main()
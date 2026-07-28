import unittest

from usv_avoidance.simulation_runner import (
    run_scenario,
)


SCENARIO_NAME = "multitarget_priority_test.txt"

EXPECTED_MMSI = {
    725000101,
    725000102,
}


class MultitargetMetricsIntegrationTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_scenario(
            SCENARIO_NAME,
            maneuver_decision_delay_s=20.0,
        )

        cls.summary = cls.result["summary"]

    def test_two_contacts_are_registered(self):
        self.assertEqual(
            self.summary[
                "contactos_unicos_detectados"
            ],
            2,
        )

        self.assertEqual(
            set(
                self.summary["mmsi_detectados"]
            ),
            EXPECTED_MMSI,
        )

    def test_maximum_simultaneous_contacts_is_two(self):
        self.assertEqual(
            self.summary[
                "max_contactos_activos_simultaneos"
            ],
            2,
        )

        self.assertGreater(
            self.summary["tiempo_multiblanco_s"],
            0.0,
        )

    def test_simultaneous_risk_is_recorded(self):
        self.assertEqual(
            self.summary[
                "max_contactos_en_riesgo_simultaneos"
            ],
            2,
        )

        self.assertGreater(
            self.summary[
                "tiempo_riesgo_simultaneo_s"
            ],
            0.0,
        )

    def test_global_minimum_identifies_a_target(self):
        self.assertIn(
            self.summary["mmsi_distancia_minima"],
            EXPECTED_MMSI,
        )

        self.assertIn(
            self.summary["mmsi_cpa_minimo"],
            EXPECTED_MMSI,
        )

    def test_per_target_minimums_are_available(self):
        distance_by_mmsi = self.summary[
            "distancia_minima_por_mmsi_m"
        ]

        cpa_by_mmsi = self.summary[
            "cpa_minimo_por_mmsi_m"
        ]

        self.assertEqual(
            set(distance_by_mmsi),
            {
                "725000101",
                "725000102",
            },
        )

        self.assertEqual(
            set(cpa_by_mmsi),
            {
                "725000101",
                "725000102",
            },
        )

    def test_replanning_metrics_are_consistent(self):
        self.assertGreaterEqual(
            self.summary[
                "cantidad_planes_evasivos"
            ],
            1,
        )

        self.assertGreaterEqual(
            self.summary[
                "cantidad_replanificaciones"
            ],
            0,
        )


if __name__ == "__main__":
    unittest.main()
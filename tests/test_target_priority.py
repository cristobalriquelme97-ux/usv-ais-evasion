import unittest

from usv_avoidance.target_priority import (
    rank_assessments,
    select_most_critical_assessment,
)


def make_assessment(
    *,
    mmsi: int,
    risk: bool,
    should_maneuver: bool,
    cpa_m: float,
    tcpa_s: float,
) -> dict:
    """
    Construye una evaluación mínima para probar la priorización
    sin ejecutar una simulación completa.
    """

    return {
        "target": {
            "mmsi": mmsi,
        },
        "cpa_result": {
            "target_mmsi": mmsi,
            "risk": risk,
            "cpa_m": cpa_m,
            "tcpa_s": tcpa_s,
        },
        "classification": {
            "risk": risk,
            "should_maneuver": should_maneuver,
        },
    }


class TargetPriorityTests(unittest.TestCase):
    def test_empty_list_returns_none(self):
        result = select_most_critical_assessment([])

        self.assertIsNone(result)

    def test_contact_with_risk_has_priority(self):
        safe_target = make_assessment(
            mmsi=725000001,
            risk=False,
            should_maneuver=False,
            cpa_m=20.0,
            tcpa_s=10.0,
        )

        risk_target = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=False,
            cpa_m=40.0,
            tcpa_s=60.0,
        )

        result = select_most_critical_assessment(
            [safe_target, risk_target]
        )

        self.assertEqual(
            result["target"]["mmsi"],
            725000002,
        )

    def test_give_way_contact_has_priority(self):
        stand_on_target = make_assessment(
            mmsi=725000001,
            risk=True,
            should_maneuver=False,
            cpa_m=20.0,
            tcpa_s=30.0,
        )

        give_way_target = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=True,
            cpa_m=40.0,
            tcpa_s=80.0,
        )

        result = select_most_critical_assessment(
            [stand_on_target, give_way_target]
        )

        self.assertEqual(
            result["target"]["mmsi"],
            725000002,
        )

    def test_smaller_positive_tcpa_has_priority(self):
        later_target = make_assessment(
            mmsi=725000001,
            risk=True,
            should_maneuver=True,
            cpa_m=20.0,
            tcpa_s=100.0,
        )

        earlier_target = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=True,
            cpa_m=35.0,
            tcpa_s=45.0,
        )

        result = select_most_critical_assessment(
            [later_target, earlier_target]
        )

        self.assertEqual(
            result["target"]["mmsi"],
            725000002,
        )

    def test_negative_tcpa_is_sent_to_end(self):
        passed_target = make_assessment(
            mmsi=725000001,
            risk=True,
            should_maneuver=True,
            cpa_m=5.0,
            tcpa_s=-10.0,
        )

        approaching_target = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=True,
            cpa_m=30.0,
            tcpa_s=70.0,
        )

        result = select_most_critical_assessment(
            [passed_target, approaching_target]
        )

        self.assertEqual(
            result["target"]["mmsi"],
            725000002,
        )

    def test_smaller_cpa_breaks_equal_tcpa(self):
        target_one = make_assessment(
            mmsi=725000001,
            risk=True,
            should_maneuver=True,
            cpa_m=45.0,
            tcpa_s=60.0,
        )

        target_two = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=True,
            cpa_m=25.0,
            tcpa_s=60.0,
        )

        result = select_most_critical_assessment(
            [target_one, target_two]
        )

        self.assertEqual(
            result["target"]["mmsi"],
            725000002,
        )

    def test_rank_assessments_returns_complete_order(self):
        target_one = make_assessment(
            mmsi=725000001,
            risk=True,
            should_maneuver=True,
            cpa_m=30.0,
            tcpa_s=80.0,
        )

        target_two = make_assessment(
            mmsi=725000002,
            risk=True,
            should_maneuver=True,
            cpa_m=40.0,
            tcpa_s=40.0,
        )

        target_three = make_assessment(
            mmsi=725000003,
            risk=False,
            should_maneuver=False,
            cpa_m=100.0,
            tcpa_s=20.0,
        )

        ranked = rank_assessments(
            [target_one, target_three, target_two]
        )

        ranked_mmsi = [
            assessment["target"]["mmsi"]
            for assessment in ranked
        ]

        self.assertEqual(
            ranked_mmsi,
            [
                725000002,
                725000001,
                725000003,
            ],
        )


if __name__ == "__main__":
    unittest.main()
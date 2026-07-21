import unittest

from usv_avoidance.encounter_classifier import classify_encounter


class TestEncounterClassifier(unittest.TestCase):

    def setUp(self) -> None:
        self.ownship = {
            "lat": -33.025,
            "lon": -71.625,
            "sog_kn": 6.0,
            "cog_deg": 0.0,
            "heading_deg": 0.0,
        }

        self.target = {
            "mmsi": 725000001,
            "lat": -33.020,
            "lon": -71.620,
            "sog_kn": 6.0,
            "cog_deg": 90.0,
            "heading_deg": 90.0,
        }

        self.risk = {
            "risk": True,
        }

    def test_crossing_starboard(self) -> None:
        bearing_info = {
            "relative_bearing_deg": 45.0,
            "relative_bearing_360_deg": 45.0,
            "side": "estribor",
            "sector": "starboard_bow_beam",
        }

        result = classify_encounter(
            ownship=self.ownship,
            target=self.target,
            cpa_result=self.risk,
            bearing_info=bearing_info,
        )

        self.assertEqual(result["encounter_type"], "crossing")
        self.assertEqual(result["ownship_role"], "give_way")
        self.assertTrue(result["should_maneuver"])

    def test_crossing_port(self) -> None:
        bearing_info = {
            "relative_bearing_deg": -45.0,
            "relative_bearing_360_deg": 315.0,
            "side": "babor",
            "sector": "port_beam_bow",
        }

        result = classify_encounter(
            ownship=self.ownship,
            target=self.target,
            cpa_result=self.risk,
            bearing_info=bearing_info,
        )

        self.assertEqual(result["encounter_type"], "crossing")
        self.assertEqual(result["ownship_role"], "stand_on")
        self.assertFalse(result["should_maneuver"])

    def test_ahead_starboard_non_reciprocal(self) -> None:
        bearing_info = {
            "relative_bearing_deg": 10.0,
            "relative_bearing_360_deg": 10.0,
            "side": "estribor",
            "sector": "ahead",
        }

        result = classify_encounter(
            ownship=self.ownship,
            target=self.target,
            cpa_result=self.risk,
            bearing_info=bearing_info,
        )

        self.assertEqual(result["encounter_type"], "crossing")
        self.assertEqual(result["ownship_role"], "give_way")

    def test_no_risk(self) -> None:
        bearing_info = {
            "relative_bearing_deg": 45.0,
            "relative_bearing_360_deg": 45.0,
            "side": "estribor",
            "sector": "starboard_bow_beam",
        }

        result = classify_encounter(
            ownship=self.ownship,
            target=self.target,
            cpa_result={"risk": False},
            bearing_info=bearing_info,
        )

        self.assertEqual(result["encounter_type"], "safe")
        self.assertEqual(result["ownship_role"], "none")
        self.assertFalse(result["should_maneuver"])


if __name__ == "__main__":
    unittest.main()
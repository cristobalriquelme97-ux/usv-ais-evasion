import unittest

from usv_avoidance.encounter_geometry import classify_bearing_sector


class TestBearingSector(unittest.TestCase):

    def test_ahead_sector(self) -> None:
        self.assertEqual(classify_bearing_sector(0.0), "ahead")
        self.assertEqual(classify_bearing_sector(22.499), "ahead")
        self.assertEqual(classify_bearing_sector(337.5), "ahead")
        self.assertEqual(classify_bearing_sector(359.999), "ahead")
        self.assertEqual(classify_bearing_sector(360.0), "ahead")
        self.assertEqual(classify_bearing_sector(-1.0), "ahead")

    def test_starboard_bow_beam_sector(self) -> None:
        self.assertEqual(
            classify_bearing_sector(22.5),
            "starboard_bow_beam",
        )
        self.assertEqual(
            classify_bearing_sector(45.0),
            "starboard_bow_beam",
        )
        self.assertEqual(
            classify_bearing_sector(89.999),
            "starboard_bow_beam",
        )

    def test_starboard_quarter_sector(self) -> None:
        self.assertEqual(
            classify_bearing_sector(90.0),
            "starboard_quarter",
        )
        self.assertEqual(
            classify_bearing_sector(112.499),
            "starboard_quarter",
        )

    def test_astern_sector(self) -> None:
        self.assertEqual(classify_bearing_sector(112.5), "astern")
        self.assertEqual(classify_bearing_sector(180.0), "astern")
        self.assertEqual(classify_bearing_sector(247.499), "astern")

    def test_port_quarter_sector(self) -> None:
        self.assertEqual(
            classify_bearing_sector(247.5),
            "port_quarter",
        )
        self.assertEqual(
            classify_bearing_sector(269.999),
            "port_quarter",
        )

    def test_port_beam_bow_sector(self) -> None:
        self.assertEqual(
            classify_bearing_sector(270.0),
            "port_beam_bow",
        )
        self.assertEqual(
            classify_bearing_sector(337.499),
            "port_beam_bow",
        )


if __name__ == "__main__":
    unittest.main()
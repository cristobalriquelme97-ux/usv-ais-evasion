import math
import unittest

from usv_avoidance.avoidance import (
    evaluate_course_candidate,
    recommend_avoidance_maneuver,
)
from usv_avoidance.cpa_tcpa import EARTH_RADIUS_M


PRIMARY_MMSI = 725000201
SECONDARY_MMSI = 725000202


def offset_m_to_latlon(
    *,
    ref_lat: float,
    ref_lon: float,
    east_m: float,
    north_m: float,
) -> tuple[float, float]:
    """
    Convierte un desplazamiento local Este/Norte en latitud y
    longitud para construir el escenario unitario.
    """

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


class MultitargetAvoidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ownship = {
            "lat": -33.025000,
            "lon": -71.625000,
            "sog_kn": 6.0,
            "cog_deg": 0.0,
            "heading_deg": 0.0,
            "timestamp": 0.0,
        }

        primary_lat, primary_lon = offset_m_to_latlon(
            ref_lat=self.ownship["lat"],
            ref_lon=self.ownship["lon"],
            east_m=300.0,
            north_m=300.0,
        )

        self.primary_target = {
            "mmsi": PRIMARY_MMSI,
            "lat": primary_lat,
            "lon": primary_lon,
            "sog_kn": 6.0,
            "cog_deg": 270.0,
            "heading_deg": 270.0,
        }

        # Este contacto se sitúa sobre la trayectoria que seguiría
        # el USV al ejecutar una caída de 15°.
        secondary_lat, secondary_lon = offset_m_to_latlon(
            ref_lat=self.ownship["lat"],
            ref_lon=self.ownship["lon"],
            east_m=100.0,
            north_m=388.0,
        )

        self.secondary_target = {
            "mmsi": SECONDARY_MMSI,
            "lat": secondary_lat,
            "lon": secondary_lon,
            "sog_kn": 0.0,
            "cog_deg": 0.0,
            "heading_deg": 0.0,
        }

        self.classification = {
            "risk": True,
            "should_maneuver": True,
            "ownship_role": "give_way",
            "encounter_type": "crossing_starboard",
            "encounter_name": "cruce",
        }

        self.state_info = {
            "current_state": "AVOIDING_TARGET",
        }

    def test_candidate_safe_for_primary_but_unsafe_for_secondary(
        self,
    ):
        primary_only = evaluate_course_candidate(
            ownship=self.ownship,
            target=self.primary_target,
            course_change_deg=15.0,
            safety_radius_m=50.0,
            time_horizon_s=300.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
        )

        multitarget = evaluate_course_candidate(
            ownship=self.ownship,
            target=self.primary_target,
            targets=[
                self.primary_target,
                self.secondary_target,
            ],
            course_change_deg=15.0,
            safety_radius_m=50.0,
            time_horizon_s=300.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
        )

        # La caída de 15° es aceptable si solo observamos el
        # contacto prioritario.
        self.assertTrue(
            primary_only["candidate_is_safe"]
        )

        self.assertGreaterEqual(
            primary_only["projected_cpa_m"],
            50.0,
        )

        # La misma caída debe rechazarse cuando se considera el
        # contacto secundario.
        self.assertFalse(
            multitarget["candidate_is_safe"]
        )

        self.assertLess(
            multitarget["projected_cpa_m"],
            50.0,
        )

        self.assertEqual(
            multitarget["blocking_target_mmsi"],
            SECONDARY_MMSI,
        )

        self.assertIn(
            SECONDARY_MMSI,
            multitarget["unsafe_target_mmsi"],
        )

    def test_recommendation_rejects_unsafe_candidate(
        self,
    ):
        primary_only = recommend_avoidance_maneuver(
            ownship=self.ownship,
            target=self.primary_target,
            classification=self.classification,
            state_info=self.state_info,
            safety_radius_m=50.0,
            time_horizon_s=300.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
            starboard_changes_deg=(
                15.0,
                25.0,
            ),
        )

        multitarget = recommend_avoidance_maneuver(
            ownship=self.ownship,
            target=self.primary_target,
            targets=[
                self.primary_target,
                self.secondary_target,
            ],
            classification=self.classification,
            state_info=self.state_info,
            safety_radius_m=50.0,
            time_horizon_s=300.0,
            dt_s=5.0,
            turn_rate_deg_s=1.0,
            starboard_changes_deg=(
                15.0,
                25.0,
            ),
        )

        # Considerando solo el primario, la primera alternativa
        # segura es una caída de 15°.
        self.assertEqual(
            primary_only["course_change_deg"],
            15.0,
        )

        # Al incorporar el contacto secundario, 15° se rechaza y
        # se selecciona la siguiente alternativa segura.
        self.assertEqual(
            multitarget["course_change_deg"],
            25.0,
        )

        self.assertTrue(
            multitarget["candidate_is_safe"]
        )

        candidate_results = multitarget[
            "candidate_results"
        ]

        self.assertEqual(
            candidate_results[0]["course_change_deg"],
            15.0,
        )

        self.assertFalse(
            candidate_results[0]["candidate_is_safe"]
        )

        self.assertEqual(
            candidate_results[0][
                "blocking_target_mmsi"
            ],
            SECONDARY_MMSI,
        )

        self.assertEqual(
            candidate_results[1]["course_change_deg"],
            25.0,
        )

        self.assertTrue(
            candidate_results[1]["candidate_is_safe"]
        )


if __name__ == "__main__":
    unittest.main()
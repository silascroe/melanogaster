"""Focused checks for the portable offline v1.0 pathway projection."""

import unittest

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection


class PursuitActivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection = ActivityProjection.from_packaged_data()

    def test_packaged_circuit_and_map_align(self) -> None:
        self.assertEqual(len(self.projection.body_ids), 275)
        self.assertEqual(self.projection.lc_to_aotu.shape, (275, 4))
        self.assertEqual(self.projection.aotu_to_dn.shape, (4, 2))
        self.assertEqual(int(self.projection.lc_to_aotu.sum()), 21241)
        self.assertEqual(int(np.abs(self.projection.aotu_to_dn).sum()), 987)

    def test_default_candidate_has_bilateral_spatial_split(self) -> None:
        """Catch an accidental reversion to the earlier 5-60 degree map."""
        for side, sign in (("L", -1), ("R", 1)):
            angles = sign * np.arange(1.0, 166.0)
            response = self.projection.fixed_fly(angles)["aotu_contact_drive"]
            peaks = {}
            for kind in ("AOTU019", "AOTU025"):
                column = next(i for i, pair in enumerate(zip(
                    self.projection.aotu_types, self.projection.aotu_sides))
                    if pair == (kind, side))
                peaks[kind] = int(abs(angles[np.argmax(response[:, column])]))
            self.assertGreaterEqual(peaks["AOTU025"] - peaks["AOTU019"], 30)

    def test_bilateral_bridge_interventions(self) -> None:
        bearings = np.array([-25.0, 0.0, 25.0])
        intact = self.projection.fixed_fly(bearings)
        removed = self.projection.fixed_fly(bearings, bridge="removed")
        swapped = self.projection.fixed_fly(bearings, bridge="side_swapped")
        signed = intact["dna02_right_minus_left"]
        self.assertLess(signed[0], 0)
        self.assertEqual(signed[1], 0)
        self.assertGreater(signed[2], 0)
        np.testing.assert_array_equal(removed["dna02_right_minus_left"], np.zeros(3))
        np.testing.assert_allclose(swapped["dna02_right_minus_left"], -signed)

    def test_reset_is_deterministic(self) -> None:
        bearings = np.array([10.0, 25.0, 40.0])
        first = self.projection.fixed_fly(bearings)
        self.projection.fixed_fly(np.array([-80.0]))
        second = self.projection.fixed_fly(bearings)
        for key in first:
            np.testing.assert_array_equal(first[key], second[key])

    def test_invalid_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.projection.fixed_fly(np.array([181.0]))
        with self.assertRaises(ValueError):
            self.projection.fixed_fly(np.array([25.0]), bridge="unknown")
        with self.assertRaises(ValueError):
            self.projection.fixed_fly(np.array([25.0]), width_deg=0)


if __name__ == "__main__":
    unittest.main()

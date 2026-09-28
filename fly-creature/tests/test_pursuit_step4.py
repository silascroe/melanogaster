"""Focused checks of the frozen offline Step 4 adapter."""

import unittest

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_reference import _nearest_lookup
from fly_creature.pursuit_step4 import (
    ActivityAdapter, _nearest_elu, run_trial, shuffled_projection, target_x,
)


class Step4AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection = ActivityProjection.from_packaged_data()
        cls.adapter = ActivityAdapter.build(cls.projection)

    def test_lookup_matches_reference_nearest_rule(self) -> None:
        grid, values = self.adapter.lookups["AOTU019"]
        for raw in np.linspace(0, self.adapter.peaks["AOTU019"], 17):
            expected = float(_nearest_lookup(grid, values, np.array([raw]))[0])
            self.assertEqual(_nearest_elu(grid, values, float(raw)), expected)

    def test_bridge_and_signs(self) -> None:
        self.assertGreater(self.adapter.activity_at(30)["signal"], 0)
        self.assertLess(self.adapter.activity_at(-30)["signal"], 0)
        for angle in (-70, -30, 30, 70):
            self.assertEqual(self.adapter.activity_at(
                angle, condition="bridge_removed")["signal"], 0.0)

    def test_shuffle_preserves_bundle_multiset_by_side(self) -> None:
        shuffled = shuffled_projection(self.projection,
                                       np.random.default_rng(20260927))
        self.assertFalse(np.array_equal(shuffled.lc_to_aotu,
                                        self.projection.lc_to_aotu))
        for side in ("L", "R"):
            rows = self.projection.sides == side
            original = sorted(map(tuple, self.projection.lc_to_aotu[rows]))
            changed = sorted(map(tuple, shuffled.lc_to_aotu[rows]))
            self.assertEqual(original, changed)

    def test_heldout_paths_are_mirrored(self) -> None:
        for name in ("chirp", "triangle", "offset", "step_hold"):
            for t in (0.0, 1.5, 4.0, 7.9):
                self.assertAlmostEqual(target_x(name, t),
                                       -target_x("mirror_" + name, t))

    def test_removed_bridge_cannot_turn(self) -> None:
        result = run_trial("step_hold", "bridge_removed", adapter=self.adapter)
        self.assertEqual(result["mean_abs_turn_rate_rad_s"], 0.0)
        self.assertEqual(result["final_heading_deg"], 0.0)


if __name__ == "__main__":
    unittest.main()

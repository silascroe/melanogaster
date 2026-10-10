"""Actual failed/revised feedback loops and boundary/queue controls."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_delay_diagnostic import (
    DECLARED, FRESH_PATHS, Timing, fresh_target, overlap_adapter, simulate,
)
from fly_creature.pursuit_step4 import ActivityAdapter, PRIMARY_PATHS, run_trial


class DelayDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = ActivityAdapter.build(ActivityProjection.from_packaged_data())
        cls.overlap = overlap_adapter(cls.base, 15)

    def test_frozen_baseline_matches_on_all_original_paths(self):
        for path in PRIMARY_PATHS:
            old = run_trial(path, "intact", adapter=self.base)
            new = simulate(path, self.base, Timing())
            for key in old.keys() & new.keys():
                self.assertEqual(old[key], new[key], (path, key))

    def test_original_failure_and_revised_continuous_residence(self):
        for path in ("step_hold", "mirror_step_hold"):
            old = simulate(path, self.base, Timing())
            self.assertIsNone(old["settling_time_s"])
            self.assertEqual(old["near_target_sign_crossings"], 9)
            new = simulate(path, self.overlap, DECLARED)
            self.assertIsNotNone(new["settling_time_s"])
            self.assertLessEqual(new["peak_after_settling_deg"], 10)
            self.assertLess(new["last_second_peak_abs_bearing_deg"], 2)

    def test_overlap_changes_center_without_renormalizing_or_rewiring(self):
        self.assertEqual(self.base.peaks, self.overlap.peaks)
        np.testing.assert_array_equal(self.base.output_edges, self.overlap.output_edges)
        np.testing.assert_allclose(self.base.response[:173], self.overlap.response[:173])
        np.testing.assert_allclose(self.base.response[188:], self.overlap.response[188:])
        old_jump = abs(self.base.activity_at(1)["signal"] - self.base.activity_at(-1)["signal"])
        new_jump = abs(self.overlap.activity_at(1)["signal"] - self.overlap.activity_at(-1)["signal"])
        self.assertLess(new_jump, old_jump / 3)

    def test_motor_delay_is_zero_padded_and_removed_bridge_stays_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.json"
            simulate("step_hold", self.overlap, DECLARED, trace_path=trace)
            rows = json.loads(trace.read_text())
            self.assertTrue(all(r["turn_rate_rad_s"] == 0 for r in rows[:20]))
            self.assertNotEqual(rows[20]["turn_rate_rad_s"], 0)
        for timing in (Timing(), DECLARED, Timing(200, 200, 15)):
            result = simulate("step_hold", self.overlap, timing, condition="bridge_removed")
            self.assertEqual(result["mean_abs_turn_rate_rad_s"], 0)

    def test_paths_and_delay_validation(self):
        self.assertFalse(set(FRESH_PATHS) & set(PRIMARY_PATHS))
        for p in FRESH_PATHS[::2]:
            for t in (0, 1.5, 3, 4.5, 5, 8):
                self.assertEqual(fresh_target(p, t), -fresh_target("mirror_" + p, t))
        for kwargs in ({"visual_ms": -10}, {"motor_ms": 11}, {"motor_ms": 20.0},
                       {"overlap_deg": float("nan")}):
            with self.assertRaises(ValueError):
                Timing(**kwargs)

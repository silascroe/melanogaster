"""Check diagnostic fairness and scoring, without tuning the frozen runtime."""
import math
import unittest

from fly_creature.pursuit_stress import Case, Direct, cases, envelope, trial


class StressTests(unittest.TestCase):
    def test_case_count_reflection_and_dropout_boundaries(self):
        suite = cases()
        self.assertEqual(len(suite), 48)
        self.assertEqual(sum(c.supported for c in suite), 36)
        self.assertEqual(len({c.name for c in suite}), 48)
        for case in suite:
            mirrored = Case(case.family, case.level, not case.mirror)
            self.assertAlmostEqual(case.heading, -mirrored.heading)
            for t in (0.01, 4, 4.2, 6, 10):
                a, b = case.target(t), mirrored.target(t)
                self.assertAlmostEqual(a["x"], -b["x"])
                self.assertEqual(a["z"], b["z"])
                self.assertEqual(a["active"], b["active"])
        case = Case("dropout", .8)
        self.assertFalse(case.target(4)["active"])
        self.assertFalse(case.target(4.79)["active"])
        self.assertTrue(case.target(4.8)["active"])

    def test_matched_queue_and_inactive_reset(self):
        controller = Direct(2)
        fly = {"x": 0, "z": 0, "heading_rad": 0}
        target = {"x": 2, "z": -6, "active": True}
        for _ in range(20):
            self.assertEqual(controller.step(fly, target, 10)["turn_rate_rad_s"], 0)
        self.assertAlmostEqual(controller.step(fly, target, 10)["turn_rate_rad_s"], 2 * math.atan2(2, 6))
        target["active"] = False
        self.assertEqual(controller.step(fly, target, 10)["turn_rate_rad_s"], 0)
        self.assertEqual(len(controller.queue), 0)
        target["active"] = True
        self.assertEqual(controller.step(fly, target, 10)["turn_rate_rad_s"], 0)

    def test_invisible_ticks_are_scored_and_mirrors_match_for_direct(self):
        result = trial(Case("unsupported", "behind"), Direct(2), steps=100)
        self.assertEqual(result["active_in_view_fraction"], 0)
        self.assertEqual(result["active_mean_abs_bearing_deg"], 180)
        self.assertFalse(result["within_envelope"])
        a = trial(Case("speed", 1.7), Direct(2), steps=200)
        b = trial(Case("speed", 1.7, True), Direct(2), steps=200)
        self.assertEqual(a["active_mean_abs_bearing_deg"], b["active_mean_abs_bearing_deg"])

    def test_recovery_failure_is_not_hidden_by_mean_error(self):
        metrics = {"active_mean_abs_bearing_deg": 1, "active_in_view_fraction": 1,
                   "turn_cap_fraction": 0, "aotu_clip_fraction": 0,
                   "dn_clip_fraction": 0, "inactive_turn_ticks": 0, "reacquisition_s": None}
        self.assertFalse(envelope(metrics, True)["reacquisition"])
        self.assertTrue(envelope(metrics, False)["reacquisition"])


if __name__ == "__main__":
    unittest.main()

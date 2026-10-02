import math
import unittest

from fly_creature.playground import MODELS, OrdinarySession, PlaygroundSession
from fly_creature.pursuit_stress import Case, Direct, activity_session, trial
from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_step4 import ActivityAdapter
from fly_creature.pursuit_delay_diagnostic import overlap_adapter


class PlaygroundTests(unittest.TestCase):
    def test_actual_parallel_world_matches_frozen_case_results(self):
        adapter = overlap_adapter(ActivityAdapter.build(ActivityProjection.from_packaged_data()), 15)
        for preset, family, level, depth in (("gentle", "speed", .35, 6),
                ("fast", "speed", 3, 6), ("reversal", "reversal", 2, 6),
                ("dropout", "dropout", .8, 6), ("reentry", "reentry", .8, 6),
                ("stationary", "stationary_depth", 5, 5)):
            for mirror in (False, True):
                world = PlaygroundSession({"preset": preset, "depth": depth, "mirror": mirror})
                case = Case(family, level, mirror)
                controllers = {}
                controllers["intact"], _ = activity_session(adapter)
                controllers["disconnected"], _ = activity_session(adapter, "disconnected")
                controllers["ordinary_delayed"] = Direct(4)
                controllers["ordinary_immediate"] = Direct(4, 0)
                for sequence in range(1, 201):
                    out = world.step({"ticks": 5, "sequence": sequence})
                self.assertTrue(out["done"])
                for name in MODELS:
                    expected = trial(case, controllers[name])
                    self.assertAlmostEqual(out["models"][name]["mean_error_deg"],
                                           expected["active_mean_abs_bearing_deg"], places=5,
                                           msg=f"{preset}/{mirror}/{name}")
                    self.assertEqual(out["models"][name]["steering"]["model_time_ms"], 10000)

    def test_batch_size_does_not_change_state(self):
        a, b = PlaygroundSession({}), PlaygroundSession({})
        for i in range(1, 51):
            a.step({"ticks": 1, "sequence": i})
        for i in range(1, 11):
            b.step({"ticks": 5, "sequence": i})
        self.assertEqual(a.snapshot()["models"], b.snapshot()["models"])
        self.assertEqual(a.target, b.target)

    def test_sequence_validation_idempotency_and_no_partial_bad_request(self):
        world = PlaygroundSession({})
        before = world.snapshot()
        for payload in ({"ticks": 6, "sequence": 1}, {"ticks": True, "sequence": 1},
                        {"ticks": 1, "sequence": 2}, {"ticks": 1, "sequence": 1,
                         "manual_target": {"x": math.nan, "z": 0}}):
            with self.assertRaises(ValueError): world.step(payload)
            self.assertEqual(world.snapshot(), before)
        payload = {"ticks": 5, "sequence": 1}
        first = world.step(payload)
        self.assertEqual(world.step(payload), first)
        self.assertEqual(world.tick, 5)
        with self.assertRaises(ValueError): world.step({"ticks": 1, "sequence": 1})

    def test_manual_hide_clears_every_pending_turn(self):
        world = PlaygroundSession({"preset": "manual"})
        for i in range(1, 10):
            world.step({"sequence": i, "ticks": 5, "manual_target": {"x": 2, "z": -6}})
        out = world.step({"sequence": 10, "ticks": 1, "target_enabled": False})
        self.assertFalse(out["target"]["active"])
        self.assertTrue(all(b["steering"]["turn_rate_rad_s"] == 0 for b in out["models"].values()))
        self.assertTrue(all(len(c.queue) == 0 for c in world.controllers.values()))

    def test_ordinary_runtime_is_identical_to_frozen_comparator(self):
        for delay in (0, 20):
            a, b = OrdinarySession(delay), Direct(4, delay)
            for tick in range(100):
                fly = {"x": .1, "z": -.2, "heading_rad": .1}
                target = {"x": math.sin(tick), "z": -6, "active": not 40 <= tick < 60}
                self.assertEqual(a.step(fly, target, 10)["turn_rate_rad_s"],
                                 b.step(fly, target, 10)["turn_rate_rad_s"])

    def test_hidden_and_manual_inputs_survive_creation(self):
        world = PlaygroundSession({"preset": "manual", "target_enabled": False,
                                   "manual_target": {"x": 3, "z": -5}})
        self.assertEqual(world.snapshot()["target"], {"x": 3, "z": -5, "active": False})
        self.assertEqual(world.tick, 0)
        with self.assertRaises(ValueError):
            PlaygroundSession({"target_enabled": "false"})


if __name__ == "__main__": unittest.main()

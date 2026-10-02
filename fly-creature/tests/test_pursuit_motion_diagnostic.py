import math
import unittest

from fly_creature.pursuit_controller import ActivitySteeringSession
from fly_creature.pursuit_motion_diagnostic import (
    MotionSession, delta_angle, fresh_cases, geometry_probes, model,
)
from fly_creature.pursuit_stress import Case


class MotionDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = model()

    def test_baseline_matches_actual_session_every_tick(self):
        for case in (Case("speed", 3), Case("reentry", .8), Case("heading", 105)):
            actual = ActivitySteeringSession()
            diagnostic = MotionSession(self.adapter)
            x = z = heading = turn = 0.
            for tick in range(1000):
                heading += turn * .01
                x += math.sin(heading) * .0055
                z -= math.cos(heading) * .0055
                fly = {"x": x, "z": z, "heading_rad": heading + case.heading}
                target = case.target((tick + 1) * .01)
                a = actual.step(fly, target, 10)
                b = diagnostic.step(fly, target, 10)
                self.assertEqual(a["turn_rate_rad_s"], b["turn_rate_rad_s"])
                self.assertEqual(a["right_minus_left_activity"], b["signal"])
                turn = a["turn_rate_rad_s"]

    def test_geometry_includes_self_motion_and_isolates_target_motion(self):
        result = geometry_probes(self.adapter)
        self.assertAlmostEqual(result["static_target_rotating_body"]["motion_deg"], -math.degrees(.01))
        self.assertEqual(result["static_target_rotating_body"]["target_only_motion_deg"], 0.)
        self.assertGreater(result["moving_target_fixed_body"]["motion_deg"], 0)
        self.assertAlmostEqual(result["moving_target_fixed_body"]["motion_deg"],
                         result["moving_target_fixed_body"]["target_only_motion_deg"])
        self.assertTrue(all(r > 1 for r in result["preferred_nonpreferred_aotu019_ratio"].values()))

    def test_motion_history_reset_on_visibility_loss(self):
        session = MotionSession(self.adapter, "continuous_visible")
        fly = {"x": 0., "z": 0., "heading_rad": 0.}
        near = {"x": 2., "z": -6., "active": True}
        session.step(fly, near, 10)
        session.step(fly, {**near, "z": -20.}, 10)
        self.assertEqual(session.step(fly, near, 10)["motion_deg"], 0.)
        session.step(fly, {**near, "active": False}, 10)
        self.assertEqual(len(session.queue), 0)
        self.assertIsNone(session.previous_bearing)
        self.assertAlmostEqual(delta_angle(-179, 179), 2.)

    def test_fresh_case_reflections_and_inputs(self):
        suite = fresh_cases()
        self.assertEqual(len(suite), 12)
        for case in suite:
            other = next(c for c in suite if c.family == case.family and c.depth == case.depth and c.mirror != case.mirror)
            for t in (.01, 3.7, 10):
                a, b = case.target(t), other.target(t)
                self.assertEqual(a["x"], -b["x"])
                self.assertEqual(a["z"], b["z"])
        with self.assertRaises(ValueError):
            MotionSession(self.adapter, "invented")
        with self.assertRaises(ValueError):
            MotionSession(self.adapter).step({}, {}, 11)

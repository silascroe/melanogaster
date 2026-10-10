"""Controller parity at the actual CreatureSession/Godot input seam."""
import math
import unittest

from fly_creature.circuit import load_circuit
from fly_creature.controller import CreatureSession
from fly_creature.pursuit_controller import ActivitySteeringSession
from fly_creature.pursuit_delay_diagnostic import DECLARED, FRESH_PATHS, fresh_target, overlap_adapter, simulate
from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_step4 import ActivityAdapter, target_x
from fly_creature.steering import SteeringSession
from fly_creature.steering_diagnostic import load_candidate


class ControllerTests(unittest.TestCase):
    def test_actual_session_matches_frozen_candidate_on_all_evaluation_paths(self):
        model = overlap_adapter(ActivityAdapter.build(ActivityProjection.from_packaged_data()), 15)
        for path in (*FRESH_PATHS, "step_hold", "mirror_step_hold"):
            session = CreatureSession(load_circuit(), steering_model="activity_v1")
            x = z = heading = turn = total = 0.0
            for tick in range(800):
                heading += turn * .01
                x += math.sin(heading) * .55 * .01
                z -= math.cos(heading) * .55 * .01
                t = (tick + 1) * .01
                tx = fresh_target(path, t) if path in FRESH_PATHS else target_x(path, t)
                out = session.step({"dt_ms": 10,
                    "fly": {"x": x, "z": z, "heading_rad": heading},
                    "object": {"x": 0, "z": -7, "radius": .45, "active": False},
                    "target": {"x": tx, "z": -7, "active": True}})["steering"]
                total += abs(out["bearing_deg"])
                turn = out["turn_rate_rad_s"]
            expected = simulate(path, model, DECLARED, fresh=path in FRESH_PATHS)
            self.assertEqual(round(total / 800, 3), expected["mean_abs_bearing_deg"], path)

    def test_disconnect_and_target_off_cannot_leave_a_queued_turn(self):
        fly = {"x": 0, "z": 0, "heading_rad": 0}
        target = {"x": 2, "z": -7, "active": True}
        disconnected = ActivitySteeringSession(condition="disconnected")
        intact = ActivitySteeringSession()
        for _ in range(25):
            self.assertEqual(disconnected.step(fly, target, 10)["turn_rate_rad_s"], 0)
            intact.step(fly, target, 10)
        self.assertGreater(intact.step(fly, target, 10)["turn_rate_rad_s"], 0)
        target["active"] = False
        self.assertEqual(intact.step(fly, target, 10)["turn_rate_rad_s"], 0)
        self.assertEqual(len(intact.queue), 0)
        with self.assertRaises(ValueError):
            intact.step(fly, target, 50)

    def test_baseline_is_still_default_and_units_are_explicit(self):
        session = CreatureSession(load_circuit(), steering_circuit=load_candidate())
        self.assertIsInstance(session.steering, SteeringSession)
        out = ActivitySteeringSession().step({"x": 0, "z": 0, "heading_rad": 0},
                                             {"x": 1, "z": -7, "active": True}, 10)
        self.assertIn("DNa02_activity", out)
        self.assertNotIn("DNa02_mean_mv", out)

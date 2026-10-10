"""Steering-only comparison world; authored motion and frozen controller settings."""
from collections import deque
from copy import deepcopy
import math
import time

from .pursuit_controller import ActivitySteeringSession
from .steering import target_feature

MODELS = ("intact", "disconnected", "ordinary_delayed", "ordinary_immediate")
PRESETS = ("gentle", "fast", "reversal", "dropout", "reentry", "stationary", "manual")
DT = .01
DURATION_TICKS = 1000


class OrdinarySession:
    """Gain 4 was selected on older paths in the frozen stress experiment."""
    def __init__(self, delay):
        self.delay = delay
        self.queue = deque()
        self.elapsed_ms = 0

    def step(self, fly, target, dt_ms):
        if dt_ms != 10:
            raise ValueError("Comparison requires exact 10 ms ticks")
        f = target_feature(fly, target)
        seen = target["active"] and .4 <= f["distance"] <= 9 and abs(f["bearing_deg"]) <= 120
        command = max(-1.2, min(1.2, 4 * math.radians(f["bearing_deg"]))) if seen else 0.0
        self.queue.append(command)
        turn = self.queue.popleft() if len(self.queue) > self.delay else 0.0
        if not target["active"]:
            self.queue.clear()
            turn = 0.0
        self.elapsed_ms += 10
        return {"model": "ordinary_delayed" if self.delay else "ordinary_immediate",
                "bearing_deg": f["bearing_deg"], "in_view": seen,
                "turn_rate_rad_s": turn, "model_time_ms": self.elapsed_ms,
                "motor_delay_ms": self.delay * 10, "readout": "ordinary proportional rule; no neurons"}


class PlaygroundSession:
    def __init__(self, config):
        self.preset = str(config.get("preset", "gentle"))
        if self.preset not in PRESETS:
            raise ValueError("Unknown comparison preset")
        self.depth = float(config.get("depth", 6))
        self.heading = float(config.get("heading_deg", 0))
        self.mirror = config.get("mirror", False)
        if not isinstance(self.mirror, bool):
            raise ValueError("mirror must be boolean")
        if not math.isfinite(self.depth) or not 3 <= self.depth <= 8:
            raise ValueError("depth must be between 3 and 8 m")
        if not math.isfinite(self.heading) or not -105 <= self.heading <= 105:
            raise ValueError("heading must be between -105 and 105 degrees")
        self.controllers = {"intact": ActivitySteeringSession(),
                            "disconnected": ActivitySteeringSession(condition="disconnected"),
                            "ordinary_delayed": OrdinarySession(20),
                            "ordinary_immediate": OrdinarySession(0)}
        initial = math.radians(self.heading) * (-1 if self.mirror else 1)
        self.bodies = {name: {"x": 0.0, "z": 0.0, "heading_rad": initial,
                             "turn": 0.0, "error_sum": 0.0, "samples": 0,
                             "seen": 0, "caps": 0, "readout": {}} for name in MODELS}
        self.tick = self.sequence = 0
        manual = config.get("manual_target", {"x": 1.5, "z": -self.depth})
        if not isinstance(manual, dict):
            raise ValueError("manual_target must be an object")
        mx, mz = float(manual["x"]), float(manual["z"])
        if not all(math.isfinite(v) and abs(v) <= 100 for v in (mx, mz)):
            raise ValueError("Manual target coordinates must be finite and within 100 m")
        self.enabled = config.get("target_enabled", True)
        if type(self.enabled) is not bool:
            raise ValueError("target_enabled must be boolean")
        self.manual = {"x": mx, "z": mz, "active": self.enabled}
        self.target = self.target_at(0)
        self.last_payload = self.last_reply = None

    def target_at(self, t):
        x = 1.6 * math.sin(.93 * t + .4) + .45 * math.sin(2.7 * t - .2)
        z = -self.depth - .55 * t
        active = self.enabled
        if self.preset in ("gentle", "fast"):
            frequency = .35 if self.preset == "gentle" else 3.0
            x = 2.2 * math.sin(frequency * t - .6) + .4 * math.sin(1.9 * frequency * t + .1)
        elif self.preset == "reversal":
            x = 1.8 * (1 - 4 * abs((t / 2) % 1 - .5))
        elif self.preset in ("dropout", "reentry"):
            active = active and not (4 <= t < 4.8)
            if self.preset == "reentry":
                x = -2 if t < 4 else 2 + .5 * math.sin(1.3 * (t - 4))
        elif self.preset == "stationary":
            z = -self.depth
        elif self.preset == "manual":
            return {**self.manual, "active": self.enabled}
        return {"x": -x if self.mirror else x, "z": z, "active": active}

    def step(self, payload):
        # Validate before mutating any clock/controller; same sequence is idempotent.
        ticks = payload.get("ticks", 1)
        sequence = payload.get("sequence")
        if type(ticks) is not int or not 1 <= ticks <= 5:
            raise ValueError("ticks must be an integer between 1 and 5")
        if type(sequence) is not int:
            raise ValueError("sequence must be an integer")
        if sequence == self.sequence and self.last_reply is not None:
            if payload != self.last_payload:
                raise ValueError("Repeated sequence has different inputs")
            return self.last_reply
        if sequence != self.sequence + 1:
            raise ValueError("Out-of-order comparison request")
        enabled = payload.get("target_enabled", True)
        if type(enabled) is not bool:
            raise ValueError("target_enabled must be boolean")
        manual = payload.get("manual_target", self.manual)
        if not isinstance(manual, dict):
            raise ValueError("manual_target must be an object")
        mx, mz = float(manual["x"]), float(manual["z"])
        if not all(math.isfinite(v) and abs(v) <= 100 for v in (mx, mz)):
            raise ValueError("Manual target coordinates must be finite and within 100 m")
        self.enabled = enabled
        self.manual = {"x": mx, "z": mz, "active": enabled}
        started = time.perf_counter()
        count = min(ticks, DURATION_TICKS - self.tick)
        for _ in range(count):
            self.tick += 1
            self.target = self.target_at(self.tick * DT)
            for name, body in self.bodies.items():
                h = body["heading_rad"] + body["turn"] * DT
                body["heading_rad"] = math.atan2(math.sin(h), math.cos(h))
                body["x"] += math.sin(h) * .55 * DT
                body["z"] -= math.cos(h) * .55 * DT
                out = self.controllers[name].step(body, self.target, 10)
                body["turn"] = out["turn_rate_rad_s"]
                body["readout"] = out
                body["caps"] += int(abs(body["turn"]) >= 1.2 - 1e-10)
                if self.target["active"]:
                    body["samples"] += 1
                    body["error_sum"] += abs(out["bearing_deg"])
                    body["seen"] += int(out["in_view"])
        self.sequence = sequence
        reply = self.snapshot()
        reply["advanced_ticks"] = count
        reply["compute_ms"] = (time.perf_counter() - started) * 1000
        self.last_payload = deepcopy(payload)
        self.last_reply = reply
        return reply

    def snapshot(self):
        return {"tick": self.tick, "time_s": self.tick * DT, "sequence": self.sequence,
                "done": self.tick == DURATION_TICKS, "preset": self.preset,
                "target": dict(self.target), "models": {
                    name: {"x": b["x"], "z": b["z"], "heading_rad": b["heading_rad"],
                           "steering": dict(b["readout"]),
                           "mean_error_deg": b["error_sum"] / b["samples"] if b["samples"] else None,
                           "visible_fraction": b["seen"] / b["samples"] if b["samples"] else None,
                           "active_samples": b["samples"],
                           "cap_fraction": b["caps"] / self.tick if self.tick else 0.0}
                    for name, b in self.bodies.items()},
                "contract": {"dt_ms": 10, "walk_speed_m_s": .55,
                             "ordinary_gain": 4, "steering_only": True}}

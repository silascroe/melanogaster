"""Experimental stateful activity controller, in explicit model activity units."""
from collections import deque
import math

from .pursuit_activity import ActivityProjection
from .pursuit_delay_diagnostic import DECLARED, overlap_adapter
from .pursuit_step4 import ActivityAdapter, AUTHOR_GAIN, DT, MAX_TURN_RATE, VIEW_DEG
from .steering import target_feature


class ActivitySteeringSession:
    def __init__(self, *, condition="intact"):
        if condition not in ("intact", "disconnected"):
            raise ValueError("Unknown activity controller condition")
        self.condition = condition
        self.adapter = overlap_adapter(ActivityAdapter.build(
            ActivityProjection.from_packaged_data()), DECLARED.overlap_deg)
        self.queue = deque()
        self.previous_bearing = None
        self.elapsed_ms = 0

    def step(self, fly, target, dt_ms):
        if dt_ms != 10:
            raise ValueError("activity_v1 requires exact 10 ms world steps")
        feature = target_feature(fly, target)
        visible = (bool(target.get("active", False)) and
                   0.4 <= feature["distance"] <= 9 and abs(feature["bearing_deg"]) <= VIEW_DEG)
        bearing = feature["bearing_deg"] if visible else 0.0
        motion = bearing - self.previous_bearing if self.previous_bearing is not None else 0.0
        self.previous_bearing = bearing
        result = self.adapter.activity_at(bearing, motion, condition=(
            "intact" if self.condition == "intact" else "bridge_removed"))
        signal = result["signal"] if visible else 0.0
        requested = math.radians(AUTHOR_GAIN * signal) / DT
        command = max(-MAX_TURN_RATE, min(MAX_TURN_RATE, requested))
        self.queue.append(command)
        turn = self.queue.popleft() if len(self.queue) > DECLARED.motor_ms // 10 else 0.0
        if not target.get("active", False):
            self.queue.clear()
            self.previous_bearing = None
            turn = 0.0
        self.elapsed_ms += 10
        return {"model": "activity_v1", "condition": self.condition,
                "in_view": visible, "bearing_deg": feature["bearing_deg"],
                "DNa02_activity": {"L": float(result["dn"][0]), "R": float(result["dn"][1])},
                "right_minus_left_activity": signal, "turn_rate_rad_s": turn,
                "model_time_ms": self.elapsed_ms,
                "motor_delay_ms": DECLARED.motor_ms, "overlap_deg": DECLARED.overlap_deg,
                "readout": "experimental normalized activity, not spikes or mV"}

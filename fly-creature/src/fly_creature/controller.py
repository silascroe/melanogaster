"""Explicit world -> visual cells -> giant fiber -> jump interface."""

from __future__ import annotations

import math
import numpy as np

from .circuit import Circuit
from .lif import LIFNetwork
from .steering import SteeringSession
from .pursuit_controller import ActivitySteeringSession


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


class CreatureSession:
    """One persistent neural state; the Godot client owns body and object state."""

    def __init__(self, circuit: Circuit, *, condition: str = "intact",
                 steering_circuit: Circuit | None = None,
                 steering_model: str = "lif") -> None:
        if condition not in ("intact", "disconnected"):
            raise ValueError("condition must be intact or disconnected")
        self.condition = condition
        if steering_model not in ("lif", "activity_v1"):
            raise ValueError("Unknown steering model")
        self.steering_model = steering_model
        self.network = LIFNetwork(circuit, connected=condition == "intact")
        self.steering = (SteeringSession(steering_circuit, condition=condition)
                         if steering_circuit is not None else None)
        if steering_model == "activity_v1":
            self.steering = ActivitySteeringSession(condition=condition)
        self.state = self.network.initial_state()
        groups = circuit.ids_by_type
        self.lc4 = np.asarray([self.network.index[i] for i in groups["LC4"]], dtype=np.int64)
        self.lplc2 = np.asarray([self.network.index[i] for i in groups["LPLC2"]], dtype=np.int64)
        self.gf = np.asarray([self.network.index[i] for i in groups["DNp01"]], dtype=np.int64)
        self.last_angle_deg: float | None = None
        self.cooldown_ms = 0.0

    def step(self, payload: dict[str, object]) -> dict[str, object]:
        fly = payload["fly"]
        obj = payload["object"]
        if not isinstance(fly, dict) or not isinstance(obj, dict):
            raise ValueError("fly and object must be objects")
        dt_ms = float(payload.get("dt_ms", 50.0))
        if not math.isfinite(dt_ms) or not 10.0 <= dt_ms <= 100.0:
            raise ValueError("dt_ms must be between 10 and 100")
        if self.steering_model == "activity_v1" and dt_ms != 10.0:
            raise ValueError("activity_v1 requires exact 10 ms world steps")
        x, z = float(fly["x"]), float(fly["z"])
        heading = float(fly["heading_rad"])
        object_x, object_z = float(obj["x"]), float(obj["z"])
        radius = float(obj["radius"])
        if not all(math.isfinite(v) for v in (x, z, heading, object_x, object_z, radius)):
            raise ValueError("World coordinates must be finite")
        if radius <= 0:
            raise ValueError("Object radius must be positive")

        dx, dz = object_x - x, object_z - z
        distance = max(0.001, math.hypot(dx, dz))
        # In this scene zero heading faces Godot's -Z direction.
        forward_dot = (dx * math.sin(heading) - dz * math.cos(heading)) / distance
        in_view = bool(obj.get("active", True)) and forward_dot >= math.cos(math.radians(65.0))
        angle_deg = math.degrees(2.0 * math.atan(radius / distance)) if in_view else 0.0
        expansion_deg_s = (
            max(0.0, (angle_deg - self.last_angle_deg) / (dt_ms / 1000.0))
            if in_view and self.last_angle_deg is not None else 0.0
        )
        self.last_angle_deg = angle_deg if in_view else None

        # The feature extraction is engineered. LC4 is driven by expansion
        # speed, LPLC2 by apparent size during expansion; the graph does not
        # receive pixels or simulate a retina.
        lc4_strength = _clamp01((expansion_deg_s - 5.0) / 80.0)
        lplc2_strength = (
            _clamp01((angle_deg - 8.0) / 25.0) if expansion_deg_s > 3.0 else 0.0
        )
        external = np.zeros(len(self.network.node_ids), dtype=np.float64)
        external[self.lc4] = 90.0 * lc4_strength
        external[self.lplc2] = 90.0 * lplc2_strength

        spike_counts = np.zeros(len(self.network.node_ids), dtype=np.int64)
        for _ in range(int(round(dt_ms))):
            spike_counts += self.network.step(self.state, external)
        lc4_spikes = int(spike_counts[self.lc4].sum())
        lplc2_spikes = int(spike_counts[self.lplc2].sum())
        gf_spikes = int(spike_counts[self.gf].sum())
        self.cooldown_ms = max(0.0, self.cooldown_ms - dt_ms)
        jump = gf_spikes > 0 and self.cooldown_ms == 0.0
        if jump:
            self.cooldown_ms = 1200.0
        # Per-side LC10a/AOTU/DNa02 activity is reported for the live brain view
        # only; it does not change what the steering circuit computes.
        steering_kwargs = {"record_cells": True} if self.steering_model == "lif" else {}
        steering = (self.steering.step(fly, payload.get("target", {"active": False}),
                                       int(round(dt_ms)), **steering_kwargs)
                    if self.steering is not None else None)
        return {
            "condition": self.condition,
            "visual": {
                "in_view": in_view,
                "angle_deg": round(angle_deg, 2),
                "expansion_deg_s": round(expansion_deg_s, 2),
            },
            "input_strength": {
                "LC4": round(lc4_strength, 3),
                "LPLC2": round(lplc2_strength, 3),
            },
            "spikes": {"LC4": lc4_spikes, "LPLC2": lplc2_spikes, "DNp01": gf_spikes},
            "jump": jump,
            "jump_rule": "DNp01 spike outside 1.2 s animation cooldown",
            **({"steering": steering} if steering is not None else {}),
        }

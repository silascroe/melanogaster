"""Engineered visual input and motor readout around a recorded steering route.

The MaleCNS supplies neuron IDs and edges. Object encoding, LIF dynamics,
voltage-to-turn gain, and movement are project choices, not fly measurements.
"""

from __future__ import annotations

import math

import numpy as np

from .circuit import Circuit
from .lif import LIFNetwork
from .steering_diagnostic import condition_circuit


INPUT_MV = 90.0
TURN_GAIN_RAD_S_PER_MV = 0.42
MAX_TURN_RATE_RAD_S = 1.2
VIEW_HALF_ANGLE_DEG = 65.0
FULL_INPUT_BEARING_DEG = 35.0


def _wrap_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def target_feature(fly: dict, target: dict) -> dict:
    """Engineered bearing feature shared by neural and direct controls."""
    if not isinstance(fly, dict) or not isinstance(target, dict):
        raise ValueError("Steering fly and target must be objects")
    values = (fly["x"], fly["z"], fly["heading_rad"],
              target.get("x", 0.0), target.get("z", 0.0))
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Steering positions and heading must be finite")
    dx = float(target.get("x", 0.0)) - float(fly["x"])
    dz = float(target.get("z", 0.0)) - float(fly["z"])
    heading = float(fly["heading_rad"])
    absolute_bearing = math.atan2(dx, -dz)
    bearing_deg = math.degrees(_wrap_angle(absolute_bearing - heading))
    distance = math.hypot(dx, dz)
    in_view = (bool(target.get("active", False)) and 0.4 <= distance <= 9.0
               and abs(bearing_deg) <= VIEW_HALF_ANGLE_DEG)
    strength = (min(1.0, max(0.0, (abs(bearing_deg) - 3.0)
                              / (FULL_INPUT_BEARING_DEG - 3.0)))
                if in_view else 0.0)
    return {"bearing_deg": bearing_deg, "distance": distance,
            "in_view": in_view, "strength": strength}


class SteeringSession:
    def __init__(self, circuit: Circuit, *, condition: str = "intact",
                 input_mv: float = INPUT_MV,
                 visual_centers_deg: dict[int, float] | None = None) -> None:
        if condition not in ("intact", "disconnected", "AOTU019_output_removed",
                             "AOTU025_output_removed", "bridge_side_swapped"):
            raise ValueError("Unknown steering condition")
        if not math.isfinite(input_mv) or input_mv < 0.0:
            raise ValueError("Steering input current must be finite and nonnegative")
        selected = condition_circuit(
            circuit, "bridge_removed" if condition == "disconnected" else condition
        )
        self.condition = condition
        self.input_mv = input_mv
        self.network = LIFNetwork(selected)
        self.state = self.network.initial_state()
        self.lc = {
            side: np.asarray([self.network.index[n.body_id] for n in selected.neurons
                              if n.cell_type == "LC10a" and n.side == side],
                             dtype=np.int64)
            for side in ("L", "R")
        }
        self.visual_centers = None
        if visual_centers_deg is not None:
            lc_ids = {n.body_id for n in selected.neurons if n.cell_type == "LC10a"}
            if set(visual_centers_deg) != lc_ids or any(
                not math.isfinite(center) or not 0.0 <= center <= VIEW_HALF_ANGLE_DEG
                for center in visual_centers_deg.values()
            ):
                raise ValueError("Visual centers must cover each LC10a ID with a finite in-view angle")
            self.visual_centers = {
                side: np.asarray([visual_centers_deg[n.body_id] for n in selected.neurons
                                  if n.cell_type == "LC10a" and n.side == side],
                                 dtype=np.float64)
                for side in ("L", "R")
            }
        self.dn = {
            side: self.network.index[next(n.body_id for n in selected.neurons
                    if n.cell_type == "DNa02" and n.side == side)]
            for side in ("L", "R")
        }
        self.aotu = {
            cell_type: {
                side: self.network.index[next(n.body_id for n in selected.neurons
                        if n.cell_type == cell_type and n.side == side)]
                for side in ("L", "R")
            }
            for cell_type in ("AOTU019", "AOTU025")
        }
        self.external = np.zeros(len(self.network.node_ids), dtype=np.float64)

    def step(self, fly: dict, target: dict, dt_ms: int, *,
             record_cells: bool = False,
             input_strength_override: float | None = None,
             visual_weights_override: np.ndarray | None = None) -> dict:
        if not 1 <= dt_ms <= 100:
            raise ValueError("Steering step must be 1 to 100 ms")
        feature = target_feature(fly, target)
        bearing_deg = feature["bearing_deg"]
        strength = feature["strength"]
        if input_strength_override is not None:
            if not math.isfinite(input_strength_override) or not 0.0 <= input_strength_override <= 1.0:
                raise ValueError("Input strength override must be finite and between zero and one")
            strength = input_strength_override if feature["in_view"] else 0.0
        self.external.fill(0.0)
        if bearing_deg < 0.0:
            side = "L"
        elif bearing_deg > 0.0:
            side = "R"
        else:
            side = None
        if side is not None and strength:
            if self.visual_centers is None:
                if visual_weights_override is not None:
                    raise ValueError("Per-cell weights require visual centers")
                self.external[self.lc[side]] = self.input_mv * strength
            else:
                # Experimental anatomical input: distribute the same total
                # side current by putative field center. The 18-degree width
                # and 0.1 floor are fixed model choices, not measured tuning.
                centers = self.visual_centers[side]
                if visual_weights_override is None:
                    weights = 0.1 + 0.9 * np.exp(-0.5 * ((abs(bearing_deg) - centers) / 18.0) ** 2)
                else:
                    weights = np.asarray(visual_weights_override, dtype=np.float64)
                    if (weights.shape != centers.shape or not np.all(np.isfinite(weights))
                            or np.any(weights < 0.0) or weights.mean() <= 0.0):
                        raise ValueError("Per-cell weights must be finite, nonnegative, and cover one side")
                self.external[self.lc[side]] = self.input_mv * strength * (weights / weights.mean())

        voltages = {"L": 0.0, "R": 0.0}
        dn_spikes = {"L": 0, "R": 0}
        if record_cells:
            aotu_voltage = {cell_type: {side: 0.0 for side in ("L", "R")}
                            for cell_type in self.aotu}
            aotu_spikes = {cell_type: {side: 0 for side in ("L", "R")}
                           for cell_type in self.aotu}
            lc_spikes = {side: 0 for side in ("L", "R")}
        for _ in range(dt_ms):
            fired = self.network.step(self.state, self.external)
            for side in ("L", "R"):
                voltages[side] += float(self.state.voltage_mv[self.dn[side]])
                dn_spikes[side] += int(fired[self.dn[side]])
                if record_cells:
                    lc_spikes[side] += int(fired[self.lc[side]].sum())
                    for cell_type in self.aotu:
                        index = self.aotu[cell_type][side]
                        aotu_voltage[cell_type][side] += float(self.state.voltage_mv[index])
                        aotu_spikes[cell_type][side] += int(fired[index])
        mean = {side: voltages[side] / dt_ms for side in ("L", "R")}
        right_minus_left = mean["R"] - mean["L"]
        turn_rate = max(-MAX_TURN_RATE_RAD_S,
                        min(MAX_TURN_RATE_RAD_S,
                            right_minus_left * TURN_GAIN_RAD_S_PER_MV))
        result = {
            "condition": self.condition,
            "in_view": feature["in_view"],
            "bearing_deg": round(bearing_deg, 2),
            "input_strength": {"L": round(strength if bearing_deg < 0 else 0.0, 3),
                               "R": round(strength if bearing_deg > 0 else 0.0, 3)},
            "DNa02_mean_mv": {side: round(mean[side], 4) for side in ("L", "R")},
            "DNa02_spikes": dn_spikes,
            "right_minus_left_mv": round(right_minus_left, 4),
            "turn_rate_rad_s": round(turn_rate, 4),
            "readout": "engineered DNa02 voltage-difference to turn-rate rule",
        }
        if record_cells:
            result["AOTU_mean_mv"] = {
                cell_type: {side: round(value / dt_ms, 4)
                            for side, value in sides.items()}
                for cell_type, sides in aotu_voltage.items()
            }
            result["AOTU_spikes"] = aotu_spikes
            result["LC10a_spikes"] = lc_spikes
        return result

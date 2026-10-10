"""Offline local LC10a motion input and new-path pursuit comparison.

Spatial centers are the upstream anatomical hypothesis. Temporal filtering,
50/50 current redistribution, LIF dynamics, and motor decoding are models.
The playable input remains unchanged unless a separately justified decision
promotes this candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

import numpy as np

from .pursuit_trust_audit import BASE_STEP_MS, DURATION_MS, WALK_SPEED_M_S
from .steering import MAX_TURN_RATE_RAD_S, SteeringSession, target_feature
from .steering_diagnostic import load_candidate
from .visual_input_experiment import SHUFFLE_SEEDS, shuffle_lc_wiring
from .visual_motion_experiment import MotionFeature, load_upstream_map


LOCAL_FRACTION = 0.5
PULSE_SPAN_DEG = 22.5
PULSE_SPEEDS_DEG_S = (25, 75)
PULSE_CENTERS_DEG = (25, 45)
PULSE_SIDES = ("L", "R")
PULSE_MOTIONS = ("static", "outward", "inward")
NEW_PATHS = ("weave", "offset_hop", "approach_arc", "lateral_drift", "flutter")


class LocalMotionInput:
    """Move half the side current toward cells the image is entering.

    The other half keeps the previous position distribution. A static image
    produces exactly the position distribution. Total side current is fixed.
    Neither the field width nor this mixture fraction was measured in flies.
    """

    def __init__(self) -> None:
        self.previous_side: str | None = None
        self.previous_weights: np.ndarray | None = None

    def weights(self, feature: dict, centers_by_side: dict[str, np.ndarray]) -> np.ndarray | None:
        if not feature["in_view"] or feature["strength"] <= 0:
            self.previous_side = None
            self.previous_weights = None
            return None
        bearing = feature["bearing_deg"]
        side = "R" if bearing > 0 else "L" if bearing < 0 else None
        if side is None:
            self.previous_side = None
            self.previous_weights = None
            return None
        centers = centers_by_side[side]
        position = 0.1 + 0.9 * np.exp(-0.5 * ((abs(bearing) - centers) / 18.0) ** 2)
        rising = None
        if self.previous_side == side and self.previous_weights is not None:
            rising = np.maximum(position - self.previous_weights, 0.0)
        self.previous_side = side
        self.previous_weights = position
        if rising is None or rising.sum() <= 1e-12:
            return position
        return ((1.0 - LOCAL_FRACTION) * position / position.mean()
                + LOCAL_FRACTION * rising / rising.mean())


def target_on_fixed_fly(side: str, angle_deg: float) -> dict:
    signed = math.radians(angle_deg if side == "R" else -angle_deg)
    return {"x": 5.0 * math.sin(signed), "z": -5.0 * math.cos(signed),
            "active": True}


def pulse_trial(circuit, centers: dict[int, float], *, side: str, center: int,
                motion: str, speed: int, input_kind: str) -> dict:
    neural = SteeringSession(circuit, visual_centers_deg=centers)
    encoder = LocalMotionInput()
    fly = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
    for _ in range(100 // BASE_STEP_MS):
        neural.step(fly, {"x": 0.0, "z": -5.0, "active": False}, BASE_STEP_MS)
    duration_ms = round(PULSE_SPAN_DEG / speed * 1000)
    frames = duration_ms // BASE_STEP_MS
    lc = a019 = a025 = dn_spikes = 0
    dn_bias = []
    total_current = []
    changed_frames = 0
    for frame in range(frames):
        fraction = (frame + 0.5) / frames
        angle = (float(center) if motion == "static" else
                 center - PULSE_SPAN_DEG / 2 + fraction * PULSE_SPAN_DEG
                 if motion == "outward" else
                 center + PULSE_SPAN_DEG / 2 - fraction * PULSE_SPAN_DEG)
        target = target_on_fixed_fly(side, angle)
        feature = target_feature(fly, target)
        weights = encoder.weights(feature, neural.visual_centers) if input_kind == "local" else None
        if weights is not None:
            base = 0.1 + 0.9 * np.exp(-0.5 * ((angle - neural.visual_centers[side]) / 18.0) ** 2)
            changed_frames += int(not np.allclose(weights / weights.mean(), base / base.mean()))
        trace = neural.step(fly, target, BASE_STEP_MS, record_cells=True,
                            input_strength_override=1.0,
                            visual_weights_override=weights)
        total_current.append(float(neural.external[neural.lc[side]].sum()))
        lc += trace["LC10a_spikes"][side]
        a019 += trace["AOTU_spikes"]["AOTU019"][side]
        a025 += trace["AOTU_spikes"]["AOTU025"][side]
        dn_spikes += sum(trace["DNa02_spikes"].values())
        dn_bias.append((1 if side == "R" else -1) * trace["right_minus_left_mv"])
    expected_current = len(neural.lc[side]) * neural.input_mv
    if not np.allclose(total_current, expected_current, atol=1e-7):
        raise RuntimeError("Local input changed total side current")
    return {"duration_ms": duration_ms, "frames_with_local_redistribution": changed_frames,
            "mean_total_LC10a_current_mv": round(mean(total_current), 3),
            "LC10a_spikes": lc, "AOTU019_spikes": a019, "AOTU025_spikes": a025,
            "DNa02_spikes": dn_spikes,
            "mean_toward_DNa02_voltage_bias_mv": round(mean(dn_bias), 4)}


def target_path(path: str, t: float) -> dict:
    if path == "weave":
        x, z = 2.6 * math.sin(0.42 * t) + 0.6 * math.sin(1.35 * t + 0.4), -6.6
    elif path == "offset_hop":
        x, z = (-1.5 if t < 2 else 1.2 if t < 4 else
                -0.8 if t < 6 else 2.0), -6.3
    elif path == "approach_arc":
        x, z = 2.4 * math.sin(0.55 * t - 0.7), -7.8 + 0.4 * t
    elif path == "lateral_drift":
        x, z = -3.2 + 0.8 * t + 0.45 * math.sin(1.1 * t), -6.5
    elif path == "flutter":
        x, z = 0.9 * math.sin(1.3 * t) + 0.8 * math.sin(0.35 * t - 1.0), -5.5
    else:
        raise ValueError(path)
    return {"x": x, "z": z, "active": True}


def pursuit_trial(circuit, centers: dict[int, float], path: str, kind: str) -> dict:
    neural = None if kind == "direct" else SteeringSession(
        circuit, visual_centers_deg=None if kind == "uniform" else centers,
        condition="disconnected" if kind == "local_disconnected" else "intact")
    local = LocalMotionInput()
    global_motion = MotionFeature()
    x = z = heading = turn_rate = 0.0
    errors, currents, view_frames = [], [], 0
    dn_spikes = 0
    local_frames = 0
    dt_s = BASE_STEP_MS / 1000.0
    for frame in range(DURATION_MS // BASE_STEP_MS):
        heading = math.atan2(math.sin(heading + turn_rate * dt_s),
                             math.cos(heading + turn_rate * dt_s))
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        fly = {"x": x, "z": z, "heading_rad": heading}
        target = target_path(path, (frame + 1) * dt_s)
        feature = target_feature(fly, target)
        if neural is None:
            turn_rate = (math.copysign(MAX_TURN_RATE_RAD_S * feature["strength"],
                                       feature["bearing_deg"])
                         if feature["strength"] else 0.0)
        else:
            weights = None
            if kind in ("local", "local_disconnected"):
                weights = local.weights(feature, neural.visual_centers)
                local_frames += int(weights is not None)
            strength = (global_motion.strength(fly, target, BASE_STEP_MS)[0]
                        if kind == "global_motion" else None)
            trace = neural.step(fly, target, BASE_STEP_MS,
                                input_strength_override=strength,
                                visual_weights_override=weights)
            turn_rate = trace["turn_rate_rad_s"]
            dn_spikes += sum(trace["DNa02_spikes"].values())
            if feature["in_view"] and feature["strength"]:
                side = "R" if feature["bearing_deg"] > 0 else "L"
                currents.append(float(neural.external[neural.lc[side]].sum()))
        errors.append(abs(feature["bearing_deg"]))
        view_frames += int(feature["in_view"])
    return {"mean_abs_bearing_deg": round(mean(errors), 3),
            "in_view_fraction": round(view_frames / len(errors), 3),
            "mean_active_side_current_mv": round(mean(currents), 3) if currents else None,
            "local_active_frames": local_frames,
            "DNa02_spikes": dn_spikes if neural is not None else None}


def run() -> dict:
    circuit = load_candidate()
    centers, mapping = load_upstream_map(circuit)
    fixed = {}
    for side in PULSE_SIDES:
        for center in PULSE_CENTERS_DEG:
            for speed in PULSE_SPEEDS_DEG_S:
                for motion in PULSE_MOTIONS:
                    key = f"{side}:{center}:{speed}:{motion}"
                    fixed[key] = {
                        kind: pulse_trial(circuit, centers, side=side, center=center,
                                          motion=motion, speed=speed, input_kind=kind)
                        for kind in ("position", "local")
                    }
    shuffled = {seed: shuffle_lc_wiring(circuit, seed) for seed in SHUFFLE_SEEDS}
    pursuit = {}
    for path in NEW_PATHS:
        trials = {kind: pursuit_trial(circuit, centers, path, kind)
                  for kind in ("direct", "uniform", "position", "global_motion",
                               "local", "local_disconnected")}
        trials["local_shuffled"] = {
            str(seed): pursuit_trial(shuffled[seed], centers, path, "local")[
                "mean_abs_bearing_deg"] for seed in SHUFFLE_SEEDS}
        trials["local_shuffled_median"] = round(median(trials["local_shuffled"].values()), 3)
        pursuit[path] = trials
    scores = {kind: round(mean(row[kind]["mean_abs_bearing_deg"]
                               for row in pursuit.values()), 3)
              for kind in ("direct", "uniform", "position", "global_motion",
                           "local", "local_disconnected")}
    scores["local_shuffled_median"] = round(mean(
        row["local_shuffled_median"] for row in pursuit.values()), 3)
    wins = {
        f"versus_{kind}": sum(row["local"]["mean_abs_bearing_deg"]
                             < (row[kind] if kind == "local_shuffled_median" else
                                row[kind]["mean_abs_bearing_deg"])
                             for row in pursuit.values())
        for kind in ("position", "uniform", "direct", "local_shuffled_median")
    }
    promote = (all(scores["local"] < scores[kind]
                   for kind in ("position", "uniform", "direct"))
               and all(count >= 3 for count in wins.values()))
    return {
        "question": "Can fixed-charge local LC10a motion input improve pursuit through the selected MaleCNS wiring?",
        "status": "offline candidate; playable default unchanged",
        "map_sha256": hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest(),
        "protocol": {
            "input": "At each 20ms step, split 50% of the existing side current by the "
                     "position weights and 50% by positive per-cell change in those weights. "
                     "If no weights rise, use position only. Side current is preserved.",
            "input_caveat": "The 18-degree field width, 0.1 floor, 50/50 split, and "
                           "rank-to-angle map are engineered. Retinal self-motion is not separated.",
            "fixed_fly": "100ms baseline; static or 22.5-degree inward/outward sweep at 25/75deg/s, "
                         "full matched mean side current, 20ms world / 1ms LIF steps.",
            "new_paths": list(NEW_PATHS),
            "path_duration_ms": DURATION_MS,
            "controls": "Playable uniform input, upstream position only, previous global speed gate, "
                        "direct-bearing software rule, bridge removal, and 12 within-side LC10a "
                        "output-bundle shuffles. Neural model and voltage decoder held fixed.",
            "predeclared_promotion_gate": "Local input must beat position, playable uniform, "
                                          "and direct control in mean bearing error and on at least "
                                          "3/5 new paths each; beat shuffle median on at least 3/5. "
                                          "Otherwise stay offline.",
        },
        "fixed_fly": fixed,
        "pursuit": pursuit,
        "mean_pursuit_error_deg": scores,
        "decision": {"promote_to_playable": promote, "path_wins_out_of_five": wins},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mean_pursuit_error_deg": result["mean_pursuit_error_deg"],
                      "decision": result["decision"]}, indent=2))


if __name__ == "__main__":
    main()

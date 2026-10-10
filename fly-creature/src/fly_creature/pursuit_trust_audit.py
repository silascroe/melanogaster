"""Controlled closed-loop audit of the existing pursuit demonstration.

Vary one factor at a time. The direct-bearing control uses the same engineered
view gate, bearing dead zone, and maximum turn rate but no connectome wiring.
Nothing here changes the playable Godot scene's default configuration.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
from statistics import mean, median

from .steering import (INPUT_MV, MAX_TURN_RATE_RAD_S, SteeringSession,
                       target_feature)
from .steering_diagnostic import load_candidate


BASE_STEP_MS = 50
DURATION_MS = 8000
WALK_SPEED_M_S = 0.55
CONDITIONS = ("intact", "disconnected", "bridge_side_swapped", "direct_bearing")
CHECKPOINT_MS = (0, 1000, 2000, 4000, 6000, 8000)
PATHS = ("crossing", "mirrored", "faster", "slower", "narrow", "stationary",
         "absent")
INPUT_MV_VALUES = (30.0, 45.0, 60.0, 75.0, 90.0, 120.0)
STEP_MS_VALUES = (25, 50, 100)


def target_at(path: str, time_s: float) -> dict:
    if path == "crossing":
        x = 3.2 * math.sin(0.62 * time_s - 1.2)
    elif path == "mirrored":
        x = -3.2 * math.sin(0.62 * time_s - 1.2)
    elif path == "faster":
        x = 3.2 * math.sin(0.90 * time_s - 1.2)
    elif path == "slower":
        x = 3.2 * math.sin(0.35 * time_s - 1.2)
    elif path == "narrow":
        x = 1.2 * math.sin(0.62 * time_s - 1.2)
    elif path == "stationary":
        x = -2.5
    elif path == "absent":
        return {"x": 0.0, "z": -6.5, "active": False}
    else:
        raise ValueError(f"Unknown target path: {path}")
    return {"x": x, "z": -6.5, "active": True}


def run_trial(circuit, *, path: str, condition: str, input_mv: float,
              step_ms: int) -> dict:
    if DURATION_MS % step_ms:
        raise ValueError("Step size must divide the fixed eight-second horizon")
    neural = (SteeringSession(circuit, condition=condition, input_mv=input_mv)
              if condition != "direct_bearing" else None)
    x = z = heading = turn_rate = 0.0
    bearing_values: list[float] = []
    turn_values: list[float] = []
    in_view_count = 0
    dn_spikes = {"L": 0, "R": 0}
    checkpoints = []
    steps = DURATION_MS // step_ms
    for frame in range(steps):
        dt_s = step_ms / 1000.0
        # Match Godot: apply the preceding command, move the body and target,
        # then compute the next neural command from the new world state.
        heading = math.atan2(math.sin(heading + turn_rate * dt_s),
                             math.cos(heading + turn_rate * dt_s))
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        elapsed_ms = (frame + 1) * step_ms
        target = target_at(path, elapsed_ms / 1000.0)
        fly = {"x": x, "z": z, "heading_rad": heading}
        feature = target_feature(fly, target)
        if neural is None:
            turn_rate = (math.copysign(MAX_TURN_RATE_RAD_S * feature["strength"],
                                       feature["bearing_deg"])
                         if feature["strength"] else 0.0)
        else:
            trace = neural.step(fly, target, step_ms)
            turn_rate = trace["turn_rate_rad_s"]
            for side in ("L", "R"):
                dn_spikes[side] += trace["DNa02_spikes"][side]
        bearing = feature["bearing_deg"]
        in_view = feature["in_view"]
        if target["active"]:
            bearing_values.append(abs(bearing))
            in_view_count += int(in_view)
        turn_values.append(abs(turn_rate))
        if elapsed_ms in CHECKPOINT_MS:
            checkpoints.append({"time_s": elapsed_ms / 1000.0,
                                "bearing_deg": round(bearing, 3),
                                "fly_x": round(x, 3),
                                "heading_deg": round(math.degrees(heading), 3),
                                "turn_rate_rad_s": round(turn_rate, 4)})
    return {
        "mean_abs_bearing_deg": round(mean(bearing_values), 3) if bearing_values else None,
        "median_abs_bearing_deg": round(median(bearing_values), 3) if bearing_values else None,
        "p90_abs_bearing_deg": (round(sorted(bearing_values)[int(0.9 * (len(bearing_values) - 1))], 3)
                                if bearing_values else None),
        "final_abs_bearing_deg": round(bearing_values[-1], 3) if bearing_values else None,
        "in_view_fraction": round(in_view_count / len(bearing_values), 3)
                            if bearing_values else None,
        "mean_abs_turn_rate_rad_s": round(mean(turn_values), 4),
        "DNa02_spikes": dn_spikes if neural is not None else None,
        "final_fly_x": round(x, 3),
        "final_heading_deg": round(math.degrees(heading), 3),
        "checkpoints": checkpoints,
    }


def run() -> dict:
    circuit = load_candidate()
    source = Path(str(files("fly_creature").joinpath("data/visual_steering_v1.json")))
    experiments = {}
    for path in PATHS:
        experiments[f"path:{path}"] = {
            condition: run_trial(circuit, path=path, condition=condition,
                                 input_mv=INPUT_MV, step_ms=BASE_STEP_MS)
            for condition in CONDITIONS
        }
    for input_mv in INPUT_MV_VALUES:
        experiments[f"input_mv:{input_mv:g}"] = {
            condition: run_trial(circuit, path="crossing", condition=condition,
                                 input_mv=input_mv, step_ms=BASE_STEP_MS)
            for condition in CONDITIONS
        }
    for step_ms in STEP_MS_VALUES:
        experiments[f"step_ms:{step_ms}"] = {
            condition: run_trial(circuit, path="crossing", condition=condition,
                                 input_mv=INPUT_MV, step_ms=step_ms)
            for condition in CONDITIONS
        }
    baseline = experiments["path:crossing"]
    if baseline != experiments["input_mv:90"] or baseline != experiments["step_ms:50"]:
        raise RuntimeError("Repeated baseline changed across factor sweeps")
    return {
        "purpose": "Pursuit behavior trust audit, not biological validation",
        "circuit": {"neurons": len(circuit.neurons),
                    "edges": len(circuit.connections),
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "protocol": {
            "duration_ms": DURATION_MS, "walk_speed_m_s": WALK_SPEED_M_S,
            "baseline": {"path": "crossing", "input_mv": INPUT_MV,
                         "step_ms": BASE_STEP_MS},
            "path_sweep": list(PATHS),
            "input_sweep_mv": list(INPUT_MV_VALUES),
            "timing_sweep_ms": list(STEP_MS_VALUES),
            "factor_rule": "Only path, input current, or step duration changes within its sweep.",
            "controls": {
                "disconnected": "Remove AOTU-to-DNa02 bridges; retain LC10a-to-AOTU edges.",
                "bridge_side_swapped": "Keep synapse counts and signs, swap DNa02 destinations.",
                "direct_bearing": "No neural graph; same view gate/dead zone and 1.2 rad/s cap, "
                                  "turn rate is signed 1.2 times encoded bearing strength. "
                                  "The direct rule is fixed across all sweeps.",
            },
            "metric": "Mean absolute target bearing over all active frames, including out-of-view frames; "
                      "lower is better only for centering, not overall biological behavior.",
        },
        "experiments": experiments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {condition: row["mean_abs_bearing_deg"]
                            for condition, row in trials.items()}
                      for key, trials in result["experiments"].items()}, indent=2))


if __name__ == "__main__":
    main()

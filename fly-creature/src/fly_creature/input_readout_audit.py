"""Offline, paired audit of LC10a input strength and DNa02 motor readout.

The visual variants see identical poses in the paired replay. The spike-only
readout is a diagnostic counterfactual, not a proposed animal motor model.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean

from .pursuit_trust_audit import BASE_STEP_MS, DURATION_MS, WALK_SPEED_M_S
from .steering import MAX_TURN_RATE_RAD_S, SteeringSession, target_feature
from .steering_diagnostic import load_candidate
from .visual_input_experiment import NEW_PATHS, trial_target
from .visual_motion_experiment import MotionFeature, load_upstream_map


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def direct_trajectory(path: str) -> list[tuple[dict, dict]]:
    """Record one common trajectory without consulting any neural output."""
    x = z = heading = turn_rate = 0.0
    dt_s = BASE_STEP_MS / 1000.0
    samples = []
    for frame in range(DURATION_MS // BASE_STEP_MS):
        heading = wrap(heading + turn_rate * dt_s)
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        fly = {"x": x, "z": z, "heading_rad": heading}
        target = trial_target(path, (frame + 1) * dt_s)
        feature = target_feature(fly, target)
        turn_rate = (math.copysign(MAX_TURN_RATE_RAD_S * feature["strength"],
                                   feature["bearing_deg"])
                     if feature["strength"] else 0.0)
        samples.append((fly, target))
    return samples


def paired_replay(circuit, centers: dict[int, float],
                  samples: list[tuple[dict, dict]], input_kind: str) -> dict:
    neural = SteeringSession(circuit, visual_centers_deg=centers)
    motion = MotionFeature()
    strengths, base_strengths, retinal_speeds = [], [], []
    object_speeds, heading_speeds, biases = [], [], []
    lc_spikes = a019_spikes = a025_spikes = dn_spikes = 0
    nonzero_voltage = correct_voltage_sign = wrong_voltage_sign = eligible = saturated = 0
    previous_world_bearing = previous_heading = None
    for fly, target in samples:
        feature = target_feature(fly, target)
        motion_strength, retinal_speed = motion.strength(fly, target, BASE_STEP_MS)
        strength = feature["strength"] if input_kind == "position" else motion_strength
        trace = neural.step(fly, target, BASE_STEP_MS, record_cells=True,
                            input_strength_override=strength)
        if feature["in_view"]:
            strengths.append(strength)
            base_strengths.append(feature["strength"])
            retinal_speeds.append(retinal_speed)
            world_bearing = wrap(math.atan2(target["x"] - fly["x"],
                                                 fly["z"] - target["z"]))
            if previous_world_bearing is not None:
                object_speeds.append(abs(math.degrees(wrap(
                    world_bearing - previous_world_bearing))) * 1000 / BASE_STEP_MS)
                heading_speeds.append(abs(math.degrees(wrap(
                    fly["heading_rad"] - previous_heading))) * 1000 / BASE_STEP_MS)
            previous_world_bearing = world_bearing
            previous_heading = fly["heading_rad"]
        else:
            previous_world_bearing = previous_heading = None
        lc_spikes += sum(trace["LC10a_spikes"].values())
        a019_spikes += sum(trace["AOTU_spikes"]["AOTU019"].values())
        a025_spikes += sum(trace["AOTU_spikes"]["AOTU025"].values())
        dn_spikes += sum(trace["DNa02_spikes"].values())
        voltage = trace["right_minus_left_mv"]
        nonzero_voltage += int(abs(voltage) > 0.0001)
        saturated += int(abs(trace["turn_rate_rad_s"]) >= MAX_TURN_RATE_RAD_S - 0.0001)
        if feature["in_view"] and abs(feature["bearing_deg"]) > 3:
            eligible += 1
            correct_voltage_sign += int(voltage * feature["bearing_deg"] > 0)
            wrong_voltage_sign += int(voltage * feature["bearing_deg"] < 0)
            biases.append(math.copysign(voltage, feature["bearing_deg"]))
    return {
        "in_view_frames": len(strengths),
        "mean_base_strength": round(mean(base_strengths), 4),
        "mean_delivered_strength": round(mean(strengths), 4),
        "mean_retinal_speed_deg_s": round(mean(retinal_speeds), 3),
        "mean_world_bearing_speed_deg_s": round(mean(object_speeds), 3),
        "mean_self_turn_speed_deg_s": round(mean(heading_speeds), 3),
        "LC10a_spikes": lc_spikes,
        "AOTU019_spikes": a019_spikes,
        "AOTU025_spikes": a025_spikes,
        "DNa02_spikes": dn_spikes,
        "mean_toward_target_DNa02_voltage_bias_mv": round(mean(biases), 4),
        "correct_voltage_sign_frames": correct_voltage_sign,
        "wrong_voltage_sign_frames": wrong_voltage_sign,
        "zero_voltage_sign_frames": eligible - correct_voltage_sign - wrong_voltage_sign,
        "eligible_sign_frames": eligible,
        "nonzero_voltage_frames": nonzero_voltage,
        "saturated_voltage_turn_frames": saturated,
    }


def closed_loop(circuit, centers: dict[int, float], path: str,
                input_kind: str, readout: str) -> dict:
    neural = SteeringSession(circuit, visual_centers_deg=centers)
    motion = MotionFeature()
    x = z = heading = turn_rate = 0.0
    dt_s = BASE_STEP_MS / 1000.0
    errors, view, dn_spikes, turning = [], 0, 0, 0
    for frame in range(DURATION_MS // BASE_STEP_MS):
        heading = wrap(heading + turn_rate * dt_s)
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        fly = {"x": x, "z": z, "heading_rad": heading}
        target = trial_target(path, (frame + 1) * dt_s)
        feature = target_feature(fly, target)
        strength = (feature["strength"] if input_kind == "position"
                    else motion.strength(fly, target, BASE_STEP_MS)[0])
        trace = neural.step(fly, target, BASE_STEP_MS,
                            input_strength_override=strength)
        if readout == "voltage":
            turn_rate = trace["turn_rate_rad_s"]
        elif readout == "spike_only":
            difference = trace["DNa02_spikes"]["R"] - trace["DNa02_spikes"]["L"]
            turn_rate = (math.copysign(MAX_TURN_RATE_RAD_S, difference)
                         if difference else 0.0)
        else:
            raise ValueError(readout)
        turning += int(turn_rate != 0.0)
        dn_spikes += sum(trace["DNa02_spikes"].values())
        errors.append(abs(feature["bearing_deg"]))
        view += int(feature["in_view"])
    return {"mean_abs_bearing_deg": round(mean(errors), 3),
            "in_view_fraction": round(view / len(errors), 3),
            "turning_frames": turning, "DNa02_spikes": dn_spikes}


def run() -> dict:
    circuit = load_candidate()
    centers, _ = load_upstream_map(circuit)
    results = {}
    for path in NEW_PATHS:
        samples = direct_trajectory(path)
        results[path] = {
            "paired_direct_path": {
                kind: paired_replay(circuit, centers, samples, kind)
                for kind in ("position", "motion")
            },
            "closed_loop": {
                f"{kind}_{readout}": closed_loop(circuit, centers, path, kind, readout)
                for kind in ("position", "motion")
                for readout in ("voltage", "spike_only")
            },
        }
    means = {kind: round(mean(results[path]["closed_loop"][kind]["mean_abs_bearing_deg"]
                              for path in NEW_PATHS), 3)
             for kind in ("position_voltage", "motion_voltage", "position_spike_only",
                          "motion_spike_only")}
    return {
        "question": "Separately, how do the motion input and DNa02 readout affect this model?",
        "status": "offline diagnostic; playable default unchanged",
        "protocol": {
            "paired_replay": "Position and motion inputs see the same direct-controller poses and target positions; "
                             "LIF and selected MaleCNS wiring fixed.",
            "closed_loop": "Five previously used paths; position versus motion input crossed with "
                           "voltage versus spike-only DNa02 readout; all other parameters fixed.",
            "spike_only": "Any nonzero signed right-left DNa02 spike-count difference commands the "
                          "existing turn cap. This is a diagnostic counterfactual, not a calibrated motor law.",
            "caveat": "Paths are reused, direction preference and receptor effects are not modeled, "
                      "and the direct-controller pose replay does not establish biological responses.",
        },
        "mean_closed_loop_error_deg": means,
        "paths": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["mean_closed_loop_error_deg"], indent=2))


if __name__ == "__main__":
    main()

"""Offline upstream-map and untuned motion-input comparison for LC10a pursuit.

No playable default is changed. Movement detection is an engineered temporal
feature applied equally to LC10a cells, not a reconstructed retinal circuit.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
from statistics import mean, median

from .pursuit_trust_audit import BASE_STEP_MS, DURATION_MS, WALK_SPEED_M_S
from .steering import SteeringSession, target_feature
from .steering_diagnostic import load_candidate
from .visual_input_experiment import (
    NEW_PATHS, SHUFFLE_SEEDS, load_map as load_old_map, run_trial,
    shuffle_lc_wiring, trial_target,
)
from .visual_pathway_probe import (
    BASELINE_MS, CENTERS_DEG, PULSE_MS, SIDES, STEP_MS,
    angle_for, target as pulse_target,
)


STATIC_FLOOR = 0.20
FULL_MOTION_DEG_S = 25.0
MOTIONS = ("static", "outward", "inward")


def load_upstream_map(circuit) -> tuple[dict[int, float], dict]:
    source = Path(str(files("fly_creature").joinpath("data/visual_steering_v1.json")))
    path = Path(str(files("fly_creature").joinpath("data/lc10a_upstream_hypothesis_v2.json")))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload["schema_version"] != 1 or
            payload["sources"]["circuit_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest()):
        raise ValueError("Upstream visual map does not match the packaged circuit")
    centers = {int(row["body_id"]): float(row["preferred_abs_bearing_deg"])
               for row in payload["cells"]}
    expected = {n.body_id for n in circuit.neurons if n.cell_type == "LC10a"}
    if set(centers) != expected or len(payload["cells"]) != len(expected):
        raise ValueError("Upstream map must cover every selected LC10a cell")
    return centers, payload


class MotionFeature:
    """Minimal speed-sensitive retinal feature, fixed before scoring paths."""

    def __init__(self) -> None:
        self.previous_bearing: float | None = None

    def strength(self, fly: dict, target: dict, dt_ms: int, *,
                 matched_current: bool = False) -> tuple[float, float]:
        feature = target_feature(fly, target)
        if not feature["in_view"]:
            self.previous_bearing = None
            return 0.0, 0.0
        current = feature["bearing_deg"]
        if self.previous_bearing is None:
            speed = 0.0
        else:
            delta = math.degrees(math.atan2(
                math.sin(math.radians(current - self.previous_bearing)),
                math.cos(math.radians(current - self.previous_bearing)),
            ))
            speed = abs(delta) * 1000.0 / dt_ms
        self.previous_bearing = current
        factor = STATIC_FLOOR + (1.0 - STATIC_FLOOR) * min(1.0, speed / FULL_MOTION_DEG_S)
        base = 1.0 if matched_current else feature["strength"]
        return base * factor, speed


def fixed_trial(circuit, centers: dict[int, float], side: str, center: int,
                motion: str, kind: str) -> dict:
    neural = SteeringSession(circuit, visual_centers_deg=centers)
    visual = MotionFeature()
    fly = {"x": 0.0, "z": 0.0, "heading_rad": 0.0}
    for _ in range(BASELINE_MS // STEP_MS):
        neural.step(fly, pulse_target(side, center, active=False), STEP_MS)
    a019 = a025 = lc = dn_spikes = 0
    dn_bias = []
    input_levels = []
    speeds = []
    for frame in range(PULSE_MS // STEP_MS):
        target = pulse_target(side, angle_for(center, motion, frame))
        if kind == "position":
            strength, speed = 1.0, 0.0
        elif kind == "motion":
            strength, speed = visual.strength(fly, target, STEP_MS, matched_current=True)
        else:
            raise ValueError(kind)
        trace = neural.step(fly, target, STEP_MS, record_cells=True,
                            input_strength_override=strength)
        a019 += trace["AOTU_spikes"]["AOTU019"][side]
        a025 += trace["AOTU_spikes"]["AOTU025"][side]
        lc += trace["LC10a_spikes"][side]
        dn_spikes += sum(trace["DNa02_spikes"].values())
        dn_bias.append((1 if side == "R" else -1) * trace["right_minus_left_mv"])
        input_levels.append(strength)
        speeds.append(speed)
    return {"LC10a_spikes": lc, "AOTU019_spikes": a019,
            "AOTU025_spikes": a025,
            "DNa02_toward_bias_mv": round(mean(dn_bias), 4),
            "DNa02_spikes": dn_spikes,
            "mean_input_strength": round(mean(input_levels), 4),
            "mean_retinal_speed_deg_s": round(mean(speeds), 4)}


def motion_pursuit_trial(circuit, centers: dict[int, float], path: str) -> dict:
    neural = SteeringSession(circuit, visual_centers_deg=centers)
    visual = MotionFeature()
    x = z = heading = turn_rate = 0.0
    errors = []
    speeds = []
    dn_spikes = 0
    view_count = 0
    for frame in range(DURATION_MS // BASE_STEP_MS):
        dt_s = BASE_STEP_MS / 1000.0
        heading = math.atan2(math.sin(heading + turn_rate * dt_s),
                             math.cos(heading + turn_rate * dt_s))
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        fly = {"x": x, "z": z, "heading_rad": heading}
        target = trial_target(path, (frame + 1) * dt_s)
        feature = target_feature(fly, target)
        strength, speed = visual.strength(fly, target, BASE_STEP_MS)
        trace = neural.step(fly, target, BASE_STEP_MS,
                            input_strength_override=strength)
        turn_rate = trace["turn_rate_rad_s"]
        dn_spikes += sum(trace["DNa02_spikes"].values())
        errors.append(abs(feature["bearing_deg"]))
        view_count += int(feature["in_view"])
        speeds.append(speed)
    return {"mean_abs_bearing_deg": round(mean(errors), 3),
            "p90_abs_bearing_deg": round(sorted(errors)[int(0.9 * (len(errors) - 1))], 3),
            "in_view_fraction": round(view_count / len(errors), 3),
            "mean_retinal_speed_deg_s": round(mean(speeds), 3),
            "DNa02_spikes": dn_spikes}


def run() -> dict:
    circuit = load_candidate()
    new_centers, mapping = load_upstream_map(circuit)
    old_centers, _ = load_old_map(circuit)
    shuffled = {seed: shuffle_lc_wiring(circuit, seed) for seed in SHUFFLE_SEEDS}
    fixed = {}
    for side in SIDES:
        for center in CENTERS_DEG:
            for motion in MOTIONS:
                key = f"{side}:{center}:{motion}"
                shuffled_rows = [fixed_trial(shuffled[seed], new_centers, side,
                                             center, motion, "motion")
                                 for seed in SHUFFLE_SEEDS]
                fixed[key] = {
                    "position": fixed_trial(circuit, new_centers, side, center, motion, "position"),
                    "motion": fixed_trial(circuit, new_centers, side, center, motion, "motion"),
                    "motion_shuffled_median": {
                        metric: round(median(row[metric] for row in shuffled_rows), 4)
                        for metric in ("AOTU019_spikes", "AOTU025_spikes",
                                       "DNa02_toward_bias_mv")
                    },
                }
    pursuit = {}
    for path in NEW_PATHS:
        shuffles = {str(seed): motion_pursuit_trial(shuffled[seed], new_centers, path)
                    for seed in SHUFFLE_SEEDS}
        pursuit[path] = {
            "uniform": run_trial(circuit, new_centers, path, "uniform_intact"),
            "old_anatomy_position": run_trial(circuit, old_centers, path, "anatomy_intact"),
            "upstream_position": run_trial(circuit, new_centers, path, "anatomy_intact"),
            "upstream_motion": motion_pursuit_trial(circuit, new_centers, path),
            "direct_bearing": run_trial(circuit, new_centers, path, "direct_bearing"),
            "upstream_motion_shuffled_median": round(median(
                row["mean_abs_bearing_deg"] for row in shuffles.values()), 3),
            "upstream_motion_shuffled": {seed: row["mean_abs_bearing_deg"]
                                          for seed, row in shuffles.items()},
        }
    scores = {kind: round(mean(row[kind]["mean_abs_bearing_deg"] for row in pursuit.values()), 3)
              for kind in ("uniform", "old_anatomy_position", "upstream_position",
                           "upstream_motion", "direct_bearing")}
    scores["upstream_motion_shuffled_median"] = round(mean(
        row["upstream_motion_shuffled_median"] for row in pursuit.values()), 3)
    wins = {
        "versus_uniform": sum(row["upstream_motion"]["mean_abs_bearing_deg"]
                              < row["uniform"]["mean_abs_bearing_deg"]
                              for row in pursuit.values()),
        "versus_direct": sum(row["upstream_motion"]["mean_abs_bearing_deg"]
                             < row["direct_bearing"]["mean_abs_bearing_deg"]
                             for row in pursuit.values()),
        "versus_shuffle_median": sum(row["upstream_motion"]["mean_abs_bearing_deg"]
                                      < row["upstream_motion_shuffled_median"]
                                      for row in pursuit.values()),
    }
    promote = (scores["upstream_motion"] < scores["uniform"] and
               scores["upstream_motion"] < scores["direct_bearing"] and
               all(count >= 3 for count in wins.values()))
    return {
        "question": "Does an independently oriented LC10a map plus an untuned motion feature improve this selected circuit?",
        "status": "offline; playable default unchanged",
        "map_sha256": hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest(),
        "protocol": {
            "map": "MaleCNS upstream medulla-column contacts plus skeleton geometry; never LC10a output weights",
            "motion": "Retinal bearing-speed magnitude. Multiply existing input by 0.2 + 0.8*min(speed/25deg/s,1). "
                      "No direction-specific per-cell assignment or gain fitting.",
            "fixed_fly": "100ms inactive baseline, 400ms static or 10-degree inward/outward sweep, "
                         "20ms world steps and 1ms neural steps, equal base current before motion factor.",
            "pursuit": "Five paths from the earlier offline experiment, 8s each, 20ms world steps; "
                       "same circuit, LIF, decoder, turn cap, walking speed, and view gate.",
            "controls": "Old uniform, old skeleton-position map, upstream map without motion, "
                        "direct-bearing software turner, and 12 within-side upstream-motion wiring shuffles.",
            "predeclared_promotion_gate": "Upstream motion must have lower mean bearing error than both uniform "
                                          "and direct and beat both on at least 3/5 paths; also beat "
                                          "shuffle median on at least 3/5 paths. Otherwise do not promote.",
            "caveat": "The five pursuit paths were previously used to evaluate v1; this is a "
                      "repeated benchmark, not a fresh held-out validation. Retinal motion "
                      "includes self-motion during turning.",
        },
        "map_diagnostics": mapping["diagnostics"],
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
    print(json.dumps({"map": result["map_diagnostics"],
                      "mean_pursuit_error_deg": result["mean_pursuit_error_deg"],
                      "decision": result["decision"]}, indent=2))


if __name__ == "__main__":
    main()

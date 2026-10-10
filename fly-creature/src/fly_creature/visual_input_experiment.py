"""Offline comparison of a MaleCNS skeleton-derived LC10a input hypothesis.

This does not change the playable creature. The hypothesized visual centers
come from distal SWC geometry, not measured single-cell receptive fields.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import random
from statistics import mean, median

from .circuit import Circuit
from .pursuit_trust_audit import BASE_STEP_MS, DURATION_MS, WALK_SPEED_M_S, target_at
from .steering import INPUT_MV, MAX_TURN_RATE_RAD_S, SteeringSession, target_feature
from .steering_diagnostic import load_candidate


SHUFFLE_SEEDS = tuple(range(101, 113))
PATHS = ("crossing", "mirrored", "faster", "slower", "narrow",
         "reverse_twice", "offset_sweep", "near_target", "far_target", "stop_go")
NEW_PATHS = PATHS[5:]


def trial_target(path: str, time_s: float) -> dict:
    if path in PATHS[:5]:
        return target_at(path, time_s)
    if path == "reverse_twice":
        x = (-3.0 + 2.0 * time_s if time_s <= 3.0 else
             3.0 - 2.0 * (time_s - 3.0) if time_s <= 6.0 else
             -3.0 + 2.0 * (time_s - 6.0))
        z = -6.5
    elif path == "offset_sweep":
        x, z = 1.5 + 2.0 * math.sin(0.48 * time_s - 1.0), -6.5
    elif path == "near_target":
        x, z = 1.8 * math.sin(0.65 * time_s - 1.2), -4.0
    elif path == "far_target":
        x, z = 3.4 * math.sin(0.60 * time_s - 1.2), -8.3
    elif path == "stop_go":
        x, z = min(3.4, -2.6 + 1.5 * max(0.0, time_s - 2.0)), -6.5
    else:
        raise ValueError(f"Unknown target path: {path}")
    return {"x": x, "z": z, "active": True}


def load_map(circuit: Circuit) -> tuple[dict[int, float], dict]:
    source = Path(str(files("fly_creature").joinpath("data/visual_steering_v1.json")))
    path = Path(str(files("fly_creature").joinpath("data/lc10a_anatomy_hypothesis_v1.json")))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["schema_version"] != 1 or payload["sources"]["circuit_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
        raise ValueError("Anatomical map and packaged circuit do not match")
    centers = {int(row["body_id"]): float(row["preferred_abs_bearing_deg"])
               for row in payload["cells"]}
    lc_ids = {n.body_id for n in circuit.neurons if n.cell_type == "LC10a"}
    if set(centers) != lc_ids or len(payload["cells"]) != len(lc_ids):
        raise ValueError("Anatomical map must cover exactly the selected LC10a cells")
    return centers, payload


def shuffle_lc_wiring(circuit: Circuit, seed: int) -> Circuit:
    """Permute whole LC10a output bundles within each side; preserve all weights."""
    rng = random.Random(seed)
    by_id = {n.body_id: n for n in circuit.neurons}
    replacement = {}
    for side in ("L", "R"):
        ids = sorted(n.body_id for n in circuit.neurons
                     if n.cell_type == "LC10a" and n.side == side)
        shuffled = ids.copy()
        rng.shuffle(shuffled)
        replacement.update(zip(ids, shuffled))
    edges = tuple(replace(edge, pre=replacement[edge.pre])
                  if edge.pre in replacement else edge
                  for edge in circuit.connections)
    if (sorted((e.post, e.synapse_count) for e in edges)
            != sorted((e.post, e.synapse_count) for e in circuit.connections)):
        raise RuntimeError("Shuffled wiring changed downstream weights")
    if any(by_id[edge.pre].side != by_id[edge.post].side for edge in edges
           if by_id[edge.pre].cell_type == "LC10a"):
        raise RuntimeError("Shuffled wiring crossed hemispheres")
    return Circuit(circuit.neurons, edges, circuit.provenance)


def run_trial(circuit: Circuit, centers: dict[int, float], path: str,
              kind: str) -> dict:
    neural = None
    if kind != "direct_bearing":
        neural = SteeringSession(
            circuit,
            condition="disconnected" if kind == "anatomy_bridge_removed" else "intact",
            visual_centers_deg=None if kind.startswith("uniform") else centers,
        )
    x = z = heading = turn_rate = 0.0
    errors = []
    view_count = 0
    dn_spikes = 0
    for frame in range(DURATION_MS // BASE_STEP_MS):
        dt_s = BASE_STEP_MS / 1000.0
        heading = math.atan2(math.sin(heading + turn_rate * dt_s),
                             math.cos(heading + turn_rate * dt_s))
        x += math.sin(heading) * WALK_SPEED_M_S * dt_s
        z -= math.cos(heading) * WALK_SPEED_M_S * dt_s
        target = trial_target(path, (frame + 1) * dt_s)
        feature = target_feature({"x": x, "z": z, "heading_rad": heading}, target)
        if neural is None:
            turn_rate = (math.copysign(MAX_TURN_RATE_RAD_S * feature["strength"],
                                       feature["bearing_deg"])
                         if feature["strength"] else 0.0)
        else:
            trace = neural.step({"x": x, "z": z, "heading_rad": heading},
                                target, BASE_STEP_MS)
            turn_rate = trace["turn_rate_rad_s"]
            dn_spikes += sum(trace["DNa02_spikes"].values())
        errors.append(abs(feature["bearing_deg"]))
        view_count += int(feature["in_view"])
    return {"mean_abs_bearing_deg": round(mean(errors), 3),
            "p90_abs_bearing_deg": round(sorted(errors)[int(0.9 * (len(errors) - 1))], 3),
            "in_view_fraction": round(view_count / len(errors), 3),
            "DNa02_spikes": dn_spikes if neural is not None else None}


def run() -> dict:
    circuit = load_candidate()
    centers, mapping = load_map(circuit)
    shuffled = {seed: shuffle_lc_wiring(circuit, seed) for seed in SHUFFLE_SEEDS}
    results = {}
    for path in PATHS:
        trials = {
            "uniform_intact": run_trial(circuit, centers, path, "uniform_intact"),
            "anatomy_intact": run_trial(circuit, centers, path, "anatomy_intact"),
            "anatomy_bridge_removed": run_trial(circuit, centers, path,
                                                "anatomy_bridge_removed"),
            "direct_bearing": run_trial(circuit, centers, path, "direct_bearing"),
            "uniform_shuffled_seed101": run_trial(shuffled[101], centers, path,
                                                   "uniform_shuffled"),
        }
        shuffled_scores = {str(seed): run_trial(shuffled[seed], centers, path,
                                                "anatomy_shuffled")
                           for seed in SHUFFLE_SEEDS}
        trials["anatomy_shuffled_summary"] = {
            "median_mean_abs_bearing_deg": round(median(
                row["mean_abs_bearing_deg"] for row in shuffled_scores.values()), 3),
            "minimum_mean_abs_bearing_deg": min(
                row["mean_abs_bearing_deg"] for row in shuffled_scores.values()),
            "maximum_mean_abs_bearing_deg": max(
                row["mean_abs_bearing_deg"] for row in shuffled_scores.values()),
            "seeds": {seed: row["mean_abs_bearing_deg"]
                      for seed, row in shuffled_scores.items()},
        }
        if (abs(trials["uniform_intact"]["mean_abs_bearing_deg"]
                - trials["uniform_shuffled_seed101"]["mean_abs_bearing_deg"]) > 0.001):
            raise RuntimeError("Uniform input changed under within-side LC10a shuffle")
        results[path] = trials
    new = [results[path] for path in NEW_PATHS]
    anatomy_wins_uniform = sum(row["anatomy_intact"]["mean_abs_bearing_deg"]
                               < row["uniform_intact"]["mean_abs_bearing_deg"] for row in new)
    anatomy_wins_direct = sum(row["anatomy_intact"]["mean_abs_bearing_deg"]
                              < row["direct_bearing"]["mean_abs_bearing_deg"] for row in new)
    anatomy_beats_shuffle_median = sum(
        row["anatomy_intact"]["mean_abs_bearing_deg"]
        < row["anatomy_shuffled_summary"]["median_mean_abs_bearing_deg"]
        for row in new)
    return {
        "question": "Does skeleton-position-specific LC10a input reveal a useful role for the selected MaleCNS wiring?",
        "status": "offline hypothesis test; playable default unchanged",
        "map_sha256": hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest(),
        "protocol": {
            "duration_ms": DURATION_MS, "world_step_ms": BASE_STEP_MS,
            "forward_speed_m_s": WALK_SPEED_M_S, "input_mv": INPUT_MV,
            "paths": list(PATHS), "new_paths": list(NEW_PATHS),
            "shuffled_wiring_seeds": list(SHUFFLE_SEEDS),
            "anatomical_input": "SWC-derived per-cell bearing centers, Gaussian width 18 deg, floor 0.1; "
                                "normalize to preserve total current on each stimulated side.",
            "wiring_shuffle": "Permute intact LC10a output bundles within each hemisphere; keep "
                              "AOTU and DNa02 cells, bridge edges, synapse counts, and signs.",
            "direct_control": "Same target feature and turn cap, no neural graph.",
            "metric": "Mean absolute target bearing; lower is better only for centering.",
            "interpretation_gate": "A strong anatomical advantage would need to hold across new paths "
                                   "against uniform input, wiring shuffles, and direct bearing; "
                                   "this audit reports all three separately and does not tune parameters.",
        },
        "new_path_win_counts": {"out_of": len(NEW_PATHS),
                                "versus_uniform": anatomy_wins_uniform,
                                "versus_direct": anatomy_wins_direct,
                                "versus_shuffle_median": anatomy_beats_shuffle_median},
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new_path_win_counts": result["new_path_win_counts"],
                      "paths": {path: {kind: row["mean_abs_bearing_deg"]
                                      for kind, row in trials.items()
                                      if kind != "anatomy_shuffled_summary"}
                                | {"shuffled_median": trials["anatomy_shuffled_summary"][
                                    "median_mean_abs_bearing_deg"]}
                                for path, trials in result["results"].items()}}, indent=2))


if __name__ == "__main__":
    main()

"""Frozen offline Step 4 adaptation and bounded pursuit experiment.

This uses source-inspired activity transformations with v1.0 recorded edges.
The eye map, LC10a response, unit normalization, sensor, and body remain
explicit hypotheses. No result here is a measured neural firing rate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path

import numpy as np

from .pursuit_activity import ActivityProjection
from .pursuit_reference import _elu_lookup
from .steering import SteeringSession
from .steering_diagnostic import load_candidate


DT = 0.01
STEPS = 800
WALK_SPEED = 0.55
TARGET_Z = -7.0
VIEW_DEG = 120.0
MAX_TURN_RATE = 1.2
AUTHOR_GAIN = 0.65
DELAY_STEPS = 45
GRID = np.arange(-180.0, 181.0)
PRIMARY_PATHS = ("chirp", "mirror_chirp", "triangle", "mirror_triangle",
                 "offset", "mirror_offset", "step_hold", "mirror_step_hold")
CONDITIONS = ("intact", "AOTU019_removed", "AOTU025_removed",
              "bridge_removed", "position_only", "direct_bearing", "playable_lif")
SHUFFLE_SEED = 20260927
SHUFFLES = 32
SENSITIVITY_MAPS = {
    "p_minus1_q0": "lc10a_registered_shift_p-1_q0.json",
    "p_plus1_q0": "lc10a_registered_shift_p1_q0.json",
    "p0_q_minus1": "lc10a_registered_shift_p0_q-1.json",
    "p0_q_plus1": "lc10a_registered_shift_p0_q1.json",
}


def _wrapped_radians(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def target_x(path: str, t: float) -> float:
    if path == "calibration_crossing":
        return 3.2 * math.sin(0.62 * t - 1.2)
    mirrored = path.startswith("mirror_")
    name = path.removeprefix("mirror_")
    if name == "chirp":
        value = 2.6 * math.sin(0.25 * t + 0.055 * t * t - 0.9)
    elif name == "triangle":
        value = -2.4 + 1.2 * t if t < 4.0 else 2.4 - 1.2 * (t - 4.0)
    elif name == "offset":
        value = 1.4 + 0.9 * math.sin(1.1 * t - 0.4)
    elif name == "step_hold":
        value = -1.8 if t < 2.0 else 1.8
    else:
        raise ValueError(f"Unknown held-out target path: {path}")
    return -value if mirrored else value


def _bearing_and_view(x: float, z: float, heading: float,
                      target_x_m: float) -> tuple[float, bool]:
    dx, dz = target_x_m - x, TARGET_Z - z
    bearing = math.degrees(_wrapped_radians(math.atan2(dx, -dz) - heading))
    visible = 0.4 <= math.hypot(dx, dz) <= 9.0 and abs(bearing) <= VIEW_DEG
    return bearing, visible


def _nearest_elu(grid: np.ndarray, values: np.ndarray, raw: float) -> float:
    index = int(math.floor((raw - grid[0]) / (grid[-1] - grid[0]) *
                           (len(grid) - 1) + 0.5))
    return float(values[max(0, min(len(grid) - 1, index))])


@dataclass
class ActivityAdapter:
    projection: ActivityProjection
    width_deg: float
    peaks: dict[str, float]
    edge_scales: dict[str, float]
    response: np.ndarray
    lookups: dict[str, tuple[np.ndarray, np.ndarray]]
    output_edges: np.ndarray

    @classmethod
    def build(cls, projection: ActivityProjection, *, width_deg: float = 18.0,
              peaks: dict[str, float] | None = None,
              edge_scales: dict[str, float] | None = None) -> "ActivityAdapter":
        response = projection.fixed_fly(GRID, width_deg=width_deg)["aotu_contact_drive"]
        if peaks is None:
            peaks = {kind: float(response[:, [i for i, name in enumerate(
                projection.aotu_types) if name == kind]].max())
                     for kind in ("AOTU019", "AOTU025")}
        if edge_scales is None:
            edge_scales = {kind: float(np.abs(projection.aotu_to_dn[[i for i, name in
                enumerate(projection.aotu_types) if name == kind]]).max())
                           for kind in ("AOTU019", "AOTU025")}
        if any(value <= 0 or not math.isfinite(value) for value in
               (*peaks.values(), *edge_scales.values())):
            raise ValueError("AOTU normalization requires positive finite peaks and edges")
        lookups = {kind: _elu_lookup(peaks[kind]) for kind in peaks}
        output_edges = projection.aotu_to_dn.copy()
        for i, kind in enumerate(projection.aotu_types):
            output_edges[i] /= edge_scales[kind]
        return cls(projection, width_deg, peaks, edge_scales, response,
                   lookups, output_edges)

    def activity_at(self, bearing_deg: float, motion_deg: float = 0.0,
                    *, direction_selective: bool = True,
                    condition: str = "intact") -> dict:
        if condition not in ("intact", "AOTU019_removed", "AOTU025_removed",
                             "bridge_removed"):
            raise ValueError("Unknown pathway intervention")
        if not math.isfinite(bearing_deg) or abs(bearing_deg) > 180:
            raise ValueError("Retinal bearing outside [-180,180]")
        bin_angle = math.copysign(math.floor(abs(bearing_deg) + 0.5), bearing_deg)
        raw = self.response[int(bin_angle) + 180].copy()
        if direction_selective:
            for i, (kind, side) in enumerate(zip(
                    self.projection.aotu_types, self.projection.aotu_sides)):
                if kind == "AOTU019" and ((side == "R" and motion_deg < 0) or
                                          (side == "L" and motion_deg > 0)):
                    raw[i] *= 0.66
        activity = np.empty(len(raw), dtype=float)
        clipped = False
        for i, kind in enumerate(self.projection.aotu_types):
            clipped |= raw[i] > self.peaks[kind] + 1e-9
            grid, values = self.lookups[kind]
            activity[i] = _nearest_elu(grid, values,
                                        min(float(raw[i]), self.peaks[kind]))
        edges = self.output_edges.copy()
        if condition == "bridge_removed":
            edges.fill(0.0)
        elif condition != "intact":
            removed = condition.removesuffix("_removed")
            for i, kind in enumerate(self.projection.aotu_types):
                if kind == removed:
                    edges[i].fill(0.0)
        dn = activity @ edges
        dn_clipped = np.clip(dn, -2.25, 4.0)
        return {"aotu": activity, "dn": dn_clipped,
                "signal": float(dn_clipped[1] - dn_clipped[0]),
                "aotu_clipped": clipped,
                "dn_clipped": bool(np.any(dn != dn_clipped))}


def shuffled_projection(projection: ActivityProjection,
                        rng: np.random.Generator) -> ActivityProjection:
    weights = projection.lc_to_aotu.copy()
    for side in ("L", "R"):
        rows = np.flatnonzero(projection.sides == side)
        weights[rows] = weights[rng.permutation(rows)]
    return replace(projection, lc_to_aotu=weights)


def continuous_settling_s(errors: list[float], path: str) -> float | None:
    if not path.endswith("step_hold"):
        return None
    consecutive = 0
    for i, error in enumerate(errors):
        if (i + 1) * DT < 2.0:
            continue
        consecutive = consecutive + 1 if abs(error) <= 10.0 else 0
        if consecutive >= 100:
            return round((i + 1 - consecutive) * DT, 2)
    return None


def run_trial(path: str, condition: str, *, adapter: ActivityAdapter | None = None,
              gain_multiplier: float = 1.0, lif_circuit=None,
              trace_path: Path | None = None) -> dict:
    if condition not in CONDITIONS and condition != "shuffle":
        raise ValueError("Unknown trial condition")
    if condition not in ("direct_bearing", "playable_lif") and adapter is None:
        raise ValueError("An activity adapter is required")
    if not math.isfinite(gain_multiplier) or gain_multiplier <= 0:
        raise ValueError("Gain multiplier must be positive")
    lif = SteeringSession(lif_circuit) if condition == "playable_lif" else None
    x = z = heading = turn_rate = 0.0
    seen: list[float] = []
    bearings: list[float] = []
    view_count = motor_caps = aotu_caps = dn_caps = 0
    turn_rates: list[float] = []
    trace = []
    for step in range(STEPS):
        heading = _wrapped_radians(heading + turn_rate * DT)
        x += math.sin(heading) * WALK_SPEED * DT
        z -= math.cos(heading) * WALK_SPEED * DT
        t = (step + 1) * DT
        target = target_x(path, t)
        bearing, visible = _bearing_and_view(x, z, heading, target)
        bearings.append(bearing)
        view_count += int(visible)
        if condition == "direct_bearing":
            turn_rate = (MAX_TURN_RATE * max(-1.0, min(1.0, bearing / 45.0))
                         if visible else 0.0)
            signal = None
        elif lif is not None:
            value = lif.step({"x": x, "z": z, "heading_rad": heading},
                             {"x": target, "z": TARGET_Z, "active": True}, 10)
            turn_rate = value["turn_rate_rad_s"]
            signal = value["right_minus_left_mv"]
        else:
            seen.append(bearing if visible else 0.0)
            delayed = max(0, len(seen) - 1 - DELAY_STEPS)
            read = seen[delayed]
            motion = read - seen[delayed - 1] if delayed > 0 else 0.0
            intervention = (condition if condition in ("AOTU019_removed",
                         "AOTU025_removed", "bridge_removed") else "intact")
            value = adapter.activity_at(read, motion,
                direction_selective=condition != "position_only",
                condition=intervention)
            signal = value["signal"]
            requested = math.radians(AUTHOR_GAIN * gain_multiplier * signal) / DT
            turn_rate = max(-MAX_TURN_RATE, min(MAX_TURN_RATE, requested))
            aotu_caps += int(value["aotu_clipped"])
            dn_caps += int(value["dn_clipped"])
        motor_caps += int(abs(turn_rate) >= MAX_TURN_RATE - 1e-10)
        turn_rates.append(turn_rate)
        if trace_path is not None:
            trace.append({"t_s": round(t, 2), "bearing_deg": round(bearing, 3),
                          "visible": visible, "heading_deg": round(math.degrees(heading), 3),
                          "target_x_m": round(target, 3), "turn_rate_rad_s": round(turn_rate, 5),
                          "dn_signal": None if signal is None else round(signal, 6)})
    crossings = sum(a * b < 0 for a, b in zip(bearings[:-1], bearings[1:])
                    if abs(a) <= 10 or abs(b) <= 10)
    result = {
        "mean_abs_bearing_deg": round(float(np.mean(np.abs(bearings))), 3),
        "median_abs_bearing_deg": round(float(np.median(np.abs(bearings))), 3),
        "final_abs_bearing_deg": round(abs(bearings[-1]), 3),
        "in_view_fraction": round(view_count / STEPS, 4),
        "target_loss_fraction": round(1 - view_count / STEPS, 4),
        "turn_cap_fraction": round(motor_caps / STEPS, 4),
        "aotu_lookup_clip_fraction": round(aotu_caps / STEPS, 4),
        "dn_lookup_clip_fraction": round(dn_caps / STEPS, 4),
        "settling_time_s": continuous_settling_s(bearings, path),
        "near_target_sign_crossings": crossings,
        "final_heading_deg": round(math.degrees(heading), 3),
        "mean_abs_turn_rate_rad_s": round(float(np.mean(np.abs(turn_rates))), 5),
    }
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    return result


def motion_probe(adapter: ActivityAdapter, *, direction_selective: bool) -> dict:
    index = {(kind, side): i for i, (kind, side) in enumerate(zip(
        adapter.projection.aotu_types, adapter.projection.aotu_sides))}
    result = {}
    for side in ("L", "R"):
        sign = -1 if side == "L" else 1
        for angle in (30, 60):
            for speed in (25, 75):
                bearing = sign * angle
                preferred = adapter.activity_at(bearing, sign * speed * DT,
                    direction_selective=direction_selective)["aotu"]
                nonpreferred = adapter.activity_at(bearing, -sign * speed * DT,
                    direction_selective=direction_selective)["aotu"]
                for kind in ("AOTU019", "AOTU025"):
                    i = index[kind, side]
                    ratio = float(preferred[i] / nonpreferred[i]) if nonpreferred[i] else None
                    result[f"{kind}_{side}_{angle}deg_{speed}dps"] = ratio
    return result


def _map_path(name: str) -> Path:
    return Path(str(files("fly_creature").joinpath("data", name)))


def run(output: Path, trace_dir: Path | None = None) -> dict:
    nominal_path = _map_path("lc10a_registered_eyemap_hypothesis_v3.json")
    circuit_path = _map_path("visual_steering_v1.json")
    protocol_path = Path("docs/pursuit_step4_protocol.md")
    projection = ActivityProjection.from_packaged_data(map_path=nominal_path)
    nominal = ActivityAdapter.build(projection)
    lif_circuit = load_candidate()
    paths = ("calibration_crossing", *PRIMARY_PATHS)
    results = {}
    for path in paths:
        results[path] = {}
        for condition in CONDITIONS:
            trace_path = (trace_dir / f"{path}_{condition}.json"
                          if trace_dir is not None and path in
                          ("step_hold", "mirror_step_hold") and condition in
                          ("intact", "bridge_removed") else None)
            results[path][condition] = run_trial(path, condition, adapter=nominal,
                                                  lif_circuit=lif_circuit,
                                                  trace_path=trace_path)
    rng = np.random.default_rng(SHUFFLE_SEED)
    shuffles = []
    for _ in range(SHUFFLES):
        model = ActivityAdapter.build(shuffled_projection(projection, rng),
            peaks=nominal.peaks, edge_scales=nominal.edge_scales)
        shuffles.append({path: run_trial(path, "shuffle", adapter=model)[
            "mean_abs_bearing_deg"] for path in PRIMARY_PATHS})
    sensitivity = {}
    for name, filename in SENSITIVITY_MAPS.items():
        variant = ActivityProjection.from_packaged_data(map_path=_map_path(filename))
        model = ActivityAdapter.build(variant, peaks=nominal.peaks,
                                      edge_scales=nominal.edge_scales)
        sensitivity[name] = {path: run_trial(path, "intact", adapter=model)[
            "mean_abs_bearing_deg"] for path in PRIMARY_PATHS}
    for width in (15.0, 21.0):
        model = ActivityAdapter.build(projection, width_deg=width,
                                      peaks=nominal.peaks,
                                      edge_scales=nominal.edge_scales)
        sensitivity[f"width_{width:g}"] = {path: run_trial(path, "intact", adapter=model)[
            "mean_abs_bearing_deg"] for path in PRIMARY_PATHS}
    for gain in (0.8, 1.2):
        sensitivity[f"gain_{gain:g}"] = {path: run_trial(path, "intact",
            adapter=nominal, gain_multiplier=gain)["mean_abs_bearing_deg"]
            for path in PRIMARY_PATHS}
    fixed_angles = np.array([-70.0, -30.0, 30.0, 70.0])
    fixed = {}
    for condition in ("intact", "AOTU019_removed", "AOTU025_removed",
                      "bridge_removed"):
        fixed[condition] = {str(angle): nominal.activity_at(float(angle),
            condition=condition)["signal"] for angle in fixed_angles}
    motion = {"author_penalty": motion_probe(nominal, direction_selective=True),
              "position_only": motion_probe(nominal, direction_selective=False)}
    heldout = [results[path] for path in PRIMARY_PATHS]
    intact_errors = np.array([row["intact"]["mean_abs_bearing_deg"] for row in heldout])
    removed_errors = np.array([row["bridge_removed"]["mean_abs_bearing_deg"]
                               for row in heldout])
    shuffled_errors = np.array([[row[path] for path in PRIMARY_PATHS]
                                for row in shuffles])
    shuffled_medians = np.median(shuffled_errors, axis=0)
    nominal_median = float(np.median(intact_errors))
    checks = {
        "median_20pct_better_than_bridge_removed": bool(
            nominal_median <= 0.8 * float(np.median(removed_errors))),
        "no_path_over_10pct_worse_than_bridge_removed": bool(
            np.all(intact_errors <= 1.1 * removed_errors)),
        "all_paths_at_least_80pct_in_view": all(row["intact"]["in_view_fraction"] >= 0.8
                                              for row in heldout),
        "all_paths_less_than_25pct_turn_cap": all(row["intact"]["turn_cap_fraction"] < 0.25
                                                  for row in heldout),
        "both_step_hold_cases_settle": all(results[path]["intact"]["settling_time_s"]
                                           is not None for path in
                                           ("step_hold", "mirror_step_hold")),
        "beats_median_shuffle_at_least_six_of_eight": int(np.sum(
            intact_errors < shuffled_medians)) >= 6,
        "bridge_removed_zero_fixed_signal": all(abs(value) < 1e-12 for value in
            fixed["bridge_removed"].values()),
        "both_single_path_removals_change_fixed_signal": all(any(
            abs(fixed[condition][key] - fixed["intact"][key]) > 1e-6
            for key in fixed["intact"]) for condition in
            ("AOTU019_removed", "AOTU025_removed")),
        "motion_penalty_has_declared_effect": all(
            value is not None and (value > 1.2 if key.startswith("AOTU019")
                                   else abs(value - 1.0) < 0.05)
            for key, value in motion["author_penalty"].items()),
        "position_only_has_no_motion_preference": all(
            value is not None and abs(value - 1.0) < 1e-12
            for value in motion["position_only"].values()),
        "one_factor_sensitivity_within_25pct": all(
            abs(float(np.median(list(rows.values()))) / nominal_median - 1.0) <= 0.25
            for rows in sensitivity.values()),
    }
    payload = {
        "protocol": "docs/pursuit_step4_protocol.md",
        "protocol_sha256": hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
        "interpretation": "offline model activity, not biological neural firing",
        "source_sha256": {"circuit": hashlib.sha256(circuit_path.read_bytes()).hexdigest(),
                          "nominal_map": hashlib.sha256(nominal_path.read_bytes()).hexdigest(),
                          "registration_variants": {name: hashlib.sha256(
                              _map_path(filename).read_bytes()).hexdigest()
                              for name, filename in SENSITIVITY_MAPS.items()}},
        "constants": {"dt_s": DT, "steps": STEPS, "walk_speed_m_s": WALK_SPEED,
                      "target_z_m": TARGET_Z, "view_half_angle_deg": VIEW_DEG,
                      "delay_steps": DELAY_STEPS, "author_gain_deg_per_step": AUTHOR_GAIN,
                      "turn_cap_rad_s": MAX_TURN_RATE,
                      "aotu_peak_contact_normalizers": nominal.peaks,
                      "aotu_to_dn_edge_normalizers": nominal.edge_scales},
        "fixed_fly_dn_signal": fixed,
        "fixed_fly_motion_ratios": motion,
        "trials": results,
        "shuffle": {"seed": SHUFFLE_SEED, "count": SHUFFLES,
                    "mean_abs_bearing_deg_by_shuffle": shuffles,
                    "per_path_median_mean_abs_bearing_deg": dict(zip(
                        PRIMARY_PATHS, np.round(shuffled_medians, 3).tolist())),
                    "fraction_shuffle_mean_better_than_intact": float(np.mean(
                        np.mean(shuffled_errors, axis=1) < float(np.mean(intact_errors))))},
        "sensitivity": sensitivity,
        "heldout_summary": {"intact_median_mean_abs_bearing_deg": nominal_median,
                            "bridge_removed_median_mean_abs_bearing_deg": float(
                                np.median(removed_errors)),
                            "path_count_intact_beats_median_shuffle": int(np.sum(
                                intact_errors < shuffled_medians))},
        "gates": checks,
        "step5_recommended": all(checks.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(
        "docs/evidence/pursuit_step4_v1.json"))
    parser.add_argument("--trace-dir", type=Path, default=Path(
        "outputs/research/pursuit_step4_traces"))
    args = parser.parse_args()
    result = run(args.output, args.trace_dir)
    print(json.dumps({"heldout_summary": result["heldout_summary"],
                      "gates": result["gates"],
                      "step5_recommended": result["step5_recommended"]}, indent=2))


if __name__ == "__main__":
    main()

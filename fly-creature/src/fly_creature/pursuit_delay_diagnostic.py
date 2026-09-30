"""Offline timing/hemisphere interventions; frozen Step 4 stays unchanged."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .pursuit_activity import ActivityProjection
from .pursuit_step4 import (
    ActivityAdapter, AUTHOR_GAIN, DT, GRID, MAX_TURN_RATE, STEPS, TARGET_Z,
    WALK_SPEED, _bearing_and_view, _map_path, _wrapped_radians,
    continuous_settling_s, run_trial, shuffled_projection, target_x,
)
from .steering import SteeringSession
from .steering_diagnostic import load_candidate


@dataclass(frozen=True)
class Timing:
    visual_ms: int = 450
    motor_ms: int = 0
    overlap_deg: float = 0.0

    def __post_init__(self):
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 or v % 10
               for v in (self.visual_ms, self.motor_ms)):
            raise ValueError("Delays must be nonnegative multiples of 10 ms")
        if not math.isfinite(self.overlap_deg) or not 0 <= self.overlap_deg <= 30:
            raise ValueError("Overlap must be finite and in [0,30]")

    @property
    def name(self):
        return f"visual{self.visual_ms}_motor{self.motor_ms}_overlap{self.overlap_deg:g}"


DECLARED = Timing(0, 200, 15)
FRESH_PATHS = tuple(p for n in ("harmonic", "dwell_reversal", "ramp_stop")
                    for p in (n, "mirror_" + n))


def fresh_target(path: str, t: float) -> float:
    name = path.removeprefix("mirror_")
    if name == "harmonic":
        value = 1.8 * math.sin(0.8 * t + 0.3) + 0.6 * math.sin(2.2 * t - 0.7)
    elif name == "dwell_reversal":
        value = -2.0 if t < 1.5 else 1.2 if t < 4.5 else -0.8
    elif name == "ramp_stop":
        value = -2.1 + 1.05 * t if t < 3 else 1.05 if t < 5 else 1.05 - 0.7 * (t - 5)
    else:
        raise ValueError(f"Unknown fresh path {path}")
    return -value if path.startswith("mirror_") else value


def overlap_adapter(base: ActivityAdapter, overlap_deg: float) -> ActivityAdapter:
    """Replace only eye aperture/contralateral Gaussian; keep gains/weights fixed."""
    if overlap_deg == 0:
        return base
    Timing(overlap_deg=overlap_deg)
    p = base.projection
    sign = np.where(p.sides == "R", 1.0, -1.0)
    angles = GRID[:, None]
    aperture = np.clip(0.5 + angles * sign / overlap_deg, 0.0, 1.0)
    visual = np.exp(-0.5 * ((angles - p.centers_deg * sign) / base.width_deg) ** 2)
    response = (visual * aperture) @ p.lc_to_aotu
    return replace(base, response=response)


def simulate(path: str, adapter: ActivityAdapter, timing: Timing, *,
             condition: str = "intact", pivot: bool = False,
             fresh: bool = False, gain: float = 1.0,
             trace_path: Path | None = None) -> dict:
    if condition not in ("intact", "bridge_removed", "direct_bearing", "playable_lif"):
        raise ValueError("Unknown condition")
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError("Gain must be positive and finite")
    x = z = heading = turn_rate = 0.0
    seen, commands, bearings, turns, trace = [], [], [], [], []
    caps = aotu_caps = dn_caps = visible_count = 0
    lif = SteeringSession(load_candidate()) if condition == "playable_lif" else None
    for step in range(STEPS):
        heading = _wrapped_radians(heading + turn_rate * DT)
        if not pivot:
            x += math.sin(heading) * WALK_SPEED * DT
            z -= math.cos(heading) * WALK_SPEED * DT
        t = (step + 1) * DT
        if pivot:
            angle = -20 if t < 2 else 20
            if path.startswith("mirror_"):
                angle = -angle
            tx = -TARGET_Z * math.tan(math.radians(angle))
        else:
            tx = fresh_target(path, t) if fresh else target_x(path, t)
        bearing, visible = _bearing_and_view(x, z, heading, tx)
        bearings.append(bearing)
        visible_count += int(visible)
        signal = 0.0
        if condition == "direct_bearing":
            turn_rate = MAX_TURN_RATE * np.clip(bearing / 45, -1, 1) if visible else 0.0
        elif lif is not None:
            result = lif.step({"x": x, "z": z, "heading_rad": heading},
                              {"x": tx, "z": TARGET_Z, "active": True}, 10)
            turn_rate = result["turn_rate_rad_s"]
        else:
            seen.append(bearing if visible else 0.0)
            read_idx = max(0, step - timing.visual_ms // 10)
            motion = seen[read_idx] - seen[read_idx - 1] if read_idx else 0.0
            result = adapter.activity_at(seen[read_idx], motion, condition=condition)
            signal = result["signal"]
            requested = math.radians(AUTHOR_GAIN * gain * signal) / DT
            command = max(-MAX_TURN_RATE, min(MAX_TURN_RATE, requested))
            commands.append(command)
            motor_idx = step - timing.motor_ms // 10
            turn_rate = commands[motor_idx] if motor_idx >= 0 else 0.0
            aotu_caps += int(result["aotu_clipped"])
            dn_caps += int(result["dn_clipped"])
        caps += int(abs(turn_rate) >= MAX_TURN_RATE - 1e-10)
        turns.append(turn_rate)
        if trace_path:
            trace.append({"t_s": t, "bearing_deg": bearing,
                          "turn_rate_rad_s": turn_rate, "signal": signal})
    out = {
        "mean_abs_bearing_deg": round(float(np.mean(np.abs(bearings))), 3),
        "final_abs_bearing_deg": round(abs(bearings[-1]), 3),
        "settling_time_s": continuous_settling_s(bearings, path),
        "near_target_sign_crossings": sum(a * b < 0 for a, b in zip(bearings[:-1], bearings[1:])
                                          if abs(a) <= 10 or abs(b) <= 10),
        "in_view_fraction": round(visible_count / STEPS, 4),
        "turn_cap_fraction": round(caps / STEPS, 4),
        "aotu_lookup_clip_fraction": round(aotu_caps / STEPS, 4),
        "dn_lookup_clip_fraction": round(dn_caps / STEPS, 4),
        "mean_abs_turn_rate_rad_s": round(float(np.mean(np.abs(turns))), 5),
        "last_second_peak_abs_bearing_deg": round(float(np.max(np.abs(bearings[-100:]))), 3),
        "last_second_mean_abs_bearing_deg": round(float(np.mean(np.abs(bearings[-100:]))), 3),
    }
    settled = out["settling_time_s"]
    out["peak_after_settling_deg"] = (None if settled is None else
        round(float(np.max(np.abs(bearings[max(0, round(settled / DT)):]))), 3))
    if trace_path:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    return out


def run(output: Path, trace_dir: Path) -> dict:
    projection = ActivityProjection.from_packaged_data()
    base = ActivityAdapter.build(projection)
    matrix = []
    for overlap in (0, 15):
        adapter = overlap_adapter(base, overlap)
        for visual in (0, 50, 200, 450):
            for motor in (0, 200):
                timing = Timing(visual, motor, overlap)
                rows = {}
                for pivot in (False, True):
                    for path in ("step_hold", "mirror_step_hold"):
                        name = ("pivot_" if pivot else "walking_") + path
                        rows[name] = simulate(path, adapter, timing, pivot=pivot,
                            trace_path=trace_dir / f"{timing.name}_{name}.json")
                matrix.append({"configuration": timing.__dict__, "name": timing.name,
                               "trials": rows})
    equivalence = {}
    for path in ("step_hold", "mirror_step_hold"):
        old = run_trial(path, "intact", adapter=base)
        replay = simulate(path, base, Timing())
        equivalence[path] = all(old[k] == v for k, v in replay.items() if k in old)
    if not all(equivalence.values()):
        raise AssertionError("Diagnostic failed frozen Step 4 equivalence")
    candidate = overlap_adapter(base, DECLARED.overlap_deg)
    heldout = {path: {name: simulate(path, model, timing, condition=condition, fresh=True)
                     for name, model, timing, condition in (
                         ("baseline", base, Timing(), "intact"),
                         ("candidate", candidate, DECLARED, "intact"),
                         ("bridge_removed", candidate, DECLARED, "bridge_removed"),
                         ("direct_bearing", base, Timing(), "direct_bearing"),
                         ("playable_lif", base, Timing(), "playable_lif"))}
               for path in FRESH_PATHS}
    rng = np.random.default_rng(20260930)
    shuffles = []
    shuffle_diagnostics = []
    for _ in range(32):
        shuffled = ActivityAdapter.build(shuffled_projection(projection, rng),
                                        peaks=base.peaks, edge_scales=base.edge_scales)
        shuffled = overlap_adapter(shuffled, DECLARED.overlap_deg)
        rows = {p: simulate(p, shuffled, DECLARED, fresh=True) for p in FRESH_PATHS}
        shuffle_diagnostics.append(rows)
        shuffles.append({p: r["mean_abs_bearing_deg"] for p, r in rows.items()})
    sensitivities = {}
    for name, gain, overlap in (("gain0.8", .8, 15), ("gain1.2", 1.2, 15),
                                ("overlap10", 1, 10), ("overlap20", 1, 20)):
        model = overlap_adapter(base, overlap)
        timing = replace(DECLARED, overlap_deg=overlap)
        sensitivities[name] = {
            "fresh": {p: simulate(p, model, timing, fresh=True, gain=gain) for p in FRESH_PATHS},
            "steps": {p: simulate(p, model, timing, gain=gain)
                      for p in ("step_hold", "mirror_step_hold")}}
    medians = {c: float(np.median([heldout[p][c]["mean_abs_bearing_deg"] for p in FRESH_PATHS]))
               for c in heldout[FRESH_PATHS[0]]}
    shuffle_medians = {p: float(np.median([s[p] for s in shuffles])) for p in FRESH_PATHS}
    steps = {p: simulate(p, candidate, DECLARED) for p in ("step_hold", "mirror_step_hold")}
    gates = {
        "both_steps_settle": all(r["settling_time_s"] is not None for r in steps.values()),
        "twenty_percent_over_bridge": medians["candidate"] <= .8 * medians["bridge_removed"],
        "five_of_six_over_median_shuffle": sum(heldout[p]["candidate"]["mean_abs_bearing_deg"]
                                             < shuffle_medians[p] for p in FRESH_PATHS) >= 5,
        "view_cap_and_lookup": all(r["in_view_fraction"] >= .8 and r["turn_cap_fraction"] < .25
                                   and r["aotu_lookup_clip_fraction"] == 0
                                   and r["dn_lookup_clip_fraction"] == 0
                                   for r in [*steps.values(), *[heldout[p]["candidate"] for p in FRESH_PATHS]]),
        "gain_robustness": all(all(r["settling_time_s"] is not None for r in sensitivities[k]["steps"].values())
                               and abs(float(np.median([r["mean_abs_bearing_deg"] for r in sensitivities[k]["fresh"].values()]))
                                       / medians["candidate"] - 1) <= .25 for k in ("gain0.8", "gain1.2")),
    }
    provenance_paths = [Path("docs/pursuit_delay_protocol.md"),
                        _map_path("visual_steering_v1.json"),
                        _map_path("lc10a_registered_eyemap_hypothesis_v3.json"),
                        Path(__file__), Path(__file__).with_name("pursuit_step4.py")]
    report = {"protocol_sha256": hashlib.sha256(provenance_paths[0].read_bytes()).hexdigest(),
              "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in provenance_paths},
              "fixed_parameters": {"dt_s": DT, "steps": STEPS, "width_deg": base.width_deg,
                                   "gain": AUTHOR_GAIN, "walk_speed_m_s": WALK_SPEED,
                                   "max_turn_rate_rad_s": MAX_TURN_RATE,
                                   "peaks": base.peaks, "edge_scales": base.edge_scales},
              "baseline_equivalence": equivalence, "matrix": matrix,
              "declared_candidate": DECLARED.__dict__, "candidate_steps": steps,
              "fresh_paths": heldout, "medians_deg": medians, "shuffle_seed": 20260930,
              "shuffles": shuffles, "shuffle_diagnostics": shuffle_diagnostics,
              "shuffle_medians_deg": shuffle_medians,
              "sensitivity": sensitivities, "gates": gates,
              "eligible_for_review": all(gates.values()), "godot_changed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"medians_deg": medians, "gates": gates,
                      "baseline_equivalence": equivalence}, indent=2))
    return report


def main():
    run(Path("docs/evidence/pursuit_delay_v1.json"), Path("outputs/research/pursuit_delay_traces"))


if __name__ == "__main__":
    main()

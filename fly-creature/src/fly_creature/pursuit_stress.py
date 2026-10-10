"""Frozen controller envelope test; no production settings are edited here."""
from __future__ import annotations

from collections import deque
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .pursuit_activity import ActivityProjection
from .pursuit_controller import ActivitySteeringSession
from .pursuit_delay_diagnostic import DECLARED, FRESH_PATHS, fresh_target, overlap_adapter, simulate
from .pursuit_step4 import ActivityAdapter, DT, MAX_TURN_RATE, VIEW_DEG, WALK_SPEED, shuffled_projection
from .steering import target_feature

STEPS = 1000
SEED = 20261002
SHUFFLES = 32
GAINS = (.5, 1, 2, 3, 4, 6, 8)
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Case:
    family: str
    level: float | str
    mirror: bool = False

    @property
    def name(self):
        return f"{self.family}_{self.level}" + ("_mirror" if self.mirror else "")

    @property
    def supported(self):
        return self.family not in ("stationary_depth", "unsupported")

    @property
    def heading(self):
        return math.radians(float(self.level)) * (-1 if self.mirror else 1) if self.family == "heading" else 0.0

    @property
    def reappears(self):
        return 4 + float(self.level) if self.family in ("dropout", "reentry") else None

    def target(self, t):
        depth = float(self.level) if self.family in ("distance", "stationary_depth") else 6.0
        z = -depth - WALK_SPEED * t
        x = 1.6 * math.sin(.93 * t + .4) + .45 * math.sin(2.7 * t - .2)
        active = True
        if self.family == "distance":
            x = depth * (.27 * math.sin(1.15 * t + .6) + .07 * math.sin(2.9 * t - .2))
        elif self.family == "speed":
            frequency = float(self.level)
            x = 2.2 * math.sin(frequency * t - .6) + .4 * math.sin(1.9 * frequency * t + .1)
        elif self.family == "reversal":
            phase = (t / float(self.level)) % 1
            x = 1.8 * (1 - 4 * abs(phase - .5))
        elif self.family in ("dropout", "reentry"):
            active = not (4 <= t < self.reappears)
            if self.family == "reentry":
                x = -2.0 if t < 4 else 2.0 + .5 * math.sin(1.3 * (t - 4))
        elif self.family == "stationary_depth":
            z = -depth
        elif self.family == "unsupported":
            x = 0.0
            z = {"behind": 4.0, "far": -12.0 - WALK_SPEED * t,
                 "close": -.2}[str(self.level)]
        return {"x": -x if self.mirror else x, "z": z, "active": active}


def cases():
    levels = {"distance": (3, 5, 8), "speed": (.35, 1.7, 3),
              "reversal": (2, 4, 6), "heading": (25, 65, 105),
              "dropout": (.2, .8, 2), "reentry": (.2, .8, 2),
              "stationary_depth": (2.5, 5, 8), "unsupported": ("behind", "far", "close")}
    return [Case(family, level, mirror) for family, values in levels.items()
            for level in values for mirror in (False, True)]


class KnownHarmonic:
    heading = 0.0
    reappears = None

    def target(self, t):
        return {"x": fresh_target("harmonic", t), "z": -7, "active": True}


def visible(feature, target):
    return bool(target["active"]) and .4 <= feature["distance"] <= 9 and abs(feature["bearing_deg"]) <= VIEW_DEG


class Direct:
    def __init__(self, gain, delay=20):
        self.gain, self.delay = gain, delay
        self.queue = deque()

    def step(self, fly, target, dt_ms):
        if dt_ms != 10:
            raise ValueError("Stress test requires 10 ms")
        feature = target_feature(fly, target)
        command = max(-MAX_TURN_RATE, min(MAX_TURN_RATE,
            self.gain * math.radians(feature["bearing_deg"]))) if visible(feature, target) else 0.0
        self.queue.append(command)
        turn = self.queue.popleft() if len(self.queue) > self.delay else 0.0
        if not target["active"]:
            self.queue.clear()
            turn = 0.0
        return {"turn_rate_rad_s": turn}


class MeasuredAdapter:
    """Observe the existing adapter without changing its outputs."""
    def __init__(self, adapter):
        self.adapter = adapter
        self.aotu_clips = self.dn_clips = 0

    def activity_at(self, *args, **kwargs):
        out = self.adapter.activity_at(*args, **kwargs)
        self.aotu_clips += int(out["aotu_clipped"])
        self.dn_clips += int(out["dn_clipped"])
        return out


def activity_session(adapter, condition="intact"):
    session = ActivitySteeringSession(condition=condition)
    measured = MeasuredAdapter(adapter)
    session.adapter = measured
    return session, measured


def envelope(metrics, needs_recovery):
    return {"mean_error": metrics["active_mean_abs_bearing_deg"] <= 10,
            "visibility": metrics["active_in_view_fraction"] >= .8,
            "motor_caps": metrics["turn_cap_fraction"] < .25,
            "lookup_range": metrics["aotu_clip_fraction"] == metrics["dn_clip_fraction"] == 0,
            "inactive_safe": metrics["inactive_turn_ticks"] == 0,
            "reacquisition": not needs_recovery or (metrics["reacquisition_s"] is not None
                                                   and metrics["reacquisition_s"] <= 1.5)}


def trial(case, controller, *, steps=STEPS, measured=None, trace_path=None):
    x = z = turn = 0.0
    heading = case.heading
    rows = []
    recovery = None
    consecutive = 0
    for tick in range(steps):
        heading = math.atan2(math.sin(heading + turn * DT), math.cos(heading + turn * DT))
        x += math.sin(heading) * WALK_SPEED * DT
        z -= math.cos(heading) * WALK_SPEED * DT
        t = (tick + 1) * DT
        target = case.target(t)
        fly = {"x": x, "z": z, "heading_rad": heading}
        feature = target_feature(fly, target)
        seen = visible(feature, target)
        out = controller.step(fly, target, 10)
        turn = out["turn_rate_rad_s"]
        if case.reappears is not None and t >= case.reappears:
            consecutive = consecutive + 1 if seen and abs(feature["bearing_deg"]) <= 10 else 0
            if consecutive >= 50 and recovery is None:
                recovery = round(t - case.reappears, 3)
        rows.append({"t_s": t, "fly_x": x, "fly_z": z,
                     "heading_deg": math.degrees(heading), "target_x": target["x"],
                     "target_z": target["z"], "active": target["active"], "visible": seen,
                     "distance_m": feature["distance"], "bearing_deg": feature["bearing_deg"],
                     "turn_rate_rad_s": turn})
    active = [r for r in rows if r["active"]]
    metrics = {"active_mean_abs_bearing_deg": round(float(np.mean([abs(r["bearing_deg"]) for r in active])), 6),
               "active_in_view_fraction": sum(r["visible"] for r in active) / len(active),
               "final_active_abs_bearing_deg": abs(active[-1]["bearing_deg"]),
               "min_active_distance_m": min(r["distance_m"] for r in active),
               "max_active_distance_m": max(r["distance_m"] for r in active),
               "turn_cap_fraction": sum(abs(r["turn_rate_rad_s"]) >= MAX_TURN_RATE - 1e-10 for r in rows) / steps,
               "mean_abs_turn_rad_s": float(np.mean([abs(r["turn_rate_rad_s"]) for r in rows])),
               "inactive_turn_ticks": sum(not r["active"] and r["turn_rate_rad_s"] != 0 for r in rows),
               "aotu_clip_fraction": measured.aotu_clips / steps if measured else 0.0,
               "dn_clip_fraction": measured.dn_clips / steps if measured else 0.0,
               "reacquisition_s": recovery, "active_ticks": len(active), "ticks": steps}
    metrics["envelope_components"] = envelope(metrics, case.reappears is not None)
    metrics["within_envelope"] = all(metrics["envelope_components"].values())
    if trace_path:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    return metrics


def calibrate_direct():
    scores = {}
    for gain in GAINS:
        path_errors = []
        for path in FRESH_PATHS:
            controller = Direct(gain)
            x = z = heading = turn = total = 0.0
            for tick in range(800):
                heading += turn * DT
                x += math.sin(heading) * WALK_SPEED * DT
                z -= math.cos(heading) * WALK_SPEED * DT
                fly = {"x": x, "z": z, "heading_rad": heading}
                target = {"x": fresh_target(path, (tick + 1) * DT), "z": -7, "active": True}
                total += abs(target_feature(fly, target)["bearing_deg"])
                turn = controller.step(fly, target, 10)["turn_rate_rad_s"]
            path_errors.append(total / 800)
        scores[gain] = float(np.mean(path_errors))
    return min(scores, key=lambda gain: (scores[gain], gain)), scores


def hashes():
    paths = [ROOT / "docs/pursuit_stress_protocol.md", Path(__file__),
             Path(__file__).with_name("pursuit_controller.py"),
             Path(__file__).with_name("pursuit_step4.py"),
             Path(__file__).with_name("pursuit_delay_diagnostic.py"),
             ROOT / "src/fly_creature/data/visual_steering_v1.json",
             ROOT / "src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(output=None, trace_dir=None):
    output = output or ROOT / "docs/evidence/pursuit_stress_v1.json"
    trace_dir = trace_dir or ROOT / "outputs/research/pursuit_stress"
    before = hashes()
    projection = ActivityProjection.from_packaged_data()
    base = ActivityAdapter.build(projection)
    adapter = overlap_adapter(base, DECLARED.overlap_deg)
    seam, seam_observed = activity_session(adapter)
    seam_result = trial(KnownHarmonic(), seam, steps=800, measured=seam_observed)
    equivalence = simulate("harmonic", adapter, DECLARED, fresh=True)["mean_abs_bearing_deg"]
    assert abs(seam_result["active_mean_abs_bearing_deg"] - equivalence) < .001
    gain, calibration = calibrate_direct()
    print(json.dumps({"calibrated_direct_gain": gain, "old_path_scores": calibration}), flush=True)
    suite = cases()
    trials = {}
    for case in suite:
        intact, observed = activity_session(adapter)
        removed, disconnected_observed = activity_session(adapter, "disconnected")
        trials[case.name] = {"case": asdict(case), "supported": case.supported,
            "intact": trial(case, intact, measured=observed, trace_path=trace_dir / f"{case.name}_intact.csv"),
            "disconnected": trial(case, removed, measured=disconnected_observed),
            "direct_matched": trial(case, Direct(gain), trace_path=trace_dir / f"{case.name}_direct.csv"),
            "direct_immediate": trial(case, Direct(gain, delay=0))}
    shuffled = []
    for index in range(SHUFFLES):
        rng = np.random.default_rng(np.random.SeedSequence([SEED, index]))
        p = shuffled_projection(projection, rng)
        model = overlap_adapter(ActivityAdapter.build(p, peaks=base.peaks, edge_scales=base.edge_scales), DECLARED.overlap_deg)
        values = {}
        for case in suite:
            session, observed = activity_session(model)
            values[case.name] = trial(case, session, measured=observed)["active_mean_abs_bearing_deg"]
        shuffled.append(values)
        print(f"Completed shuffle {index + 1}/{SHUFFLES}", flush=True)
    for case in suite:
        row = trials[case.name]
        errors = [s[case.name] for s in shuffled]
        row["shuffle_error_deg"] = {"median": float(np.median(errors)),
            "min": min(errors), "max": max(errors),
            "intact_beats": sum(row["intact"]["active_mean_abs_bearing_deg"] < e for e in errors)}
    groups = {}
    for group in ("supported", "challenge", *dict.fromkeys(c.family for c in suite)):
        selected = [c.name for c in suite if (c.supported if group == "supported" else
                    not c.supported if group == "challenge" else c.family == group)]
        groups[group] = {"cases": len(selected), "controllers": {}}
        for control in ("intact", "disconnected", "direct_matched", "direct_immediate"):
            rows = [trials[n][control] for n in selected]
            groups[group]["controllers"][control] = {
                "mean_case_error_deg": float(np.mean([r["active_mean_abs_bearing_deg"] for r in rows])),
                "within_envelope": sum(r["within_envelope"] for r in rows)}
        intact_mean = groups[group]["controllers"]["intact"]["mean_case_error_deg"]
        groups[group]["shuffle_aggregate_errors_deg"] = [float(np.mean([s[n] for n in selected])) for s in shuffled]
        groups[group]["intact_beats_shuffle_aggregates"] = sum(intact_mean < e for e in groups[group]["shuffle_aggregate_errors_deg"])
        groups[group]["intact_beats_median_shuffle_cases"] = sum(trials[n]["intact"]["active_mean_abs_bearing_deg"] < trials[n]["shuffle_error_deg"]["median"] for n in selected)
    assert equivalence == 2.350, equivalence
    assert before == hashes(), "Frozen inputs changed during run"
    report = {"protocol": "pursuit_stress_v1", "input_sha256": before,
              "dt_s": DT, "steps": STEPS, "shuffle_seed": SEED, "shuffles": SHUFFLES,
              "direct_gain": gain, "calibration_old_paths": calibration,
              "known_harmonic_offline_error_deg": equivalence,
              "known_harmonic_actual_session": seam_result, "trials": trials,
              "groups": groups, "shuffle_case_errors_deg": shuffled,
              "production_controller_changed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    compact = [{"case": n, "family": r["case"]["family"], "supported": r["supported"],
                "controller": control, **{k: v for k, v in r[control].items() if k != "envelope_components"}}
               for n, r in trials.items() for control in ("intact", "disconnected", "direct_matched", "direct_immediate")]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=compact[0])
        writer.writeheader()
        writer.writerows(compact)
    print(json.dumps({g: groups[g] for g in ("supported", "challenge")}, indent=2), flush=True)
    return report


if __name__ == "__main__":
    run()

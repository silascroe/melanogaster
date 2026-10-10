"""Offline one-factor motion interventions; production controller stays frozen."""
from collections import deque
from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .pursuit_activity import ActivityProjection
from .pursuit_controller import ActivitySteeringSession
from .pursuit_delay_diagnostic import DECLARED, overlap_adapter
from .pursuit_step4 import ActivityAdapter, AUTHOR_GAIN, DT, MAX_TURN_RATE, shuffled_projection
from .pursuit_stress import Direct, ROOT, cases, trial, visible
from .steering import target_feature

VARIANTS = ("baseline", "position_only", "reversed_direction", "target_only",
            "continuous_visible", "zero_delay")
SEED = 20261003


def delta_angle(a, b):
    return math.degrees(math.atan2(math.sin(math.radians(a - b)),
                                   math.cos(math.radians(a - b))))


class MotionSession:
    """Explicit diagnostic copy, validated tick-for-tick against actual runtime."""
    def __init__(self, adapter, variant="baseline", condition="intact"):
        if variant not in VARIANTS:
            raise ValueError("Unknown motion intervention")
        self.adapter, self.variant, self.condition = adapter, variant, condition
        self.queue = deque()
        self.previous_bearing = self.previous_target = None
        self.previous_visible = False
        self.elapsed_ms = 0
        self.aotu_clips = self.dn_clips = 0
        self.opposing_turns = self.eligible_turns = self.motion_sign_disagreements = 0
        self.observable_motion_ticks = self.visibility_gaps = 0

    def step(self, fly, target, dt_ms):
        if dt_ms != 10:
            raise ValueError("Diagnostic requires exact 10 ms ticks")
        feature = target_feature(fly, target)
        seen = visible(feature, target)
        bearing = feature["bearing_deg"] if seen else 0.0
        motion = bearing - self.previous_bearing if self.previous_bearing is not None else 0.0
        target_motion = 0.0
        if seen and self.previous_visible and self.previous_target is not None:
            old_target_bearing = target_feature(fly, self.previous_target)["bearing_deg"]
            target_motion = delta_angle(bearing, old_target_bearing)
            self.observable_motion_ticks += 1
            self.motion_sign_disagreements += int(motion * target_motion < 0)
        if seen and not self.previous_visible:
            self.visibility_gaps += int(self.previous_bearing is not None)
        if self.variant == "target_only":
            motion = target_motion
        elif self.variant == "continuous_visible":
            motion = delta_angle(bearing, self.previous_bearing) if seen and self.previous_visible else 0.0
        elif self.variant == "reversed_direction":
            motion = -motion
        result = self.adapter.activity_at(bearing, motion,
            direction_selective=self.variant != "position_only", condition=self.condition)
        self.aotu_clips += int(result["aotu_clipped"])
        self.dn_clips += int(result["dn_clipped"])
        signal = result["signal"] if seen else 0.0
        command = max(-MAX_TURN_RATE, min(MAX_TURN_RATE, math.radians(AUTHOR_GAIN * signal) / DT))
        self.queue.append(command)
        delay = 0 if self.variant == "zero_delay" else DECLARED.motor_ms // 10
        turn = self.queue.popleft() if len(self.queue) > delay else 0.0
        self.previous_bearing = bearing
        self.previous_target = dict(target)
        self.previous_visible = seen
        if not target["active"]:
            self.queue.clear()
            self.previous_bearing = self.previous_target = None
            self.previous_visible = False
            turn = 0.0
        if seen and abs(bearing) > 1.0 and abs(turn) > 1e-12:
            self.eligible_turns += 1
            self.opposing_turns += int(turn * bearing < 0)
        self.elapsed_ms += 10
        return {"turn_rate_rad_s": turn, "signal": signal, "motion_deg": motion,
                "target_only_motion_deg": target_motion}

    def observations(self):
        return {"opposing_current_error_turn_fraction": self.opposing_turns / max(1, self.eligible_turns),
                "retinal_target_motion_sign_disagreement_fraction":
                    self.motion_sign_disagreements / max(1, self.observable_motion_ticks),
                "visible_motion_ticks": self.observable_motion_ticks,
                "visibility_reentry_ticks": self.visibility_gaps}


@dataclass(frozen=True)
class FreshCase:
    family: str
    depth: float
    mirror: bool = False
    heading = 0.0
    reappears = None

    @property
    def name(self):
        return f"{self.family}_{self.depth:g}" + ("_mirror" if self.mirror else "")

    def target(self, t):
        if self.family == "chirp":
            x = 2.0 * math.sin(.8 * t + .16 * t * t - .3)
        elif self.family == "asymmetric":
            x = 1.9 * math.sin(2.1 * t + .5) + .55 * math.sin(4.2 * t - .9)
        elif self.family == "modulated":
            x = (1.6 + .5 * math.sin(.43 * t)) * math.sin(2.65 * t + .7)
        else:
            raise ValueError("Unknown fresh case")
        return {"x": -x if self.mirror else x, "z": -self.depth - .55 * t, "active": True}


def fresh_cases():
    return [FreshCase(f, d, m) for f in ("chirp", "asymmetric", "modulated")
            for d in (5., 7.) for m in (False, True)]


def model(projection=None, base=None):
    adapter = ActivityAdapter.build(projection or ActivityProjection.from_packaged_data(),
        peaks=base.peaks if base else None, edge_scales=base.edge_scales if base else None)
    return overlap_adapter(adapter, DECLARED.overlap_deg)


def score(case, adapter, variant="baseline", condition="intact", trace_path=None):
    session = MotionSession(adapter, variant, condition)
    metrics = trial(case, session, measured=session, trace_path=trace_path)
    return {**metrics, "observations": session.observations()}


def mean(rows, key):
    return float(np.mean([row[key]["active_mean_abs_bearing_deg"] for row in rows]))


def select_candidate(old):
    supported = [r for r in old.values() if r["supported"]]
    hard = [r for r in supported if (r["case"]["family"] == "speed" and r["case"]["level"] in (1.7, 3))
            or (r["case"]["family"] == "reversal" and r["case"]["level"] == 2)]
    gates = {}
    for name in ("position_only", "continuous_visible"):
        gates[name] = {"hard_5pct_improvement": mean(hard, name) <= .95 * mean(hard, "baseline"),
            "supported_no_1pct_regression": mean(supported, name) <= 1.01 * mean(supported, "baseline"),
            "no_case_10pct_regression": all(r[name]["active_mean_abs_bearing_deg"] <=
                1.1 * r["baseline"]["active_mean_abs_bearing_deg"] + 1e-9 for r in supported)}
    eligible = [n for n, checks in gates.items() if all(checks.values())]
    selected = min(eligible, key=lambda n: mean(hard, n)) if eligible else None
    return selected, gates


def geometry_probes(adapter):
    fly = {"x": 0., "z": 0., "heading_rad": 0.}
    target = {"x": 2., "z": -6., "active": True}
    turning = MotionSession(adapter)
    turning.step(fly, target, 10)
    turn = turning.step({**fly, "heading_rad": .01}, target, 10)
    moving = MotionSession(adapter)
    moving.step(fly, target, 10)
    move = moving.step(fly, {**target, "x": 2.1}, 10)
    ratios = {}
    for side in ("L", "R"):
        sign = -1 if side == "L" else 1
        a = adapter.activity_at(30 * sign, sign)["aotu"]
        b = adapter.activity_at(30 * sign, -sign)["aotu"]
        i = next(i for i, pair in enumerate(zip(adapter.projection.aotu_types,
                adapter.projection.aotu_sides)) if pair == ("AOTU019", side))
        ratios[side] = float(a[i] / b[i])
    return {"static_target_rotating_body": turn, "moving_target_fixed_body": move,
            "preferred_nonpreferred_aotu019_ratio": ratios}


def input_hashes():
    paths = [ROOT / "docs/pursuit_motion_protocol.md", Path(__file__),
             *[ROOT / "src/fly_creature" / n for n in ("pursuit_controller.py", "pursuit_step4.py",
                "pursuit_delay_diagnostic.py", "pursuit_stress.py", "data/visual_steering_v1.json",
                "data/lc10a_registered_eyemap_hypothesis_v3.json")]]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(output):
    before = input_hashes()
    adapter = model()
    frozen = json.loads((ROOT / "docs/evidence/pursuit_stress_v1.json").read_text())
    old = {}
    for case in cases():
        old[case.name] = {"supported": case.supported, "case": {"family": case.family,
            "level": case.level, "mirror": case.mirror}}
        for variant in VARIANTS:
            old[case.name][variant] = score(case, adapter, variant)
        expected = frozen["trials"][case.name]["intact"]
        assert all(old[case.name]["baseline"][k] == v for k, v in expected.items()), case.name
    selected, gates = select_candidate(old)
    print(json.dumps({"selected": selected, "selection_gates": gates}), flush=True)
    fresh = {}
    neural = ["baseline", "position_only"] + ([selected] if selected not in (None, "position_only") else [])
    trace_dir = ROOT / "outputs/research/pursuit_motion"
    for case in fresh_cases():
        fresh[case.name] = {name: score(case, adapter, name,
            trace_path=trace_dir / f"{case.name}_{name}.csv") for name in neural}
        fresh[case.name]["disconnected"] = score(case, adapter, condition="bridge_removed")
        fresh[case.name]["ordinary_delayed"] = trial(case, Direct(4))
        fresh[case.name]["ordinary_immediate"] = trial(case, Direct(4, 0))
    shuffle = {name: [] for name in neural}
    for index in range(32):
        rng = np.random.default_rng(np.random.SeedSequence([SEED, index]))
        shuffled = model(shuffled_projection(adapter.projection, rng), adapter)
        for name in neural:
            shuffle[name].append({c.name: score(c, shuffled, name)["active_mean_abs_bearing_deg"]
                                 for c in fresh_cases()})
        if (index + 1) % 8 == 0:
            print(f"Shuffle {index + 1}/32", flush=True)
    summary = {}
    for name in fresh[next(iter(fresh))]:
        rows = [r[name] for r in fresh.values()]
        summary[name] = {"mean_error_deg": mean(list(fresh.values()), name),
                         "envelope_cases": sum(r["within_envelope"] for r in rows)}
        if name in shuffle:
            aggregates = [float(np.mean(list(r.values()))) for r in shuffle[name]]
            summary[name]["shuffle_aggregate_errors"] = aggregates
            summary[name]["beats_shuffle_aggregates"] = sum(summary[name]["mean_error_deg"] < x for x in aggregates)
    promotion_gates = None
    if selected:
        promotion_gates = {"fresh_5pct_improvement": summary[selected]["mean_error_deg"] <= .95 * summary["baseline"]["mean_error_deg"],
            "no_case_10pct_regression": all(r[selected]["active_mean_abs_bearing_deg"] <= 1.1 * r["baseline"]["active_mean_abs_bearing_deg"] for r in fresh.values()),
            "no_envelope_loss": all(not r["baseline"]["within_envelope"] or r[selected]["within_envelope"] for r in fresh.values()),
            "safe_unclipped": all(r[selected]["inactive_turn_ticks"] == r[selected]["aotu_clip_fraction"] == r[selected]["dn_clip_fraction"] == 0 for r in fresh.values()),
            "beats_all_shuffles": summary[selected]["beats_shuffle_aggregates"] == 32}
    assert before == input_hashes()
    report = {"input_sha256": before, "baseline_parity_cases": 48, "geometry": geometry_probes(adapter),
        "old_cases": old, "selected_candidate": selected, "selection_gates": gates,
        "fresh_cases": fresh, "fresh_summary": summary, "shuffle_seed": SEED,
        "shuffle_errors": shuffle, "promotion_gates": promotion_gates,
        "promotion_recommended": bool(promotion_gates and all(promotion_gates.values())),
        "production_changed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    rows = [{"case": case, "controller": name, "error_deg": values["active_mean_abs_bearing_deg"],
             "within_envelope": values["within_envelope"]}
            for case, controls in fresh.items() for name, values in controls.items()]
    with output.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"fresh_summary": summary, "promotion_gates": promotion_gates}, indent=2), flush=True)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/pursuit_motion_v1.json")
    run(parser.parse_args().output)

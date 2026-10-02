"""Frozen rotation-only reference comparison; no playable settings changed."""
from collections import deque
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .pursuit_activity import ActivityProjection
from .pursuit_motion_diagnostic import model
from .pursuit_reference import (ReferenceConfig, load_response_fields, simulate_step,
                                _elu_lookup, _nearest_lookup)
from .pursuit_step4 import shuffled_projection

DT = .01
N = 1200
HOLD = 100
DELAY = 20
CAP = math.degrees(1.2)
ROOT = Path(__file__).resolve().parents[2]
SEED = 20261004


def wrap(value):
    return (value + 180.) % 360. - 180.


class AuthorResponse:
    """Pinned dynamic response, excluding minor pathways as in our selection."""
    def __init__(self, fields, direction=True):
        self.r019 = np.abs(fields.aotu019_right)
        self.r025 = np.abs(fields.aotu025_right)
        self.look019 = _elu_lookup(float(self.r019.max()))
        self.look025 = _elu_lookup(float(self.r025.max()))
        self.dn_grid = np.linspace(-2.25, 4., 1000)
        self.direction = direction

    def activity_at(self, bearing, motion):
        idx = int(math.copysign(math.floor(abs(bearing) + .5), bearing)) + 180
        p_r = .66 if self.direction and motion < 0 else 1.
        p_l = .66 if self.direction and motion > 0 else 1.
        r019 = float(_nearest_lookup(*self.look019, self.r019[idx] * p_r))
        l019 = float(_nearest_lookup(*self.look019, self.r019[360-idx] * p_l))
        r025 = float(_nearest_lookup(*self.look025, self.r025[idx]))
        l025 = float(_nearest_lookup(*self.look025, self.r025[360-idx]))
        dn = _nearest_lookup(self.dn_grid, self.dn_grid,
                             np.array([l025-r019, r025-l019]))
        return {"aotu": [r019, l019, r025, l025], "dn": dn,
                "signal": float(dn[1]-dn[0])}


def parity(fields):
    """Independent delayed Eq6 loop vs unchanged source port with 200 ms override."""
    errors = {}
    for direction in (False, True):
        response = AuthorResponse(fields, direction)
        for moving in (False, True):
            config = ReferenceConfig(duration_s=12, aotu019_delay_ms=200,
                                     other_delay_ms=200, direction_mode=int(direction))
            noise = np.zeros((2, N))
            if moving:
                noise[0, HOLD:] = .18*np.sin(np.arange(N-HOLD)*.013)
                noise[1] = -noise[0]
            expected = simulate_step(fields, config, movement_noise_deg=noise)
            actual = np.zeros((2, N))
            actual[:, :HOLD] = np.array([120., -120.])[:, None]
            turns = np.zeros((2, N))
            for t in range(HOLD, N):
                read = t-DELAY
                for side in range(2):
                    motion = actual[side, read]-actual[side, read-1]
                    signal = response.activity_at(actual[side, read], motion)["signal"]
                    turns[side, t] = .65*signal
                    actual[side, t] = wrap(actual[side, t-1]-turns[side, t]+noise[side, t])
            error = max(float(np.max(np.abs(actual-expected["azimuth_deg"]))),
                        float(np.max(np.abs(turns-expected["turn_per_step_deg"]))))
            if error > 1e-10:
                raise AssertionError(f"Reference Eq6 parity failed: {error}")
            errors[f"direction_{direction}_moving_{moving}"] = error
    return errors


def streams():
    t = np.maximum(0., np.arange(N)*DT-1.)
    paths = {}
    for angle in (20., 60., 105.):
        paths[f"step_{angle:g}"] = np.full(N, angle)
    for speed in (25., 75.):
        paths[f"sweep_{speed:g}"] = 60.-np.abs((speed*t) % 240.-120.)
    rng = np.random.default_rng(SEED)
    for k in range(2):
        freq = rng.uniform(.4, 2.5, 3)
        phase = rng.uniform(-math.pi, math.pi, 3)
        paths[f"smooth_{k}"] = sum(a*np.sin(f*t+p) for a, f, p in
                                   zip((24., 14., 7.), freq, phase))
    paths["smooth_chirp"] = 40.*np.sin(.5*t+.12*t*t-.7)
    for freq in (.35, 3.):
        x = 2.2*np.sin(freq*t-.6)+.4*np.sin(1.9*freq*t+.1)
        paths[f"old_speed_{freq:g}"] = np.degrees(np.arctan2(x, 6.))
    x = 1.8*(1.-4.*np.abs((t/2.) % 1.-.5))
    paths["old_reversal"] = np.degrees(np.arctan2(x, 6.))
    return {name+suffix: values*sign for name, values in paths.items()
            for suffix, sign in (("", 1.), ("_mirror", -1.))}


def table(response, direction=True, condition="intact", author=False):
    result = np.empty((3, 361, 7))
    for m in (-1, 0, 1):
        for bearing in range(-180, 181):
            row = response.activity_at(bearing, m) if author else response.activity_at(
                bearing, m, direction_selective=direction, condition=condition)
            result[m+1, bearing+180] = [row["signal"], *row["aotu"], *row["dn"]]
    return result


def trial(path, lookup, *, cap=CAP, proportional=False, trace=None):
    queue = deque()
    heading = delivered = previous = 0.
    errors, visibility, saturation = [], [], []
    rows = []
    consecutive = 0
    settling = None
    for tick, world_angle in enumerate(path):
        # Previous delivered rate rotates the interval ending at this timestamp.
        applied = delivered if tick >= HOLD else 0.
        heading = wrap(heading+applied*DT)
        bearing = wrap(world_angle-heading)
        seen = abs(bearing) <= 120.
        sensed = bearing if seen else 0.
        motion = sensed-previous
        idx = int(math.copysign(math.floor(abs(sensed)+.5), sensed))+180
        activity = lookup[int(np.sign(motion))+1, idx] if lookup is not None else np.zeros(7)
        raw = 4.*sensed if proportional else .65*activity[0]/DT
        raw = raw if seen else 0.
        command = float(np.clip(raw, -cap, cap))
        queue.append((tick, command))
        origin, delivered = queue.popleft() if len(queue)>DELAY else (-1, 0.)
        previous = sensed
        if tick >= HOLD:
            errors.append(abs(bearing))
            visibility.append(seen)
            saturation.append(abs(raw)>cap)
            consecutive = consecutive+1 if abs(bearing)<=10. else 0
            if consecutive == 100 and settling is None:
                settling = (tick-99-HOLD)*DT
        if trace is not None:
            rows.append([tick*10, world_angle, heading, bearing, sensed, motion,
                         *activity, command, origin*10 if origin>=0 else -1,
                         delivered, applied, seen])
    if trace is not None:
        with trace.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sample_ms", "world_deg", "heading_deg", "bearing_deg",
                "sensed_deg", "motion_deg", "signal", "aotu0", "aotu1", "aotu2", "aotu3",
                "dn_left", "dn_right", "created_deg_s", "delivered_origin_ms",
                "delivered_deg_s", "applied_deg_s", "visible"])
            writer.writerows(rows)
    return {"mean_abs_error_deg": float(np.mean(errors)),
            "visible_fraction": float(np.mean(visibility)),
            "saturation_fraction": float(np.mean(saturation)), "settling_s": settling}


def run(csv_path, destination=ROOT/"docs/evidence/pursuit_retinal_v1.json"):
    csv_path = Path(csv_path)
    manifest = json.loads((ROOT/"docs/evidence/pursuit_reference_source_v1.json").read_text())
    source_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if source_hash != manifest["sha256"]["Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("External response table does not match the pinned source")
    fields = load_response_fields(csv_path)
    parity_errors = parity(fields)
    paths = streams()
    local = ROOT/"outputs/research/retinal-benchmark"
    local.mkdir(parents=True, exist_ok=True)
    # Freeze exact input bytes BEFORE any comparative model is evaluated.
    hashes = {}
    for name, values in paths.items():
        payload = np.asarray(values, dtype="<f8").tobytes()
        (local/(name+".f64")).write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    base = model()
    variants = {
        "author_ds": table(AuthorResponse(fields), author=True),
        "author_position": table(AuthorResponse(fields, False), author=True),
        "adapted_ds": table(base), "adapted_position": table(base, False),
        "bridge_removed": table(base, condition="bridge_removed"), "ordinary_p4": None}
    variants["author_ds_uncapped"] = variants["author_ds"]
    rng = np.random.default_rng(SEED+1)
    projection = ActivityProjection.from_packaged_data()
    for k in range(32):
        shuffled = model(shuffled_projection(projection, rng), base)
        variants[f"shuffle_ds_{k:02}"] = table(shuffled)
        variants[f"shuffle_position_{k:02}"] = table(shuffled, False)
    rows = []
    for name, path in paths.items():
        for variant, lookup in variants.items():
            trace = local/(name+"_"+variant+".csv") if (
                name in ("step_60", "sweep_75") and not variant.startswith("shuffle")) else None
            metric = trial(path, lookup, proportional=variant=="ordinary_p4",
                cap=float("inf") if variant.endswith("uncapped") else CAP, trace=trace)
            rows.append({"case": name, "variant": variant, **metric})
    summary = {}
    for family in ("step", "sweep_25", "sweep_75", "smooth", "old"):
        selected = [r for r in rows if r["case"].startswith(family)]
        means = {v: float(np.mean([r["mean_abs_error_deg"] for r in selected if r["variant"]==v]))
                 for v in variants}
        summary[family] = {"means_deg": means, "adapted_ds_beats_shuffles": sum(
            means["adapted_ds"]<means[f"shuffle_ds_{k:02}"] for k in range(32)),
            "adapted_position_beats_shuffles": sum(means["adapted_position"]<means[
                f"shuffle_position_{k:02}"] for k in range(32))}
    result = {"protocol": "pursuit_retinal_protocol.md", "seed": SEED,
        "source_table_sha256": source_hash, "input_sha256": hashes,
        "article_variant_eq6_max_abs_errors": parity_errors,
        "dt_ms": 10, "delay_ms": 200, "cap_deg_s": CAP,
        "production_body_extra_interval_ms": 10, "author_aotu_order": ["019R", "019L", "025R", "025L"],
        "adapted_aotu_order": list(base.projection.aotu_types),
        "adapted_aotu_sides": list(base.projection.aotu_sides),
        "summary": summary, "rows": rows}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    with destination.with_suffix(".csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({f: {k:v for k,v in s.items() if k!="means_deg"} |
        {"means_deg": {k:v for k,v in s["means_deg"].items() if not k.startswith("shuffle")}}
        for f,s in summary.items()}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response_csv", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT/"docs/evidence/pursuit_retinal_v1.json")
    args = parser.parse_args()
    run(args.response_csv, args.output)

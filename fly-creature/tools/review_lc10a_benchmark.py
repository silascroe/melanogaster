"""Audit the next assay's contracts without generating or fitting new responses."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from fly_creature.pursuit_physiology import (
    ARCHIVES, P1_ARCHIVES, SEED, extract, read_recording, visible_segments,
)
from fly_creature.pursuit_motion_diagnostic import model
from fly_creature.pursuit_step4 import shuffled_projection
from fly_creature.pursuit_reference import _nearest_lookup

ROOT = Path(__file__).resolve().parents[1]
DUPLICATE = "AOTU019/2023_06_15_fly03"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def array_hash(value):
    return hashlib.sha256(np.asarray(value, dtype="<f8").tobytes(order="C")).hexdigest()


def key(r):
    return (r["condition"], r["type"], r["recording"], int(r["trial"]),
            int(r["speed_deg_s"]), int(r["direction"]), int(r["center_bin"]))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def fold_audit(observations, previous_folds):
    pools = defaultdict(list)
    for r in observations:
        pools[r["condition"], r["type"]].append(r)
    previous = {key(r): r for r in previous_folds}
    assert len(previous) == len(previous_folds) == 34554
    folds, all_held, max_prediction_error = [], set(), 0.0
    for (condition, kind), rows in sorted(pools.items()):
        groups = defaultdict(lambda: defaultdict(list))
        for r in rows:
            groups[r["recording"]][key(r)[4:]].append(r)
        good = {rec: {s: rs for s, rs in cells.items() if len(rs) >= 4}
                for rec, cells in groups.items()}
        for held_rec, cells in sorted(good.items()):
            others = {rec: cs for rec, cs in good.items() if rec != held_rec}
            held = sorted((r for s, rs in cells.items()
                           if sum(s in cs for cs in others.values()) >= 3
                           for r in rs), key=key)
            train = sorted((r for rec, cs in others.items() for s, rs in cs.items()
                            if sum(s in other for name, other in others.items()
                                   if name != rec) >= 3 for r in rs), key=key)
            assert held and train
            assert not {key(r) for r in held} & {key(r) for r in train}
            assert all(r["recording"] != held_rec for r in train)
            n_cells = Counter((r["recording"], r["trial"]) for r in train)
            trials = defaultdict(set)
            for r in train:
                trials[r["recording"]].add(r["trial"])
            weights = np.array([1 / (n_cells[r["recording"], r["trial"]]
                                     * len(trials[r["recording"]]) * len(trials))
                                for r in train])
            assert abs(float(weights.sum()) - 1) < 1e-12
            y = np.array([float(r["response_spikes_s"]) for r in train])
            legacy_gains = {}
            for name in ("anatomy", "simple_spatial"):
                x = np.array([float(r[name + "_x"]) for r in train])
                xx = float(weights @ (x*x))
                assert xx > 1e-14  # Exact-zero and previous guard agree on legacy.
                gain = max(0., float(weights @ (x*y)) / xx)
                legacy_gains[name] = gain
                for r in held:
                    error = abs(float(r[name + "_x"]) * gain
                                - float(previous[key(r)][name]))
                    max_prediction_error = max(max_prediction_error, error)
            identities = [key(r) for r in held]
            all_held.update(identities)
            folds.append(dict(condition=condition, type=kind, recording=held_rec,
                              held_count=len(held), train_count=len(train),
                              train_recordings=len(trials),
                              held_signature_sha256=digest(identities),
                              train_signature_sha256=digest([key(r) for r in train]),
                              train_target_sha256=digest(y.tolist()),
                              train_weights_sha256=digest(weights.tolist()),
                              legacy_gains=legacy_gains))
    assert all_held == set(previous)
    assert len(folds) == 69 and max_prediction_error < 1e-10
    return folds, max_prediction_error


def raw_audit(directory, observations, population):
    reference = {key(r): r for r in observations}
    prior = {(r["condition"], r["recording"]): r for r in population["archives"]}
    reconstructed, records = {}, []
    target_error = 0.
    for condition, archives in (("NoP1", ARCHIVES), ("P1", P1_ARCHIVES)):
        for kind, (filename, expected) in archives.items():
            path = directory / filename
            with path.open("rb") as stream:
                assert hashlib.file_digest(stream, "md5").hexdigest() == expected
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind + "/" + Path(member).stem.removesuffix("_int")
                    if identity == DUPLICATE:
                        continue
                    payload = archive.read(member)  # Includes native ZIP CRC validation.
                    old = prior[condition, identity]
                    assert hashlib.sha256(payload).hexdigest() == old["member_sha256"]
                    time, dt, data = read_recording(payload)
                    elapsed = time - time[0]
                    grid_error = float(np.max(np.abs(elapsed - np.arange(len(time))*dt)))
                    assert grid_error <= 1e-9
                    pulses, rejected = extract(time, dt, data, identity, kind, "canonical")
                    segments = sum(len(visible_segments(data["int_panelps"][:, j]))
                                   for j in range(data["int_panelps"].shape[1]))
                    assert len(pulses) == old["accepted"] and rejected == old["rejected"]
                    assert segments == old["segments"] == len(pulses) + sum(rejected.values())
                    grouped = defaultdict(list)
                    quiet = [p for p in pulses if p["state"] == "quiescent"]
                    for p in quiet:
                        start = p["start_sample"]
                        stop = start + len(p["position"]) - 2*p["margin"]
                        indices = np.flatnonzero((time-time[start] >= -.250)
                                                 & (time-time[start] <= -.100))
                        rate = data["int_spikert"][:, p["trial"]]
                        value = float(rate[start:stop].mean()-rate[indices].mean())
                        k = (condition, kind, identity, p["trial"], p["speed_deg_s"],
                             p["direction"], int(round(p["center_deg"]/11.25)))
                        grouped[k].append(value)
                    assert len(quiet) == old["quiescent_pulses"]
                    assert len(grouped) == old["trial_cells"]
                    for k, values in grouped.items():
                        assert k not in reconstructed and k in reference
                        value = float(np.mean(values))
                        assert len(values) == int(reference[k]["pulses"])
                        target_error = max(target_error, abs(value-float(reference[k]["response_spikes_s"])))
                        reconstructed[k] = value
                    positions = data["int_panelps"]
                    finite = positions[np.isfinite(positions)]
                    assert np.max(np.abs(finite)) <= 180
                    used_trials = sorted({p["trial"] for p in quiet})
                    records.append(dict(condition=condition, type=kind, recording=identity,
                                        samples=len(time), all_trials=positions.shape[1],
                                        replay_trials=len(used_trials), dt_s=dt,
                                        elapsed_grid_max_error_s=grid_error,
                                        finite_samples=int(np.isfinite(positions[:, used_trials]).sum()),
                                        maximum_abs_position_deg=float(np.max(np.abs(finite))),
                                        quiescent_pulses=len(quiet), trial_cells=len(grouped)))
                    print(f"Reviewed native input/target: {condition} {identity}", flush=True)
    assert set(reconstructed) == set(reference) and len(reference) == 35484
    assert target_error < 1e-12 and len(records) == 69
    return records, target_error


def wiring_audit():
    base = model()
    p = base.projection
    rng, direct_rng = np.random.default_rng(SEED), np.random.default_rng(SEED)
    permutations = []
    for k in range(32):
        order = np.arange(len(p.body_ids))
        for side in ("L", "R"):
            rows = np.flatnonzero(p.sides == side)
            order[rows] = direct_rng.permutation(rows)
        shuffled = shuffled_projection(p, rng).lc_to_aotu
        assert np.array_equal(shuffled, p.lc_to_aotu[order])
        assert np.array_equal(shuffled.sum(axis=0), p.lc_to_aotu.sum(axis=0))
        permutations.append(dict(index=k, source_row_indices=order.tolist(),
                                 weight_sha256=array_hash(shuffled)))
    spatial, flat = np.zeros_like(p.lc_to_aotu), np.zeros_like(p.lc_to_aotu)
    for j, (kind, side) in enumerate(zip(p.aotu_types, p.aotu_sides)):
        rows = np.flatnonzero(p.sides == side)
        q = np.exp(-.5*((p.centers_deg[rows]-(35 if kind == "AOTU019" else 65))/20)**2)
        total = p.lc_to_aotu[:, j].sum()
        spatial[rows, j] = q/q.sum()*total
        flat[rows, j] = total/len(rows)
    assert np.max(np.abs(spatial.sum(axis=0)-p.lc_to_aotu.sum(axis=0))) < 1e-10
    assert np.max(np.abs(flat.sum(axis=0)-p.lc_to_aotu.sum(axis=0))) < 1e-10
    return dict(body_ids=p.body_ids.tolist(), sides=p.sides.tolist(),
                aotu_columns=[dict(body_id=i, type=k, side=s) for i, k, s in
                              zip(p.aotu_ids, p.aotu_types, p.aotu_sides)],
                contact_totals=p.lc_to_aotu.sum(axis=0).tolist(), peaks=base.peaks,
                intact_weight_sha256=array_hash(p.lc_to_aotu),
                spatial_weight_sha256=array_hash(spatial), flat_weight_sha256=array_hash(flat),
                numpy_version=np.__version__, shuffle_seed=SEED, shuffles=permutations)


def probe_lookup_audit():
    """Range/order diagnostic on existing synthetic traces, never physiology."""
    archive = ROOT/"outputs/research/lc10a-response-v1/activity_traces.npz"
    trace = np.load(archive)
    base = model()
    p = base.projection
    rows, order_error = [], 0.
    for name in sorted(n for n in trace.files if n.startswith("bar_") and n.endswith("_R")):
        right = trace[name] @ p.lc_to_aotu
        left = trace[name[:-1]+"L"] @ p.lc_to_aotu
        for kind in ("AOTU019", "AOTU025"):
            ir = next(i for i, pair in enumerate(zip(p.aotu_types, p.aotu_sides))
                      if pair == (kind, "R"))
            il = next(i for i, pair in enumerate(zip(p.aotu_types, p.aotu_sides))
                      if pair == (kind, "L"))
            rr, ll = right[:, ir], left[:, il]
            grid, values = base.lookups[kind]
            vr, vl = _nearest_lookup(grid, values, rr), _nearest_lookup(grid, values, ll)
            correct, wrong = (vr+vl)/2, _nearest_lookup(grid, values, (rr+ll)/2)
            order_error = max(order_error, float(np.max(np.abs(correct-wrong))))
            rows.append(dict(probe=name, type=kind,
                             raw_to_peak_max=float(max(rr.max(), ll.max())/base.peaks[kind]),
                             right_distinct_lookup_bins=len(np.unique(vr)),
                             left_distinct_lookup_bins=len(np.unique(vl)),
                             right_positive_raw_zero_output_samples=int(np.sum((rr>0)&(vr==0))),
                             left_positive_raw_zero_output_samples=int(np.sum((ll>0)&(vl==0)))))
    assert len(rows) == 16 and order_error > 0
    return dict(scope="synthetic pre-existing bar probes only; no recording fit",
                trace_archive_sha256=sha(archive),
                wrong_average_before_lookup_max_error=order_error, bars=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT/"outputs/research/aotu-recordings")
    parser.add_argument("--population-dir", type=Path, default=ROOT/"outputs/research/aotu-population-v1")
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/research/lc10a-benchmark-review-v1/report.json")
    args = parser.parse_args()
    checks_path = ROOT/"docs/evidence/pursuit_population_checks_v1.json"
    population_path = ROOT/"docs/evidence/pursuit_population_v1.json"
    checks = json.loads(checks_path.read_text())
    population = json.loads(population_path.read_text())
    for name, expected in checks["artifact_sha256"].items():
        assert sha(args.population_dir/name) == expected, name
    for name, expected in population["frozen_component_sha256"].items():
        assert sha(ROOT/name) == expected, name
    observations = read_csv(args.population_dir/"observations.csv")
    previous_folds = read_csv(args.population_dir/"folds.csv")
    assert len({key(r) for r in observations}) == len(observations) == 35484
    folds, prediction_error = fold_audit(observations, previous_folds)
    records, target_error = raw_audit(args.data_dir, observations, population)
    wiring = wiring_audit()
    protected = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p)
                 for p in sorted((ROOT/"src/fly_creature").glob("*.py"))}
    protected.update({str(p.relative_to(ROOT)).replace("\\", "/"): sha(p)
                      for p in sorted((ROOT/"src/fly_creature/data").glob("*.json"))})
    report = dict(status="pass", scope="protocol/input/target/legacy/calibration/wiring review; no new sensory scoring",
                  counts=dict(recordings=len(records), quiescent_pulses=sum(r["quiescent_pulses"] for r in records),
                              observations=len(observations), scored_trial_cells=len(previous_folds),
                              native_replay_frames=sum(r["samples"]*r["replay_trials"] for r in records)),
                  raw_target_max_error=target_error, legacy_prediction_max_error=prediction_error,
                  records=records, folds=folds, wiring=wiring,
                  probe_lookup=probe_lookup_audit(), protected_component_sha256=protected,
                  cache_sha256=checks["artifact_sha256"],
                  basis_sha256={"docs/evidence/pursuit_population_v1.json": sha(population_path),
                                "docs/evidence/pursuit_population_checks_v1.json": sha(checks_path),
                                "docs/lc10a_response_design.md": sha(ROOT/"docs/lc10a_response_design.md"),
                                "docs/evidence/lc10a_response_design_v1.json": sha(ROOT/"docs/evidence/lc10a_response_design_v1.json")},
                  implementation_sha256=sha(Path(__file__)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("status", "counts", "raw_target_max_error", "legacy_prediction_max_error")}, indent=2))


if __name__ == "__main__":
    main()

"""Offline repeated-stimulus audit; no production controller imports this module."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np

from .pursuit_physiology import ARCHIVES, P1_ARCHIVES, ROOT, extract, read_recording, sha, visible_segments

DUPLICATE = "AOTU019/2023_06_15_fly03"
FEATURES = ("forward_on_mm_s", "abs_angular_on_deg_s",
            "forward_pre_mm_s", "abs_angular_pre_deg_s")
RIDGE = .1


def csv_write(path, rows):
    import csv
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def collect(directory):
    import h5py
    observations, audit, motion = [], [], defaultdict(list)
    for condition, archives in (("NoP1", ARCHIVES), ("P1", P1_ARCHIVES)):
        for kind, (filename, expected) in archives.items():
            path = directory / filename
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "md5").hexdigest()
            if digest != expected:
                raise ValueError(f"Checksum mismatch: {filename}")
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind + "/" + Path(member).stem.removesuffix("_int")
                    if identity == DUPLICATE:
                        audit.append(dict(condition=condition, recording=identity, excluded="known duplicate"))
                        continue
                    payload = archive.read(member)
                    time, dt, data = read_recording(payload)
                    with h5py.File(io.BytesIO(payload), "r") as stream:
                        angular = np.asarray(stream["int_angular"], dtype=float).T
                    if angular.shape != data["int_forward"].shape or not np.isfinite(angular).all():
                        raise ValueError("Invalid angular signal")
                    pulses, rejected = extract(time, dt, data, identity, kind, "canonical")
                    segments = sum(len(visible_segments(data["int_panelps"][:, j]))
                                   for j in range(data["int_panelps"].shape[1]))
                    assert len(pulses) + sum(rejected.values()) == segments
                    grouped = defaultdict(list)
                    quiet = [p for p in pulses if p["state"] == "quiescent"]
                    for p in quiet:
                        start, margin, trial = p["start_sample"], p["margin"], p["trial"]
                        stop = start + len(p["position"]) - 2 * margin
                        pre = (p["time"] >= -.250) & (p["time"] <= -.100)
                        f = data["int_forward"][start-margin:stop+margin, trial]
                        a = angular[start-margin:stop+margin, trial]
                        on = slice(margin, len(f)-margin)
                        x = [float(f[on].mean()), float(np.abs(a[on]).mean()),
                             float(f[pre].mean()), float(np.abs(a[pre]).mean())]
                        center = int(round(p["center_deg"] / 11.25))
                        key = (p["speed_deg_s"], p["direction"], center, trial)
                        fraction = float(np.mean(np.abs(f[on]) > .5))
                        grouped[key].append((p["evoked_spikes_s"], x, p["center_deg"], fraction))
                        motion[condition, kind].append((x[0], x[1], fraction))
                    for (speed, direction, center, trial), values in sorted(grouped.items()):
                        ys = np.array([v[0] for v in values])
                        xs = np.array([v[1] for v in values])
                        row = dict(condition=condition, type=kind, recording=identity,
                                   trial=trial, speed_deg_s=speed, direction=direction,
                                   center_bin=center, center_deg=center*11.25,
                                   actual_center_deg=float(np.mean([v[2] for v in values])),
                                   pulses=len(values), response_spikes_s=float(ys.mean()))
                        row.update(zip(FEATURES, xs.mean(axis=0).tolist()))
                        observations.append(row)
                    audit.append(dict(condition=condition, recording=identity, member=member,
                                      archive_md5=digest, member_sha256=hashlib.sha256(payload).hexdigest(),
                                      trials=data["int_forward"].shape[1], dt_s=dt,
                                      segments=segments, accepted=len(pulses), rejected=rejected,
                                      quiescent_pulses=len(quiet), trial_cells=len(grouped)))
                    print(f"{condition} {identity}: {len(quiet)} quiet pulses / {len(grouped)} trial cells", flush=True)
    return observations, audit, motion


def cell(row):
    return row["speed_deg_s"], row["direction"], row["center_bin"]


def record_loss(rows, field):
    """Equal cells within trial and equal trials within recording."""
    trials = defaultdict(list)
    for row in rows:
        trials[row["trial"]].append((row[field] - row["response_spikes_s"]) ** 2)
    return float(np.sqrt(np.mean([np.mean(v) for v in trials.values()])))


def evaluate(observations):
    pools = defaultdict(list)
    for row in observations:
        pools[row["condition"], row["type"]].append(row)
    folds, records = [], []
    checks = dict(held_trial_leakage=0, held_recording_leakage=0, folds=0,
                  ridge_normal_equation_max_error=0., center_bin_max_offset_deg=0.)
    for (condition, kind), raw in sorted(pools.items()):
        by_record = defaultdict(list)
        for row in raw:
            by_record[row["recording"]].append(row)
            checks["center_bin_max_offset_deg"] = max(checks["center_bin_max_offset_deg"],
                abs(row["actual_center_deg"]-row["center_deg"]))
        eligible, means, within_sd = {}, {}, {}
        for identity, rows in sorted(by_record.items()):
            by_cell = defaultdict(list)
            for row in rows:
                by_cell[cell(row)].append(row)
            good = {key: values for key, values in by_cell.items() if len(values) >= 4}
            eligible[identity] = [row for values in good.values() for row in values]
            means[identity] = {key: float(np.mean([v["response_spikes_s"] for v in values]))
                               for key, values in good.items()}
            within_sd[identity] = float(np.mean([np.std([v["response_spikes_s"] for v in values], ddof=1)
                                                for values in good.values()])) if good else None
        for identity, rows in sorted(eligible.items()):
            if not rows:
                continue
            common = {}
            for key in means[identity]:
                other = [m[key] for rec, m in means.items() if rec != identity and key in m]
                if len(other) >= 3:
                    common[key] = (float(np.mean(other)), len(other), float(np.std(other, ddof=1)))
            record_folds = []
            for trial in sorted(set(r["trial"] for r in rows)):
                train = [r for r in rows if r["trial"] != trial]
                held = [r for r in rows if r["trial"] == trial and cell(r) in common]
                if not held:
                    continue
                assert all(r["trial"] != trial and r["recording"] == identity for r in train)
                groups = defaultdict(list)
                for row in train:
                    groups[cell(row)].append(row)
                assert all(len(groups[cell(r)]) >= 3 for r in held)
                y_means, x_means = {}, {}
                for key, values in groups.items():
                    y_means[key] = np.mean([v["response_spikes_s"] for v in values])
                    x_means[key] = np.mean([[v[f] for f in FEATURES] for v in values], axis=0)
                x = np.array([[r[f] for f in FEATURES] for r in train])
                x -= np.stack([x_means[cell(r)] for r in train])
                y = np.array([r["response_spikes_s"] - y_means[cell(r)] for r in train])
                counts = Counter(r["trial"] for r in train)
                w = np.array([1 / counts[r["trial"]] for r in train], dtype=float)
                w /= w.sum()
                scale = np.sqrt(w @ (x*x))
                scale = np.where(scale > 1e-12, scale, 1.)
                z = x / scale
                lhs = (z.T*w) @ z + RIDGE*np.eye(len(FEATURES))
                rhs = (z.T*w) @ y
                beta = np.linalg.solve(lhs, rhs)
                error = float(np.max(np.abs(lhs @ beta - rhs)))
                checks["ridge_normal_equation_max_error"] = max(checks["ridge_normal_equation_max_error"], error)
                blind = float(np.sum(w*np.array([r["response_spikes_s"] for r in train])))
                for row in held:
                    key = cell(row)
                    adjustment = float(((np.array([row[f] for f in FEATURES])-x_means[key])/scale) @ beta)
                    result = dict(row, same_recording=float(y_means[key]), stimulus_blind=blind,
                                  other_recordings=common[key][0], other_recording_count=common[key][1],
                                  motor_augmented=float(y_means[key]+adjustment),
                                  training_trials=len(counts), same_cell_training_trials=len(groups[key]))
                    record_folds.append(result)
                checks["folds"] += 1
            if not record_folds:
                continue
            folds.extend(record_folds)
            losses = {f+"_rmse": record_loss(record_folds, f) for f in
                      ("same_recording", "stimulus_blind", "other_recordings", "motor_augmented")}
            records.append(dict(condition=condition, type=kind, recording=identity,
                                raw_trial_cells=len(by_record[identity]), eligible_trial_cells=len(rows),
                                scored_trial_cells=len(record_folds),
                                scored_trials=len(set(r["trial"] for r in record_folds)),
                                scored_cells=len(common), within_cell_trial_sd=within_sd[identity],
                                across_recording_cell_sd=float(np.mean([v[2] for v in common.values()])),
                                **losses))
    return folds, records, checks


def report(records, observations, audit, motion, checks):
    summary = []
    for condition in ("NoP1", "P1"):
        for kind in ARCHIVES:
            selected = [r for r in records if (r["condition"], r["type"]) == (condition, kind)]
            raw = [r for r in observations if (r["condition"], r["type"]) == (condition, kind)]
            values = np.asarray(motion[condition, kind])
            entry = dict(condition=condition, type=kind, recordings=len(selected),
                         raw_trial_cells=len(raw), scored_trial_cells=sum(r["scored_trial_cells"] for r in selected),
                         quiescent_pulses=len(values))
            for f in ("same_recording", "stimulus_blind", "other_recordings", "motor_augmented"):
                entry[f+"_rmse"] = float(np.mean([r[f+"_rmse"] for r in selected]))
            for reference, candidate, label in (("stimulus_blind", "same_recording", "stimulus"),
                                                ("other_recordings", "same_recording", "personalization"),
                                                ("same_recording", "motor_augmented", "motor")):
                entry[label+"_reduction_percent"] = 100*(1-entry[candidate+"_rmse"]/entry[reference+"_rmse"])
                entry[label+"_recordings_improved"] = sum(r[candidate+"_rmse"] < r[reference+"_rmse"] for r in selected)
            for f in ("within_cell_trial_sd", "across_recording_cell_sd"):
                entry[f] = float(np.mean([r[f] for r in selected]))
            entry["quiet_pulses_with_forward_above_0p5"] = int(np.sum(values[:, 2] > 0))
            entry["quiet_motion_quantiles"] = {name: np.quantile(values[:, i], [.1,.5,.9,.99]).tolist()
                for i, name in enumerate(("mean_forward_mm_s", "mean_abs_angular_deg_s", "fraction_forward_above_0p5"))}
            summary.append(entry)
    return dict(protocol_sha256=sha(ROOT/"docs/pursuit_repeatability_protocol.md"),
                implementation_sha256=sha(Path(__file__)), ridge=RIDGE, features=FEATURES,
                units_source="CollieWilson 65d72773121ffe148b56b8ba4f594a7a51c51789 processSettings.m:119",
                excluded_identity=DUPLICATE, primary_state="quiescent", target="evoked pulse mean spikes/s",
                weighting="equal cells within trial, equal trials within recording, equal recordings",
                caveat="Same-recording prediction is not held-animal accuracy or a noise ceiling; motor association is not causal.",
                summary=summary, checks=checks, archives=audit)


def plot(path, summary, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    labels = ("Other recordings", "Same recording", "+ descriptive motion")
    fields = ("other_recordings_rmse", "same_recording_rmse", "motor_augmented_rmse")
    for ax, s in zip(axes.flat, summary):
        selected = [r for r in records if (r["condition"],r["type"]) == (s["condition"],s["type"])]
        for r in selected:
            ax.plot(range(3), [r[f] for f in fields], color="gray", alpha=.3, linewidth=.7)
        ax.plot(range(3), [s[f] for f in fields], color="#145a80", marker="o", linewidth=2)
        ax.set_xticks(range(3), labels, fontsize=8)
        ax.set_ylabel("Held-trial pulse-mean RMSE (spikes/s)")
        ax.set_title(f"{s['condition']} / {s['type']} ({s['recordings']} recordings)")
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Matching stimuli: recording differences and descriptive motor association\nNot a causal motor test or a biological noise ceiling", fontsize=12)
    fig.savefig(path, dpi=150, metadata={"Software":"Fly Creature repeatability audit"})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT/"outputs/research/aotu-recordings")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    observations, audit, motion = collect(args.data_dir)
    folds, records, checks = evaluate(observations)
    result = report(records, observations, audit, motion, checks)
    for name, rows in (("observations",observations),("folds",folds),("recordings",records)):
        csv_write(args.output_dir/(name+".csv"), rows)
    (args.output_dir/"report.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8", newline="\n")
    plot(args.output_dir/"repeatability.png", result["summary"], records)
    print(json.dumps(result["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()

"""Offline measured AOTU pulse comparison; never imported by the playable app."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SEED = 20261006
ARCHIVES = {
    "AOTU019": ("AOTU019 Motion Pulse NoP1.zip", "6ebc8edd2bb348fa14b9dbd8f2cbea01"),
    "AOTU025": ("AOTU025 Motion Pulse NoP1.zip", "ebeace816547366b8325182f80a08a5b"),
}
P1_ARCHIVES = {
    "AOTU019": ("AOTU019 Motion Pulse.zip", "848680fbccbb80353d05f828cc6feef1"),
    "AOTU025": ("AOTU025 Motion Pulse.zip", "eae5a827f7e75b373c95b1ce9ee76c9b"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_recording(payload):
    import h5py
    with h5py.File(io.BytesIO(payload), "r") as f:
        data = {k: np.asarray(f[k], dtype=float).T for k in
                ("int_time", "int_panelps", "int_spikert", "int_forward")}
    time = data.pop("int_time").ravel()
    dt = float(np.median(np.diff(time)))
    if not np.isfinite(time).all() or dt <= 0 or not np.allclose(np.diff(time), dt, atol=1e-9):
        raise ValueError("Recording must have a uniform finite time axis")
    if any(v.ndim != 2 or v.shape[0] != len(time) for v in data.values()):
        raise ValueError("MATLAB dimensions do not match time")
    if len({v.shape for v in data.values()}) != 1:
        raise ValueError("Signal shapes disagree")
    for k, value in data.items():
        if np.isinf(value).any() or (k != "int_panelps" and not np.isfinite(value).all()):
            raise ValueError(f"Invalid recording values: {k}")
    return time, dt, data


def visible_segments(position):
    edges = np.diff(np.r_[False, np.isfinite(position), False].astype(int))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def extract(time, dt, data, identity, kind, side):
    """Independent finite-interval extraction, with explicit rejection accounting."""
    pulses, rejected = [], Counter()
    margin = int(round(.250 / dt))
    for trial in range(data["int_panelps"].shape[1]):
        position = data["int_panelps"][:, trial]
        for start, stop in visible_segments(position):
            if start == 0 or stop == len(time):
                rejected["boundary_segment"] += 1
                continue
            duration = (stop - start) * dt
            speed = min((25, 75), key=lambda s: abs(duration - 22.5 / s))
            if abs(duration - 22.5 / speed) > .20 * (22.5 / speed):
                rejected["duration"] += 1
                continue
            p = position[start:stop]
            if abs(abs(p[-1] - p[0]) - 22.5) > 3:
                rejected["span"] += 1
                continue
            t = time[start:stop] - time[start]
            slope, intercept = np.polyfit(t, p, 1)
            residual = float(np.sum((p - (intercept + slope * t)) ** 2))
            variance = float(np.sum((p - p.mean()) ** 2))
            r2 = 1 - residual / variance if variance else 0
            if abs(abs(slope) - speed) > .1 * speed or r2 < .98:
                rejected["slope_or_r2"] += 1
                continue
            lo, hi = start - margin, stop + margin
            if lo < 0 or hi > len(time):
                rejected["observation_boundary"] += 1
                continue
            if np.isfinite(position[lo:start]).any() or np.isfinite(position[stop:hi]).any():
                rejected["neighboring_stimulus"] += 1
                continue
            rate = data["int_spikert"][lo:hi, trial]
            forward = data["int_forward"][start:stop, trial]
            state = ("quiescent" if np.mean(np.abs(forward) <= .5) >= .5 else
                     "running" if np.mean(forward > 2) >= .75 else "mixed")
            rel_time = time[lo:hi] - time[start]
            baseline = float(rate[(rel_time >= -.250) & (rel_time <= -.100)].mean())
            pulses.append({"fly": identity, "type": kind, "side": side,
                "trial": trial, "start_sample": int(start), "state": state,
                "speed_deg_s": speed, "direction": 1 if slope > 0 else -1,
                "center_deg": float((p[0] + p[-1]) / 2), "span_deg": float(p[-1] - p[0]),
                "duration_s": duration, "slope_deg_s": float(slope), "position_r2": r2,
                "baseline_spikes_s": baseline, "mean_spikes_s": float(rate[margin:margin+len(p)].mean()),
                "evoked_spikes_s": float(rate[margin:margin+len(p)].mean() - baseline),
                "margin": margin, "dt": dt, "position": position[lo:hi].copy(),
                "rate": rate.copy(), "time": rel_time})
    return pulses, dict(rejected)


def load_archives(directory, condition="NoP1"):
    from scipy.io import loadmat
    pulses, audit = [], []
    archives = {"NoP1": ARCHIVES, "P1": P1_ARCHIVES}[condition]
    for kind, (name, expected) in archives.items():
        path = directory / name
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"Archive checksum mismatch: {name}")
        with zipfile.ZipFile(path) as archive:
            members = sorted(n for n in archive.namelist() if n.endswith("_int.mat"))
            metadata = [n for n in archive.namelist() if n.endswith("/trackLR.mat")]
            if len(metadata) != 1:
                raise ValueError("Expected one side metadata file")
            sides = str(loadmat(io.BytesIO(archive.read(metadata[0])), simplify_cells=True)["trackLR"])
            if len(sides) != len(members) or set(sides) - set("LR"):
                raise ValueError("Side metadata does not match sorted recordings")
            for member, side in zip(members, sides):
                payload = archive.read(member)  # zipfile verifies the member CRC.
                identity = kind + "/" + Path(member).stem.removesuffix("_int")
                time, dt, data = read_recording(payload)
                extracted, rejected = extract(time, dt, data, identity, kind, side)
                pulses.extend(extracted)
                audit.append({"fly": identity, "side": side, "member": member,
                    "archive_md5": digest, "member_sha256": hashlib.sha256(payload).hexdigest(),
                    "shape": list(data["int_panelps"].shape), "dt_s": dt,
                    "finite_segments": sum(len(visible_segments(data["int_panelps"][:, j]))
                        for j in range(data["int_panelps"].shape[1])),
                    "accepted_pulses": len(extracted), "rejected": rejected})
                print(f"{identity}: {len(extracted)} pulses, rejected {rejected}", flush=True)
    if not pulses:
        raise ValueError("No valid pulses extracted")
    return pulses, audit


def model_tables():
    from .pursuit_motion_diagnostic import model
    from .pursuit_footprints import footprint_adapter, load_footprints
    from .pursuit_step4 import shuffled_projection
    base = model()
    footprint, _, _ = footprint_adapter(base, load_footprints())
    adapters = {"baseline": base, "footprint": footprint}
    rng = np.random.default_rng(SEED)
    for k in range(32):
        shuffled = model(shuffled_projection(base.projection, rng), base)
        adapters[f"baseline_shuffle_{k:02}"] = shuffled
        adapters[f"footprint_shuffle_{k:02}"] = footprint_adapter(shuffled, load_footprints())[0]
    names = list(adapters) + ["simple_spatial", "intercept_only"]
    tables = {}
    for kind in ARCHIVES:
        for side in "LR":
            i = [i for i, pair in enumerate(zip(base.projection.aotu_types,
                base.projection.aotu_sides)) if pair == (kind, side)]
            if len(i) != 1:
                raise ValueError("Expected one selected AOTU per type/side")
            data = []
            for name in names:
                if name == "intercept_only":
                    data.append(np.zeros((2, 361)))
                elif name == "simple_spatial":
                    angles = np.arange(-180, 181) * (1 if side == "R" else -1)
                    peak = 35 if kind == "AOTU019" else 65
                    response = np.exp(-.5 * ((angles - peak) / 20) ** 2)
                    data.append(np.tile(response, (2, 1)))
                else:
                    a = adapters[name]
                    data.append([[a.activity_at(float(angle), motion)["aotu"][i[0]]
                        for angle in range(-180, 181)] for motion in (-1, 1)])
            tables[kind, side] = np.asarray(data)
            if not np.isfinite(tables[kind, side]).all():
                raise ValueError("Nonfinite model lookup")
    return names, tables


def summarize_predictions(pulses, names, tables):
    from scipy.signal import fftconvolve
    for pulse in pulses:
        position = pulse["position"]
        visible = np.isfinite(position)
        sign = 1 if pulse["side"] == "R" else -1
        angle = np.where(visible, position * sign, 0)
        if np.any(np.abs(angle) > 180):
            raise ValueError("Recorded angle outside model field")
        bins = (np.sign(angle) * np.floor(np.abs(angle) + .5)).astype(int) + 180
        direction = 0 if pulse["direction"] * sign < 0 else 1
        response = tables[pulse["type"], pulse["side"]][:, direction, bins] * visible
        dt = pulse["dt"]
        radius = int(round(.250 / dt))
        kernel = np.exp(-.5 * (np.arange(-radius, radius+1) * dt / .05) ** 2)
        kernel /= kernel.sum()
        prediction = fftconvolve(response, kernel[None, :], mode="same", axes=1)
        margin = pulse["margin"]
        on = slice(margin, len(position) - margin)
        baseline_mask = (pulse["time"] >= -.250) & (pulse["time"] <= -.100)
        pulse["x"] = prediction[:, on].mean(axis=1)
        pulse["x_baseline"] = prediction[:, baseline_mask].mean(axis=1)
        # Sufficient statistics give held-out time RMSE without storing 67 full traces.
        pulse["time_moments"] = np.array([prediction.mean(axis=1), (prediction**2).mean(axis=1),
            (prediction * pulse["rate"]).mean(axis=1)])
        pulse["rate_mean"] = float(pulse["rate"].mean())
        pulse["rate_square_mean"] = float((pulse["rate"]**2).mean())
        pulse["plot_predictions"] = prediction[[names.index(n) for n in
            ("baseline", "footprint", "simple_spatial")], ::7].copy()
        if pulse is pulses[0]:
            direct = np.convolve(response[0], kernel, mode="same")
            if not np.allclose(prediction[0], direct, rtol=0, atol=1e-12):
                raise AssertionError("FFT observation filter disagrees with direct convolution")
            pulse["filter_max_abs_error"] = float(np.max(np.abs(prediction[0]-direct)))


def affine(x, y, weights):
    """Equal recording weights; nonnegative gain; intercept fitted jointly."""
    weights = weights / weights.sum()
    mean_x = weights @ x
    mean_y = float(weights @ y)
    centered = x - mean_x
    variance = weights @ (centered**2)
    covariance = (weights * (y - mean_y)) @ centered
    gain = np.maximum(0, np.divide(covariance, variance, out=np.zeros_like(variance), where=variance>1e-14))
    return gain, mean_y - gain * mean_x


def evaluate(pulses, names):
    folds, coefficients = [], {}
    for kind in ARCHIVES:
        for state in ("quiescent", "running", "mixed"):
            selected = [p for p in pulses if p["type"] == kind and p["state"] == state]
            flies = sorted(set(p["fly"] for p in selected))
            if len(flies) < 4:
                continue
            for fly in flies:
                train = [p for p in selected if p["fly"] != fly]
                held = [p for p in selected if p["fly"] == fly]
                counts = Counter(p["fly"] for p in train)
                weights = np.array([1 / counts[p["fly"]] for p in train])
                gain, intercept = affine(np.stack([p["x"] for p in train]),
                    np.array([p["mean_spikes_s"] for p in train]), weights)
                coefficients[kind, state, fly] = gain, intercept
                pred = np.stack([p["x"] for p in held]) * gain + intercept
                y = np.array([p["mean_spikes_s"] for p in held])[:, None]
                evoked_pred = np.stack([p["x"] - p["x_baseline"] for p in held]) * gain
                evoked_y = np.array([p["evoked_spikes_s"] for p in held])[:, None]
                time_mse = []
                for p in held:
                    mx, mx2, mxy = p["time_moments"]
                    value = gain**2 * mx2 + intercept**2 + p["rate_square_mean"] + 2*gain*intercept*mx
                    value -= 2*gain*mxy + 2*intercept*p["rate_mean"]
                    time_mse.append(np.maximum(value, 0))
                for i, name in enumerate(names):
                    folds.append({"type": kind, "state": state, "fly": fly, "variant": name,
                        "held_pulses": len(held), "train_flies": len(counts),
                        "gain": float(gain[i]), "intercept_spikes_s": float(intercept[i]),
                        "pulse_rmse_spikes_s": float(np.sqrt(np.mean((pred[:, i]-y[:, 0])**2))),
                        "evoked_rmse_spikes_s": float(np.sqrt(np.mean((evoked_pred[:, i]-evoked_y[:, 0])**2))),
                        "time_rmse_spikes_s": float(np.sqrt(np.mean(np.asarray(time_mse)[:, i])))})
    if not folds:
        raise ValueError("Insufficient animal coverage for declared cross-validation")
    summary = {}
    for kind in ARCHIVES:
        for state in ("quiescent", "running", "mixed"):
            group = [r for r in folds if r["type"] == kind and r["state"] == state]
            if not group:
                summary[kind + "/" + state] = {"available": False}
                continue
            scores = {}
            for name in names:
                rows = [r for r in group if r["variant"] == name]
                scores[name] = {metric: {"mean": float(np.mean([r[metric] for r in rows])),
                    "sem": float(np.std([r[metric] for r in rows], ddof=1) / np.sqrt(len(rows)))}
                    for metric in ("pulse_rmse_spikes_s", "evoked_rmse_spikes_s", "time_rmse_spikes_s")}
            ranks = {candidate: sum(scores[candidate]["pulse_rmse_spikes_s"]["mean"] <
                scores[f"{candidate}_shuffle_{k:02}"]["pulse_rmse_spikes_s"]["mean"] for k in range(32))
                for candidate in ("baseline", "footprint")}
            summary[kind + "/" + state] = {"available": True,
                "flies": len(set(r["fly"] for r in group)),
                "pulses": sum(r["held_pulses"] for r in group if r["variant"] == "baseline"),
                "scores": scores, "pulse_error_beats_shuffles": ranks}
    return folds, coefficients, summary


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def binned_curves(pulses, names, coefficients):
    groups = defaultdict(list)
    for p in pulses:
        groups[p["type"], p["state"], p["fly"], p["speed_deg_s"], p["direction"],
               float(round(p["center_deg"] / 11.25) * 11.25)].append(p)
    rows = []
    for (kind, state, fly, speed, direction, center), group in sorted(groups.items()):
        row = {"type": kind, "state": state, "fly": fly, "speed": speed,
            "direction": direction, "center_deg": center, "pulses": len(group),
            "measured_raw_spikes_s": float(np.mean([p["mean_spikes_s"] for p in group])),
            "measured_evoked_spikes_s": float(np.mean([p["evoked_spikes_s"] for p in group]))}
        if (kind, state, fly) not in coefficients:
            continue
        gain, intercept = coefficients[kind, state, fly]
        for name in ("baseline", "footprint", "simple_spatial"):
            i = names.index(name)
            row[name + "_activity"] = float(np.mean([p["x"][i] for p in group]))
            row[name + "_spikes_s"] = float(np.mean([p["x"][i] for p in group]) * gain[i] + intercept[i])
            row[name + "_evoked_spikes_s"] = float(np.mean([p["x"][i] - p["x_baseline"][i] for p in group]) * gain[i])
        rows.append(row)
    return rows


def make_plot(path, curves, summary, condition="NoP1"):
    os.environ.setdefault("MPLCONFIGDIR", str(path.parent / "mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    colors = {"measured_raw_spikes_s": "black", "baseline_spikes_s": "#0072B2",
        "footprint_spikes_s": "#D55E00", "simple_spatial_spikes_s": "#009E73"}
    for row, kind in enumerate(ARCHIVES):
        for col, state in enumerate(("quiescent", "running")):
            ax = axes[row, col]
            for key, color in colors.items():
                # First each fly averages directions/speeds, then animals receive equal weight.
                grouped = defaultdict(list)
                for r in curves:
                    if r["type"] == kind and r["state"] == state:
                        grouped[r["center_deg"], r["fly"]].append(r[key])
                centers = sorted(set(center for center, fly in grouped))
                values = [[float(np.mean(grouped[c, fly])) for center, fly in grouped if center == c] for c in centers]
                if centers:
                    ax.plot(centers, [np.mean(v) for v in values], color=color, label=key.removesuffix("_spikes_s"))
                    if key == "measured_raw_spikes_s":
                        sem = [np.std(v, ddof=1)/np.sqrt(len(v)) if len(v)>1 else 0 for v in values]
                        ax.errorbar(centers, [np.mean(v) for v in values], yerr=sem, fmt="none", color=color, alpha=.4)
            ax.set(title=f"{kind} / {state}", xlabel="Position (ipsilateral-positive degrees)", ylabel="Raw firing rate (spikes/s)")
            if row == 0 and col == 0:
                ax.legend(fontsize=8)
        ax = axes[row, 2]
        available = [(state, summary[kind + "/" + state]) for state in ("quiescent", "running") if summary[kind + "/" + state]["available"]]
        for offset, name in enumerate(("baseline", "footprint", "simple_spatial")):
            ax.bar(np.arange(len(available)) + offset*.25,
                [g["scores"][name]["pulse_rmse_spikes_s"]["mean"] for s, g in available],
                width=.25, label=name, color=list(colors.values())[offset+1])
        ax.set_xticks(np.arange(len(available))+.25, [s for s,g in available])
        ax.set(title=f"{kind} / held-out errors", ylabel="Mean animal pulse RMSE (spikes/s)")
        ax.legend(fontsize=8)
    fig.suptitle(f"Measured AOTU responses vs frozen models — {condition}, leave-one-recording-out\nObservation calibration only; size/contrast and neural dynamics remain unmodelled")
    fig.savefig(path, dpi=150, metadata={"Software": "Fly Creature physiological diagnostic"})
    plt.close(fig)


def direction_rows(curves):
    pairs = defaultdict(dict)
    for r in curves:
        pairs[r["type"], r["state"], r["fly"], r["speed"], r["center_deg"]][r["direction"]] = r
    result = []
    for (kind, state, fly, speed, center), directions in sorted(pairs.items()):
        if set(directions) != {-1, 1}:
            continue
        row = {"type": kind, "state": state, "fly": fly, "speed": speed, "center_deg": center}
        for field in ("measured_evoked_spikes_s", "baseline_evoked_spikes_s",
                      "footprint_evoked_spikes_s", "simple_spatial_evoked_spikes_s"):
            forward, backward = directions[1][field], directions[-1][field]
            row[field + "_difference"] = forward - backward
            row[field + "_ratio"] = forward / backward if forward > 0 and backward > 0 else ""
        result.append(row)
    return result


def temporal_plot(path, pulses, names, coefficients):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    output = []
    for row, kind in enumerate(ARCHIVES):
        target = 33.75 if kind == "AOTU019" else 56.25
        for col, speed in enumerate((25, 75)):
            ax = axes[row, col]
            group = [p for p in pulses if p["type"] == kind and p["state"] == "quiescent"
                and p["speed_deg_s"] == speed and p["direction"] == 1
                and abs(p["center_deg"] - target) < 1]
            # Illustrative fixed-position ipsiversive responses, equal weight per fly.
            duration = float(np.median([p["duration_s"] for p in group])) if group else 22.5/speed
            grid = np.arange(-.240, duration+.240, .010)
            animals = defaultdict(list)
            for p in group:
                gain, intercept = coefficients[kind, "quiescent", p["fly"]]
                indices = [names.index(n) for n in ("baseline", "footprint", "simple_spatial")]
                pred = p["plot_predictions"] * gain[indices, None] + intercept[indices, None]
                values = np.vstack([np.interp(grid, p["time"], p["rate"]),
                    *[np.interp(grid, p["time"][::7], v) for v in pred]])
                animals[p["fly"]].append(values)
            if animals:
                values = np.stack([np.mean(v, axis=0) for v in animals.values()])
                mean = values.mean(axis=0)
                sem = values.std(axis=0, ddof=1)/np.sqrt(len(animals)) if len(animals)>1 else np.zeros_like(mean)
                for i, label in enumerate(("measured", "baseline", "footprint", "simple_spatial")):
                    color = ("black", "#0072B2", "#D55E00", "#009E73")[i]
                    ax.plot(grid, mean[i], label=label, color=color)
                    if i == 0:
                        ax.fill_between(grid, mean[i]-sem[i], mean[i]+sem[i], color=color, alpha=.15)
                for t, values_at_time in zip(grid, mean.T):
                    output.append({"type": kind, "nominal_speed_deg_s": speed, "time_s": float(t),
                        "flies": len(animals), "measured_spikes_s": float(values_at_time[0]),
                        "baseline_spikes_s": float(values_at_time[1]), "footprint_spikes_s": float(values_at_time[2]),
                        "simple_spatial_spikes_s": float(values_at_time[3])})
            ax.axvspan(0, duration, color="gray", alpha=.08)
            ax.set(title=f"{kind}: ipsiversive, {speed}°/s nominal, center {target}°",
                xlabel="Seconds from visible onset", ylabel="Raw firing rate (spikes/s)")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Quiescent fixed-position examples — held-out observation calibration\nMeasured SEM across animals; gray region = visible stimulus")
    fig.savefig(path, dpi=150, metadata={"Software": "Fly Creature physiological diagnostic"})
    plt.close(fig)
    return output


def run(data_dir, output_dir, condition="NoP1"):
    output_dir.mkdir(parents=True, exist_ok=True)
    frozen_paths = [ROOT / "src/fly_creature" / name for name in
        ("pursuit_controller.py", "pursuit_activity.py", "pursuit_step4.py", "pursuit_delay_diagnostic.py",
         "data/visual_steering_v1.json", "data/lc10a_registered_eyemap_hypothesis_v3.json", "data/lc10a_column_footprints_v1.json")]
    frozen = {str(p.relative_to(ROOT)): sha(p) for p in frozen_paths}
    pulses, audit = load_archives(data_dir, condition)
    names, tables = model_tables()
    summarize_predictions(pulses, names, tables)
    folds, coefficients, summary = evaluate(pulses, names)
    if frozen != {str(p.relative_to(ROOT)): sha(p) for p in frozen_paths}:
        raise AssertionError("Frozen code or inputs changed during comparison")
    curves = binned_curves(pulses, names, coefficients)
    filter_error = pulses[0].pop("filter_max_abs_error")
    write_csv(output_dir / "folds.csv", folds)
    write_csv(output_dir / "curves.csv", curves)
    write_csv(output_dir / "direction.csv", direction_rows(curves))
    scalar_keys = [k for k,v in pulses[0].items() if np.isscalar(v)]
    write_csv(output_dir / "pulses.csv", [{k: p[k] for k in scalar_keys} for p in pulses])
    protocol = "pursuit_physiology_protocol.md" if condition == "NoP1" else "pursuit_p1_protocol.md"
    result = {"protocol": protocol, "condition": condition, "seed": SEED,
        "dataset_url": "https://zenodo.org/records/15474938", "audit": audit,
        "accepted_pulses": len(pulses), "variant_count": len(names), "summary": summary,
        "frozen_code_and_input_sha256": frozen,
        "checks": {"archives_md5_verified": True, "member_crc_verified": True,
            "accepted_plus_rejected_equals_finite_segments": all(a["accepted_pulses"] + sum(a["rejected"].values()) == a["finite_segments"] for a in audit),
            "filter_direct_convolution_max_abs_error": filter_error,
            "frozen_hashes_unchanged": True},
        "source_sha256": sha(Path(__file__)), "protocol_sha256": sha(ROOT / "docs" / protocol),
        "inputs_sha256": {name: sha(ROOT / "src/fly_creature/data" / name) for name in
            ("visual_steering_v1.json", "lc10a_registered_eyemap_hypothesis_v3.json", "lc10a_column_footprints_v1.json")},
        "limitations": [("NoP1 is not a measured uniform internal state" if condition == "NoP1" else
            "P1 label comes from archive and source provenance; stimulation markers not read from int_* files"), "Finite object size/contrast metadata unavailable in sample MAT variables",
            "Static adapter lacks neural temporal dynamics", "Calibration is observation-only, not a production change",
            "Source MATLAB analysis pipeline not reproduced", "Aggregate AOTU responses cannot uniquely identify individual LC10a fields"]}
    (output_dir / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    make_plot(output_dir / "overview.png", curves, summary, condition)
    write_csv(output_dir / "temporal.csv", temporal_plot(output_dir / "temporal.png", pulses, names, coefficients))
    print(json.dumps({k: {"flies": v.get("flies"), "pulses": v.get("pulses"),
        "rmse": {n: v["scores"][n]["pulse_rmse_spikes_s"]["mean"] for n in ("baseline", "footprint", "simple_spatial")},
        "wiring_ranks": v["pulse_error_beats_shuffles"]} for k,v in summary.items() if v["available"]}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--condition", choices=("NoP1", "P1"), default="NoP1")
    args = parser.parse_args()
    run(args.data_dir, args.output_dir, args.condition)


if __name__ == "__main__":
    main()

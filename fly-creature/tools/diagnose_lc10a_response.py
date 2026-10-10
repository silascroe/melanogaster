"""Bounded posthoc diagnosis; never changes the frozen benchmark or controller.

Reuses scored ablations and replays trial zero of the first retained P1
recording of each type. Selection depends on filenames and geometry, not rates.
"""
from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

import numpy as np
from scipy.signal import fftconvolve

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fly_creature.lc10a_response import (LC10aVisualResponse, causal_envelope,
    temporal_kernel_unnormalized, temporal_interval_weights)
from fly_creature.lc10a_response_benchmark import (_load_controls, _movie_state,
    _separable_features, _vertical_coverage, CONTRACT_PATH, DUPLICATE)
from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_physiology import P1_ARCHIVES, extract, read_recording
from fly_creature.pursuit_motion_diagnostic import model
from fly_creature.pursuit_temporal import observation_kernel
from fly_creature.retina import RetinalRenderer

BENCH = ROOT / "outputs/research/lc10a-recorded-benchmark-v1"
OUT = ROOT / "outputs/research/lc10a-response-diagnosis-v1"
EVIDENCE = ROOT / "docs/evidence/lc10a_response_diagnosis_v1.json"


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plot(report):
    os.environ.setdefault("MPLCONFIGDIR", str(OUT / "mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 4, figsize=(14, 6), sharex=True)
    for row, kind in enumerate(P1_ARCHIVES):
        with np.load(OUT/(kind+"_trial0.npz")) as saved:
            elapsed, primary, instant = (saved[k] for k in
                ("elapsed", "primary_raw", "instantaneous_raw"))
        for col, p in enumerate(x for x in report["pulses"] if x["type"] == kind):
            relative = elapsed-elapsed[p["start_sample"]]
            mask = (relative >= -.25) & (relative <= 1.6)
            scale = instant[mask].max()
            ax = axes[row, col]
            ax.axvspan(0, p["duration_s"], color="gray", alpha=.16)
            ax.plot(relative[mask], instant[mask]/scale, label="Envelope removed", color="#226b9b")
            ax.plot(relative[mask], primary[mask]/scale, label="Frozen envelope", color="#bd402e")
            ax.set_title(f"{kind}: {p['speed']} deg/s, dir {p['direction']:+d}\ncenter {p['center_deg']:.1f} deg")
            ax.set_ylim(-.02, 1.1)
            ax.grid(alpha=.2)
            if row == 1:
                ax.set_xlabel("Seconds after target onset")
            if col == 0:
                ax.set_ylabel("Contact drive / unfiltered peak")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Two native P1 trials: envelope moves contact drive beyond the visible pulse\n"
                 "Gray = target visible; same scale within each panel; posthoc geometry-selected examples")
    fig.tight_layout()
    fig.savefig(ROOT/"docs/evidence/lc10a_response_diagnosis_v1.png", dpi=150)
    plt.close(fig)


def run():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    source_manifest = json.loads((ROOT/"docs/evidence/lc10a_response_design_v1.json").read_text())
    source_files = {}
    for name, record in source_manifest["source_files"].items():
        local = ROOT/"outputs/research/lc10a-response-design-v1/sources"/Path(name).name
        actual = digest(local)
        assert actual == record["sha256"], f"Pinned author source changed: {name}"
        source_files[name] = actual
    summary = rows(BENCH / "configuration_summary.csv")
    scores = rows(BENCH / "recording_scores.csv")
    ablations = []
    for kind in P1_ARCHIVES:
        group = {r["predictor"]: float(r["mean_recording_rmse_spikes_s"])
                 for r in summary if r["condition"] == "P1" and r["type"] == kind}
        for name in ("primary:intact", "instantaneous:intact",
                     "instantaneous:matched_spatial", "no_surround:intact",
                     "no_static:intact", "direction_neutral:intact",
                     "width_half:intact", "width_double:intact", "legacy_intact"):
            individual = {r["recording"]: float(r["rmse_spikes_s"]) for r in scores
                if r["condition"] == "P1" and r["type"] == kind and r["predictor"] == name}
            old = {r["recording"]: float(r["rmse_spikes_s"]) for r in scores
                if r["condition"] == "P1" and r["type"] == kind
                and r["predictor"] == "legacy_intact"}
            ablations.append(dict(type=kind, predictor=name, rmse=group[name],
                improvement_vs_legacy_pct=100*(1-group[name]/group["legacy_intact"]),
                wins_vs_legacy=sum(individual[k] < old[k] for k in old), recordings=len(old)))
        assert group["primary:intact"] > group["legacy_intact"], "Symptom no longer reproduced"

    # Independent transcription of author MATLAB, whose times are past-current.
    lag = np.linspace(0, 3, 30001)
    source_shape = np.exp(5.5273*(.84962-lag)) / (
        (np.exp(15.5884*(-lag+.1859))+1)*(np.exp(5.5273*(.84962-lag))+1))
    source_error = float(np.max(np.abs(source_shape-temporal_kernel_unnormalized(lag))))
    assert source_error < 1e-14
    dt = .0015
    w = temporal_interval_weights(dt)
    kernel = dict(source_equation_max_error=source_error,
        peak_lag_s=float(lag[np.argmax(source_shape)]),
        mean_lag_s=float(np.sum(w*(np.arange(len(w))+.5)*dt)),
        mass_before_300ms=float(w[:int(.3/dt)].sum()))
    projection = ActivityProjection.from_packaged_data()
    names, matrices, _ = _load_controls(json.loads(CONTRACT_PATH.read_text()), projection)
    weights = matrices[:2].transpose(1, 0, 2).reshape(275, 8)
    response, renderer = LC10aVisualResponse(projection=projection), RetinalRenderer()
    lookup_model = model(projection)
    vertical = _vertical_coverage(renderer, 60.)
    with np.load(BENCH / "trial_cell_predictors.npz", allow_pickle=False) as saved:
        cached_keys = {tuple(json.loads(k)): i for i, k in enumerate(saved["keys"])}
        cached_names = saved["predictor_names"].tolist()
        cached_predictions = saved["predictions"]
    traces, replay_checks = [], []
    for kind, (filename, expected_md5) in P1_ARCHIVES.items():
        archive_path = ROOT / "outputs/research/aotu-recordings" / filename
        with archive_path.open("rb") as stream:
            assert hashlib.file_digest(stream, "md5").hexdigest() == expected_md5
        with zipfile.ZipFile(archive_path) as archive:
            member = next(n for n in sorted(archive.namelist()) if n.endswith("_int.mat")
                and kind+"/"+Path(n).stem.removesuffix("_int") != DUPLICATE)
            payload = archive.read(member)
        identity = kind+"/"+Path(member).stem.removesuffix("_int")
        native, step, signals = read_recording(payload)
        pulses, _ = extract(native, step, signals, identity, kind, "canonical")
        quiet = [p for p in pulses if p["state"] == "quiescent" and p["trial"] == 0]
        position, elapsed = signals["int_panelps"][:, 0], native-native[0]
        state = _movie_state(position, elapsed, step, renderer, 11.25, 1.)
        raw = {}
        commutation_error = 0.
        for movie, dark, motion in (("canonical", state["dark"], state["motion"]),
                                   ("mirror", state["mirror_dark"], state["mirror_motion"])):
            features = _separable_features(response, dark, motion, vertical, "primary")
            instantaneous = features @ weights
            raw["instantaneous", movie] = instantaneous
            raw["primary", movie] = causal_envelope(instantaneous, step)
            # Check moving the linear envelope after contact projection.
            probe = features[:2048]
            err = np.max(np.abs(causal_envelope(probe, step) @ weights
                                - causal_envelope(probe @ weights, step)))
            commutation_error = max(commutation_error, float(err))
            del features
        assert commutation_error < 1e-10
        order = list(zip(projection.aotu_types, projection.aotu_sides))
        right, left = order.index((kind, "R")), order.index((kind, "L"))
        grid, values = lookup_model.lookups[kind]
        peak = lookup_model.peaks[kind]
        radius, obs_kernel = observation_kernel(step)
        filtered, paired_raw, quantization = {}, {}, []
        for variant in ("primary", "instantaneous"):
            for control, offset in (("intact", 0), ("matched_spatial", 4)):
                channels = [raw[variant, "canonical"][:, right+offset],
                            raw[variant, "mirror"][:, left+offset]]
                paired_raw[variant, control] = .5*(channels[0]+channels[1])
                assert max(c.max() for c in channels) <= peak+1e-9
                for decoding in ("nearest", "linear"):
                    activated = []
                    for c in channels:
                        index = np.floor(np.clip(c/peak*(len(grid)-1), 0, len(grid)-1)+.5).astype(int)
                        activated.append(values[index] if decoding == "nearest"
                                         else np.interp(c, grid, values))
                    signal = .5*(activated[0]+activated[1])
                    padded = np.pad(signal, (radius, radius))
                    filtered[variant, control, decoding] = fftconvolve(
                        padded, obs_kernel, mode="same")[radius:radius+len(signal)]
                positive = sum(np.count_nonzero(c > 0) for c in channels)
                zeroed = sum(np.count_nonzero((c > 0) &
                    (np.floor(c/peak*(len(grid)-1)+.5) == 0)) for c in channels)
                quantization.append(dict(variant=variant, control=control,
                    positive_samples=int(positive), positive_to_zero=int(zeroed),
                    raw_peak_fraction=max(float(c.max()/peak) for c in channels)))
        def evoked(signal, p):
            start, margin = p["start_sample"], p["margin"]
            stop = start+len(p["position"])-2*margin
            baseline = start-margin+np.flatnonzero((p["time"]>=-.250)&(p["time"]<=-.100))
            return float(signal[start:stop].mean()-signal[baseline].mean())
        max_cached_error = 0.
        grouped = {}
        for p in quiet:
            key = ("P1", kind, identity, 0, p["speed_deg_s"], p["direction"],
                   int(round(p["center_deg"]/11.25)))
            grouped.setdefault(key, []).append(p)
        for key, ps in grouped.items():
            for variant in ("primary", "instantaneous"):
                for control in ("intact", "matched_spatial"):
                    prediction = np.mean([evoked(filtered[variant, control, "nearest"], p) for p in ps])
                    cached = cached_predictions[cached_keys[key], cached_names.index(variant+":"+control)]
                    max_cached_error = max(max_cached_error, abs(float(prediction-cached)))
        assert max_cached_error < 1e-10, max_cached_error
        selected = []
        for speed in (25, 75):
            for direction in (-1, 1):
                options = [p for p in quiet if p["speed_deg_s"] == speed and p["direction"] == direction]
                preferred = 35 if kind == "AOTU019" else 65
                selected.append(min(options, key=lambda p: (abs(p["center_deg"]-preferred), p["start_sample"])))
        for p in selected:
            start = p["start_sample"]
            stop = start+len(p["position"])-2*p["margin"]
            end = min(len(native), stop+int(1.5/step))
            item = dict(type=kind, recording=identity, trial=0, start_sample=start,
                speed=p["speed_deg_s"], direction=p["direction"], center_deg=p["center_deg"],
                duration_s=float(p["duration_s"]), measured_evoked=float(p["evoked_spikes_s"]))
            for variant in ("primary", "instantaneous"):
                signal = paired_raw[variant, "intact"]
                peak_sample = start+int(np.argmax(signal[start:end]))
                item[variant+"_raw_peak_after_onset_s"] = (peak_sample-start)*step
                item[variant+"_raw_visible_mean"] = float(signal[start:stop].mean())
                for decoding in ("nearest", "linear"):
                    item[variant+"_"+decoding+"_evoked"] = evoked(filtered[variant, "intact", decoding], p)
            traces.append(item)
        np.savez_compressed(OUT/(kind+"_trial0.npz"), position=position, elapsed=elapsed,
            primary_raw=paired_raw["primary", "intact"],
            instantaneous_raw=paired_raw["instantaneous", "intact"])
        replay_checks.append(dict(type=kind, recording=identity, member=member,
            member_sha256=hashlib.sha256(payload).hexdigest(), native_frames=len(native),
            scored_trial0_cells=len(grouped), cached_prediction_max_error=max_cached_error,
            linear_commutation_max_error=commutation_error, quantization=quantization))
        print(kind, "native replay matches cache:", max_cached_error, flush=True)
    report = dict(date="2026-10-09", status="diagnosis_complete_no_promotion",
        scope="posthoc; two native P1 trial-zero replays, eight geometry-selected pulses; no tuning",
        verdict="Retire the transferred-envelope primary candidate; instantaneous is diagnostic, not promoted.",
        pinned_author_sources=source_files,
        output_units="Raw contact drive and pre-calibration dimensionless lookup responses; not firing rates.",
        reproduced_primary_failure=True, kernel=kernel, ablations=ablations,
        replay_checks=replay_checks, pulses=traces,
        source_hashes={str(p.relative_to(ROOT)):digest(p) for p in (
            ROOT/"src/fly_creature/lc10a_response.py", ROOT/"src/fly_creature/lc10a_response_benchmark.py",
            CONTRACT_PATH, BENCH/"configuration_summary.csv", BENCH/"recording_scores.csv")},
        elapsed_s=time.monotonic()-started)
    def scalar(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Unsupported report value: {type(value).__name__}")
    EVIDENCE.write_text(json.dumps(report, indent=2, allow_nan=False, default=scalar)+"\n", encoding="utf-8")
    plot(report)
    print(json.dumps(dict(kernel=kernel, ablations=ablations, pulses=traces), indent=2, default=scalar))
    return report


if __name__ == "__main__":
    run()

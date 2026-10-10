"""Synthetic-only checks of the prospective audit; never opens recordings."""
import io
import json
import argparse
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np

from audit_downstream_recordings import (
    FORBIDDEN, coverage, extract_metadata, metadata_recording, read_allowed,
)
from fly_creature.pursuit_physiology import extract


def main():
    dt = .0015
    time = np.arange(6000) * dt
    pos = np.full((len(time), 4), np.nan)
    forward = np.zeros_like(pos)
    # Two separate slow pulses, opposite directions; four distinct trials.
    pos[500:1100, :] = np.linspace(-11.25, 11.25, 600)[:, None]
    pos[2000:2600, :] = np.linspace(11.25, -11.25, 600)[:, None]
    # A third visible segment deliberately fails the duration gate.
    pos[3500:3520, :] = 0
    payload = io.BytesIO()
    with h5py.File(payload, "w") as f:
        for name, value in {"int_time": time[:, None], "int_panelps": pos,
                "int_forward": forward, "int_angular": np.zeros_like(pos),
                "int_sideway": np.zeros_like(pos), "int_spikert": np.zeros_like(pos),
                "int_voltage": np.zeros_like(pos)}.items():
            f.create_dataset(name, data=value.T)
    native_array = h5py.Dataset.__array__
    accesses = []

    def guarded(dataset, *args, **kwargs):
        name = dataset.name.rsplit("/", 1)[-1]
        if name in FORBIDDEN:
            raise AssertionError("Audit attempted neural numerical access")
        accesses.append(name)
        return native_array(dataset, *args, **kwargs)

    with patch.object(h5py.Dataset, "__array__", guarded):
        native, actual_dt, p, fwd, info = metadata_recording(payload.getvalue())
    assert set(accesses) == {"int_time", "int_panelps", "int_forward"}
    assert not any(info["schema"][k]["numerical_values_read"] for k in FORBIDDEN)
    for name in FORBIDDEN:
        try:
            read_allowed({}, name, set())
        except ValueError:
            pass
        else:
            raise AssertionError("Allowlist accepted forbidden dataset")
    pulses, rejected, gaps = extract_metadata(native, actual_dt, p, fwd)
    # Reference extractor receives manufactured zero rates, never real data.
    reference, ref_rejected = extract(native, actual_dt,
        {"int_panelps": p, "int_forward": fwd, "int_spikert": np.zeros_like(p)},
        "synthetic", "AOTU019", "R")
    assert rejected == ref_rejected == {"duration": 4}
    assert len(pulses) == len(reference) == 8
    for a, b in zip(pulses, reference):
        for key in ("trial", "start_sample", "state", "direction", "center_deg", "duration_s"):
            assert a[key] == b[key], key
        assert a["speed"] == b["speed_deg_s"]
        assert a["baseline_samples"] == 100
    assert pulses[0]["preceding_gap_s"] is None
    assert abs(pulses[1]["preceding_gap_s"] - 1.35) < 1e-12
    assert len(gaps) == 8
    assert len(coverage(pulses)) == 2
    assert not coverage([p for p in pulses if p["trial"] < 3])
    print(json.dumps({"status": "pass", "synthetic_only": True,
        "numerical_read_guard": True, "reference_exclusion_parity": True,
        "distinct_trial_coverage": True, "first_pulse_gap": True}))


def check_report(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["phase"] == "A" and report["status"] == "stop"
    assert not report["response_values_read"] and not report["fit_performed"]
    assert sum(r["type"]=="DNa02" for r in report["recordings"]) == 11
    assert len(report["recordings"]) == 80
    for r in report["recordings"]:
        assert set(r["numerical_datasets_read"]) <= {
            "int_time", "int_panelps", "int_forward", "int_optostm"}
        assert not any(r["schema"][k]["numerical_values_read"] for k in FORBIDDEN)
        assert r["dt_s"] > 0 and r["grid_error_s"] < 1e-8
        pulses = json.loads((path.parent / (r["condition"]+"_"+
            r["recording"].replace("/","_")+"_pulses.json")).read_text(encoding="utf-8"))
        assert len(pulses) == r["accepted_pulses"]
        trials = defaultdict(set)
        for p in pulses:
            if p["state"]=="quiescent" and p["speed"]==25:
                trials[p["direction"],p["center_bin"]].add(p["trial"])
        expected = {k:sorted(v) for k,v in trials.items() if len(v)>=4}
        saved = {(c["direction"],c["center_bin"]):c["trials"]
            for c in r["eligible_25_quiet_cells"]}
        assert expected == saved
    for candidate in report["cohort_candidates"].values():
        for cell in candidate["common_cells"]:
            assert cell["speed"] == 25
            assert all(len(v)>=4 for v in cell["recordings"].values())
            assert len(cell["mirrored_aotu019_recordings"])>=4
        units = {r for c in candidate["common_cells"] for r in c["recordings"]["DNa02"]}
        assert sorted(units) == candidate["eligible_dna02_recordings"]
        assert candidate["coverage_pass"] == (len(units)>=6 and bool(candidate["common_cells"]))
    print(json.dumps({"status": "pass", "metadata_artifact_only": True,
        "recordings_checked": len(report["recordings"]),
        "response_access_declarations": "pass", "trial_coverage_reconstructed": "pass"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path)
    args = parser.parse_args()
    main()
    if args.report:
        check_report(args.report)

"""Descriptive condition audit of two frozen physiology evaluations."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .pursuit_physiology import write_csv


def rows(directory, name):
    with (directory / name).open(encoding="utf8", newline="") as stream:
        return list(csv.DictReader(stream))


def describe(values):
    values = np.asarray(values, dtype=float)
    return {"n": len(values), "mean": float(values.mean()),
        "median": float(np.median(values)), "min": float(values.min()),
        "max": float(values.max())}


def compare(nop1_dir, p1_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    directories = {"NoP1": nop1_dir, "P1": p1_dir}
    reports = {c: json.loads((d / "report.json").read_text(encoding="utf8"))
        for c, d in directories.items()}
    if reports["NoP1"]["frozen_code_and_input_sha256"] != reports["P1"]["frozen_code_and_input_sha256"]:
        raise ValueError("Conditions did not use the same frozen model")
    audits = {c: {a["fly"]: a for a in r["audit"]} for c, r in reports.items()}
    shared = sorted(audits["NoP1"].keys() & audits["P1"].keys())
    overlap = [{"identity": identity,
        "same_side": audits["NoP1"][identity]["side"] == audits["P1"][identity]["side"],
        "same_member_bytes": audits["NoP1"][identity]["member_sha256"] == audits["P1"][identity]["member_sha256"],
        "NoP1_shape": audits["NoP1"][identity]["shape"],
        "P1_shape": audits["P1"][identity]["shape"]} for identity in shared]
    source_pulses = {c: rows(d, "pulses.csv") for c, d in directories.items()}
    source_folds = {c: rows(d, "folds.csv") for c, d in directories.items()}
    coverage, errors, direction = [], [], []
    for condition, report in reports.items():
        for kind in ("AOTU019", "AOTU025"):
            selected = [p for p in source_pulses[condition] if p["type"] == kind]
            for state in ("quiescent", "running", "mixed"):
                pulses = [p for p in selected if p["state"] == state]
                if not pulses:
                    continue
                animals = sorted({p["fly"] for p in pulses})
                coverage.append({"condition": condition, "type": kind, "state": state,
                    "recordings": len(animals), "pulses": len(pulses),
                    "fraction_of_type_pulses": len(pulses) / len(selected),
                    "center_deg": describe([p["center_deg"] for p in pulses]),
                    "speed_counts": dict(Counter(p["speed_deg_s"] for p in pulses)),
                    "direction_counts": dict(Counter(p["direction"] for p in pulses)),
                    "by_animal": [{"identity": animal,
                        **{key: describe([p[key] for p in pulses if p["fly"] == animal])
                            for key in ("baseline_spikes_s", "mean_spikes_s", "evoked_spikes_s")}}
                        for animal in animals]})
                group = report["summary"][kind + "/" + state]
                if not group["available"]:
                    continue
                constant = group["scores"]["intercept_only"]["pulse_rmse_spikes_s"]["mean"]
                simple = group["scores"]["simple_spatial"]["pulse_rmse_spikes_s"]["mean"]
                for variant in ("baseline", "footprint", "simple_spatial", "intercept_only"):
                    folds = [r for r in source_folds[condition] if r["type"] == kind
                        and r["state"] == state and r["variant"] == variant]
                    score = group["scores"][variant]
                    error = score["pulse_rmse_spikes_s"]["mean"]
                    errors.append({"condition": condition, "type": kind, "state": state,
                        "recordings": group["flies"], "pulses": group["pulses"], "variant": variant,
                        "raw_rmse_spikes_s": error, "raw_rmse_sem": score["pulse_rmse_spikes_s"]["sem"],
                        "evoked_rmse_spikes_s": score["evoked_rmse_spikes_s"]["mean"],
                        "time_rmse_spikes_s": score["time_rmse_spikes_s"]["mean"],
                        "error_reduction_vs_constant_percent": 100 * (constant - error) / constant,
                        "error_reduction_vs_simple_percent": 100 * (simple - error) / simple,
                        "beat_shuffle_count": group["pulse_error_beats_shuffles"].get(variant, ""),
                        "median_training_gain": float(np.median([float(f["gain"]) for f in folds])),
                        "median_training_intercept_spikes_s": float(np.median([float(f["intercept_spikes_s"]) for f in folds]))})
        paired = rows(directories[condition], "direction.csv")
        # Within-recording direction pairs, not a cross-condition P1-effect estimate.
        for kind in ("AOTU019", "AOTU025"):
            for state in ("quiescent", "running", "mixed"):
                selected = [r for r in paired if r["type"] == kind and r["state"] == state
                    and 0 < float(r["center_deg"]) < 90]
                animals = sorted({r["fly"] for r in selected})
                for field in ("measured_evoked_spikes_s", "baseline_evoked_spikes_s",
                              "footprint_evoked_spikes_s", "simple_spatial_evoked_spikes_s"):
                    if not animals:
                        continue
                    values = [np.mean([float(r[field + "_difference"]) for r in selected if r["fly"] == a])
                        for a in animals]
                    direction.append({"condition": condition, "type": kind, "state": state,
                        "field": field, "recordings": len(animals),
                        "mean_animal_ipsiversive_minus_contraversive_spikes_s": float(np.mean(values)),
                        "sem": float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0})
    result = {"protocol": "pursuit_p1_protocol.md", "condition_reports_sha256":
        {c: hashlib.sha256((d / "report.json").read_bytes()).hexdigest() for c, d in directories.items()},
        "overlapping_identities": overlap, "only_NoP1": sorted(audits["NoP1"].keys() - audits["P1"].keys()),
        "only_P1": sorted(audits["P1"].keys() - audits["NoP1"].keys()),
        "coverage": coverage, "errors": errors, "direction_descriptive": direction,
        "limitations": ["Shared date/fly names suggest repeated animals but do not establish randomization or protocol order",
            "Independent calibration within each condition does not predict a causal P1 gain effect",
            "Direction summary averages available ipsilateral positions/speeds per animal; coverage can differ",
            "Cross-condition descriptive rate differences are not paired causal estimates"]}
    (output_dir / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf8")
    write_csv(output_dir / "comparison.csv", errors)
    write_csv(output_dir / "direction_comparison.csv", direction)
    print(json.dumps({"shared_recording_names": len(overlap), "only_NoP1": len(result["only_NoP1"]),
        "only_P1": len(result["only_P1"]), "errors": errors}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nop1-dir", type=Path, required=True)
    parser.add_argument("--p1-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    compare(args.nop1_dir, args.p1_dir, args.output_dir)


if __name__ == "__main__":
    main()

"""Offline hemisphere and duplicated-recording sensitivity; no model fitting changes."""
import argparse
import json
from pathlib import Path

from .pursuit_physiology import load_archives, model_tables, summarize_predictions, evaluate, write_csv


def run(data_dir, comparison_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison = json.loads((comparison_dir / "comparison.json").read_text(encoding="utf8"))
    duplicates = [r["identity"] for r in comparison["numeric_trial_overlap"]
        if len(r["exact_four_signal_matches"]) == r["NoP1_trials"] == r["P1_trials"]]
    names, tables = model_tables()
    summaries, compact = {}, []
    keys = ("x", "x_baseline", "time_moments", "rate_mean", "rate_square_mean")
    for condition in ("NoP1", "P1"):
        pulses, audit = load_archives(data_dir, condition)
        metadata_sides = [p["side"] for p in pulses]
        by_side = {}
        # Both hemisphere predictions are reused; the identical recorded rates remain fixed.
        for assignment in ("metadata", "opposite"):
            for p, side in zip(pulses, metadata_sides):
                p["side"] = side if assignment == "metadata" else ("R" if side == "L" else "L")
            summarize_predictions(pulses, names, tables)
            by_side[assignment] = [{k: p[k] for k in keys} for p in pulses]
            for p in pulses:
                p.pop("plot_predictions", None)
        for assignment in ("metadata", "opposite", "all_L", "all_R", "metadata_exclude_duplicate"):
            for j, (p, side) in enumerate(zip(pulses, metadata_sides)):
                opposite = assignment == "opposite" or (assignment in ("all_L", "all_R") and side != assignment[-1])
                p.update(by_side["opposite" if opposite else "metadata"][j])
                p["side"] = ("R" if side == "L" else "L") if opposite else side
            selected = [p for p in pulses if assignment != "metadata_exclude_duplicate" or p["fly"] not in duplicates]
            folds, _, summary = evaluate(selected, names)
            summaries[condition + "/" + assignment] = summary
            write_csv(output_dir / f"{condition}_{assignment}_folds.csv", folds)
            for group, value in summary.items():
                if not value["available"]:
                    continue
                constant = value["scores"]["intercept_only"]["pulse_rmse_spikes_s"]["mean"]
                for variant in ("baseline", "footprint", "simple_spatial", "intercept_only"):
                    error = value["scores"][variant]["pulse_rmse_spikes_s"]["mean"]
                    compact.append({"condition": condition, "assignment": assignment, "group": group,
                        "variant": variant, "recordings": value["flies"], "pulses": value["pulses"],
                        "raw_rmse_spikes_s": error, "error_reduction_vs_constant_percent": 100*(constant-error)/constant,
                        "beat_shuffle_count": value["pulse_error_beats_shuffles"].get(variant, "")})
            print(condition, assignment, "complete", flush=True)
        original = json.loads((comparison_dir.parent / ("aotu-nop1-regression" if condition == "NoP1" else "aotu-p1-v1") / "report.json").read_text())
        if summaries[condition + "/metadata"] != original["summary"]:
            raise AssertionError("Sensitivity replay changed original metadata-assigned summaries")
        del pulses, by_side
    result = {"excluded_duplicate_identities": duplicates, "summary": summaries,
        "metadata_summaries_exactly_reproduced": True,
        "scope": "Hemisphere scenarios are pre-fit declared; duplicate exclusion is post hoc. Neither tunes model parameters.",
        "limitations": ["Four side scenarios do not exhaust all per-recording assignments",
            "Excluding one duplicate does not certify every remaining trial's stimulation condition"]}
    (output_dir / "sensitivity.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf8")
    write_csv(output_dir / "sensitivity.csv", compact)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--comparison-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.data_dir, args.comparison_dir, args.output_dir)

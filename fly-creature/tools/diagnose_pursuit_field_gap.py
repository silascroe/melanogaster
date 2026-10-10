"""Isolate why the v1 LC10a hypothesis misses the AOTU025 reference field.

All alternative angle mappings are diagnostic counterfactuals. This program
does not change the packaged map, fit a runtime input, or enable Godot.
"""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection


SOURCE = Path("outputs/research/CollieWilson/Modeling_Code/Pursuit_RFs.csv")
MAP = Path("src/fly_creature/data/lc10a_upstream_hypothesis_v2.json")
OUTPUT = Path("docs/evidence/pursuit_field_gap_v1.json")
GRID = np.arange(0.0, 166.0)
BRANCHES = ("AOTU019", "AOTU025")


def main() -> None:
    source_manifest = json.loads(Path("docs/evidence/pursuit_reference_source_v1.json").read_text())
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != source_manifest["sha256"][
            "Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("Reference table is not the pinned source")
    with SOURCE.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    reference = {name: np.array([float(row[name]) for row in rows])[180:346]
                 for name in BRANCHES}
    projection = ActivityProjection.from_packaged_data()
    index = {(kind, side): i for i, (kind, side) in enumerate(
        zip(projection.aotu_types, projection.aotu_sides))}
    visual_map = {int(row["body_id"]): row for row in json.loads(MAP.read_text())["cells"]}
    horizontal = np.array([visual_map[int(body_id)]["horizontal_position"]
                           for body_id in projection.body_ids])
    rank = (projection.centers_deg - 5.0) / 55.0
    direct = np.array([visual_map[int(body_id)]["position_source"] ==
                       "upstream column contacts" for body_id in projection.body_ids])

    def compare(centers: np.ndarray, width: float = 18.0,
                weights: np.ndarray | None = None) -> dict:
        candidate = replace(projection, centers_deg=centers,
                            lc_to_aotu=projection.lc_to_aotu if weights is None else weights)
        result = candidate.fixed_fly(GRID, width_deg=width)["aotu_contact_drive"]
        summary = {}
        for name in BRANCHES:
            target = reference[name]
            trial = result[:, index[name, "R"]]
            summary[name] = {
                "peak_deg": int(GRID[np.argmax(trial)]),
                "reference_peak_deg": int(GRID[np.argmax(target)]),
                "normalized_shape_pearson": float(np.corrcoef(trial, target)[0, 1]),
                "normalized_shape_mean_absolute_difference": float(np.mean(
                    np.abs(trial / trial.max() - target / target.max()))),
            }
        return summary

    baseline = compare(projection.centers_deg)
    left_response = projection.fixed_fly(-GRID)["aotu_contact_drive"]
    left_hemisphere = {}
    for name in BRANCHES:
        trial = left_response[:, index[name, "L"]]
        target = reference[name]
        left_hemisphere[name] = {
            "absolute_peak_deg": int(GRID[np.argmax(trial)]),
            "reference_peak_deg": int(GRID[np.argmax(target)]),
            "normalized_shape_pearson": float(np.corrcoef(trial, target)[0, 1]),
        }
    width_sweep = {str(width): compare(projection.centers_deg, width)
                   for width in (5.0, 10.0, 18.0, 30.0)}
    minimum_contact_sweep = {
        str(minimum): compare(projection.centers_deg,
                              weights=np.where(projection.lc_to_aotu >= minimum,
                                               projection.lc_to_aotu, 0.0))
        for minimum in (1, 5, 10, 20)
    }
    contact_cap_sweep = {
        str(cap): compare(projection.centers_deg,
                          weights=np.minimum(projection.lc_to_aotu, cap))
        for cap in (50, 100, 170)
    }
    rank_span = {str(upper): compare(5.0 + (upper - 5.0) * rank)
                 for upper in (60.0, 75.0, 90.0, 120.0)}
    global_h = (horizontal - horizontal.min()) / (horizontal.max() - horizontal.min())
    anatomical_axis = {
        "0_to_90": compare(90.0 * global_h),
        "source_stated_minus15_to_165_clipped": compare(np.clip(-15.0 + 180.0 * global_h,
                                                                 0.0, 180.0)),
    }
    side_profiles = {}
    for name in BRANCHES:
        side_profiles[name] = {}
        for side in ("L", "R"):
            weights = projection.lc_to_aotu[:, index[name, side]]
            side_profiles[name][side] = {
                "contacts": int(weights.sum()),
                "direct_upstream_position_contact_fraction": float(weights[direct].sum()
                                                                    / weights.sum()),
                "mean_assumed_center_deg_weighted_by_contacts": float(
                    np.dot(weights, projection.centers_deg) / weights.sum()),
            }
    # A coarse two-parameter fit is *only* an identifiability check. If it
    # works, peak agreement alone cannot validate the anatomical angle map.
    best = None
    for lower in range(-40, 31, 2):
        for upper in range(80, 151, 2):
            result = compare(np.clip(lower + (upper - lower) * rank, 0.0, 180.0))
            peak_error = sum(abs(result[name]["peak_deg"] -
                                 result[name]["reference_peak_deg"])
                             for name in BRANCHES)
            record = (peak_error, lower, upper, result)
            if best is None or record[:3] < best[:3]:
                best = record
    report = {
        "status": "diagnostic only; source curves are not independent validation for a fitted angle scale",
        "source_commit": source_manifest["commit"],
        "baseline": baseline,
        "opposite_hemisphere_baseline": left_hemisphere,
        "width_sweep_deg": width_sweep,
        "minimum_lc10a_to_aotu_contact_sweep": minimum_contact_sweep,
        "lc10a_to_aotu_contact_cap_sweep": contact_cap_sweep,
        "rank_based_upper_span_sweep_deg": rank_span,
        "raw_horizontal_position_counterfactuals": anatomical_axis,
        "branch_input_position_coverage": side_profiles,
        "coarse_peak_fit_demonstrating_nonidentifiability": {
            "lower_deg": best[1], "upper_deg": best[2],
            "total_peak_error_deg": best[0], "comparison": best[3],
            "warning": "Fit uses the two output peaks being evaluated; never promote it as a measured visual map",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": baseline, "width_peaks": {
        width: {name: item["peak_deg"] for name, item in branch.items()}
        for width, branch in width_sweep.items()},
        "best_peak_fit": report["coarse_peak_fit_demonstrating_nonidentifiability"]}, indent=2))


if __name__ == "__main__":
    main()

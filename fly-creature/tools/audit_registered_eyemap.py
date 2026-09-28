"""Audit the registered eye-map candidate and fixed-fly wiring controls."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection
from derive_lc10a_registered_eyemap import (
    EYE_BLOB_SHA, MED_BLOB_SHA, EyeMap, NEIGHBORS, hex_distance_squared,
)


GRID = np.arange(0.0, 166.0)
TYPES = ("AOTU019", "AOTU025")
MAP = Path("src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json")
OUTPUT = Path("docs/evidence/registered_eyemap_v3.json")


def field_scores(projection: ActivityProjection, reference: dict[str, np.ndarray],
                 index: dict[tuple[str, str], int]) -> dict:
    result = {}
    for side in ("L", "R"):
        trial = projection.fixed_fly(-GRID if side == "L" else GRID)[
            "aotu_contact_drive"]
        result[side] = {}
        for kind in TYPES:
            values = trial[:, index[kind, side]]
            target = reference[kind]
            result[side][kind] = {
                "peak_deg": int(GRID[np.argmax(values)]),
                "reference_peak_deg": int(GRID[np.argmax(target)]),
                "shape_pearson": float(np.corrcoef(values, target)[0, 1]),
            }
        result[side]["peak_separation_deg"] = (
            result[side]["AOTU025"]["peak_deg"] -
            result[side]["AOTU019"]["peak_deg"])
    return result


def main() -> None:
    map_bytes = MAP.read_bytes()
    visual_map = json.loads(map_bytes)
    if (visual_map["sources"]["eye_map_git_blob_sha1"] != EYE_BLOB_SHA or
            visual_map["sources"]["fafb_medulla_grid_git_blob_sha1"] != MED_BLOB_SHA):
        raise ValueError("Packaged map provenance differs from pinned eye-map files")
    cells = {int(row["body_id"]): row for row in visual_map["cells"]}
    eye = EyeMap(Path("outputs/research/eyemap_T4/eyemap.RData"),
                 Path("outputs/research/eyemap_T4/med_ixy.RData"))
    leave_one_out = []
    for row_index, point in enumerate(eye.coords):
        distances = hex_distance_squared(eye.coords, point).astype(float)
        distances[row_index] = np.inf
        near = np.argsort(distances)[:NEIGHBORS]
        weights = 1.0 / (distances[near] + 0.1)
        design = np.column_stack((eye.coords[near], np.ones(NEIGHBORS)))
        coefficients = np.linalg.lstsq(
            design * np.sqrt(weights[:, None]),
            eye.azimuth[near] * np.sqrt(weights), rcond=None,
        )[0]
        leave_one_out.append(abs(float(np.append(point, 1.0) @ coefficients) -
                                 eye.azimuth[row_index]))
    loo = np.asarray(leave_one_out)

    source = Path("outputs/research/CollieWilson/Modeling_Code/Pursuit_RFs.csv")
    manifest = json.loads(Path("docs/evidence/pursuit_reference_source_v1.json").read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["sha256"][
            "Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("Authors' field table differs from pinned source")
    with source.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    reference = {kind: np.array([float(row[kind]) for row in rows])[180:346]
                 for kind in TYPES}
    projection = ActivityProjection.from_packaged_data(map_path=MAP)
    index = {(kind, side): i for i, (kind, side) in enumerate(
        zip(projection.aotu_types, projection.aotu_sides))}
    intact = field_scores(projection, reference, index)
    old_projection = ActivityProjection.from_packaged_data(map_path=Path(
        "src/fly_creature/data/lc10a_upstream_hypothesis_v2.json"))
    old = field_scores(old_projection, reference, index)

    branch_coverage = {}
    for side in ("L", "R"):
        for kind in TYPES:
            weights = projection.lc_to_aotu[:, index[kind, side]]
            total = weights.sum()
            direct = np.array([cells[int(body_id)]["angle_source"] ==
                               "upstream registered columns"
                               for body_id in projection.body_ids])
            interpolated = np.array([
                cells[int(body_id)]["eye_map_interpolated_contact_fraction"] or 0.0
                for body_id in projection.body_ids
            ])
            branch_coverage[f"{kind}_{side}"] = {
                "lc10a_to_aotu_contacts": int(total),
                "direct_angle_contact_fraction": float(weights[direct].sum() / total),
                "boundary_interpolation_fraction_within_direct": float(
                    np.dot(weights[direct], interpolated[direct]) / weights[direct].sum()),
            }

    rng = np.random.default_rng(20260926)
    null_correlations = []
    null_separations = []
    for _ in range(500):
        weights = projection.lc_to_aotu.copy()
        for side in ("L", "R"):
            rows_for_side = np.flatnonzero(projection.sides == side)
            # Permute each LC10a's whole two-branch output bundle, preserving
            # input totals and the original edge weights within each side.
            columns_for_side = [index[kind, side] for kind in TYPES]
            weights[np.ix_(rows_for_side, columns_for_side)] = (
                projection.lc_to_aotu[np.ix_(rng.permutation(rows_for_side),
                                              columns_for_side)])
        shuffled = field_scores(replace(projection, lc_to_aotu=weights), reference, index)
        null_correlations.append(np.mean([
            shuffled[side][kind]["shape_pearson"] for side in ("L", "R")
            for kind in TYPES
        ]))
        null_separations.append(np.mean([
            shuffled[side]["peak_separation_deg"] for side in ("L", "R")
        ]))
    observed_correlation = float(np.mean([
        intact[side][kind]["shape_pearson"] for side in ("L", "R")
        for kind in TYPES
    ]))
    observed_separation = float(np.mean([
        intact[side]["peak_separation_deg"] for side in ("L", "R")
    ]))
    null_correlations = np.asarray(null_correlations)
    null_separations = np.asarray(null_separations)
    result = {
        "map_sha256": hashlib.sha256(map_bytes).hexdigest(),
        "pursuit_reference_source_commit": manifest["commit"],
        "eye_map_git_blob_sha1": EYE_BLOB_SHA,
        "fafb_medulla_grid_git_blob_sha1": MED_BLOB_SHA,
        "interpretation": "fixed-fly anatomical hypothesis; not measured cell fields or calibrated firing",
        "eye_map_local_affine_leave_one_out_azimuth_abs_error_deg": {
            "median": float(np.median(loo)), "p95": float(np.quantile(loo, 0.95)),
            "max": float(loo.max()),
            "warning": "Same-dataset interpolation error; excludes cross-specimen registration uncertainty",
        },
        "branch_coverage": branch_coverage,
        "old_v2_field": old,
        "registered_v3_field": intact,
        "within_side_whole_bundle_shuffle": {
            "seed": 20260926, "count": len(null_correlations),
            "mean_four_branch_shape_correlation": observed_correlation,
            "null_mean_shape_correlation_median": float(np.median(null_correlations)),
            "null_mean_shape_correlation_p95": float(np.quantile(null_correlations, 0.95)),
            "null_fraction_at_least_observed_shape": float(np.mean(
                null_correlations >= observed_correlation)),
            "mean_bilateral_branch_peak_separation_deg": observed_separation,
            "null_peak_separation_median_deg": float(np.median(null_separations)),
            "null_fraction_at_least_observed_separation": float(np.mean(
                null_separations >= observed_separation)),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registered_v3_field": intact,
                      "branch_coverage": branch_coverage,
                      "shuffle": result["within_side_whole_bundle_shuffle"]}, indent=2))


if __name__ == "__main__":
    main()

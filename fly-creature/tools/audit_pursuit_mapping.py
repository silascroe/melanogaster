"""Audit author v0.9 pathway tables against MaleCNS v1.0 and our adaptation.

Development only: requires the ignored pinned author clone and the official
working annotations. Writes compact metrics, not licensed response curves.
Run from fly-creature with PYTHONPATH=src and the workspace Python environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.feather as feather

from fly_creature.pursuit_activity import ActivityProjection


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def _normalized_shape(values: np.ndarray) -> np.ndarray:
    maximum = float(np.max(np.abs(values)))
    if maximum <= 0:
        raise ValueError("Cannot compare a zero response shape")
    return values / maximum


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path,
                        default=Path("outputs/research/CollieWilson"))
    parser.add_argument("--annotations", type=Path, default=Path(
        "../data/working/male-cns-v1.0/body-annotations-male-cns-v1.0-minconf-0.5.feather"))
    parser.add_argument("--output", type=Path,
                        default=Path("docs/evidence/pursuit_mapping_v1.json"))
    args = parser.parse_args()
    manifest = json.loads(Path("docs/evidence/pursuit_reference_source_v1.json").read_text())
    relative = "Connectomics_Code/AOTU_MaleCNS/data/dn_type_avg_DNa02.csv"
    weighted_relative = "Connectomics_Code/AOTU_MaleCNS/rf/weighted_rf_by_cell.csv"
    modeled_relative = "Modeling_Code/Pursuit_RFs.csv"
    for name in (relative, weighted_relative, modeled_relative):
        actual = hashlib.sha256((args.source_root / name).read_bytes()).hexdigest()
        if actual != manifest["sha256"][name]:
            raise ValueError(f"Pinned source file changed: {name}")
    source = _rows(args.source_root / relative)
    weighted = _rows(args.source_root / weighted_relative)
    modeled = _rows(args.source_root / modeled_relative)
    if len(source) != 16 or len(weighted) != 465 or len(modeled) != 361:
        raise ValueError("Unexpected pinned source table dimensions")
    annotations = feather.read_table(
        args.annotations, columns=["bodyId", "type", "instance", "status", "somaSide"],
        memory_map=True,
    )
    source_ids = {int(row["partner"]): row for row in source}
    v1 = {int(row["bodyId"]): row for row in annotations.to_pylist()
          if row["bodyId"] is not None and int(row["bodyId"]) in source_ids}
    identity_rows = []
    for body_id, older in source_ids.items():
        current = v1.get(body_id)
        identity_rows.append({
            "source_type": older["type"], "source_partner_id": body_id,
            "v1_type": None if current is None else current["type"],
            "v1_instance": None if current is None else current["instance"],
            "v1_side": None if current is None else current["somaSide"],
            "v1_status": None if current is None else current["status"],
            "same_type_traced": bool(current and current["type"] == older["type"]
                                     and current["status"] == "Traced"),
        })
    projection = ActivityProjection.from_packaged_data()
    grid = np.arange(-180, 181, dtype=float)
    predicted = projection.fixed_fly(grid)
    removed = projection.fixed_fly(grid, bridge="removed")
    swapped = projection.fixed_fly(grid, bridge="side_swapped")
    source_by_type = {row["type"]: row for row in source}
    sampled = []
    for cell_type in ("AOTU019", "AOTU025"):
        right_index = next(i for i, (kind, side) in enumerate(zip(
            projection.aotu_types, projection.aotu_sides))
                           if kind == cell_type and side == "R")
        left_index = next(i for i, (kind, side) in enumerate(zip(
            projection.aotu_types, projection.aotu_sides))
                          if kind == cell_type and side == "L")
        adaptation = predicted["aotu_contact_drive"][:, right_index]
        source_values = np.array([float(row[cell_type]) for row in modeled])
        visible = (grid >= 0) & (grid <= 165)
        a, b = _normalized_shape(adaptation[visible]), _normalized_shape(source_values[visible])
        contacts_by_side = projection.lc_to_aotu[:, [left_index, right_index]].sum(axis=0)
        output_by_side = projection.aotu_to_dn[[left_index, right_index], :].sum(axis=1)
        sampled.append({
            "type": cell_type,
            "source_v09_mean_lc10a_contacts": float(source_by_type[cell_type]["sum_LC10a"]),
            "v1_lc10a_contacts_left_right": [int(value) for value in contacts_by_side],
            "source_v09_mean_dna02_contacts": float(source_by_type[cell_type]["DNa02"]),
            "v1_signed_dna02_contacts_left_right": [int(value) for value in output_by_side],
            "source_weighted_field_peak_deg": int(grid[np.argmax(source_values)]),
            "v1_hypothesis_contact_drive_peak_deg": int(grid[np.argmax(adaptation)]),
            "right_field_shape_pearson_0_to_165_deg": float(np.corrcoef(a, b)[0, 1]),
            "right_field_shape_mean_absolute_difference_0_to_165_deg": float(np.mean(np.abs(a - b))),
            "source_weighted_field_max": float(source_values.max()),
            "v1_hypothesis_contact_drive_max": float(adaptation.max()),
        })
    weighted_column_names = set(weighted[0]) - {"rPos_deg"}
    model_column_names = set(modeled[0]) - {"rPos_deg"}
    weighted_angles = np.array([float(row["rPos_deg"]) for row in weighted])
    model_angles = np.array([float(row["rPos_deg"]) for row in modeled])
    shared = (model_angles >= weighted_angles[0]) & (model_angles <= weighted_angles[-1])
    interpolation_errors = {}
    for name in sorted(model_column_names):
        matches = [column for column in weighted_column_names
                   if column == name or column.startswith(name + "_")]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous source weighted field for {name}")
        source_values = np.array([float(row[matches[0]]) for row in weighted])
        modeled_values = np.array([float(row[name]) for row in modeled])
        interpolation_errors[name] = float(np.max(np.abs(
            np.interp(model_angles[shared], weighted_angles, source_values)
            - modeled_values[shared])))
    weights = [float(row["DNa02"]) for row in source]
    expected_ratio = {row["type"]: float(row["DNa02"]) / max(weights) for row in source}
    report = {
        "source_commit": manifest["commit"],
        "identity_scope": "16 source partner IDs only; source LC10a body IDs not retained in released heatmap/response tables",
        "source_partners_checked": len(identity_rows),
        "same_id_type_and_traced_in_v1": sum(row["same_type_traced"] for row in identity_rows),
        "source_partner_identity": identity_rows,
        "source_weighting_lineage": {
            "lc10a_to_target": "v0.9 LC10a-to-target counts color the source heatmap before image processing and normalization; not a per-LC10a response table",
            "target_to_dna02": "weighted_rf_by_cell multiplies the image-derived response by source mean DNa02 weight divided by the largest mean DNa02 weight",
            "aotu019_dna02_multiplier": expected_ratio["AOTU019"],
            "aotu025_dna02_multiplier": expected_ratio["AOTU025"],
            "multiply_again_by_v1_edges": "prohibited: would reuse a strength component already present in source fields",
        },
        "weighted_rf_columns": len(weighted_column_names),
        "modeled_rf_columns": len(model_column_names),
        "linear_interpolation_max_error_by_modeled_column_on_shared_range": interpolation_errors,
        "linear_interpolation_max_error_all_columns": max(interpolation_errors.values()),
        "modeled_major_branches": sampled,
        "v1_input": {
            "lc10a_cells": len(projection.body_ids),
            "position_sources": dict(sorted({
                key: sum(row["position_source"] == key for row in json.loads(
                    Path("src/fly_creature/data/lc10a_upstream_hypothesis_v2.json").read_text())["cells"])
                for key in ("upstream column contacts", "skeleton geometry calibrated by upstream columns")
            }.items())),
            "width_deg": 18.0,
            "width_status": "assumed Gaussian response width, not measured",
            "preferred_angle_status": "anatomy-derived ordering with assumed 5-60 degree scale",
        },
        "v1_fixed_fly": {
            "right_25_deg_aotu_contact_drive": {
                f"{kind}_{side}": float(predicted["aotu_contact_drive"][205, i])
                for i, (kind, side) in enumerate(zip(projection.aotu_types, projection.aotu_sides))
            },
            "right_25_deg_dna02_signed_contact_product_left_right": [
                float(value) for value in predicted["dna02_signed_contact_product"][205]
            ],
            "right_25_deg_right_minus_left": float(predicted["dna02_right_minus_left"][205]),
            "right_25_deg_bridge_removed_right_minus_left": float(
                removed["dna02_right_minus_left"][205]),
            "right_25_deg_bridge_side_swapped_right_minus_left": float(
                swapped["dna02_right_minus_left"][205]),
        },
        "interpretation": "The v1 projection uses each selected v1 edge once, but remains an uncalibrated anatomical-input hypothesis; no reference behavioral parity or neural firing claim.",
    }
    if report["same_id_type_and_traced_in_v1"] != 16:
        raise ValueError("Some published partner IDs changed in v1; inspect before use")
    if not predicted["dna02_right_minus_left"][205] > 0:
        raise ValueError("Right object should yield a right-minus-left drive under stated signs")
    if (not np.allclose(removed["dna02_right_minus_left"], 0)
            or not np.allclose(swapped["dna02_right_minus_left"],
                               -predicted["dna02_right_minus_left"])):
        raise ValueError("Bridge intervention did not preserve the selected sign convention")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"partner_id_matches": report["same_id_type_and_traced_in_v1"],
                      "major_branches": sampled,
                      "right_25_deg_readout": report["v1_fixed_fly"]["right_25_deg_right_minus_left"]},
                     indent=2))


if __name__ == "__main__":
    main()

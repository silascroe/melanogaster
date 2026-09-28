"""Derive an LC10a horizontal input map without reading its steering outputs.

The MaleCNS medulla-column annotations and direct upstream contacts locate
visual inputs. Distal LC10a skeleton position fills cells with sparse upstream
coverage. Retinal degrees remain an explicit engineering approximation.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather


MIN_DIRECT_EDGES = 3
FRONTAL_DEG = 5.0
LATERAL_DEG = 60.0
OPTIC_WINDOW_MAX_Y = 20000.0
OPTIC_WINDOW_MAX_Z = 26000.0


def distal_y(path: Path) -> float:
    points = np.loadtxt(path, comments="#")
    if points.ndim != 2 or points.shape[1] != 7:
        raise ValueError(f"Invalid SWC: {path}")
    distal = points[(points[:, 3] < OPTIC_WINDOW_MAX_Y) &
                    (points[:, 4] < OPTIC_WINDOW_MAX_Z)]
    if len(distal) < 100:
        raise ValueError(f"Too few distal SWC points: {path}")
    return float(np.median(distal[:, 3]))


def derive(circuit_path: Path, annotations_path: Path, weights_path: Path,
           skeleton_dir: Path) -> dict:
    circuit_bytes = circuit_path.read_bytes()
    circuit = json.loads(circuit_bytes)
    selected = {int(n["body_id"]): n for n in circuit["neurons"]
                if n["type"] == "LC10a"}
    if len(selected) != 275:
        raise ValueError("Expected the packaged 275 LC10a neurons")

    annotation = feather.read_table(
        annotations_path,
        columns=["bodyId", "instance", "assignedOlHex1", "assignedOlHex2"],
    )
    # This source lookup contains optic-lobe input-side anatomy only. Neither
    # AOTU019/025 nor DNa02 edges are read to build or orient the map.
    sources = {}
    for row in annotation.to_pylist():
        instance = row["instance"] or ""
        if (row["assignedOlHex1"] is not None and
                row["assignedOlHex2"] is not None and
                instance.endswith(("_L", "_R"))):
            sources[int(row["bodyId"])] = (
                instance[-1], float(row["assignedOlHex2"] - row["assignedOlHex1"])
            )

    reader = pa.ipc.RecordBatchFileReader(pa.memory_map(str(weights_path)))
    target_ids = np.asarray(sorted(selected), dtype=np.int64)
    upstream = defaultdict(list)
    for i in range(reader.num_record_batches):
        batch = reader.get_batch(i)
        post = batch.column(1).to_numpy()
        matching = np.isin(post, target_ids)
        if not matching.any():
            continue
        pre = batch.column(0).to_numpy()[matching]
        weight = batch.column(2).to_numpy()[matching]
        for src, dst, synapses in zip(pre, post[matching], weight):
            src, dst, synapses = int(src), int(dst), int(synapses)
            if (synapses > 0 and src in sources and
                    sources[src][0] == selected[dst]["side"]):
                upstream[dst].append((src, synapses))

    digest = hashlib.sha256()
    rows = []
    for body_id, neuron in sorted(selected.items()):
        content = (skeleton_dir / f"{body_id}.swc").read_bytes()
        digest.update(str(body_id).encode("ascii") + b"\0")
        digest.update(hashlib.sha256(content).digest())
        contacts = upstream[body_id]
        total = sum(weight for _, weight in contacts)
        direct_h = (sum(sources[src][1] * weight for src, weight in contacts) / total
                    if total else None)
        rows.append({"body_id": body_id, "side": neuron["side"],
                     "distal_median_y_vox": distal_y(skeleton_dir / f"{body_id}.swc"),
                     "upstream_mapped_edges": len(contacts),
                     "upstream_mapped_synapses": total,
                     "upstream_h": round(direct_h, 5) if direct_h is not None else None})

    diagnostics = {}
    for side in ("L", "R"):
        side_rows = [r for r in rows if r["side"] == side]
        covered = [r for r in side_rows if r["upstream_h"] is not None]
        y = np.asarray([r["distal_median_y_vox"] for r in covered])
        h = np.asarray([r["upstream_h"] for r in covered])
        slope, intercept = np.polyfit(y, h, 1)
        correlation = float(np.corrcoef(y, h)[0, 1])
        if correlation < 0.8:
            raise ValueError(f"Upstream horizontal axis and skeleton axis disagree on {side}")
        for row in side_rows:
            if row["upstream_mapped_edges"] >= MIN_DIRECT_EDGES:
                row["horizontal_position"] = row["upstream_h"]
                row["position_source"] = "upstream column contacts"
            else:
                row["horizontal_position"] = round(
                    slope * row["distal_median_y_vox"] + intercept, 5)
                row["position_source"] = "skeleton geometry calibrated by upstream columns"
        ordered = sorted(side_rows, key=lambda r: (r["horizontal_position"], r["body_id"]))
        for rank, row in enumerate(ordered):
            row["preferred_abs_bearing_deg"] = round(
                FRONTAL_DEG + (LATERAL_DEG - FRONTAL_DEG) * rank / (len(ordered) - 1), 4)
        diagnostics[side] = {
            "cells": len(side_rows), "upstream_covered": len(covered),
            "direct_position_cells": sum(r["position_source"] == "upstream column contacts"
                                         for r in side_rows),
            "upstream_h_vs_skeleton_y_pearson": round(correlation, 4),
            "linear_h_from_y": [round(float(slope), 8), round(float(intercept), 5)],
        }

    return {
        "schema_version": 1,
        "status": "independently oriented anatomical hypothesis, not measured visual fields",
        "sources": {
            "release": "FlyEM Male CNS v1.0",
            "annotations": annotations_path.name,
            "weights": weights_path.name,
            "circuit_sha256": hashlib.sha256(circuit_bytes).hexdigest(),
            "ordered_skeleton_sha256": digest.hexdigest(),
            "column_reference": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12119369/",
        },
        "method": {
            "source": "Weighted direct contacts from annotated medulla-column neurons into LC10a; "
                      "column horizontal coordinate is assignedOlHex2 - assignedOlHex1.",
            "axis_orientation": "The published male optic-lobe eye map puts frontal space at the low "
                                "horizontal end. Upstream h increases with distal skeleton y.",
            "fallback": "Cells with fewer than three mapped incoming column edges use a "
                        "within-side linear h-from-skeleton-y fit to the covered cells.",
            "bearing_scale": "Within-side horizontal rank linearly mapped to 5-60 degrees; "
                             "this degree scale is engineered, not measured.",
            "excluded_information": "No LC10a-to-AOTU019/AOTU025/DNa02 weights or pursuit scores "
                                    "were used for assignment or axis orientation.",
        },
        "diagnostics": diagnostics,
        "cells": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--circuit", type=Path,
                        default=Path("src/fly_creature/data/visual_steering_v1.json"))
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--skeleton-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = derive(args.circuit, args.annotations, args.weights, args.skeleton_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["diagnostics"], indent=2))


if __name__ == "__main__":
    main()

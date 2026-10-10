"""Transfer a published eye map to MaleCNS LC10a upstream columns.

This development-only derivation reads official MaleCNS v1.0 data and Zhao et
al.'s female FAFB/micro-CT eye map. It never reads AOTU outputs, the authors'
pursuit reference, or behavioral scores. The resulting JSON travels with the
standalone creature; the large source files do not.
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
import rdata


EYE_BLOB_SHA = "f3ee4a5aeb5be159de7071952dc52eb20d8b42d6"
MED_BLOB_SHA = "66d5b9f1e9d06d65a77bfa04d305396e3ff21a9f"
MIN_DIRECT_EDGES = 3
NEIGHBORS = 12


def git_blob_sha(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") +
                        b"\0" + content).hexdigest()


def hex_distance_squared(points: np.ndarray, point: np.ndarray) -> np.ndarray:
    """FAFB p/q axes are 120 degrees apart; (1,1) is also a neighbor."""
    delta = points - point
    return delta[:, 0] ** 2 + delta[:, 1] ** 2 - delta[:, 0] * delta[:, 1]


class EyeMap:
    def __init__(self, eye_file: Path, med_file: Path):
        if git_blob_sha(eye_file) != EYE_BLOB_SHA or git_blob_sha(med_file) != MED_BLOB_SHA:
            raise ValueError("Eye-map RData differs from the pinned public source")
        eye = rdata.read_rda(eye_file)
        med = np.asarray(rdata.read_rda(med_file)["med_ixy"])
        med_by_id = {int(row[0]): row[1:].astype(int) for row in med}
        paired = np.asarray(eye["eyemap"])
        self.coords = np.array([med_by_id[int(idx)] for idx in paired[:, 0]])
        vectors = np.asarray(eye["ucl_rot_sm"])
        if len(self.coords) != len(vectors) or len({tuple(c) for c in self.coords}) != len(vectors):
            raise ValueError("Eye-map indices do not uniquely pair medulla columns and vectors")
        # The source's cart2Mercator flips vector y before extracting azimuth.
        self.azimuth = np.degrees(np.arctan2(-vectors[:, 1], vectors[:, 0]))
        self.elevation = np.degrees(np.arcsin(vectors[:, 2]))
        self.index = {tuple(c): i for i, c in enumerate(self.coords)}
        self.levels = np.sort(np.unique(self.coords[:, 0] - self.coords[:, 1] + 1))
        self.level_azimuth = np.array([
            np.median(self.azimuth[self.coords[:, 0] - self.coords[:, 1] + 1 == h])
            for h in self.levels
        ])

    def at(self, coord: tuple[int, int]) -> tuple[float, str, int]:
        """Return azimuth, lookup method and nearest hex-grid distance.

        Absent boundary columns use a local affine estimate. The audit checks
        its leave-one-out error; no AOTU response is involved in the fit.
        """
        if coord in self.index:
            return float(self.azimuth[self.index[coord]]), "exact", 0
        point = np.asarray(coord)
        distances = hex_distance_squared(self.coords, point)
        near = np.argsort(distances)[:NEIGHBORS]
        weights = 1.0 / (distances[near] + 0.1)
        design = np.column_stack((self.coords[near], np.ones(NEIGHBORS)))
        coefficients = np.linalg.lstsq(
            design * np.sqrt(weights[:, None]),
            self.azimuth[near] * np.sqrt(weights), rcond=None,
        )[0]
        angle = float(np.append(point, 1.0) @ coefficients)
        return angle, "local_affine", int(round(np.sqrt(distances[near[0]])))

    def fallback(self, horizontal_position: float) -> float:
        return float(np.interp(horizontal_position, self.levels, self.level_azimuth))


def derive(circuit_path: Path, old_map_path: Path, annotations_path: Path,
           weights_path: Path, eye_file: Path, med_file: Path,
           shift_p: int = 0, shift_q: int = 0) -> dict:
    circuit_bytes = circuit_path.read_bytes()
    old_map_bytes = old_map_path.read_bytes()
    circuit = json.loads(circuit_bytes)
    previous = {int(row["body_id"]): row for row in json.loads(old_map_bytes)["cells"]}
    selected = {int(row["body_id"]): row["side"] for row in circuit["neurons"]
                if row["type"] == "LC10a"}
    if len(selected) != 275 or set(previous) != set(selected):
        raise ValueError("Expected the selected 275 LC10a cells and complete previous map")
    eye = EyeMap(eye_file, med_file)
    annotation = feather.read_table(annotations_path, columns=[
        "bodyId", "type", "instance", "assignedOlHex1", "assignedOlHex2",
    ])
    sources = {}
    male_mi1 = {"L": set(), "R": set()}
    for row in annotation.to_pylist():
        instance = row["instance"] or ""
        h1, h2 = row["assignedOlHex1"], row["assignedOlHex2"]
        if h1 is None or h2 is None or not instance.endswith(("_L", "_R")):
            continue
        if not float(h1).is_integer() or not float(h2).is_integer():
            raise ValueError("Nonintegral MaleCNS column address")
        side = instance[-1]
        # Hoeller/Nern MaleCNS column diagram: hex1 -> q, hex2 -> p,
        # [hex1,hex2]=[18,19] is the centered p/q origin. Zhao et al.'s
        # med_ixy uses the same p/q axis convention centered at the eye.
        coord = (int(h2) - 19, int(h1) - 18)
        sources[int(row["bodyId"])] = (side, coord)
        if row["type"] == "Mi1":
            male_mi1[side].add(coord)
    overlap = {side: len({(p + shift_p, q + shift_q) for p, q in male_mi1[side]}
                         & set(eye.index)) for side in ("L", "R")}
    if min(overlap.values()) < (0.99 if shift_p == shift_q == 0 else 0.95) * len(eye.index):
        raise ValueError("The centered MaleCNS and FAFB column grids fail to overlap")

    reader = pa.ipc.RecordBatchFileReader(pa.memory_map(str(weights_path)))
    selected_ids = np.asarray(sorted(selected), dtype=np.int64)
    upstream = defaultdict(list)
    for batch_index in range(reader.num_record_batches):
        batch = reader.get_batch(batch_index)
        post = batch.column(1).to_numpy()
        matching = np.isin(post, selected_ids)
        if not matching.any():
            continue
        pre = batch.column(0).to_numpy()[matching]
        count = batch.column(2).to_numpy()[matching]
        for src, dst, weight in zip(pre, post[matching], count):
            src, dst, weight = int(src), int(dst), int(weight)
            if weight > 0 and src in sources and sources[src][0] == selected[dst]:
                upstream[dst].append((src, weight))

    rows = []
    method_count = {"L": defaultdict(int), "R": defaultdict(int)}
    eye_cache = {}
    for body_id, side in sorted(selected.items()):
        old = previous[body_id]
        links = upstream[body_id]
        if len(links) != old["upstream_mapped_edges"]:
            raise ValueError(f"Upstream edge count changed for {body_id}")
        if len(links) >= MIN_DIRECT_EDGES:
            positions = []
            counts = []
            extrapolated = 0
            for src, weight in links:
                p, q = sources[src][1]
                coord = (p + shift_p, q + shift_q)
                if coord not in eye_cache:
                    eye_cache[coord] = eye.at(coord)
                angle, method, distance = eye_cache[coord]
                if distance > (2 if shift_p == shift_q == 0 else 3):
                    raise ValueError("A source column lies too far outside the eye map")
                positions.append(angle)
                counts.append(weight)
                if method == "local_affine":
                    extrapolated += weight
            signed_angle = float(np.average(positions, weights=counts))
            spread = float(np.sqrt(np.average(
                (np.asarray(positions) - signed_angle) ** 2, weights=counts)))
            method = "upstream registered columns"
            method_count[side]["direct"] += 1
        else:
            signed_angle = eye.fallback(float(old["horizontal_position"]) +
                                        shift_p - shift_q)
            spread = None
            extrapolated = None
            method = "skeleton horizontal fallback via eye-map median"
            method_count[side]["fallback"] += 1
        row = dict(old)
        row["preferred_eye_bearing_deg"] = round(signed_angle, 4)
        # The existing offline projection imposes a hard hemifield gate. Keep
        # its legacy field explicit; preserve the signed eye angle separately
        # so a later overlap test does not invent it from the clipped value.
        row["preferred_abs_bearing_deg"] = round(float(np.clip(signed_angle, 0, 180)), 4)
        row["angle_source"] = method
        row["angle_spread_deg"] = None if spread is None else round(spread, 4)
        row["eye_map_interpolated_contact_fraction"] = (
            None if extrapolated is None else round(extrapolated / sum(counts), 4))
        rows.append(row)
    return {
        "schema_version": 1,
        "status": ("cross-specimen anatomical eye-map hypothesis; not measured LC10a fields"
                   if shift_p == shift_q == 0 else
                   "registration-shift sensitivity variant; not a selected map"),
        "sources": {
            "male_release": "FlyEM Male CNS v1.0",
            "annotations": annotations_path.name,
            "weights": weights_path.name,
            "circuit_sha256": hashlib.sha256(circuit_bytes).hexdigest(),
            "prior_upstream_map_sha256": hashlib.sha256(old_map_bytes).hexdigest(),
            "eye_map": "https://github.com/reiserlab/eyemap_T4/blob/main/data/eyemap.RData",
            "eye_map_git_blob_sha1": EYE_BLOB_SHA,
            "fafb_medulla_grid": "https://github.com/reiserlab/eyemap_T4/blob/main/data/med_ixy.RData",
            "fafb_medulla_grid_git_blob_sha1": MED_BLOB_SHA,
            "male_grid_axes": "https://github.com/reiserlab/visualpathways/blob/main/docs/column_coord.pdf",
        },
        "method": {
            "registration": "MaleCNS p=assignedOlHex2-19, q=assignedOlHex1-18; matched to centered FAFB p/q without fitting AOTU curves.",
            "shift_p": shift_p,
            "shift_q": shift_q,
            "angle": "Zhao et al. eye vector azimuth atan2(-y,x) in degrees; weighted upstream-column average per LC10a.",
            "boundary": "Unmatched MaleCNS boundary columns use 12-neighbor local affine eye-map interpolation/extrapolation.",
            "fallback": "Fewer than three upstream column edges: previous skeleton-estimated h, converted by median FAFB eye-map azimuth at each h.",
            "excluded_information": "No LC10a-to-AOTU edges, DNa02 edges, author pursuit curves, or behavioral scores used to assign angles.",
        },
        "diagnostics": {
            "eye_map_columns": len(eye.index),
            "male_mi1_grid_cells": {side: len(male_mi1[side]) for side in ("L", "R")},
            "male_mi1_overlap_with_eye_map": overlap,
            "angle_methods": {side: dict(method_count[side]) for side in ("L", "R")},
        },
        "cells": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--circuit", type=Path, default=Path(
        "src/fly_creature/data/visual_steering_v1.json"))
    parser.add_argument("--upstream-map", type=Path, default=Path(
        "src/fly_creature/data/lc10a_upstream_hypothesis_v2.json"))
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--eye-file", type=Path, default=Path(
        "outputs/research/eyemap_T4/eyemap.RData"))
    parser.add_argument("--med-file", type=Path, default=Path(
        "outputs/research/eyemap_T4/med_ixy.RData"))
    parser.add_argument("--output", type=Path, default=Path(
        "src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json"))
    parser.add_argument("--shift-p", type=int, default=0,
                        help="Sensitivity shift in FAFB p columns; nominal registration is zero")
    parser.add_argument("--shift-q", type=int, default=0,
                        help="Sensitivity shift in FAFB q columns; nominal registration is zero")
    args = parser.parse_args()
    result = derive(args.circuit, args.upstream_map, args.annotations,
                    args.weights, args.eye_file, args.med_file,
                    args.shift_p, args.shift_q)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["diagnostics"], indent=2))


if __name__ == "__main__":
    main()

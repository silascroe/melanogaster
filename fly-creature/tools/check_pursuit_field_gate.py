"""Fast fixed-fly check for the specific frontal/lateral field mismatch.

The reference is an older aggregate connectome-derived model, so passing this
check licenses a controlled Step 4 experiment, not a measured LC10a map.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from fly_creature.pursuit_activity import ActivityProjection


GRID = np.arange(0.0, 166.0)
BRANCHES = ("AOTU019", "AOTU025")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=Path(
        "src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json"))
    args = parser.parse_args()
    source = Path("outputs/research/CollieWilson/Modeling_Code/Pursuit_RFs.csv")
    source_manifest = json.loads(Path(
        "docs/evidence/pursuit_reference_source_v1.json").read_text(encoding="utf-8"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_manifest["sha256"][
            "Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("The authors' source table differs from the pinned copy")
    with source.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    reference = {name: np.array([float(row[name]) for row in rows])[180:346]
                 for name in BRANCHES}
    projection = ActivityProjection.from_packaged_data(map_path=args.map)
    index = {(kind, side): i for i, (kind, side) in enumerate(
        zip(projection.aotu_types, projection.aotu_sides))}
    result = {}
    passed = True
    for side in ("L", "R"):
        response = projection.fixed_fly(-GRID if side == "L" else GRID)[
            "aotu_contact_drive"]
        side_result = {}
        for kind in BRANCHES:
            trial = response[:, index[kind, side]]
            target = reference[kind]
            peak = int(GRID[np.argmax(trial)])
            target_peak = int(GRID[np.argmax(target)])
            correlation = float(np.corrcoef(trial, target)[0, 1])
            branch_pass = (abs(peak - target_peak) <= 15 and correlation >= 0.8)
            passed &= branch_pass
            side_result[kind] = {
                "peak_deg": peak, "reference_peak_deg": target_peak,
                "peak_error_deg": peak - target_peak,
                "shape_pearson": correlation, "passes": branch_pass,
            }
        gap = side_result["AOTU025"]["peak_deg"] - side_result["AOTU019"]["peak_deg"]
        side_result["branch_peak_separation_deg"] = gap
        side_result["separation_passes"] = gap >= 30
        passed &= gap >= 30
        result[side] = side_result
    print(json.dumps({"map": str(args.map), "passes": bool(passed),
                      "results": result}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Export display positions for the game's neuron map (data/brain_map_v1.npz).

The map covers every neuron in the packaged brain subsets (v1, v3, v4), so each
sense's brain copy can be drawn on one shared picture. Positions are display
data only; the brain model never reads them.

Where a neuron sits on the map, in order of preference:
1. its cell body (somaLocation in the MaleCNS release);
2. a point on its neurite towards the cell body (tosomaLocation);
3. approximate: the average position of the neurons it connects to, with a
   small fixed jitter. This covers mostly sensory neurons (taste, antenna,
   leg bristles), whose cell bodies lie outside the scanned brain and nerve
   cord. These are flagged so the game can say their position is approximate.

Axes: x = the fly's left-right, y = up from nerve cord to brain, z = depth;
the largest half-extent of the recorded cell bodies is scaled to 1.
Run from fly-creature/: ../.venv/Scripts/python.exe tools/export_brain_map.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pyarrow.feather as feather

CREATURE_DIR = Path(__file__).resolve().parent.parent
DATA = CREATURE_DIR / "src" / "fly_creature" / "data"
OUT = DATA / "brain_map_v1.npz"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
PACKAGES = ("v1", "v3", "v4")
JITTER = 0.012  # display units; keeps approximately placed cells from stacking


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    args = parser.parse_args()

    packages = [np.load(DATA / f"brain_subset_{v}.npz") for v in PACKAGES]
    body_ids = np.unique(np.concatenate([p["body_ids"] for p in packages]))
    n = len(body_ids)

    ann = feather.read_table(args.release / ANNOTATIONS,
                             columns=["bodyId", "somaLocation", "tosomaLocation"]).to_pandas()
    ann = ann.drop_duplicates("bodyId").set_index("bodyId").reindex(body_ids)
    xyz = np.full((n, 3), np.nan)
    source = np.full(n, 2, dtype=np.uint8)  # 0 soma, 1 towards soma, 2 approximate
    for code, column in ((1, "tosomaLocation"), (0, "somaLocation")):
        has = ann[column].notna().to_numpy()
        xyz[has] = np.stack(ann[column][has].to_numpy())
        source[has] = code

    # Undirected partner lists over all packaged connections, in map indices.
    pairs = []
    for p in packages:
        local = np.searchsorted(body_ids, p["body_ids"])
        pairs.append(np.stack([local[p["pre"]], local[p["post"]]], axis=1))
    pairs = np.unique(np.concatenate(pairs), axis=0)
    pairs = np.concatenate([pairs, pairs[:, ::-1]])

    # Approximate cells: average of placed partners; repeat so chains resolve.
    for _ in range(4):
        missing = np.isnan(xyz[:, 0])
        if not missing.any():
            break
        use = missing[pairs[:, 0]] & ~np.isnan(xyz[pairs[:, 1], 0])
        total = np.zeros((n, 3))
        count = np.zeros(n)
        np.add.at(total, pairs[use, 0], xyz[pairs[use, 1]])
        np.add.at(count, pairs[use, 0], 1)
        fill = missing & (count > 0)
        xyz[fill] = total[fill] / count[fill, None]
    still = np.isnan(xyz[:, 0])
    xyz[still] = np.nanmean(xyz[source == 0], axis=0)

    # Display frame: x left-right, y = brain up, z depth; scaled on recorded somata.
    display = np.stack([xyz[:, 0], -xyz[:, 2], xyz[:, 1]], axis=1)
    recorded = display[source == 0]
    lo, hi = recorded.min(0), recorded.max(0)
    centre = (lo + hi) / 2
    scale = 2.0 / (hi - lo).max()
    display = (display - centre) * scale
    rng = np.random.default_rng(0)
    approx = source == 2
    display[approx] += rng.normal(0.0, JITTER, (int(approx.sum()), 3))

    np.savez_compressed(OUT, body_ids=body_ids, xyz=display.astype(np.float32), source=source)
    print(f"{n} neurons: {int((source == 0).sum())} cell bodies, {int((source == 1).sum())} "
          f"towards cell body, {int(approx.sum())} approximate ({int(still.sum())} with no placed "
          f"partner); {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()

"""Export a direct LC4/LPLC2 -> DNp01 circuit from official MaleCNS files.

Development-only tool. The shipped runtime uses its compact JSON and does not
need the full release or pyarrow. No source Feather file is modified.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pyarrow.dataset as ds
import pyarrow.feather as feather


ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
TRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
SOURCE = "https://male-cns.janelia.org/download/"


def export(release_dir: Path, output: Path) -> dict[str, int]:
    annotations = feather.read_table(
        release_dir / ANNOTATIONS,
        columns=["bodyId", "type", "status", "somaSide"],
        memory_map=True,
    )
    chosen = [
        row for row in annotations.to_pylist()
        if row["status"] == "Traced" and row["type"] in ("LC4", "LPLC2", "DNp01")
    ]
    ids = {int(row["bodyId"]) for row in chosen}
    visual_ids = np.asarray(
        [int(row["bodyId"]) for row in chosen if row["type"] in ("LC4", "LPLC2")],
        dtype=np.int64,
    )
    gf_ids = np.asarray(
        [int(row["bodyId"]) for row in chosen if row["type"] == "DNp01"],
        dtype=np.int64,
    )
    if not len(visual_ids) or len(gf_ids) != 2:
        raise ValueError("Expected visual inputs and two traced DNp01 giant fibers")
    nt_table = feather.read_table(
        release_dir / TRANSMITTERS, columns=["body", "predicted_nt"], memory_map=True
    )
    predicted = {
        int(row["body"]): str(row["predicted_nt"])
        for row in nt_table.to_pylist() if int(row["body"]) in ids
    }
    if ids - predicted.keys():
        raise ValueError("A selected neuron has no predicted transmitter")
    neurons = [
        {
            "body_id": int(row["bodyId"]),
            "type": str(row["type"]),
            "side": str(row["somaSide"]),
            "predicted_nt": predicted[int(row["bodyId"])],
        }
        for row in chosen
    ]
    neurons.sort(key=lambda row: row["body_id"])
    connections: list[dict[str, int]] = []
    for batch in ds.dataset(release_dir / WEIGHTS, format="ipc").scanner(
        columns=["body_pre", "body_post", "weight"], batch_size=1_048_576
    ).to_batches():
        pre = batch.column("body_pre").to_numpy(zero_copy_only=False)
        post = batch.column("body_post").to_numpy(zero_copy_only=False)
        weight = batch.column("weight").to_numpy(zero_copy_only=False)
        keep = np.isin(pre, visual_ids) & np.isin(post, gf_ids)
        connections.extend(
            {"pre": int(a), "post": int(b), "synapse_count": int(w)}
            for a, b, w in zip(pre[keep], post[keep], weight[keep])
        )
    connections.sort(key=lambda edge: (edge["pre"], edge["post"]))
    if not connections:
        raise ValueError("No direct visual-to-giant-fiber connections found")
    counts = Counter(row["type"] for row in neurons)
    payload = {
        "schema_version": 1,
        "provenance": {
            "dataset": "FlyEM Male CNS v1.0",
            "source_url": SOURCE,
            "license": "CC-BY",
            "selection": "Traced LC4, LPLC2, and DNp01 bodies; direct LC4/LPLC2 to DNp01 weighted edges only",
            "source_files": [ANNOTATIONS, TRANSMITTERS, WEIGHTS],
            "predicted_transmitter_note": "Predictions are annotations, not measured synaptic signs",
        },
        "summary": {
            "neurons": len(neurons),
            "connections": len(connections),
            "types": dict(sorted(counts.items())),
        },
        "neurons": neurons,
        "connections": connections,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {"neurons": len(neurons), "connections": len(connections)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.release_dir, args.output)))


if __name__ == "__main__":
    main()

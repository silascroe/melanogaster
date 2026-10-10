"""Read-only MaleCNS wiring probe for a possible visual walking-turn circuit.

This is a development diagnostic. It does not change the shipped looming
circuit, simulate vision, or command a turn. Pass a release directory explicitly.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
import pyarrow.dataset as ds
import pyarrow.feather as feather


ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
TRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
TYPES = ("LC10a", "AOTU019", "AOTU025", "DNa02")
BRIDGES = {("LC10a", "AOTU019"), ("LC10a", "AOTU025"),
           ("AOTU019", "DNa02"), ("AOTU025", "DNa02")}


def path_scores(neurons: list[dict], edges: list[dict]) -> dict:
    """Score two-edge paths; this is structural arithmetic, not a neural model."""
    by_id = {neuron["body_id"]: neuron for neuron in neurons}
    results = {}
    for stimulus_side in ("L", "R"):
        aotu_input: dict[int, int] = defaultdict(int)
        for edge in edges:
            if edge["pre_type"] == "LC10a" and edge["pre_side"] == stimulus_side:
                aotu_input[edge["post"]] += edge["synapse_count"]

        condition_scores = {}
        for condition in ("intact", "bridge_removed", "bridge_side_swapped"):
            output = {"L": 0, "R": 0}
            if condition != "bridge_removed":
                for edge in edges:
                    if edge["post_type"] != "DNa02":
                        continue
                    transmitter = (by_id[edge["pre"]].get("consensus_nt")
                                   or by_id[edge["pre"]].get("predicted_nt"))
                    if transmitter not in ("acetylcholine", "gaba"):
                        raise ValueError(f"Unknown AOTU transmitter: {transmitter!r}")
                    sign = 1 if transmitter == "acetylcholine" else -1
                    target_side = edge["post_side"]
                    if condition == "bridge_side_swapped":
                        target_side = "R" if target_side == "L" else "L"
                    output[target_side] += (aotu_input[edge["pre"]]
                                            * edge["synapse_count"] * sign)
            condition_scores[condition] = {
                "DNa02_L": output["L"],
                "DNa02_R": output["R"],
                "left_minus_right": output["L"] - output["R"],
            }
        results[f"LC10a_{stimulus_side}"] = condition_scores
    return {
        "definition": "Each stimulated-side LC10a supplies one abstract unit. "
                      "For each two-edge path, multiply its two synapse counts "
                      "and the AOTU transmitter sign (ACh +1, GABA -1), then "
                      "sum by DNa02 side. No currents, spikes, timing, receptors, "
                      "sensory tuning, or motor commands are modeled.",
        "controls": {
            "bridge_removed": "Set all selected AOTU-to-DNa02 edges to zero.",
            "bridge_side_swapped": "Retain every selected edge weight and sign, "
                                   "but send each AOTU-to-DNa02 edge to the "
                                   "opposite DNa02 side.",
        },
        "conditions": results,
    }


def probe(release_dir: Path) -> dict:
    annotations = feather.read_table(
        release_dir / ANNOTATIONS,
        columns=["bodyId", "type", "instance", "status", "somaSide"],
        memory_map=True,
    )
    neurons = [
        {"body_id": int(row["bodyId"]), "type": row["type"],
         "instance": row["instance"], "side": row["somaSide"]}
        for row in annotations.to_pylist()
        if row["status"] == "Traced" and row["type"] in TYPES
    ]
    by_id = {row["body_id"]: row for row in neurons}
    counts = Counter(row["type"] for row in neurons)
    if any(counts[cell_type] == 0 for cell_type in TYPES):
        raise ValueError(f"Missing traced candidate type: {dict(counts)}")
    nt_table = feather.read_table(
        release_dir / TRANSMITTERS,
        columns=["body", "predicted_nt", "consensus_nt", "predicted_nt_confidence"],
        memory_map=True,
    )
    for row in nt_table.to_pylist():
        neuron = by_id.get(int(row["body"]))
        if neuron is not None:
            neuron["predicted_nt"] = row["predicted_nt"]
            neuron["consensus_nt"] = row["consensus_nt"]
            neuron["nt_confidence"] = row["predicted_nt_confidence"]

    pre_ids = np.asarray(sorted(row["body_id"] for row in neurons
                                if row["type"] in ("LC10a", "AOTU019", "AOTU025")),
                         dtype=np.int64)
    post_ids = np.asarray(sorted(row["body_id"] for row in neurons
                                 if row["type"] in ("AOTU019", "AOTU025", "DNa02")),
                          dtype=np.int64)
    edges = []
    for batch in ds.dataset(release_dir / WEIGHTS, format="ipc").scanner(
        columns=["body_pre", "body_post", "weight"], batch_size=1_048_576
    ).to_batches():
        pre = batch.column("body_pre").to_numpy(zero_copy_only=False)
        post = batch.column("body_post").to_numpy(zero_copy_only=False)
        weight = batch.column("weight").to_numpy(zero_copy_only=False)
        keep = np.isin(pre, pre_ids) & np.isin(post, post_ids)
        for a, b, w in zip(pre[keep], post[keep], weight[keep]):
            source, target = by_id[int(a)], by_id[int(b)]
            if (source["type"], target["type"]) not in BRIDGES:
                continue
            edges.append({"pre": int(a), "post": int(b), "synapse_count": int(w),
                          "pre_type": source["type"], "post_type": target["type"],
                          "pre_side": source["side"], "post_side": target["side"]})
    edges.sort(key=lambda edge: (edge["pre_type"], edge["post_type"],
                                 edge["pre_side"], edge["post_side"],
                                 edge["pre"], edge["post"]))
    aggregate: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"edges": 0, "synapses": 0}
    )
    for edge in edges:
        key = (edge["pre_type"], edge["post_type"], edge["pre_side"], edge["post_side"])
        aggregate[key]["edges"] += 1
        aggregate[key]["synapses"] += edge["synapse_count"]
    return {
        "dataset": "FlyEM Male CNS v1.0",
        "source_url": "https://male-cns.janelia.org/download/",
        "selection": "Traced LC10a, AOTU019, AOTU025, DNa02; only named two-hop bridges",
        "counts": dict(sorted(counts.items())),
        "neurons": sorted(neurons, key=lambda row: row["body_id"]),
        "edge_count": len(edges),
        "edge_aggregate": [
            {"pre_type": a, "post_type": b, "pre_side": c, "post_side": d, **value}
            for (a, b, c, d), value in sorted(aggregate.items())
        ],
        "edges": edges,
        "structural_path_probe": path_scores(neurons, edges),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--circuit-output", type=Path,
                        help="Optional compact standalone creature circuit JSON")
    args = parser.parse_args()
    payload = probe(args.release_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.circuit_output is not None:
        compact = {
            "schema_version": 1,
            "provenance": {
                "release": payload["dataset"],
                "source_url": payload["source_url"],
                "selection": payload["selection"],
                "weight_meaning": "Recorded synapse counts, not currents",
                "transmitter_sign": "Model convention: ACh positive, GABA negative",
            },
            "neurons": [
                {"body_id": row["body_id"], "type": row["type"],
                 "side": row["side"],
                 "predicted_nt": row.get("consensus_nt") or row.get("predicted_nt")}
                for row in payload["neurons"]
            ],
            "connections": [
                {"pre": row["pre"], "post": row["post"],
                 "synapse_count": row["synapse_count"]}
                for row in payload["edges"]
            ],
        }
        args.circuit_output.parent.mkdir(parents=True, exist_ok=True)
        args.circuit_output.write_text(json.dumps(compact, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps({"counts": payload["counts"], "edge_count": payload["edge_count"],
                      "edge_aggregate": payload["edge_aggregate"],
                      "structural_path_probe": payload["structural_path_probe"]}, indent=2))


if __name__ == "__main__":
    main()

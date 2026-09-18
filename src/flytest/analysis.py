"""Dataset inspection and small traced-neighborhood extraction."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.compute as pc

from .data import (
    ANNOTATION_COLUMNS,
    NEUROTRANSMITTER_COLUMNS,
    MaleCNSPaths,
    _membership_mask,
    annotation_records,
    body_ids_for_type,
    eligible_body_ids,
    feather_schema_summary,
    iter_weight_batches,
    load_annotations,
    load_neurotransmitters,
    neurotransmitter_records,
    value_counts,
    weight_statistics,
)


DEFAULT_SIGN_MAP = {
    "acetylcholine": 1.0,
    "gaba": -1.0,
    "glutamate": -1.0,
    "histamine": -1.0,
    "dopamine": 0.0,
    "octopamine": 0.0,
    "serotonin": 0.0,
    "tyramine": 0.0,
    "unclear": 0.0,
}


@dataclass(frozen=True)
class NodeRecord:
    body_id: int
    type: str | None
    instance: str | None
    status: str | None
    superclass: str | None
    class_label: str | None
    soma_side: str | None
    consensus_nt: str | None
    predicted_nt: str | None
    nt_confidence: float | None
    fast_sign: float
    is_seed: bool

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["class"] = result.pop("class_label")
        return result


@dataclass(frozen=True)
class EdgeRecord:
    body_pre: int
    body_post: int
    weight: int
    transmitter_pre: str | None
    sign: float
    signed_weight: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalNetwork:
    nodes: tuple[NodeRecord, ...]
    edges: tuple[EdgeRecord, ...]
    seed_ids: tuple[int, ...]
    selection: dict[str, Any]


@dataclass(frozen=True)
class PathwaySelection:
    """A deterministic three-role pathway and its induced local graph."""

    nodes: tuple[NodeRecord, ...]
    edges: tuple[EdgeRecord, ...]
    source_id: int
    intermediate_id: int
    target_id: int
    path_edge_keys: tuple[tuple[int, int, int], ...]
    selection: dict[str, Any]


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _label_for_nt(record: dict[str, Any] | None) -> str | None:
    if not record:
        return None
    return _clean_string(record.get("consensus_nt") or record.get("predicted_nt"))


def transmitter_sign(
    label: str | None,
    *,
    sign_map: dict[str, float] | None = None,
    unknown_sign: float = 0.0,
) -> float:
    """Map a predicted transmitter to a configurable fast-current sign."""

    if label is None:
        return float(unknown_sign)
    mapping = sign_map or DEFAULT_SIGN_MAP
    return float(mapping.get(label.strip().lower(), unknown_sign))


def _eligible_edge_mask(
    pre: np.ndarray,
    post: np.ndarray,
    weight: np.ndarray,
    eligible: np.ndarray,
    selected: np.ndarray | None = None,
    min_weight: int = 1,
) -> np.ndarray:
    mask = _membership_mask(pre, eligible) & _membership_mask(post, eligible) & (weight >= min_weight)
    if selected is not None:
        mask &= np.isin(pre, selected) & np.isin(post, selected)
    return mask


def select_local_network(
    paths: MaleCNSPaths,
    seed_ids: list[int] | tuple[int, ...],
    *,
    neighbor_limit: int = 64,
    min_weight: int = 3,
    traced_only: bool = True,
    max_edges: int | None = None,
    sign_map: dict[str, float] | None = None,
    unknown_sign: float = 0.0,
) -> LocalNetwork:
    """Select strongest traced neighbors and return their induced directed graph.

    The large weight table is scanned twice: once to rank neighbors incident to
    the seed IDs, and once to collect edges among the selected node set. This
    keeps the local artifact small while leaving the source graph untouched.
    """

    if neighbor_limit < 0:
        raise ValueError("neighbor_limit must be non-negative")
    if min_weight < 1:
        raise ValueError("min_weight must be at least 1")
    seeds = tuple(sorted({int(body_id) for body_id in seed_ids}))
    if not seeds:
        raise ValueError("At least one seed body ID is required")

    eligible = eligible_body_ids(paths, traced_only=traced_only)
    eligible_set = set(int(body_id) for body_id in eligible.tolist())
    missing = [body_id for body_id in seeds if body_id not in eligible_set]
    if missing:
        policy = "Traced" if traced_only else "annotation"
        raise ValueError(f"Seed body ID(s) not in the {policy} population: {missing}")

    seed_array = np.asarray(seeds, dtype=np.int64)
    scores: defaultdict[int, int] = defaultdict(int)
    counts: defaultdict[int, int] = defaultdict(int)

    for batch in iter_weight_batches(paths):
        pre = np.asarray(batch.column("body_pre"))
        post = np.asarray(batch.column("body_post"))
        weight = np.asarray(batch.column("weight"))
        mask = _eligible_edge_mask(pre, post, weight, eligible, min_weight=min_weight)
        mask &= np.isin(pre, seed_array) | np.isin(post, seed_array)
        if not mask.any():
            continue
        for pre_id, post_id, edge_weight in zip(pre[mask].tolist(), post[mask].tolist(), weight[mask].tolist()):
            pre_id = int(pre_id)
            post_id = int(post_id)
            edge_weight = int(edge_weight)
            if pre_id not in seeds and post_id in seeds:
                scores[pre_id] += edge_weight
                counts[pre_id] += 1
            elif post_id not in seeds and pre_id in seeds:
                scores[post_id] += edge_weight
                counts[post_id] += 1

    ranked_neighbors = sorted(scores, key=lambda body_id: (-scores[body_id], -counts[body_id], body_id))
    selected_neighbors = ranked_neighbors[:neighbor_limit]
    selected_ids = tuple(sorted(set(seeds).union(selected_neighbors)))
    selected_array = np.asarray(selected_ids, dtype=np.int64)

    edge_tuples: list[tuple[int, int, int]] = []
    for batch in iter_weight_batches(paths):
        pre = np.asarray(batch.column("body_pre"))
        post = np.asarray(batch.column("body_post"))
        weight = np.asarray(batch.column("weight"))
        mask = _eligible_edge_mask(pre, post, weight, eligible, selected=selected_array, min_weight=min_weight)
        if mask.any():
            edge_tuples.extend(
                (int(pre_id), int(post_id), int(edge_weight))
                for pre_id, post_id, edge_weight in zip(pre[mask].tolist(), post[mask].tolist(), weight[mask].tolist())
            )

    if max_edges is not None and max_edges >= 0 and len(edge_tuples) > max_edges:
        edge_tuples = sorted(edge_tuples, key=lambda edge: (-edge[2], edge[0], edge[1]))[:max_edges]
    else:
        edge_tuples.sort(key=lambda edge: (edge[0], edge[1], -edge[2]))

    annotations = annotation_records(paths, selected_ids)
    neurotransmitters = neurotransmitter_records(paths, selected_ids)
    nodes: list[NodeRecord] = []
    for body_id in selected_ids:
        annotation = annotations.get(body_id, {})
        nt_record = neurotransmitters.get(body_id, {})
        consensus_nt = _clean_string(nt_record.get("consensus_nt"))
        predicted_nt = _clean_string(nt_record.get("predicted_nt"))
        label = consensus_nt or predicted_nt
        confidence = nt_record.get("predicted_nt_confidence")
        nodes.append(
            NodeRecord(
                body_id=body_id,
                type=_clean_string(annotation.get("type")),
                instance=_clean_string(annotation.get("instance")),
                status=_clean_string(annotation.get("status")),
                superclass=_clean_string(annotation.get("superclass")),
                class_label=_clean_string(annotation.get("class")),
                soma_side=_clean_string(annotation.get("somaSide")),
                consensus_nt=consensus_nt,
                predicted_nt=predicted_nt,
                nt_confidence=float(confidence) if confidence is not None else None,
                fast_sign=transmitter_sign(label, sign_map=sign_map, unknown_sign=unknown_sign),
                is_seed=body_id in seeds,
            )
        )

    node_by_id = {node.body_id: node for node in nodes}
    edges = tuple(
        EdgeRecord(
            body_pre=pre,
            body_post=post,
            weight=weight,
            transmitter_pre=_label_for_nt(neurotransmitters.get(pre)),
            sign=node_by_id[pre].fast_sign,
            signed_weight=float(weight) * node_by_id[pre].fast_sign,
        )
        for pre, post, weight in edge_tuples
    )

    selection = {
        "traced_only": traced_only,
        "eligible_nodes": int(len(eligible)),
        "neighbor_limit": neighbor_limit,
        "min_weight": min_weight,
        "max_edges": max_edges,
        "ranked_neighbor_count": len(ranked_neighbors),
        "selected_neighbors": [
            {"body_id": body_id, "incident_weight": scores[body_id], "incident_edges": counts[body_id]}
            for body_id in selected_neighbors
        ],
    }
    return LocalNetwork(nodes=tuple(nodes), edges=edges, seed_ids=seeds, selection=selection)


def select_native_pathway(
    paths: MaleCNSPaths,
    *,
    source_superclass: str = "vnc_sensory",
    intermediate_superclass: str = "vnc_intrinsic",
    target_superclass: str = "descending_neuron",
    min_weight: int = 3,
    traced_only: bool = True,
    sign_map: dict[str, float] | None = None,
    unknown_sign: float = 0.0,
) -> PathwaySelection:
    """Select the strongest native-positive three-role pathway.

    The large weight table is streamed twice. The first pass ranks candidate
    source -> intermediate -> target paths using only traced annotations,
    superclass labels, weight, and the existing transmitter sign convention.
    The second pass keeps every induced edge among the selected three nodes so
    reverse or inhibitory edges are not silently discarded.
    """

    if min_weight < 1:
        raise ValueError("min_weight must be at least 1")

    annotation_map = annotation_records(paths)
    if traced_only:
        eligible = {
            body_id
            for body_id, record in annotation_map.items()
            if record.get("status") == "Traced"
        }
    else:
        eligible = set(annotation_map)
    category_by_id = {
        body_id: annotation_map[body_id].get("superclass")
        for body_id in eligible
    }
    neurotransmitters = neurotransmitter_records(paths, sorted(eligible))
    sign_by_id = {
        body_id: transmitter_sign(
            _label_for_nt(neurotransmitters.get(body_id)),
            sign_map=sign_map,
            unknown_sign=unknown_sign,
        )
        for body_id in eligible
    }

    best_incoming: dict[int, tuple[int, int, int]] = {}
    best_outgoing: dict[int, tuple[int, int, int]] = {}

    def keep_stronger(
        current: tuple[int, int, int] | None,
        candidate: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        if current is None:
            return candidate
        current_key = (current[0], -current[1], -current[2])
        candidate_key = (candidate[0], -candidate[1], -candidate[2])
        return candidate if candidate_key > current_key else current

    for batch in iter_weight_batches(paths):
        pre = np.asarray(batch.column("body_pre"))
        post = np.asarray(batch.column("body_post"))
        weight = np.asarray(batch.column("weight"))
        mask = weight >= min_weight
        if not mask.any():
            continue
        for pre_id, post_id, edge_weight in zip(
            pre[mask].tolist(), post[mask].tolist(), weight[mask].tolist()
        ):
            pre_id = int(pre_id)
            post_id = int(post_id)
            edge_weight = int(edge_weight)
            if pre_id not in eligible or post_id not in eligible:
                continue
            pre_category = category_by_id[pre_id]
            post_category = category_by_id[post_id]
            candidate = (edge_weight, pre_id, post_id)
            if (
                pre_category == source_superclass
                and post_category == intermediate_superclass
                and sign_by_id[pre_id] > 0
            ):
                best_incoming[post_id] = keep_stronger(best_incoming.get(post_id), candidate)
            elif (
                pre_category == intermediate_superclass
                and post_category == target_superclass
                and sign_by_id[pre_id] > 0
            ):
                best_outgoing[pre_id] = keep_stronger(best_outgoing.get(pre_id), candidate)

    candidates: list[dict[str, Any]] = []
    for intermediate_id in sorted(set(best_incoming) & set(best_outgoing)):
        incoming = best_incoming[intermediate_id]
        outgoing = best_outgoing[intermediate_id]
        source_id = incoming[1]
        target_id = outgoing[2]
        candidates.append(
            {
                "source_id": source_id,
                "intermediate_id": intermediate_id,
                "target_id": target_id,
                "source_to_intermediate_weight": incoming[0],
                "intermediate_to_target_weight": outgoing[0],
                "score": incoming[0] * outgoing[0],
                "weakest_edge_weight": min(incoming[0], outgoing[0]),
                "weight_sum": incoming[0] + outgoing[0],
            }
        )
    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            -candidate["weakest_edge_weight"],
            -candidate["weight_sum"],
            candidate["source_id"],
            candidate["intermediate_id"],
            candidate["target_id"],
        )
    )
    if not candidates:
        raise ValueError(
            "No native-positive pathway found for "
            f"{source_superclass} -> {intermediate_superclass} -> {target_superclass}"
        )

    chosen = candidates[0]
    source_id = int(chosen["source_id"])
    intermediate_id = int(chosen["intermediate_id"])
    target_id = int(chosen["target_id"])
    selected_ids = tuple(sorted((source_id, intermediate_id, target_id)))
    selected_array = np.asarray(selected_ids, dtype=np.int64)
    eligible_array = np.asarray(sorted(eligible), dtype=np.int64)

    edge_tuples: list[tuple[int, int, int]] = []
    for batch in iter_weight_batches(paths):
        pre = np.asarray(batch.column("body_pre"))
        post = np.asarray(batch.column("body_post"))
        weight = np.asarray(batch.column("weight"))
        mask = (
            _membership_mask(pre, eligible_array)
            & _membership_mask(post, eligible_array)
            & np.isin(pre, selected_array)
            & np.isin(post, selected_array)
            & (weight >= min_weight)
        )
        if mask.any():
            edge_tuples.extend(
                (int(pre_id), int(post_id), int(edge_weight))
                for pre_id, post_id, edge_weight in zip(
                    pre[mask].tolist(), post[mask].tolist(), weight[mask].tolist()
                )
            )
    edge_tuples.sort(key=lambda edge: (edge[0], edge[1], -edge[2]))

    annotations = annotation_records(paths, selected_ids)
    selected_neurotransmitters = neurotransmitter_records(paths, selected_ids)
    nodes: list[NodeRecord] = []
    for body_id in selected_ids:
        annotation = annotations.get(body_id, {})
        nt_record = selected_neurotransmitters.get(body_id, {})
        consensus_nt = _clean_string(nt_record.get("consensus_nt"))
        predicted_nt = _clean_string(nt_record.get("predicted_nt"))
        label = consensus_nt or predicted_nt
        confidence = nt_record.get("predicted_nt_confidence")
        nodes.append(
            NodeRecord(
                body_id=body_id,
                type=_clean_string(annotation.get("type")),
                instance=_clean_string(annotation.get("instance")),
                status=_clean_string(annotation.get("status")),
                superclass=_clean_string(annotation.get("superclass")),
                class_label=_clean_string(annotation.get("class")),
                soma_side=_clean_string(annotation.get("somaSide")),
                consensus_nt=consensus_nt,
                predicted_nt=predicted_nt,
                nt_confidence=float(confidence) if confidence is not None else None,
                fast_sign=transmitter_sign(label, sign_map=sign_map, unknown_sign=unknown_sign),
                is_seed=body_id == source_id,
            )
        )

    node_by_id = {node.body_id: node for node in nodes}
    edges = tuple(
        EdgeRecord(
            body_pre=pre,
            body_post=post,
            weight=weight,
            transmitter_pre=_label_for_nt(selected_neurotransmitters.get(pre)),
            sign=node_by_id[pre].fast_sign,
            signed_weight=float(weight) * node_by_id[pre].fast_sign,
        )
        for pre, post, weight in edge_tuples
    )
    path_edge_keys = (
        (source_id, intermediate_id, int(chosen["source_to_intermediate_weight"])),
        (intermediate_id, target_id, int(chosen["intermediate_to_target_weight"])),
    )
    selection = {
        "traced_only": traced_only,
        "min_weight": min_weight,
        "source_superclass": source_superclass,
        "intermediate_superclass": intermediate_superclass,
        "target_superclass": target_superclass,
        "candidate_count": len(candidates),
        "ranking": "weight_product, weakest_edge_weight, weight_sum, ascending body IDs",
        "chosen_path": chosen,
        "path_edge_keys": [list(key) for key in path_edge_keys],
        "induced_edge_count": len(edges),
    }
    return PathwaySelection(
        nodes=tuple(nodes),
        edges=edges,
        source_id=source_id,
        intermediate_id=intermediate_id,
        target_id=target_id,
        path_edge_keys=path_edge_keys,
        selection=selection,
    )


def inspect_dataset(paths: MaleCNSPaths) -> dict[str, Any]:
    """Produce a JSON-serializable schema and statistics report."""

    paths.validate()
    annotations = load_annotations(paths)
    nt = load_neurotransmitters(paths)
    return {
        "dataset": "MaleCNS",
        "release": "v1.0",
        "schemas": [
            feather_schema_summary(paths.annotations),
            feather_schema_summary(paths.neurotransmitters),
            feather_schema_summary(paths.weights),
        ],
        "annotations": {
            "rows": int(annotations.num_rows),
            "columns": list(annotations.column_names),
            "status_counts": value_counts(annotations, "status"),
            "type_counts_top": value_counts(annotations, "type", limit=20),
            "superclass_counts_top": value_counts(annotations, "superclass", limit=20),
        },
        "neurotransmitters": {
            "rows": int(nt.num_rows),
            "columns": list(nt.column_names),
            "body_distinct": int(pc.count_distinct(nt["body"]).as_py()),
            "consensus_counts": value_counts(nt, "consensus_nt"),
            "predicted_counts": value_counts(nt, "predicted_nt"),
        },
        "weights": weight_statistics(paths, traced_only=True),
        "notes": [
            "Raw weights are segment-to-segment and include uncurated endpoint IDs.",
            "The filtered graph keeps both endpoints in annotation rows with status == 'Traced'.",
            "Weight is retained as a positive synapse-count magnitude; transmitter sign is applied separately.",
        ],
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a local MaleCNS v1.0 release")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/inspection"))
    args = parser.parse_args()
    report = inspect_dataset(MaleCNSPaths(args.data_dir))
    output_path = args.output / "dataset_report.json"
    _write_json(output_path, report)
    print(json.dumps({"output": str(output_path), "weights": report["weights"]}, indent=2))


if __name__ == "__main__":
    main()

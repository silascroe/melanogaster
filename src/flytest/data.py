"""Read-only accessors for the local MaleCNS Feather release files.

This module owns file formats and streaming. It does not assign biological
signs or run a neural simulation; those decisions live in ``analysis`` and
``simulation`` respectively.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.feather as feather


ANNOTATION_FILENAME = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
NEUROTRANSMITTER_FILENAME = "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS_FILENAME = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"


@dataclass(frozen=True)
class MaleCNSPaths:
    """Paths to the three locally downloaded baseline files."""

    data_dir: Path

    @property
    def annotations(self) -> Path:
        return self.data_dir / ANNOTATION_FILENAME

    @property
    def neurotransmitters(self) -> Path:
        return self.data_dir / NEUROTRANSMITTER_FILENAME

    @property
    def weights(self) -> Path:
        return self.data_dir / WEIGHTS_FILENAME

    def validate(self) -> None:
        missing = [str(path) for path in (self.annotations, self.neurotransmitters, self.weights) if not path.is_file()]
        if missing:
            raise FileNotFoundError("Missing MaleCNS release file(s): " + ", ".join(missing))


ANNOTATION_COLUMNS = (
    "bodyId",
    "type",
    "instance",
    "status",
    "superclass",
    "class",
    "somaSide",
)

NEUROTRANSMITTER_COLUMNS = (
    "body",
    "cell_type",
    "predicted_nt",
    "predicted_nt_confidence",
    "consensus_nt",
    "total_nt_predictions",
)

WEIGHT_COLUMNS = ("body_pre", "body_post", "weight")


def load_annotations(paths: MaleCNSPaths, columns: Sequence[str] | None = None) -> pa.Table:
    """Load the small body-annotation table into an Arrow table."""

    paths.validate()
    return feather.read_table(paths.annotations, columns=columns, memory_map=True)


def load_neurotransmitters(
    paths: MaleCNSPaths,
    body_ids: Sequence[int] | None = None,
    columns: Sequence[str] | None = None,
) -> pa.Table:
    """Load body-level neurotransmitter predictions, optionally filtered by body ID."""

    paths.validate()
    selected_columns = tuple(columns or NEUROTRANSMITTER_COLUMNS)
    table = feather.read_table(paths.neurotransmitters, columns=selected_columns, memory_map=True)
    if body_ids is None:
        return table
    ids = sorted({int(body_id) for body_id in body_ids})
    if not ids:
        return table.slice(0, 0)
    value_set = pa.array(ids, type=pa.int64())
    return table.filter(pc.is_in(table["body"], value_set=value_set))


def iter_weight_batches(
    paths: MaleCNSPaths,
    *,
    columns: Sequence[str] = WEIGHT_COLUMNS,
    batch_size: int = 1_048_576,
) -> Iterator[pa.RecordBatch]:
    """Stream the large weight table without materializing it as one object."""

    paths.validate()
    dataset = ds.dataset(paths.weights, format="ipc")
    scanner = dataset.scanner(columns=list(columns), batch_size=batch_size, use_threads=True)
    yield from scanner.to_batches()


def annotation_records(paths: MaleCNSPaths, body_ids: Sequence[int] | None = None) -> dict[int, dict[str, Any]]:
    """Return compact Python records keyed by annotated body ID."""

    table = load_annotations(paths, columns=ANNOTATION_COLUMNS)
    wanted = None if body_ids is None else {int(body_id) for body_id in body_ids}
    records: dict[int, dict[str, Any]] = {}
    for row in table.to_pylist():
        body_id = int(row.pop("bodyId"))
        if wanted is None or body_id in wanted:
            records[body_id] = row
    return records


def neurotransmitter_records(paths: MaleCNSPaths, body_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
    """Return only the body-level neurotransmitter records needed by a subgraph."""

    table = load_neurotransmitters(paths, body_ids=body_ids, columns=NEUROTRANSMITTER_COLUMNS)
    records: dict[int, dict[str, Any]] = {}
    for row in table.to_pylist():
        body_id = int(row.pop("body"))
        records[body_id] = row
    return records


def body_ids_for_type(paths: MaleCNSPaths, cell_type: str, *, traced_only: bool = True) -> list[int]:
    """Find body IDs with an exact curated ``type`` label."""

    records = annotation_records(paths)
    result = []
    for body_id, row in records.items():
        if row.get("type") != cell_type:
            continue
        if traced_only and row.get("status") != "Traced":
            continue
        result.append(body_id)
    return sorted(result)


def eligible_body_ids(paths: MaleCNSPaths, *, traced_only: bool = True) -> np.ndarray:
    """Return sorted annotation IDs allowed to participate in a graph selection."""

    table = load_annotations(paths, columns=("bodyId", "status"))
    if traced_only:
        table = table.filter(pc.equal(table["status"], pa.scalar("Traced")))
    ids = np.asarray(table["bodyId"].to_numpy(zero_copy_only=False), dtype=np.int64)
    return np.sort(ids)


def _membership_mask(values: np.ndarray, sorted_ids: np.ndarray) -> np.ndarray:
    """Vectorized membership for sorted int64 IDs."""

    if len(sorted_ids) == 0:
        return np.zeros(len(values), dtype=bool)
    positions = np.searchsorted(sorted_ids, values)
    clipped = np.minimum(positions, len(sorted_ids) - 1)
    return (positions < len(sorted_ids)) & (sorted_ids[clipped] == values)


def feather_schema_summary(path: Path) -> dict[str, Any]:
    """Read a Feather schema and row count without loading data columns."""

    table = feather.read_table(path, columns=[], memory_map=True)
    return {
        "path": str(path),
        "rows": int(table.num_rows),
        "columns": [{"name": field.name, "type": str(field.type)} for field in table.schema],
    }


def value_counts(table: pa.Table, column: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """JSON-friendly value counts with a stable null spelling."""

    counts = pc.value_counts(table[column]).to_pylist()
    counts.sort(key=lambda item: (-int(item["counts"]), str(item["values"])))
    if limit is not None:
        counts = counts[:limit]
    return [{"value": item["values"], "count": int(item["counts"])} for item in counts]


def _empty_weight_stats() -> dict[str, Any]:
    return {
        "rows": 0,
        "unique_pre": 0,
        "unique_post": 0,
        "min_weight": None,
        "max_weight": None,
        "mean_weight": None,
        "sum_weight": 0,
    }


def _update_weight_stats(stats: dict[str, Any], pre: np.ndarray, post: np.ndarray, weight: np.ndarray) -> None:
    stats["rows"] += int(len(weight))
    if len(weight) == 0:
        return
    stats["sum_weight"] += int(weight.sum(dtype=np.int64))
    batch_min = int(weight.min())
    batch_max = int(weight.max())
    stats["min_weight"] = batch_min if stats["min_weight"] is None else min(stats["min_weight"], batch_min)
    stats["max_weight"] = batch_max if stats["max_weight"] is None else max(stats["max_weight"], batch_max)


def weight_statistics(paths: MaleCNSPaths, *, traced_only: bool = True) -> dict[str, Any]:
    """Compute raw and optionally traced-only graph statistics in one streamed pass."""

    eligible = eligible_body_ids(paths, traced_only=traced_only)
    raw = _empty_weight_stats()
    filtered = _empty_weight_stats()
    unique_pre: set[int] = set()
    unique_post: set[int] = set()

    for batch in iter_weight_batches(paths):
        pre = np.asarray(batch.column("body_pre"))
        post = np.asarray(batch.column("body_post"))
        weight = np.asarray(batch.column("weight"))
        _update_weight_stats(raw, pre, post, weight)
        if not traced_only:
            mask = np.ones(len(weight), dtype=bool)
        else:
            mask = _membership_mask(pre, eligible) & _membership_mask(post, eligible)
        if mask.any():
            _update_weight_stats(filtered, pre[mask], post[mask], weight[mask])
            unique_pre.update(np.unique(pre[mask]).tolist())
            unique_post.update(np.unique(post[mask]).tolist())

    filtered["unique_pre"] = len(unique_pre)
    filtered["unique_post"] = len(unique_post)
    if filtered["rows"]:
        filtered["mean_weight"] = filtered["sum_weight"] / filtered["rows"]
    if raw["rows"]:
        raw["mean_weight"] = raw["sum_weight"] / raw["rows"]
    return {"raw": raw, "filtered": filtered, "eligible_nodes": int(len(eligible))}

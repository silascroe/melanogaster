"""Load the small, attributed circuit shipped with Fly Creature."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path


@dataclass(frozen=True)
class Neuron:
    body_id: int
    cell_type: str
    side: str
    predicted_nt: str


@dataclass(frozen=True)
class Connection:
    pre: int
    post: int
    synapse_count: int


@dataclass(frozen=True)
class Circuit:
    neurons: tuple[Neuron, ...]
    connections: tuple[Connection, ...]
    provenance: dict[str, object]

    @property
    def ids_by_type(self) -> dict[str, tuple[int, ...]]:
        return {
            cell_type: tuple(n.body_id for n in self.neurons if n.cell_type == cell_type)
            for cell_type in ("LC4", "LPLC2", "DNp01")
        }


def load_circuit(path: Path | None = None) -> Circuit:
    if path is None:
        path = Path(str(files("fly_creature").joinpath("data/loom_escape_v1.json")))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported circuit schema")
    neurons = tuple(
        Neuron(int(row["body_id"]), str(row["type"]), str(row["side"]), str(row["predicted_nt"]))
        for row in payload["neurons"]
    )
    connections = tuple(
        Connection(int(row["pre"]), int(row["post"]), int(row["synapse_count"]))
        for row in payload["connections"]
    )
    ids = {n.body_id for n in neurons}
    if len(ids) != len(neurons):
        raise ValueError("Circuit contains duplicate neuron IDs")
    types = {n.body_id: n.cell_type for n in neurons}
    if not all(cell_type in types.values() for cell_type in ("LC4", "LPLC2", "DNp01")):
        raise ValueError("Circuit is missing an input or giant-fiber type")
    for edge in connections:
        if edge.pre not in ids or edge.post not in ids or edge.synapse_count <= 0:
            raise ValueError("Circuit contains an invalid connection")
        if types[edge.pre] not in ("LC4", "LPLC2") or types[edge.post] != "DNp01":
            raise ValueError("Circuit contains an edge outside the documented direct path")
    return Circuit(neurons, connections, dict(payload["provenance"]))

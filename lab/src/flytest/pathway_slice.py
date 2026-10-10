"""Run a small native-sign MaleCNS pathway slice.

The selector lives in :mod:`flytest.analysis`; this module only orchestrates
the existing simulator and writes readable diagnostic artifacts. It is a
calibration experiment, not a behavioral or FlyDoom simulation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .analysis import EdgeRecord, PathwaySelection, select_native_pathway
from .data import MaleCNSPaths
from .simulation import LIFConfig, SimulationResult, simulate_lif


DEFAULT_COUPLING_VALUES = (0.05, 0.5, 1.5, 3.0, 4.0)


@dataclass(frozen=True)
class PathwaySliceConfig:
    """Fixed LIF parameters shared by every coupling condition."""

    duration_ms: float = 40.0
    dt_ms: float = 1.0
    tau_ms: float = 20.0
    rest_mv: float = -65.0
    threshold_mv: float = -50.0
    reset_mv: float = -65.0
    refractory_ms: float = 2.0
    input_current_mv: float = 80.0
    input_start_ms: float = 5.0
    input_duration_ms: float = 5.0

    def to_lif(self, coupling_mv_per_synapse: float) -> LIFConfig:
        if coupling_mv_per_synapse < 0:
            raise ValueError("coupling_mv_per_synapse cannot be negative")
        return LIFConfig(
            dt_ms=self.dt_ms,
            duration_ms=self.duration_ms,
            tau_ms=self.tau_ms,
            rest_mv=self.rest_mv,
            threshold_mv=self.threshold_mv,
            reset_mv=self.reset_mv,
            refractory_ms=self.refractory_ms,
            mv_per_synapse=float(coupling_mv_per_synapse),
            input_current_mv=self.input_current_mv,
            input_start_ms=self.input_start_ms,
            input_duration_ms=self.input_duration_ms,
        )


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _path_leg_map(selection: PathwaySelection) -> dict[tuple[int, int, int], str]:
    source_key, target_key = selection.path_edge_keys
    return {
        source_key: "source_to_intermediate",
        target_key: "intermediate_to_target",
    }


def _node_rows(selection: PathwaySelection) -> list[dict[str, Any]]:
    roles = {
        selection.source_id: "source",
        selection.intermediate_id: "intermediate",
        selection.target_id: "target",
    }
    return [{**node.as_dict(), "role": roles[node.body_id]} for node in selection.nodes]


def _edge_rows(selection: PathwaySelection) -> list[dict[str, Any]]:
    path_legs = _path_leg_map(selection)
    rows = []
    for edge in selection.edges:
        key = (edge.body_pre, edge.body_post, edge.weight)
        rows.append(
            {
                **edge.as_dict(),
                "is_path_edge": key in path_legs,
                "path_leg": path_legs.get(key, ""),
            }
        )
    return rows


def _first_spike_ms(result: SimulationResult, body_id: int) -> float | None:
    for event in result.spike_events():
        if int(event["body_id"]) == body_id:
            return float(event["time_ms"])
    return None


def _run_row(
    selection: PathwaySelection,
    result: SimulationResult,
    coupling_mv_per_synapse: float,
    config: PathwaySliceConfig,
) -> dict[str, Any]:
    counts = result.spike_counts()
    source_first = _first_spike_ms(result, selection.source_id)
    intermediate_first = _first_spike_ms(result, selection.intermediate_id)
    target_first = _first_spike_ms(result, selection.target_id)

    source_to_intermediate = (
        source_first is not None
        and intermediate_first == source_first + config.dt_ms
    )
    intermediate_to_target = (
        intermediate_first is not None
        and target_first == intermediate_first + config.dt_ms
    )
    return {
        "coupling_mv_per_synapse": coupling_mv_per_synapse,
        "source_spike_count": counts.get(selection.source_id, 0),
        "intermediate_spike_count": counts.get(selection.intermediate_id, 0),
        "target_spike_count": counts.get(selection.target_id, 0),
        "source_first_spike_ms": source_first,
        "intermediate_first_spike_ms": intermediate_first,
        "target_first_spike_ms": target_first,
        "source_to_intermediate_one_step": source_to_intermediate,
        "intermediate_to_target_one_step": intermediate_to_target,
        "complete_path": source_to_intermediate and intermediate_to_target,
        "total_spikes": int(result.spikes.sum()),
    }


def _spike_rows(result: SimulationResult, coupling_mv_per_synapse: float) -> list[dict[str, Any]]:
    return [
        {
            "coupling_mv_per_synapse": coupling_mv_per_synapse,
            **event,
        }
        for event in result.spike_events()
    ]


def _voltage_rows(result: SimulationResult, coupling_mv_per_synapse: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for time_index, time_ms in enumerate(result.times_ms.tolist()):
        for node_index, body_id in enumerate(result.node_ids):
            rows.append(
                {
                    "coupling_mv_per_synapse": coupling_mv_per_synapse,
                    "time_ms": float(time_ms),
                    "body_id": int(body_id),
                    "neuron_index": node_index,
                    "voltage_mv": float(result.voltages_mv[time_index, node_index]),
                }
            )
    return rows


def _edge_contribution_rows(
    selection: PathwaySelection,
    result: SimulationResult,
    *,
    coupling_mv_per_synapse: float,
    config: PathwaySliceConfig,
) -> list[dict[str, Any]]:
    path_legs = _path_leg_map(selection)
    outgoing: dict[int, list[EdgeRecord]] = {}
    for edge in selection.edges:
        outgoing.setdefault(edge.body_pre, []).append(edge)

    rows: list[dict[str, Any]] = []
    for event in result.spike_events():
        body_pre = int(event["body_id"])
        spike_time = float(event["time_ms"])
        for edge in outgoing.get(body_pre, []):
            key = (edge.body_pre, edge.body_post, edge.weight)
            synaptic_current = edge.signed_weight * coupling_mv_per_synapse
            rows.append(
                {
                    "coupling_mv_per_synapse": coupling_mv_per_synapse,
                    "source_spike_time_ms": spike_time,
                    "arrival_time_ms": spike_time + config.dt_ms,
                    "body_pre": edge.body_pre,
                    "body_post": edge.body_post,
                    "weight": edge.weight,
                    "transmitter_pre": edge.transmitter_pre,
                    "sign": edge.sign,
                    "synaptic_current": synaptic_current,
                    "euler_voltage_increment_mv": (config.dt_ms / config.tau_ms) * synaptic_current,
                    "is_path_edge": key in path_legs,
                    "path_leg": path_legs.get(key, ""),
                }
            )
    return rows


def run_pathway_slice(
    paths: MaleCNSPaths,
    *,
    output_dir: Path,
    min_weight: int = 3,
    coupling_values: Iterable[float] = DEFAULT_COUPLING_VALUES,
    config: PathwaySliceConfig | None = None,
) -> dict[str, Any]:
    """Select, simulate, and write a small native-sign pathway slice."""

    slice_config = config or PathwaySliceConfig()
    couplings = tuple(float(value) for value in coupling_values)
    if not couplings:
        raise ValueError("At least one coupling value is required")
    if any(value < 0 for value in couplings):
        raise ValueError("coupling values cannot be negative")

    selection = select_native_pathway(paths, min_weight=min_weight)
    node_ids = [node.body_id for node in selection.nodes]
    edge_pre = [edge.body_pre for edge in selection.edges]
    edge_post = [edge.body_post for edge in selection.edges]
    edge_weights = [edge.weight for edge in selection.edges]
    edge_signs = [edge.sign for edge in selection.edges]

    run_rows: list[dict[str, Any]] = []
    spike_rows: list[dict[str, Any]] = []
    voltage_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    for coupling in couplings:
        result = simulate_lif(
            node_ids,
            edge_pre,
            edge_post,
            edge_weights,
            edge_signs,
            input_nodes=[selection.source_id],
            config=slice_config.to_lif(coupling),
        )
        run_rows.append(_run_row(selection, result, coupling, slice_config))
        spike_rows.extend(_spike_rows(result, coupling))
        voltage_rows.extend(_voltage_rows(result, coupling))
        contribution_rows.extend(
            _edge_contribution_rows(
                selection,
                result,
                coupling_mv_per_synapse=coupling,
                config=slice_config,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    node_rows = _node_rows(selection)
    edge_rows = _edge_rows(selection)
    _write_csv(output_dir / "nodes.csv", node_rows, list(node_rows[0].keys()))
    _write_csv(output_dir / "edges.csv", edge_rows, list(edge_rows[0].keys()))
    _write_csv(
        output_dir / "spikes.csv",
        spike_rows,
        ["coupling_mv_per_synapse", "time_ms", "body_id", "neuron_index"],
    )
    _write_csv(
        output_dir / "voltages.csv",
        voltage_rows,
        ["coupling_mv_per_synapse", "time_ms", "body_id", "neuron_index", "voltage_mv"],
    )
    _write_csv(
        output_dir / "edge_contributions.csv",
        contribution_rows,
        [
            "coupling_mv_per_synapse",
            "source_spike_time_ms",
            "arrival_time_ms",
            "body_pre",
            "body_post",
            "weight",
            "transmitter_pre",
            "sign",
            "synaptic_current",
            "euler_voltage_increment_mv",
            "is_path_edge",
            "path_leg",
        ],
    )
    _write_csv(
        output_dir / "runs.csv",
        run_rows,
        [
            "coupling_mv_per_synapse",
            "source_spike_count",
            "intermediate_spike_count",
            "target_spike_count",
            "source_first_spike_ms",
            "intermediate_first_spike_ms",
            "target_first_spike_ms",
            "source_to_intermediate_one_step",
            "intermediate_to_target_one_step",
            "complete_path",
            "total_spikes",
        ],
    )

    summary = {
        "experiment": "native-sign data-driven pathway slice",
        "data_dir": str(paths.data_dir),
        "node_count": len(selection.nodes),
        "edge_count": len(selection.edges),
        "path": {
            "source_id": selection.source_id,
            "intermediate_id": selection.intermediate_id,
            "target_id": selection.target_id,
            "path_edge_keys": [list(key) for key in selection.path_edge_keys],
        },
        "selection": selection.selection,
        "fixed_parameters": asdict(slice_config),
        "coupling_values_mv_per_synapse": list(couplings),
        "runs": run_rows,
        "notes": [
            "The selector uses traced annotations and native positive signs on the first two path legs.",
            "Every induced edge among the selected nodes is retained, including reverse or inhibitory edges.",
            "Coupling values are calibration probes; they are not biological parameter estimates.",
            "This experiment does not model behavior or FlyDoom inputs and outputs.",
        ],
        "outputs": {
            "nodes": str(output_dir / "nodes.csv"),
            "edges": str(output_dir / "edges.csv"),
            "spikes": str(output_dir / "spikes.csv"),
            "voltages": str(output_dir / "voltages.csv"),
            "edge_contributions": str(output_dir / "edge_contributions.csv"),
            "runs": str(output_dir / "runs.csv"),
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a native-sign MaleCNS pathway slice")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/pathway-slice"))
    parser.add_argument("--min-weight", type=int, default=3)
    parser.add_argument("--duration-ms", type=float, default=40.0)
    parser.add_argument(
        "--coupling",
        action="append",
        type=float,
        help="Coupling value; repeat to override the default five-value sweep",
    )
    args = parser.parse_args()
    config = PathwaySliceConfig(duration_ms=args.duration_ms)
    summary = run_pathway_slice(
        MaleCNSPaths(args.data_dir),
        output_dir=args.output,
        min_weight=args.min_weight,
        coupling_values=args.coupling or DEFAULT_COUPLING_VALUES,
        config=config,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

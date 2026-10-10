"""Compare legacy and exponentially decaying synaptic-current dynamics."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .simulation import LIFConfig, SimulationResult, simulate_lif


DEFAULT_GAIN_VALUES = (1.0, 3.0, 6.0, 12.0)
DEFAULT_TAU_VALUES: tuple[float | None, ...] = (None, 5.0)
DEFAULT_MV_PER_SYNAPSE = 0.05


@dataclass(frozen=True)
class DiagnosticGraph:
    """A small derived graph and the nodes used for its impulse response."""

    name: str
    node_ids: tuple[int, ...]
    edges: tuple[dict[str, Any], ...]
    source_id: int
    target_id: int
    intermediate_id: int | None = None


@dataclass(frozen=True)
class SynapticDynamicsConfig:
    """Fixed parameters shared by every gain/decay condition."""

    mv_per_synapse: float = DEFAULT_MV_PER_SYNAPSE
    dt_ms: float = 1.0
    duration_ms: float = 40.0
    tau_ms: float = 20.0
    rest_mv: float = -65.0
    threshold_mv: float = -50.0
    reset_mv: float = -65.0
    refractory_ms: float = 2.0
    input_current_mv: float = 80.0
    input_start_ms: float = 5.0
    input_duration_ms: float = 5.0

    def to_lif(self, synaptic_gain: float, synaptic_tau_ms: float | None) -> LIFConfig:
        return LIFConfig(
            dt_ms=self.dt_ms,
            duration_ms=self.duration_ms,
            tau_ms=self.tau_ms,
            rest_mv=self.rest_mv,
            threshold_mv=self.threshold_mv,
            reset_mv=self.reset_mv,
            refractory_ms=self.refractory_ms,
            mv_per_synapse=self.mv_per_synapse,
            synaptic_gain=float(synaptic_gain),
            synaptic_tau_ms=synaptic_tau_ms,
            input_current_mv=self.input_current_mv,
            input_start_ms=self.input_start_ms,
            input_duration_ms=self.input_duration_ms,
        )


def load_derived_graph(
    directory: Path,
    *,
    name: str,
    source_id: int,
    target_id: int,
    intermediate_id: int | None = None,
    node_filename: str = "selected_neurons.csv",
    edge_filename: str = "selected_edges.csv",
) -> DiagnosticGraph:
    """Load a small graph artifact without reading the raw connectome."""

    node_path = directory / node_filename
    edge_path = directory / edge_filename
    if not node_path.is_file() or not edge_path.is_file():
        raise FileNotFoundError(f"Expected derived graph CSVs under {directory}")
    with node_path.open(newline="", encoding="utf-8") as handle:
        node_ids = tuple(int(row["body_id"]) for row in csv.DictReader(handle))
    node_set = set(node_ids)
    requested = [source_id, target_id]
    if intermediate_id is not None:
        requested.append(intermediate_id)
    missing = [body_id for body_id in requested if body_id not in node_set]
    if missing:
        raise ValueError(f"Graph {name!r} is missing required node(s): {missing}")

    with edge_path.open(newline="", encoding="utf-8") as handle:
        edges = tuple(
            {
                "body_pre": int(row["body_pre"]),
                "body_post": int(row["body_post"]),
                "weight": float(row["weight"]),
                "sign": float(row["sign"]),
                "transmitter_pre": row.get("transmitter_pre") or None,
            }
            for row in csv.DictReader(handle)
        )
    return DiagnosticGraph(
        name=name,
        node_ids=node_ids,
        edges=edges,
        source_id=source_id,
        target_id=target_id,
        intermediate_id=intermediate_id,
    )


def _first_spike_ms(result: SimulationResult, body_id: int) -> float | None:
    for event in result.spike_events():
        if int(event["body_id"]) == body_id:
            return float(event["time_ms"])
    return None


def _tau_label(synaptic_tau_ms: float | None) -> str:
    return "legacy_one_step" if synaptic_tau_ms is None else "exponential"


def _trace_rows(
    graph: DiagnosticGraph,
    result: SimulationResult,
    *,
    synaptic_gain: float,
    synaptic_tau_ms: float | None,
    config: SynapticDynamicsConfig,
) -> list[dict[str, Any]]:
    currents = result.synaptic_currents
    if currents is None:
        currents = np.zeros_like(result.voltages_mv)
    rows: list[dict[str, Any]] = []
    for time_index, time_ms in enumerate(result.times_ms.tolist()):
        for node_index, body_id in enumerate(result.node_ids):
            rows.append(
                {
                    "topology": graph.name,
                    "synaptic_gain": synaptic_gain,
                    "synaptic_tau_ms": synaptic_tau_ms,
                    "synaptic_mode": _tau_label(synaptic_tau_ms),
                    "time_ms": float(time_ms),
                    "body_id": int(body_id),
                    "neuron_index": node_index,
                    "voltage_mv": float(result.voltages_mv[time_index, node_index]),
                    "synaptic_current": float(currents[time_index, node_index]),
                    "spike": bool(result.spikes[time_index, node_index]),
                    "mv_per_synapse": config.mv_per_synapse,
                }
            )
    return rows


def _result_row(
    graph: DiagnosticGraph,
    result: SimulationResult,
    *,
    synaptic_gain: float,
    synaptic_tau_ms: float | None,
    config: SynapticDynamicsConfig,
) -> dict[str, Any]:
    source_first = _first_spike_ms(result, graph.source_id)
    target_first = _first_spike_ms(result, graph.target_id)
    intermediate_first = (
        _first_spike_ms(result, graph.intermediate_id)
        if graph.intermediate_id is not None
        else None
    )
    target_index = result.node_ids.index(graph.target_id)
    currents = result.synaptic_currents
    if currents is None:
        currents = np.zeros_like(result.voltages_mv)
    target_one_step = (
        source_first is not None
        and target_first == source_first + config.dt_ms
    )
    complete_path = None
    if graph.intermediate_id is not None:
        complete_path = (
            source_first is not None
            and intermediate_first == source_first + config.dt_ms
            and target_first is not None
            and target_first == intermediate_first + config.dt_ms
        )
    return {
        "topology": graph.name,
        "node_count": len(graph.node_ids),
        "edge_count": len(graph.edges),
        "source_id": graph.source_id,
        "intermediate_id": graph.intermediate_id,
        "target_id": graph.target_id,
        "mv_per_synapse": config.mv_per_synapse,
        "synaptic_gain": synaptic_gain,
        "synaptic_tau_ms": synaptic_tau_ms,
        "synaptic_mode": _tau_label(synaptic_tau_ms),
        "source_spike_count": result.spike_counts().get(graph.source_id, 0),
        "intermediate_spike_count": (
            result.spike_counts().get(graph.intermediate_id, 0)
            if graph.intermediate_id is not None
            else None
        ),
        "target_spike_count": result.spike_counts().get(graph.target_id, 0),
        "source_first_spike_ms": source_first,
        "intermediate_first_spike_ms": intermediate_first,
        "target_first_spike_ms": target_first,
        "one_step_target_spike": target_one_step,
        "complete_path": complete_path,
        "target_peak_voltage_mv": float(np.max(result.voltages_mv[:, target_index])),
        "target_peak_synaptic_current": float(np.max(currents[:, target_index])),
        "total_spikes": int(result.spikes.sum()),
        "all_spike_events": result.spike_events(),
    }


def run_synaptic_dynamics_matrix(
    graphs: Iterable[DiagnosticGraph],
    *,
    config: SynapticDynamicsConfig | None = None,
    gain_values: Iterable[float] = DEFAULT_GAIN_VALUES,
    tau_values: Iterable[float | None] = DEFAULT_TAU_VALUES,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the fixed native-sign gain/decay matrix on supplied derived graphs."""

    diagnostic_config = config or SynapticDynamicsConfig()
    gains = tuple(float(value) for value in gain_values)
    taus = tuple(None if value is None else float(value) for value in tau_values)
    if not gains:
        raise ValueError("At least one synaptic gain is required")
    if any(value < 0 for value in gains):
        raise ValueError("synaptic gains cannot be negative")
    if not taus:
        raise ValueError("At least one synaptic tau value is required")
    for tau in taus:
        if tau is not None and tau <= 0:
            raise ValueError("synaptic tau values must be positive or None")

    normalized_graphs = tuple(graphs)
    if not normalized_graphs:
        raise ValueError("At least one diagnostic graph is required")

    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for graph in normalized_graphs:
        edge_pre = [edge["body_pre"] for edge in graph.edges]
        edge_post = [edge["body_post"] for edge in graph.edges]
        edge_weights = [edge["weight"] for edge in graph.edges]
        edge_signs = [edge["sign"] for edge in graph.edges]
        for gain in gains:
            for tau in taus:
                result = simulate_lif(
                    graph.node_ids,
                    edge_pre,
                    edge_post,
                    edge_weights,
                    edge_signs,
                    input_nodes=[graph.source_id],
                    config=diagnostic_config.to_lif(gain, tau),
                )
                results.append(
                    _result_row(
                        graph,
                        result,
                        synaptic_gain=gain,
                        synaptic_tau_ms=tau,
                        config=diagnostic_config,
                    )
                )
                traces.extend(
                    _trace_rows(
                        graph,
                        result,
                        synaptic_gain=gain,
                        synaptic_tau_ms=tau,
                        config=diagnostic_config,
                    )
                )
    report = {
        "experiment": "legacy versus exponential synaptic dynamics",
        "fixed_parameters": asdict(diagnostic_config),
        "gain_values": list(gains),
        "tau_values_ms": list(taus),
        "topologies": [
            {
                "name": graph.name,
                "node_count": len(graph.node_ids),
                "edge_count": len(graph.edges),
                "source_id": graph.source_id,
                "intermediate_id": graph.intermediate_id,
                "target_id": graph.target_id,
            }
            for graph in normalized_graphs
        ],
        "results": results,
        "interpretation": [
            "synaptic_gain multiplies the existing raw-count current; no weight normalization is introduced.",
            "None synaptic tau is the legacy one-step current mode.",
            "Positive synaptic tau uses exponential decay while preserving the one-step spike delay.",
            "All conditions use native stored signs and the same topology, pulse, timestep, and membrane parameters.",
        ],
    }
    return report, traces


def _write_artifacts(
    report: dict[str, Any],
    traces: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "synaptic_dynamics_matrix.json"
    csv_path = output_dir / "synaptic_dynamics_matrix.csv"
    trace_path = output_dir / "synaptic_dynamics_traces.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result_fields = [
        "topology",
        "node_count",
        "edge_count",
        "source_id",
        "intermediate_id",
        "target_id",
        "mv_per_synapse",
        "synaptic_gain",
        "synaptic_tau_ms",
        "synaptic_mode",
        "source_spike_count",
        "intermediate_spike_count",
        "target_spike_count",
        "source_first_spike_ms",
        "intermediate_first_spike_ms",
        "target_first_spike_ms",
        "one_step_target_spike",
        "complete_path",
        "target_peak_voltage_mv",
        "target_peak_synaptic_current",
        "total_spikes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=result_fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in result_fields} for row in report["results"])

    trace_fields = [
        "topology",
        "synaptic_gain",
        "synaptic_tau_ms",
        "synaptic_mode",
        "time_ms",
        "body_id",
        "neuron_index",
        "voltage_mv",
        "synaptic_current",
        "spike",
        "mv_per_synapse",
    ]
    with trace_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=trace_fields)
        writer.writeheader()
        writer.writerows(traces)
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy and decaying synaptic dynamics")
    parser.add_argument("--baseline-dir", type=Path, default=Path("outputs/baseline"))
    parser.add_argument("--pathway-dir", type=Path, default=Path("outputs/pathway-slice"))
    parser.add_argument("--output", type=Path, default=Path("outputs/diagnostics"))
    args = parser.parse_args()

    baseline = load_derived_graph(
        args.baseline_dir,
        name="DNpe056_edge_10732_to_10968",
        source_id=10732,
        target_id=10968,
    )
    pathway = load_derived_graph(
        args.pathway_dir,
        name="native_pathway_806745_to_800225_to_22012",
        source_id=806745,
        intermediate_id=800225,
        target_id=22012,
        node_filename="nodes.csv",
        edge_filename="edges.csv",
    )
    report, traces = run_synaptic_dynamics_matrix([baseline, pathway])
    json_path, csv_path = _write_artifacts(report, traces, args.output)
    trace_path = args.output / "synaptic_dynamics_traces.csv"
    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "traces": str(trace_path),
                "condition_count": len(report["results"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

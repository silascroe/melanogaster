"""Command-line baseline: extract a local graph and run the LIF simulator."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .analysis import LocalNetwork, NodeRecord, select_local_network
from .data import MaleCNSPaths, body_ids_for_type
from .simulation import LIFConfig, SimulationResult, simulate_lif


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _node_rows(network: LocalNetwork) -> list[dict[str, Any]]:
    return [node.as_dict() for node in network.nodes]


def _edge_rows(network: LocalNetwork, config: LIFConfig) -> list[dict[str, Any]]:
    return [
        {
            **edge.as_dict(),
            "effective_weight_mv": edge.signed_weight * config.mv_per_synapse,
        }
        for edge in network.edges
    ]


def _voltage_rows(result: SimulationResult) -> list[dict[str, Any]]:
    rows = []
    for time_index, time_ms in enumerate(result.times_ms.tolist()):
        row: dict[str, Any] = {"time_ms": float(time_ms)}
        row.update(
            {f"body_{body_id}": float(result.voltages_mv[time_index, index]) for index, body_id in enumerate(result.node_ids)}
        )
        rows.append(row)
    return rows


def run_baseline(
    paths: MaleCNSPaths,
    *,
    seed_ids: list[int],
    output_dir: Path,
    neighbors: int = 64,
    min_weight: int = 3,
    max_edges: int | None = None,
    traced_only: bool = True,
    duration_ms: float = 100.0,
    dt_ms: float = 1.0,
    tau_ms: float = 20.0,
    rest_mv: float = -65.0,
    threshold_mv: float = -50.0,
    reset_mv: float = -65.0,
    refractory_ms: float = 2.0,
    mv_per_synapse: float = 0.05,
    input_nodes: list[int] | None = None,
    input_current_mv: float = 80.0,
    input_start_ms: float = 5.0,
    input_duration_ms: float = 5.0,
    unknown_sign: float = 0.0,
) -> dict[str, Any]:
    network = select_local_network(
        paths,
        seed_ids,
        neighbor_limit=neighbors,
        min_weight=min_weight,
        traced_only=traced_only,
        max_edges=max_edges,
        unknown_sign=unknown_sign,
    )
    config = LIFConfig(
        dt_ms=dt_ms,
        duration_ms=duration_ms,
        tau_ms=tau_ms,
        rest_mv=rest_mv,
        threshold_mv=threshold_mv,
        reset_mv=reset_mv,
        refractory_ms=refractory_ms,
        mv_per_synapse=mv_per_synapse,
        input_current_mv=input_current_mv,
        input_start_ms=input_start_ms,
        input_duration_ms=input_duration_ms,
    )
    pulse_nodes = input_nodes if input_nodes is not None else list(network.seed_ids)
    result = simulate_lif(
        [node.body_id for node in network.nodes],
        [edge.body_pre for edge in network.edges],
        [edge.body_post for edge in network.edges],
        [edge.weight for edge in network.edges],
        [edge.sign for edge in network.edges],
        input_nodes=pulse_nodes,
        config=config,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    node_fields = list(_node_rows(network)[0].keys()) if network.nodes else ["body_id"]
    edge_fields = list(_edge_rows(network, config)[0].keys()) if network.edges else [
        "body_pre",
        "body_post",
        "weight",
        "transmitter_pre",
        "sign",
        "signed_weight",
        "effective_weight_mv",
    ]
    _write_csv(output_dir / "selected_neurons.csv", _node_rows(network), node_fields)
    _write_csv(output_dir / "selected_edges.csv", _edge_rows(network, config), edge_fields)
    _write_csv(output_dir / "spikes.csv", result.spike_events(), ["time_ms", "body_id", "neuron_index"])
    voltage_rows = _voltage_rows(result)
    voltage_fields = list(voltage_rows[0].keys()) if voltage_rows else ["time_ms"]
    _write_csv(output_dir / "voltages.csv", voltage_rows, voltage_fields)

    sign_counts: dict[str, int] = {}
    for node in network.nodes:
        key = str(node.fast_sign)
        sign_counts[key] = sign_counts.get(key, 0) + 1
    summary = {
        "data_dir": str(paths.data_dir),
        "seed_ids": list(network.seed_ids),
        "input_nodes": pulse_nodes,
        "node_count": len(network.nodes),
        "edge_count": len(network.edges),
        "sign_counts_by_node": sign_counts,
        "selection": network.selection,
        "simulation": {
            "config": {
                "dt_ms": config.dt_ms,
                "duration_ms": config.duration_ms,
                "tau_ms": config.tau_ms,
                "rest_mv": config.rest_mv,
                "threshold_mv": config.threshold_mv,
                "reset_mv": config.reset_mv,
                "refractory_ms": config.refractory_ms,
                "mv_per_synapse": config.mv_per_synapse,
                "input_current_mv": config.input_current_mv,
                "input_start_ms": config.input_start_ms,
                "input_duration_ms": config.input_duration_ms,
            },
            "steps": len(result.times_ms),
            "total_spikes": int(result.spikes.sum()),
            "spike_counts": {str(body_id): count for body_id, count in result.spike_counts().items()},
        },
        "outputs": {
            "neurons": str(output_dir / "selected_neurons.csv"),
            "edges": str(output_dir / "selected_edges.csv"),
            "spikes": str(output_dir / "spikes.csv"),
            "voltages": str(output_dir / "voltages.csv"),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and simulate a bounded MaleCNS subgraph")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/baseline"))
    parser.add_argument("--type", default="DNge104", help="Exact annotation type used for default seed selection")
    parser.add_argument("--body-id", action="append", type=int, help="Explicit seed body ID; repeat for multiple seeds")
    parser.add_argument("--neighbors", type=int, default=64)
    parser.add_argument("--min-weight", type=int, default=3)
    parser.add_argument("--max-edges", type=int, default=None)
    parser.add_argument("--include-untraced", action="store_true")
    parser.add_argument("--duration-ms", type=float, default=100.0)
    parser.add_argument("--dt-ms", type=float, default=1.0)
    parser.add_argument("--tau-ms", type=float, default=20.0)
    parser.add_argument("--rest-mv", type=float, default=-65.0)
    parser.add_argument("--threshold-mv", type=float, default=-50.0)
    parser.add_argument("--reset-mv", type=float, default=-65.0)
    parser.add_argument("--refractory-ms", type=float, default=2.0)
    parser.add_argument("--mv-per-synapse", type=float, default=0.05)
    parser.add_argument("--input-body-id", action="append", type=int)
    parser.add_argument("--input-current-mv", type=float, default=80.0)
    parser.add_argument("--input-start-ms", type=float, default=5.0)
    parser.add_argument("--input-duration-ms", type=float, default=5.0)
    parser.add_argument("--unknown-sign", type=float, default=0.0)
    args = parser.parse_args()

    paths = MaleCNSPaths(args.data_dir)
    traced_only = not args.include_untraced
    seed_ids = args.body_id or body_ids_for_type(paths, args.type, traced_only=traced_only)
    if not seed_ids:
        raise SystemExit(f"No seed body IDs found for type {args.type!r}")
    summary = run_baseline(
        paths,
        seed_ids=seed_ids,
        output_dir=args.output,
        neighbors=args.neighbors,
        min_weight=args.min_weight,
        max_edges=args.max_edges,
        traced_only=traced_only,
        duration_ms=args.duration_ms,
        dt_ms=args.dt_ms,
        tau_ms=args.tau_ms,
        rest_mv=args.rest_mv,
        threshold_mv=args.threshold_mv,
        reset_mv=args.reset_mv,
        refractory_ms=args.refractory_ms,
        mv_per_synapse=args.mv_per_synapse,
        input_nodes=args.input_body_id,
        input_current_mv=args.input_current_mv,
        input_start_ms=args.input_start_ms,
        input_duration_ms=args.input_duration_ms,
        unknown_sign=args.unknown_sign,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

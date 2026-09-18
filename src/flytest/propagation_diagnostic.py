"""Controlled single-edge propagation diagnostic.

This is intentionally separate from the baseline runner. It consumes the
small derived baseline CSVs, changes no simulator defaults, and runs a 2x2
matrix over sign policy and coupling strength for one known edge.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from .simulation import LIFConfig, SimulationResult, simulate_lif


SOURCE_BODY_ID = 10732
TARGET_BODY_ID = 10968
COUPLING_VALUES = (0.05, 1.5)
SIGN_MODES = ("native", "forced_excitatory")


@dataclass(frozen=True)
class PropagationDiagnosticConfig:
    """Fixed parameters for the impulse-response matrix."""

    dt_ms: float = 1.0
    duration_ms: float = 30.0
    tau_ms: float = 20.0
    rest_mv: float = -65.0
    threshold_mv: float = -50.0
    reset_mv: float = -65.0
    refractory_ms: float = 2.0
    input_current_mv: float = 80.0
    input_start_ms: float = 5.0
    input_duration_ms: float = 5.0

    def to_lif(self, coupling_mv_per_synapse: float) -> LIFConfig:
        return LIFConfig(
            dt_ms=self.dt_ms,
            duration_ms=self.duration_ms,
            tau_ms=self.tau_ms,
            rest_mv=self.rest_mv,
            threshold_mv=self.threshold_mv,
            reset_mv=self.reset_mv,
            refractory_ms=self.refractory_ms,
            mv_per_synapse=coupling_mv_per_synapse,
            input_current_mv=self.input_current_mv,
            input_start_ms=self.input_start_ms,
            input_duration_ms=self.input_duration_ms,
        )


def load_baseline_csv(baseline_dir: Path) -> tuple[list[int], list[dict[str, Any]]]:
    """Load the existing small baseline graph without touching raw Feather data."""

    node_path = baseline_dir / "selected_neurons.csv"
    edge_path = baseline_dir / "selected_edges.csv"
    if not node_path.is_file() or not edge_path.is_file():
        raise FileNotFoundError(f"Expected baseline CSVs under {baseline_dir}")
    with node_path.open(newline="", encoding="utf-8") as handle:
        node_ids = [int(row["body_id"]) for row in csv.DictReader(handle)]
    with edge_path.open(newline="", encoding="utf-8") as handle:
        edges = list(csv.DictReader(handle))
    matches = [
        row
        for row in edges
        if int(row["body_pre"]) == SOURCE_BODY_ID and int(row["body_post"]) == TARGET_BODY_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {SOURCE_BODY_ID}->{TARGET_BODY_ID} edge, found {len(matches)}")
    return node_ids, edges


def _result_row(
    *,
    sign_mode: str,
    coupling_mv_per_synapse: float,
    native_edge_sign: float,
    applied_edge_sign: float,
    result: SimulationResult,
    config: PropagationDiagnosticConfig,
) -> dict[str, Any]:
    source_events = [event for event in result.spike_events() if event["body_id"] == SOURCE_BODY_ID]
    target_events = [event for event in result.spike_events() if event["body_id"] == TARGET_BODY_ID]
    source_first = source_events[0]["time_ms"] if source_events else None
    target_first = target_events[0]["time_ms"] if target_events else None
    expected_time = source_first + config.dt_ms if source_first is not None else None
    return {
        "sign_mode": sign_mode,
        "coupling_mv_per_synapse": coupling_mv_per_synapse,
        "native_edge_sign": native_edge_sign,
        "applied_edge_sign": applied_edge_sign,
        "source_spike_count": len(source_events),
        "source_first_spike_ms": source_first,
        "target_spike_count": len(target_events),
        "target_first_spike_ms": target_first,
        "one_step_target_spike": target_first is not None and target_first == expected_time,
        "total_spikes": int(result.spikes.sum()),
        "all_spike_events": result.spike_events(),
    }


def run_propagation_matrix(
    node_ids: Sequence[int],
    edges: Sequence[dict[str, Any]],
    *,
    config: PropagationDiagnosticConfig | None = None,
    coupling_values: Sequence[float] = COUPLING_VALUES,
) -> dict[str, Any]:
    """Run native/forced-sign x conservative/permissive coupling conditions."""

    diagnostic_config = config or PropagationDiagnosticConfig()
    normalized_edges = [
        {
            "body_pre": int(edge["body_pre"]),
            "body_post": int(edge["body_post"]),
            "weight": float(edge["weight"]),
            "sign": float(edge["sign"]),
        }
        for edge in edges
    ]
    test_edges = [
        edge
        for edge in normalized_edges
        if edge["body_pre"] == SOURCE_BODY_ID and edge["body_post"] == TARGET_BODY_ID
    ]
    if len(test_edges) != 1:
        raise ValueError(f"Expected exactly one {SOURCE_BODY_ID}->{TARGET_BODY_ID} edge, found {len(test_edges)}")
    test_edge = test_edges[0]
    native_sign = test_edge["sign"]
    matrix: list[dict[str, Any]] = []
    for sign_mode in SIGN_MODES:
        applied_sign = 1.0 if sign_mode == "forced_excitatory" else native_sign
        for coupling in coupling_values:
            signs = [
                applied_sign if edge is test_edge else edge["sign"]
                for edge in normalized_edges
            ]
            result = simulate_lif(
                node_ids,
                [edge["body_pre"] for edge in normalized_edges],
                [edge["body_post"] for edge in normalized_edges],
                [edge["weight"] for edge in normalized_edges],
                signs,
                input_nodes=[SOURCE_BODY_ID],
                config=diagnostic_config.to_lif(float(coupling)),
            )
            matrix.append(
                _result_row(
                    sign_mode=sign_mode,
                    coupling_mv_per_synapse=float(coupling),
                    native_edge_sign=native_sign,
                    applied_edge_sign=applied_sign,
                    result=result,
                    config=diagnostic_config,
                )
            )
    return {
        "experiment": "single-edge propagation impulse response",
        "edge_under_test": {
            "body_pre": SOURCE_BODY_ID,
            "body_post": TARGET_BODY_ID,
            "weight": test_edge["weight"],
            "native_sign": native_sign,
            "native_transmitter": "acetylcholine",
        },
        "input": {
            "body_id": SOURCE_BODY_ID,
            "target_body_id": TARGET_BODY_ID,
            "node_count": len(node_ids),
            "edge_count": len(normalized_edges),
        },
        "fixed_parameters": asdict(diagnostic_config),
        "sign_modes": list(SIGN_MODES),
        "coupling_values_mv_per_synapse": [float(value) for value in coupling_values],
        "results": matrix,
        "interpretation": [
            "Native uses the stored per-edge transmitter sign; forced_excitatory sets only the edge under test to +1.",
            "The selected edge is natively acetylcholine/excitatory, so the two sign rows are expected to match for the one-step response.",
            "All four conditions use the same topology, pulse timing, timestep, threshold, refractory period, and duration.",
        ],
    }


def _write_artifacts(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "propagation_matrix.json"
    csv_path = output_dir / "propagation_matrix.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = [
        "sign_mode",
        "coupling_mv_per_synapse",
        "native_edge_sign",
        "applied_edge_sign",
        "source_spike_count",
        "source_first_spike_ms",
        "target_spike_count",
        "target_first_spike_ms",
        "one_step_target_spike",
        "total_spikes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in report["results"])
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled 10732->10968 propagation diagnostic")
    parser.add_argument("--baseline-dir", type=Path, default=Path("outputs/baseline"))
    parser.add_argument("--output", type=Path, default=Path("outputs/diagnostics"))
    args = parser.parse_args()
    node_ids, edges = load_baseline_csv(args.baseline_dir)
    report = run_propagation_matrix(node_ids, edges)
    json_path, csv_path = _write_artifacts(report, args.output)
    compact = [
        {
            "sign_mode": row["sign_mode"],
            "coupling_mv_per_synapse": row["coupling_mv_per_synapse"],
            "target_spike_count": row["target_spike_count"],
            "target_first_spike_ms": row["target_first_spike_ms"],
            "one_step_target_spike": row["one_step_target_spike"],
        }
        for row in report["results"]
    ]
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "results": compact}, indent=2))


if __name__ == "__main__":
    main()

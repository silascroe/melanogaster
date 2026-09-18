"""Give a small real pathway a toy body and a sensorimotor action.

This is the next layer above :mod:`flytest.circuit_story`: the selected
connectome pathway receives a sensory pulse, its descending spikes are decoded
as turn commands, and a tiny point-mass body records the resulting trajectory.
The decoder is an explicit modelling assumption, not a biological annotation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .analysis import PathwaySelection, select_native_pathway
from .data import MaleCNSPaths
from .simulation import LIFConfig, SimulationResult, simulate_lif


SOURCE_MANIFEST = "data/metadata/source_manifest.json"


@dataclass(frozen=True)
class SensorimotorConfig:
    """Fixed neural and toy-body parameters for one reflex run."""

    duration_ms: float = 60.0
    dt_ms: float = 1.0
    tau_ms: float = 20.0
    rest_mv: float = -65.0
    threshold_mv: float = -50.0
    reset_mv: float = -65.0
    refractory_ms: float = 2.0
    coupling_mv_per_synapse: float = 4.0
    input_current_mv: float = 80.0
    input_start_ms: float = 5.0
    input_duration_ms: float = 30.0
    turn_degrees_per_target_spike: float = 15.0
    forward_step_per_target_spike: float = 1.0
    initial_heading_degrees: float = 0.0
    initial_x: float = 0.0
    initial_y: float = 0.0

    def validate(self) -> None:
        if self.coupling_mv_per_synapse < 0:
            raise ValueError("coupling_mv_per_synapse cannot be negative")
        if not math.isfinite(self.turn_degrees_per_target_spike):
            raise ValueError("turn_degrees_per_target_spike must be finite")
        if not math.isfinite(self.forward_step_per_target_spike):
            raise ValueError("forward_step_per_target_spike must be finite")
        if not math.isfinite(self.initial_heading_degrees):
            raise ValueError("initial_heading_degrees must be finite")
        if not math.isfinite(self.initial_x) or not math.isfinite(self.initial_y):
            raise ValueError("initial position must be finite")

    def to_lif(self) -> LIFConfig:
        self.validate()
        return LIFConfig(
            dt_ms=self.dt_ms,
            duration_ms=self.duration_ms,
            tau_ms=self.tau_ms,
            rest_mv=self.rest_mv,
            threshold_mv=self.threshold_mv,
            reset_mv=self.reset_mv,
            refractory_ms=self.refractory_ms,
            mv_per_synapse=self.coupling_mv_per_synapse,
            input_current_mv=self.input_current_mv,
            input_start_ms=self.input_start_ms,
            input_duration_ms=self.input_duration_ms,
        )


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fieldnames} for row in rows)


def _node_rows(selection: PathwaySelection) -> list[dict[str, Any]]:
    roles = {
        selection.source_id: "source",
        selection.intermediate_id: "intermediate",
        selection.target_id: "target",
    }
    return [{**node.as_dict(), "role": roles[node.body_id]} for node in selection.nodes]


def _edge_rows(selection: PathwaySelection) -> list[dict[str, Any]]:
    path_legs = {
        selection.path_edge_keys[0]: "source_to_intermediate",
        selection.path_edge_keys[1]: "intermediate_to_target",
    }
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


def _stimulus_active(time_ms: float, config: SensorimotorConfig) -> bool:
    return config.input_start_ms <= time_ms < config.input_start_ms + config.input_duration_ms


def _simulate_sensorimotor(
    selection: PathwaySelection,
    config: SensorimotorConfig,
) -> tuple[SimulationResult, list[dict[str, Any]]]:
    """Run the neural pathway and decode descending spikes into body motion."""

    lif_config = config.to_lif()
    result = simulate_lif(
        [node.body_id for node in selection.nodes],
        [edge.body_pre for edge in selection.edges],
        [edge.body_post for edge in selection.edges],
        [edge.weight for edge in selection.edges],
        [edge.sign for edge in selection.edges],
        input_nodes=[selection.source_id],
        config=lif_config,
    )
    node_indices = {body_id: index for index, body_id in enumerate(result.node_ids)}
    source_index = node_indices[selection.source_id]
    intermediate_index = node_indices[selection.intermediate_id]
    target_index = node_indices[selection.target_id]

    heading = config.initial_heading_degrees
    position_x = config.initial_x
    position_y = config.initial_y
    trajectory: list[dict[str, Any]] = []
    for time_index, time_ms in enumerate(result.times_ms.tolist()):
        target_spike = bool(result.spikes[time_index, target_index])
        turn_command = config.turn_degrees_per_target_spike if target_spike else 0.0
        if target_spike:
            heading += turn_command
            radians = math.radians(heading)
            position_x += config.forward_step_per_target_spike * math.cos(radians)
            position_y += config.forward_step_per_target_spike * math.sin(radians)
        trajectory.append(
            {
                "time_ms": float(time_ms),
                "stimulus_active": _stimulus_active(float(time_ms), config),
                "source_spike": bool(result.spikes[time_index, source_index]),
                "intermediate_spike": bool(result.spikes[time_index, intermediate_index]),
                "target_spike": target_spike,
                "source_voltage_mv": float(result.voltages_mv[time_index, source_index]),
                "intermediate_voltage_mv": float(result.voltages_mv[time_index, intermediate_index]),
                "target_voltage_mv": float(result.voltages_mv[time_index, target_index]),
                "turn_command_degrees": float(turn_command),
                "heading_degrees": float(heading),
                "position_x": float(position_x),
                "position_y": float(position_y),
            }
        )
    return result, trajectory


def _story_markdown(
    *,
    selection: PathwaySelection,
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    trajectory: list[dict[str, Any]],
    config: SensorimotorConfig,
    data_dir: Path,
) -> str:
    node_by_id = {int(row["body_id"]): row for row in node_rows}
    source = node_by_id[selection.source_id]
    target = node_by_id[selection.target_id]
    target_spikes = sum(bool(row["target_spike"]) for row in trajectory)
    final = trajectory[-1]
    lines = [
        "# Connectome-backed sensorimotor reflex",
        "",
        "This is the first body-facing layer above the circuit story: a real "
        "Male CNS pathway receives a sensory pulse, and its descending spikes "
        "move a deliberately tiny point-mass body.",
        "",
        "## What is data and what is ours",
        "",
        f"- Dataset: FlyEM Male CNS v1.0 (`{data_dir}`)",
        f"- Provenance manifest: `{SOURCE_MANIFEST}`",
        f"- Source: body {source['body_id']} ({source.get('instance') or source.get('type')}), "
        f"annotated as `{source.get('class') or 'no class label'}`.",
        f"- Target: body {target['body_id']} ({target.get('instance') or target.get('type')}), "
        "a descending neuron.",
        "- The selected edges, transmitter labels, signs, and pathway roles come "
        "from the local release and existing model conventions.",
        "- Our toy action decoder maps each target spike to a fixed turn impulse "
        f"of {config.turn_degrees_per_target_spike:g} degrees and a forward step of "
        f"{config.forward_step_per_target_spike:g} body units.",
        "",
        "## Neural path",
        "",
    ]
    for edge in edge_rows:
        if edge["is_path_edge"]:
            sign_label = (
                "excitatory"
                if float(edge["sign"]) > 0
                else "inhibitory"
                if float(edge["sign"]) < 0
                else "neutral/unknown"
            )
            lines.append(
                f"- {edge['body_pre']} → {edge['body_post']}: {edge['weight']:g} "
                f"synapses, {edge['transmitter_pre'] or 'unknown'} ({sign_label})"
            )
    lines.extend(
        [
            "",
            "## Result",
            "",
            f"A {config.input_duration_ms:g} ms sensory pulse starts at "
            f"{config.input_start_ms:g} ms. The pathway produces {target_spikes} "
            "descending target spike(s), which produce "
            f"{target_spikes} toy turn command(s).",
            f"The body ends at ({final['position_x']:.3f}, {final['position_y']:.3f}) "
            f"with heading {final['heading_degrees']:.3f} degrees.",
            "",
            "This is not a claim that this exact pathway controls a named fly "
            "behavior. It demonstrates the important interface: sensory input "
            "enters the connectome-backed network, a descending neuron spikes, "
            "and only then does the body state change through an explicit decoder.",
            "",
            "The full neural/body trajectory is in `trajectory.csv`; the selected "
            "node and edge tables are beside this report.",
            "",
        ]
    )
    return "\n".join(lines)


def run_sensorimotor(
    paths: MaleCNSPaths,
    *,
    output_dir: Path,
    min_weight: int = 3,
    config: SensorimotorConfig | None = None,
) -> dict[str, Any]:
    """Run a connectome-backed sensory-to-body reflex experiment."""

    reflex_config = config or SensorimotorConfig()
    selection = select_native_pathway(paths, min_weight=min_weight)
    result, trajectory = _simulate_sensorimotor(selection, reflex_config)
    node_rows = _node_rows(selection)
    edge_rows = _edge_rows(selection)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "nodes.csv", node_rows, list(node_rows[0].keys()))
    _write_csv(output_dir / "edges.csv", edge_rows, list(edge_rows[0].keys()))
    _write_csv(
        output_dir / "trajectory.csv",
        trajectory,
        [
            "time_ms",
            "stimulus_active",
            "source_spike",
            "intermediate_spike",
            "target_spike",
            "source_voltage_mv",
            "intermediate_voltage_mv",
            "target_voltage_mv",
            "turn_command_degrees",
            "heading_degrees",
            "position_x",
            "position_y",
        ],
    )

    spike_counts = result.spike_counts()
    final = trajectory[-1]
    output_paths = {
        "story": str(output_dir / "story.md"),
        "summary": str(output_dir / "summary.json"),
        "nodes": str(output_dir / "nodes.csv"),
        "edges": str(output_dir / "edges.csv"),
        "trajectory": str(output_dir / "trajectory.csv"),
    }
    summary = {
        "experiment": "connectome-backed sensorimotor reflex",
        "dataset": {
            "name": "FlyEM Male CNS",
            "release": "v1.0",
            "data_dir": str(paths.data_dir),
            "source_manifest": SOURCE_MANIFEST,
        },
        "node_count": len(selection.nodes),
        "edge_count": len(selection.edges),
        "path": {
            "source_id": selection.source_id,
            "intermediate_id": selection.intermediate_id,
            "target_id": selection.target_id,
            "path_edge_keys": [list(key) for key in selection.path_edge_keys],
        },
        "selection": selection.selection,
        "parameters": asdict(reflex_config),
        "neural_parameters": asdict(reflex_config.to_lif()),
        "action_decoder": {
            "input": "one selected sensory-source pulse",
            "output": "one fixed turn and forward step per descending-target spike",
            "turn_degrees_per_target_spike": reflex_config.turn_degrees_per_target_spike,
            "forward_step_per_target_spike": reflex_config.forward_step_per_target_spike,
            "heading_convention": "positive degrees rotate counterclockwise; arbitrary toy axis",
        },
        "outcome": {
            "spike_counts": {str(body_id): count for body_id, count in spike_counts.items()},
            "target_spike_count": int(spike_counts[selection.target_id]),
            "turn_event_count": sum(bool(row["target_spike"]) for row in trajectory),
            "final_heading_degrees": final["heading_degrees"],
            "final_position": [final["position_x"], final["position_y"]],
        },
        "outputs": output_paths,
        "notes": [
            "Only the selected sensory source receives external input.",
            "Native transmitter signs and the existing one-step synaptic delay are preserved.",
            "The body and action decoder are explicit toy assumptions, not measured biology.",
            "The experiment demonstrates sensorimotor wiring; it does not identify a complete fly behavior.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "story.md").write_text(
        _story_markdown(
            selection=selection,
            node_rows=node_rows,
            edge_rows=edge_rows,
            trajectory=trajectory,
            config=reflex_config,
            data_dir=paths.data_dir,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a connectome-backed sensorimotor reflex")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/sensorimotor"))
    parser.add_argument("--min-weight", type=int, default=3)
    parser.add_argument("--duration-ms", type=float, default=60.0)
    parser.add_argument("--coupling", type=float, default=4.0)
    parser.add_argument("--input-duration-ms", type=float, default=30.0)
    parser.add_argument("--turn-degrees", type=float, default=15.0)
    parser.add_argument("--forward-step", type=float, default=1.0)
    args = parser.parse_args()
    config = SensorimotorConfig(
        duration_ms=args.duration_ms,
        coupling_mv_per_synapse=args.coupling,
        input_duration_ms=args.input_duration_ms,
        turn_degrees_per_target_spike=args.turn_degrees,
        forward_step_per_target_spike=args.forward_step,
    )
    summary = run_sensorimotor(
        MaleCNSPaths(args.data_dir), output_dir=args.output, min_weight=args.min_weight, config=config
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

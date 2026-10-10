"""Write a readable input-to-output story for a small real pathway.

This is a separate diagnostic built on the existing native-sign pathway
selector and LIF simulator. It does not change the production simulator or
the existing pathway-slice outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .analysis import EdgeRecord, PathwaySelection, select_native_pathway
from .data import MaleCNSPaths
from .pathway_slice import DEFAULT_COUPLING_VALUES, PathwaySliceConfig
from .simulation import SimulationResult, simulate_lif


SOURCE_MANIFEST = "data/metadata/source_manifest.json"


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fieldnames} for row in rows)


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


def _synaptic_currents(result: SimulationResult) -> np.ndarray:
    if result.synaptic_currents is None:
        return np.zeros_like(result.voltages_mv)
    return result.synaptic_currents


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
    target_index = result.node_ids.index(selection.target_id)
    currents = _synaptic_currents(result)
    return {
        "coupling_mv_per_synapse": coupling_mv_per_synapse,
        "source_id": selection.source_id,
        "intermediate_id": selection.intermediate_id,
        "target_id": selection.target_id,
        "source_spike_count": counts.get(selection.source_id, 0),
        "intermediate_spike_count": counts.get(selection.intermediate_id, 0),
        "target_spike_count": counts.get(selection.target_id, 0),
        "source_first_spike_ms": source_first,
        "intermediate_first_spike_ms": intermediate_first,
        "target_first_spike_ms": target_first,
        "source_to_intermediate_one_step": source_to_intermediate,
        "intermediate_to_target_one_step": intermediate_to_target,
        "complete_path": source_to_intermediate and intermediate_to_target,
        "target_peak_voltage_mv": float(np.max(result.voltages_mv[:, target_index])),
        "target_peak_synaptic_current": float(np.max(currents[:, target_index])),
        "total_spikes": int(result.spikes.sum()),
        "spike_events": result.spike_events(),
    }


def _trace_rows(
    selection: PathwaySelection,
    result: SimulationResult,
    *,
    label: str,
    coupling_mv_per_synapse: float,
) -> list[dict[str, Any]]:
    roles = {
        selection.source_id: "source",
        selection.intermediate_id: "intermediate",
        selection.target_id: "target",
    }
    currents = _synaptic_currents(result)
    rows: list[dict[str, Any]] = []
    for time_index, time_ms in enumerate(result.times_ms.tolist()):
        for node_index, body_id in enumerate(result.node_ids):
            rows.append(
                {
                    "condition_label": label,
                    "coupling_mv_per_synapse": coupling_mv_per_synapse,
                    "time_ms": float(time_ms),
                    "body_id": int(body_id),
                    "neuron_index": node_index,
                    "role": roles[int(body_id)],
                    "voltage_mv": float(result.voltages_mv[time_index, node_index]),
                    "synaptic_current": float(currents[time_index, node_index]),
                    "spike": bool(result.spikes[time_index, node_index]),
                }
            )
    return rows


def _edge_contribution_rows(
    selection: PathwaySelection,
    result: SimulationResult,
    *,
    label: str,
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
                    "condition_label": label,
                    "coupling_mv_per_synapse": coupling_mv_per_synapse,
                    "source_spike_time_ms": spike_time,
                    "arrival_time_ms": spike_time + config.dt_ms,
                    "body_pre": edge.body_pre,
                    "body_post": edge.body_post,
                    "weight": edge.weight,
                    "transmitter_pre": edge.transmitter_pre,
                    "sign": edge.sign,
                    "synaptic_current": synaptic_current,
                    "euler_voltage_increment_mv": (config.dt_ms / config.tau_ms)
                    * synaptic_current,
                    "is_path_edge": key in path_legs,
                    "path_leg": path_legs.get(key, ""),
                }
            )
    return rows


def _sign_description(sign: float) -> str:
    if sign > 0:
        return "excitatory"
    if sign < 0:
        return "inhibitory"
    return "neutral/unknown"


def _node_description(node: dict[str, Any]) -> str:
    label = node.get("instance") or node.get("type") or "unnamed neuron"
    transmitter = node.get("consensus_nt") or node.get("predicted_nt") or "unknown transmitter"
    sign = _sign_description(float(node["fast_sign"]))
    return (
        f"body {node['body_id']} ({label}), {node['role']}; "
        f"{transmitter}, modelled as {sign}"
    )


def _format_time(value: float | None) -> str:
    return "no spike" if value is None else f"{value:g} ms"


def _story_markdown(
    *,
    selection: PathwaySelection,
    node_rows: list[dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    run_rows: list[dict[str, Any]],
    trace_conditions: list[dict[str, Any]],
    config: PathwaySliceConfig,
    data_dir: Path,
) -> str:
    node_by_id = {int(row["body_id"]): row for row in node_rows}
    reference = run_rows[trace_conditions[0]["run_index"]]
    comparison = run_rows[trace_conditions[-1]["run_index"]]
    comparison_label = trace_conditions[-1]["label"]

    lines = [
        "# Circuit story",
        "",
        "This is a small, connectome-backed input-to-output experiment. It is "
        "a diagnostic, not a behavioral or FlyDoom simulation.",
        "",
        "## Data and model",
        "",
        f"- Dataset: FlyEM Male CNS v1.0 (`{data_dir}`)",
        f"- Provenance manifest: `{SOURCE_MANIFEST}`",
        "- External input: a brief pulse applied only to the selected source neuron.",
        f"- Fixed timestep: {config.dt_ms:g} ms; membrane time constant: {config.tau_ms:g} ms.",
        f"- Threshold/reset: {config.threshold_mv:g} / {config.reset_mv:g} mV.",
        "- Native transmitter signs are used; gain and synaptic decay remain at "
        "their production-compatible defaults.",
        "- An edge's sign comes from its presynaptic neuron: the target's own "
        "GABA label describes what it sends onward, not the incoming edge.",
        "",
        "## Selected circuit",
        "",
    ]
    lines.extend(f"- {_node_description(node_by_id[node.body_id])}" for node in selection.nodes)
    lines.extend(["", "Path edges:"])
    for edge in edge_rows:
        if edge["is_path_edge"]:
            lines.append(
                f"- {edge['body_pre']} → {edge['body_post']}: "
                f"{edge['weight']:g} synapses, {edge['transmitter_pre'] or 'unknown'} "
                f"({_sign_description(float(edge['sign']))})"
            )

    lines.extend(
        [
            "",
            "## What happened",
            "",
            f"At the lowest tested coupling ({reference['coupling_mv_per_synapse']:g} "
            "mV/synapse), the source fires at "
            f"{_format_time(reference['source_first_spike_ms'])}. The intermediate "
            f"and target are {_format_time(reference['intermediate_first_spike_ms'])} "
            f"and {_format_time(reference['target_first_spike_ms'])}; the path is "
            "silent after the source.",
            "",
        ]
    )
    if comparison["complete_path"]:
        lines.extend(
            [
                f"The first complete condition is the `{comparison_label}` condition "
                f"at {comparison['coupling_mv_per_synapse']:g} mV/synapse. The source "
                f"fires at {_format_time(comparison['source_first_spike_ms'])}, the "
                f"intermediate at {_format_time(comparison['intermediate_first_spike_ms'])}, "
                f"and the target at {_format_time(comparison['target_first_spike_ms'])}. "
                "Each hop is one simulator timestep.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"No tested condition produced a complete path. The `{comparison_label}` "
                f"condition at {comparison['coupling_mv_per_synapse']:g} mV/synapse "
                "is the highest-coupling comparison trace.",
                "",
            ]
        )

    lines.extend(
        [
            "The coupling sweep changes only the current contribution per synapse. "
            "These values are calibration probes for this simplified model, not "
            "measurements of biological synaptic strength.",
            "",
            "## Sweep results",
            "",
            "| Coupling | Source | Intermediate | Target | Complete path |",
            "| ---: | ---: | ---: | ---: | :--- |",
        ]
    )
    for row in run_rows:
        lines.append(
            f"| {row['coupling_mv_per_synapse']:g} | "
            f"{_format_time(row['source_first_spike_ms'])} | "
            f"{_format_time(row['intermediate_first_spike_ms'])} | "
            f"{_format_time(row['target_first_spike_ms'])} | "
            f"{'yes' if row['complete_path'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "The selected neuron and edge tables, full sweep summary, and two key "
            "time traces are stored beside this report.",
            "",
        ]
    )
    return "\n".join(lines)


def run_circuit_story(
    paths: MaleCNSPaths,
    *,
    output_dir: Path,
    min_weight: int = 3,
    coupling_values: Iterable[float] = DEFAULT_COUPLING_VALUES,
    config: PathwaySliceConfig | None = None,
) -> dict[str, Any]:
    """Select, simulate, and explain a small native-sign pathway."""

    story_config = config or PathwaySliceConfig()
    couplings = tuple(float(value) for value in coupling_values)
    if not couplings:
        raise ValueError("At least one coupling value is required")
    if any(not math.isfinite(value) or value < 0 for value in couplings):
        raise ValueError("coupling values must be finite and non-negative")

    selection = select_native_pathway(paths, min_weight=min_weight)
    node_ids = [node.body_id for node in selection.nodes]
    edge_pre = [edge.body_pre for edge in selection.edges]
    edge_post = [edge.body_post for edge in selection.edges]
    edge_weights = [edge.weight for edge in selection.edges]
    edge_signs = [edge.sign for edge in selection.edges]

    run_rows: list[dict[str, Any]] = []
    simulated: list[tuple[float, SimulationResult]] = []
    for coupling in couplings:
        result = simulate_lif(
            node_ids,
            edge_pre,
            edge_post,
            edge_weights,
            edge_signs,
            input_nodes=[selection.source_id],
            config=story_config.to_lif(coupling),
        )
        run_rows.append(_run_row(selection, result, coupling, story_config))
        simulated.append((coupling, result))

    reference_index = min(range(len(couplings)), key=lambda index: couplings[index])
    first_complete_index = next(
        (index for index, row in enumerate(run_rows) if row["complete_path"]),
        None,
    )
    comparison_index = (
        first_complete_index
        if first_complete_index is not None
        else max(range(len(couplings)), key=lambda index: couplings[index])
    )

    trace_conditions = [
        {
            "label": "conservative_reference",
            "coupling_mv_per_synapse": couplings[reference_index],
            "run_index": reference_index,
        }
    ]
    if comparison_index != reference_index:
        trace_conditions.append(
            {
                "label": (
                    "first_complete_path"
                    if first_complete_index is not None
                    else "highest_coupling_fallback"
                ),
                "coupling_mv_per_synapse": couplings[comparison_index],
                "run_index": comparison_index,
            }
        )

    trace_rows: list[dict[str, Any]] = []
    contribution_rows: list[dict[str, Any]] = []
    for condition in trace_conditions:
        index = int(condition["run_index"])
        coupling, result = simulated[index]
        trace_rows.extend(
            _trace_rows(
                selection,
                result,
                label=str(condition["label"]),
                coupling_mv_per_synapse=coupling,
            )
        )
        contribution_rows.extend(
            _edge_contribution_rows(
                selection,
                result,
                label=str(condition["label"]),
                coupling_mv_per_synapse=coupling,
                config=story_config,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    node_rows = _node_rows(selection)
    edge_rows = _edge_rows(selection)
    _write_csv(output_dir / "nodes.csv", node_rows, list(node_rows[0].keys()))
    _write_csv(output_dir / "edges.csv", edge_rows, list(edge_rows[0].keys()))
    _write_csv(
        output_dir / "runs.csv",
        run_rows,
        [
            "coupling_mv_per_synapse",
            "source_id",
            "intermediate_id",
            "target_id",
            "source_spike_count",
            "intermediate_spike_count",
            "target_spike_count",
            "source_first_spike_ms",
            "intermediate_first_spike_ms",
            "target_first_spike_ms",
            "source_to_intermediate_one_step",
            "intermediate_to_target_one_step",
            "complete_path",
            "target_peak_voltage_mv",
            "target_peak_synaptic_current",
            "total_spikes",
        ],
    )
    _write_csv(
        output_dir / "key_traces.csv",
        trace_rows,
        [
            "condition_label",
            "coupling_mv_per_synapse",
            "time_ms",
            "body_id",
            "neuron_index",
            "role",
            "voltage_mv",
            "synaptic_current",
            "spike",
        ],
    )
    _write_csv(
        output_dir / "key_edge_contributions.csv",
        contribution_rows,
        [
            "condition_label",
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

    output_paths = {
        "story": str(output_dir / "story.md"),
        "summary": str(output_dir / "summary.json"),
        "nodes": str(output_dir / "nodes.csv"),
        "edges": str(output_dir / "edges.csv"),
        "runs": str(output_dir / "runs.csv"),
        "key_traces": str(output_dir / "key_traces.csv"),
        "key_edge_contributions": str(output_dir / "key_edge_contributions.csv"),
    }
    summary = {
        "experiment": "native-sign input-to-output circuit story",
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
        "fixed_parameters": asdict(story_config),
        "synaptic_parameters": {
            "synaptic_gain": 1.0,
            "synaptic_tau_ms": None,
            "sign_mode": "native stored signs",
        },
        "coupling_values_mv_per_synapse": list(couplings),
        "trace_selection": trace_conditions,
        "runs": run_rows,
        "outputs": output_paths,
        "notes": [
            "Only the selected source neuron receives external input.",
            "Every induced edge among the selected nodes is retained, including reverse or inhibitory edges.",
            "Coupling values are calibration probes for this simplified LIF model, not biological parameter estimates.",
            "This experiment does not model behavior, muscles, or FlyDoom inputs and outputs.",
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "story.md").write_text(
        _story_markdown(
            selection=selection,
            node_rows=node_rows,
            edge_rows=edge_rows,
            run_rows=run_rows,
            trace_conditions=trace_conditions,
            config=story_config,
            data_dir=paths.data_dir,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain propagation through a small native-sign pathway")
    parser.add_argument("--data-dir", type=Path, default=Path("data/working/male-cns-v1.0"))
    parser.add_argument("--output", type=Path, default=Path("outputs/circuit-story"))
    parser.add_argument("--min-weight", type=int, default=3)
    parser.add_argument("--duration-ms", type=float, default=40.0)
    parser.add_argument(
        "--coupling",
        action="append",
        type=float,
        help="Coupling value; repeat to override the default five-value sweep",
    )
    args = parser.parse_args()
    summary = run_circuit_story(
        MaleCNSPaths(args.data_dir),
        output_dir=args.output,
        min_weight=args.min_weight,
        coupling_values=args.coupling or DEFAULT_COUPLING_VALUES,
        config=PathwaySliceConfig(duration_ms=args.duration_ms),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

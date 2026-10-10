"""Scalable circuit containers for the closed-loop Arena.

The connectome selector and the LIF implementation deliberately remain
separate.  This module is the small piece of harness between them: it turns a
stage's annotated node/edge rows into one or two reusable LIF networks,
projects named sensory populations into currents, and aggregates descending
population spikes into inspectable toy motor votes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .simulation import LIFConfig, LIFNetwork, LIFState, LIFStepResult


INPUT_GROUPS = (
    "visual_left",
    "visual_center",
    "visual_right",
    "visual_motion",
    "visual_looming",
    "touch_left",
    "touch_right",
    "threat_urgency",
)

ACTION_ORDER = (
    "escape_left",
    "escape_right",
    "turn_left",
    "turn_right",
    "forward",
    "stop",
)


@dataclass(frozen=True)
class ArenaStage:
    """A cached graph stage and the metadata needed to run it."""

    stage: int
    target_node_count: int
    unified: bool
    channels: tuple[Any, ...]
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    selection: dict[str, Any]


@dataclass(frozen=True)
class CircuitStep:
    """Observable result from one stateful Arena circuit update."""

    spikes_by_network: dict[str, np.ndarray]
    voltages_by_network: dict[str, np.ndarray]
    currents_by_network: dict[str, np.ndarray]
    active_nodes: list[dict[str, Any]]
    output_votes: dict[str, float]
    output_nodes: dict[str, list[int]]


def _row_channels(row: Mapping[str, Any]) -> set[str]:
    channels = row.get("channels")
    if isinstance(channels, Sequence) and not isinstance(channels, (str, bytes)):
        return {str(channel) for channel in channels}
    channel = row.get("channel")
    return {str(channel)} if channel else set()


def _is_input_row(row: Mapping[str, Any], channel: str) -> bool:
    superclasses = {
        "vnc_sensory",
        "visual_projection",
        "ol_sensory",
        "visual_centrifugal",
    }
    if channel not in _row_channels(row):
        return False
    return row.get("superclass") in superclasses or row.get("role") == "source"


def _is_descending_row(row: Mapping[str, Any], channel: str | None = None) -> bool:
    if channel is not None and channel not in _row_channels(row):
        return False
    return row.get("superclass") == "descending_neuron" or row.get("role") == "target"


def _side(row: Mapping[str, Any]) -> str:
    value = str(row.get("soma_side") or row.get("somaSide") or "").upper()
    if value.startswith("L"):
        return "left"
    if value.startswith("R"):
        return "right"
    return "center"


class ArenaCircuitRuntime:
    """Compile one Arena stage and run named population inputs through it."""

    def __init__(
        self,
        stage: ArenaStage,
        config: LIFConfig,
        *,
        network_configs: Mapping[str, LIFConfig] | None = None,
    ) -> None:
        self.stage = stage
        self.config = config
        self.network_configs = dict(network_configs or {})
        self.networks: dict[str, LIFNetwork] = {}
        self.states: dict[str, LIFState] = {}
        self.node_rows = {int(row["body_id"]): dict(row) for row in stage.nodes}
        self.node_indices: dict[str, dict[int, int]] = {}
        self._input_fallbacks: dict[str, bool] = {}

        if stage.unified:
            node_ids = sorted(self.node_rows)
            network = LIFNetwork(
                node_ids,
                [int(edge["body_pre"]) for edge in stage.edges],
                [int(edge["body_post"]) for edge in stage.edges],
                [float(edge["weight"]) for edge in stage.edges],
                [float(edge["sign"]) for edge in stage.edges],
                config=config,
            )
            self.networks["merged"] = network
        else:
            for channel in stage.channels:
                network = LIFNetwork(
                    [node.body_id for node in channel.network.nodes],
                    [edge.body_pre for edge in channel.network.edges],
                    [edge.body_post for edge in channel.network.edges],
                    [edge.weight for edge in channel.network.edges],
                    [edge.sign for edge in channel.network.edges],
                    config=self.network_configs.get(channel.name, config),
                )
                self.networks[channel.name] = network

        for name, network in self.networks.items():
            self.states[name] = network.initial_state()
            self.node_indices[name] = dict(network.node_index)

        self.input_refs = self._build_input_refs()
        self.output_refs = self._build_output_refs()

    def _refs_for_rows(self, rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, int]]:
        refs: list[tuple[str, int]] = []
        for row in rows:
            body_id = int(row["body_id"])
            for network_name, indices in self.node_indices.items():
                if body_id in indices:
                    refs.append((network_name, indices[body_id]))
        return refs

    def _channel_rows(self, channel: str) -> list[dict[str, Any]]:
        return [
            row
            for row in self.node_rows.values()
            if channel in _row_channels(row)
        ]

    def _build_input_refs(self) -> dict[str, tuple[tuple[str, int], ...]]:
        refs: dict[str, tuple[tuple[str, int], ...]] = {}
        for channel, prefix in (("vision", "visual"), ("touch", "touch")):
            rows = [row for row in self._channel_rows(channel) if _is_input_row(row, channel)]
            if not rows:
                rows = self._channel_rows(channel)
            if not rows:
                continue
            by_side = {
                side: [row for row in rows if _side(row) == side]
                for side in ("left", "center", "right")
            }
            all_refs = tuple(self._refs_for_rows(rows))
            for side, group in by_side.items():
                specific_refs = tuple(self._refs_for_rows(group))
                side_refs = specific_refs or all_refs
                group_name = f"{prefix}_{side}"
                self._input_fallbacks[group_name] = not bool(specific_refs)
                if prefix == "visual":
                    refs[group_name] = side_refs
                else:
                    refs[group_name] = side_refs
            if prefix == "visual":
                refs["visual_motion"] = all_refs
                refs["visual_looming"] = all_refs
                self._input_fallbacks["visual_motion"] = False
                self._input_fallbacks["visual_looming"] = False
            else:
                refs["threat_urgency"] = all_refs
                self._input_fallbacks["threat_urgency"] = False

        for group in INPUT_GROUPS:
            refs.setdefault(group, ())
            self._input_fallbacks.setdefault(group, True)
        return refs

    def _build_output_refs(self) -> dict[str, tuple[tuple[str, int], ...]]:
        output_refs: dict[str, list[tuple[str, int]]] = {action: [] for action in ACTION_ORDER}
        descending = [
            row
            for row in self.node_rows.values()
            if _is_descending_row(row)
        ]
        if not descending:
            descending = list(self.node_rows.values())

        for row in descending:
            sides = _row_channels(row)
            body_id = int(row["body_id"])
            refs = self._refs_for_rows([row])
            side = _side(row)
            if "touch" in sides:
                action = "escape_right" if side == "left" else "escape_left"
                if side == "center":
                    action = "escape_right"
                output_refs[action].extend(refs)
            if "vision" in sides:
                action = {
                    "left": "turn_left",
                    "right": "turn_right",
                    "center": "forward",
                }[side]
                output_refs[action].extend(refs)

        # A tiny fixture or a sparse 54-node context may have only a single
        # descending target. Keep the network-driven path alive and expose the
        # fallback in the output metadata instead of returning no motor votes.
        if not any(output_refs[action] for action in ("turn_left", "turn_right", "forward")):
            vision_targets = [
                row for row in descending if "vision" in _row_channels(row)
            ]
            if vision_targets:
                output_refs["forward"].extend(self._refs_for_rows(vision_targets))
        if not any(output_refs[action] for action in ("escape_left", "escape_right")):
            touch_targets = [
                row for row in descending if "touch" in _row_channels(row)
            ]
            if touch_targets:
                output_refs["escape_right"].extend(self._refs_for_rows(touch_targets))

        return {
            action: tuple(
                sorted(
                    set(refs),
                    key=lambda ref: (int(self.networks[ref[0]].node_ids[ref[1]]), ref[0], ref[1]),
                )
            )
            for action, refs in output_refs.items()
        }

    def fresh_state(self) -> None:
        """Reset the compiled circuit to rest for a new replay."""

        self.states = {
            name: network.initial_state() for name, network in self.networks.items()
        }

    def new_run(self) -> "ArenaCircuitRuntime":
        """Create a state-isolated runner sharing this stage's compiled networks."""

        runner = object.__new__(type(self))
        runner.stage = self.stage
        runner.config = self.config
        runner.network_configs = self.network_configs
        runner.networks = self.networks
        runner.states = {
            name: network.initial_state() for name, network in self.networks.items()
        }
        runner.node_rows = self.node_rows
        runner.node_indices = self.node_indices
        runner.input_refs = self.input_refs
        runner.output_refs = self.output_refs
        runner._input_fallbacks = self._input_fallbacks
        return runner

    def group_metadata(self) -> dict[str, list[int]]:
        return {
            group: sorted(
                {
                    int(self.networks[name].node_ids[index])
                    for name, index in refs
                }
            )
            for group, refs in sorted(self.input_refs.items())
        }

    def group_details(self) -> dict[str, dict[str, Any]]:
        """Return population IDs and explicit 54-node sharing fallbacks."""

        body_ids = {
            group: {
                int(self.networks[name].node_ids[index])
                for name, index in refs
            }
            for group, refs in self.input_refs.items()
        }
        return {
            group: {
                "body_ids": sorted(ids),
                "fallback": bool(self._input_fallbacks.get(group, False)),
                "shared_with": sorted(
                    other for other, other_ids in body_ids.items()
                    if other != group and ids and ids == other_ids
                ),
            }
            for group, ids in sorted(body_ids.items())
        }

    def _external_currents(
        self,
        group_currents: Mapping[str, float],
    ) -> dict[str, np.ndarray]:
        external = {
            name: np.zeros(len(network.node_ids), dtype=np.float64)
            for name, network in self.networks.items()
        }
        for group, current in group_currents.items():
            if not np.isfinite(float(current)) or current == 0:
                continue
            for network_name, index in self.input_refs.get(group, ()):
                external[network_name][index] += float(current)
        return external

    def step(self, group_currents: Mapping[str, float]) -> CircuitStep:
        external = self._external_currents(group_currents)
        step_results: dict[str, LIFStepResult] = {}
        for name, network in self.networks.items():
            step_results[name] = network.step(self.states[name], external[name])

        active_nodes: list[dict[str, Any]] = []
        for network_name, result in step_results.items():
            network = self.networks[network_name]
            for index, active in enumerate(result.spikes.tolist()):
                if not active:
                    continue
                row = self.node_rows.get(int(network.node_ids[index]), {})
                active_nodes.append(
                    {
                        "channel": row.get("channel", network_name),
                        "channels": row.get("channels", [network_name]),
                        "body_id": int(network.node_ids[index]),
                        "neuron_index": index,
                        "role": row.get("role", "context"),
                        "superclass": row.get("superclass"),
                    }
                )

        votes: dict[str, float] = {action: 0.0 for action in ACTION_ORDER}
        output_nodes: dict[str, list[int]] = {action: [] for action in ACTION_ORDER}
        for action, refs in self.output_refs.items():
            for network_name, index in refs:
                if step_results[network_name].spikes[index]:
                    votes[action] += 1.0
                    output_nodes[action].append(
                        int(self.networks[network_name].node_ids[index])
                    )

        return CircuitStep(
            spikes_by_network={
                name: result.spikes.copy() for name, result in step_results.items()
            },
            voltages_by_network={
                name: result.voltage_mv.copy() for name, result in step_results.items()
            },
            currents_by_network={
                name: result.synaptic_currents_mv.copy() for name, result in step_results.items()
            },
            active_nodes=active_nodes,
            output_votes=votes,
            output_nodes=output_nodes,
        )

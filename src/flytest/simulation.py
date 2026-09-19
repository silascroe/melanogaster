"""A small configurable discrete-time leaky integrate-and-fire simulator.

The batch API remains the public baseline used by the original diagnostics.
``LIFNetwork`` and ``LIFState`` provide the same update one timestep at a time
for experiments whose sensory input depends on the body or world state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class LIFConfig:
    """Parameters for a current-based LIF network."""

    dt_ms: float = 1.0
    duration_ms: float = 100.0
    tau_ms: float = 20.0
    rest_mv: float = -65.0
    threshold_mv: float = -50.0
    reset_mv: float = -65.0
    refractory_ms: float = 2.0
    mv_per_synapse: float = 0.05
    synaptic_gain: float = 1.0
    synaptic_tau_ms: float | None = None
    input_current_mv: float = 80.0
    input_start_ms: float = 5.0
    input_duration_ms: float = 5.0

    def validate(self) -> None:
        if self.dt_ms <= 0:
            raise ValueError("dt_ms must be positive")
        if self.duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        if self.tau_ms <= 0:
            raise ValueError("tau_ms must be positive")
        if self.refractory_ms < 0:
            raise ValueError("refractory_ms cannot be negative")
        if self.mv_per_synapse < 0:
            raise ValueError("mv_per_synapse cannot be negative")
        if self.synaptic_gain < 0:
            raise ValueError("synaptic_gain cannot be negative")
        if self.synaptic_tau_ms is not None and self.synaptic_tau_ms <= 0:
            raise ValueError("synaptic_tau_ms must be positive or None")
        if self.input_duration_ms < 0:
            raise ValueError("input_duration_ms cannot be negative")


@dataclass(frozen=True)
class SimulationResult:
    """Voltage, spike, and aggregate synaptic-current traces."""

    times_ms: np.ndarray
    voltages_mv: np.ndarray
    spikes: np.ndarray
    node_ids: tuple[int, ...]
    synaptic_currents: np.ndarray | None = None

    def spike_counts(self) -> dict[int, int]:
        counts = self.spikes.sum(axis=0)
        return {body_id: int(counts[index]) for index, body_id in enumerate(self.node_ids)}

    def spike_events(self) -> list[dict[str, float | int]]:
        events: list[dict[str, float | int]] = []
        time_indices, node_indices = np.nonzero(self.spikes)
        for time_index, node_index in zip(time_indices.tolist(), node_indices.tolist()):
            events.append(
                {
                    "time_ms": float(self.times_ms[time_index]),
                    "body_id": int(self.node_ids[node_index]),
                    "neuron_index": int(node_index),
                }
            )
        return events


@dataclass
class LIFState:
    """Mutable state for one timestep of a compiled LIF network."""

    voltage_mv: np.ndarray
    refractory_steps: np.ndarray
    synaptic_state_mv: np.ndarray
    previous_spikes: np.ndarray


@dataclass(frozen=True)
class LIFStepResult:
    """The observable result of one LIF update."""

    voltage_mv: np.ndarray
    spikes: np.ndarray
    synaptic_currents_mv: np.ndarray


class LIFNetwork:
    """Compile a directed weighted network for repeated stateful updates."""

    def __init__(
        self,
        node_ids: Sequence[int],
        body_pre: Sequence[int],
        body_post: Sequence[int],
        synapse_counts: Sequence[float],
        signs: Sequence[float],
        *,
        config: LIFConfig | None = None,
    ) -> None:
        self.config = config or LIFConfig()
        self.config.validate()
        self.node_ids = tuple(int(body_id) for body_id in node_ids)
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("node_ids must be unique")
        self.node_index = {body_id: index for index, body_id in enumerate(self.node_ids)}

        try:
            self.pre = np.asarray(
                [self.node_index[int(body_id)] for body_id in body_pre], dtype=np.int64
            )
            self.post = np.asarray(
                [self.node_index[int(body_id)] for body_id in body_post], dtype=np.int64
            )
        except KeyError as error:
            raise ValueError(f"edge body ID is not in node_ids: {error.args[0]}") from error
        self.counts = np.asarray(synapse_counts, dtype=np.float64)
        self.edge_signs = np.asarray(signs, dtype=np.float64)
        if not (len(self.pre) == len(self.post) == len(self.counts) == len(self.edge_signs)):
            raise ValueError("edge arrays must have equal length")
        if np.any(self.counts < 0):
            raise ValueError("synapse counts must be non-negative")

        self.refractory_steps = int(round(self.config.refractory_ms / self.config.dt_ms))
        self.edge_current = (
            self.counts
            * self.edge_signs
            * self.config.mv_per_synapse
            * self.config.synaptic_gain
        )
        self.decay_factor = (
            None
            if self.config.synaptic_tau_ms is None
            else float(np.exp(-self.config.dt_ms / self.config.synaptic_tau_ms))
        )

    def initial_state(self) -> LIFState:
        """Return a fresh resting state for this network."""

        node_count = len(self.node_ids)
        return LIFState(
            voltage_mv=np.full(node_count, self.config.rest_mv, dtype=np.float64),
            refractory_steps=np.zeros(node_count, dtype=np.int64),
            synaptic_state_mv=np.zeros(node_count, dtype=np.float64),
            previous_spikes=np.zeros(node_count, dtype=bool),
        )

    def step(
        self,
        state: LIFState,
        external_current_mv: Sequence[float] | np.ndarray | None = None,
    ) -> LIFStepResult:
        """Advance one timestep, preserving the existing delayed edge update."""

        node_count = len(self.node_ids)
        if external_current_mv is None:
            external = np.zeros(node_count, dtype=np.float64)
        else:
            external = np.asarray(external_current_mv, dtype=np.float64)
            if external.shape != (node_count,):
                raise ValueError(
                    "external_current_mv must have one value per network node"
                )
            if not np.all(np.isfinite(external)):
                raise ValueError("external_current_mv must contain only finite values")

        if self.decay_factor is None:
            synaptic_current = np.zeros(node_count, dtype=np.float64)
        else:
            state.synaptic_state_mv *= self.decay_factor
            synaptic_current = state.synaptic_state_mv.copy()

        if len(self.pre) and state.previous_spikes.any():
            active_pre = state.previous_spikes[self.pre]
            if active_pre.any():
                if self.decay_factor is None:
                    np.add.at(synaptic_current, self.post[active_pre], self.edge_current[active_pre])
                else:
                    np.add.at(state.synaptic_state_mv, self.post[active_pre], self.edge_current[active_pre])
                    synaptic_current = state.synaptic_state_mv.copy()

        is_refractory = state.refractory_steps > 0
        state.voltage_mv[is_refractory] = self.config.reset_mv
        state.refractory_steps[is_refractory] -= 1
        free = ~is_refractory
        state.voltage_mv[free] += (self.config.dt_ms / self.config.tau_ms) * (
            (self.config.rest_mv - state.voltage_mv[free])
            + synaptic_current[free]
            + external[free]
        )
        fired = free & (state.voltage_mv >= self.config.threshold_mv)
        state.voltage_mv[fired] = self.config.reset_mv
        state.refractory_steps[fired] = self.refractory_steps
        state.previous_spikes = fired.copy()
        return LIFStepResult(
            voltage_mv=state.voltage_mv.copy(),
            spikes=fired.copy(),
            synaptic_currents_mv=synaptic_current.copy(),
        )


def simulate_lif(
    node_ids: Sequence[int],
    body_pre: Sequence[int],
    body_post: Sequence[int],
    synapse_counts: Sequence[float],
    signs: Sequence[float],
    *,
    input_nodes: Sequence[int] = (),
    config: LIFConfig | None = None,
    external_currents_mv: Sequence[Sequence[float]] | np.ndarray | None = None,
) -> SimulationResult:
    """Simulate a directed weighted network using an explicit Euler update.

    ``synapse_counts`` remains the positive anatomical magnitude. ``signs``
    supplies the transmitter-derived fast-current sign for each edge. The
    effective edge current is ``count * sign * mv_per_synapse * synaptic_gain``.
    With ``synaptic_tau_ms=None`` the current is the legacy one-step pulse. With
    a positive tau, the aggregate current state decays exponentially between
    delayed spike arrivals.
    """

    cfg = config or LIFConfig()
    network = LIFNetwork(
        node_ids,
        body_pre,
        body_post,
        synapse_counts,
        signs,
        config=cfg,
    )
    ids = network.node_ids
    node_index = network.node_index
    if any(int(body_id) not in node_index for body_id in input_nodes):
        missing = [int(body_id) for body_id in input_nodes if int(body_id) not in node_index]
        raise ValueError(f"input node(s) are not in node_ids: {missing}")

    n_steps = max(1, int(round(cfg.duration_ms / cfg.dt_ms)))
    times = np.arange(n_steps, dtype=np.float64) * cfg.dt_ms
    voltages = np.empty((n_steps, len(ids)), dtype=np.float64)
    spikes = np.zeros((n_steps, len(ids)), dtype=bool)
    synaptic_currents = np.empty((n_steps, len(ids)), dtype=np.float64)
    input_indices = np.asarray([node_index[int(body_id)] for body_id in input_nodes], dtype=np.int64)
    if external_currents_mv is None:
        external_trace = None
    else:
        external_trace = np.asarray(external_currents_mv, dtype=np.float64)
        if external_trace.shape != (n_steps, len(ids)):
            raise ValueError(
                "external_currents_mv must have shape (n_steps, node_count)"
            )
        if not np.all(np.isfinite(external_trace)):
            raise ValueError("external_currents_mv must contain only finite values")

    state = network.initial_state()
    for step, time_ms in enumerate(times):
        in_pulse = cfg.input_start_ms <= time_ms < (cfg.input_start_ms + cfg.input_duration_ms)
        external_current = np.zeros(len(ids), dtype=np.float64)
        if external_trace is not None:
            external_current += external_trace[step]
        if in_pulse and len(input_indices):
            external_current[np.unique(input_indices)] += cfg.input_current_mv
        step_result = network.step(state, external_current)
        spikes[step] = step_result.spikes
        voltages[step] = step_result.voltage_mv
        synaptic_currents[step] = step_result.synaptic_currents_mv

    return SimulationResult(
        times_ms=times,
        voltages_mv=voltages,
        spikes=spikes,
        node_ids=ids,
        synaptic_currents=synaptic_currents,
    )

"""A small configurable discrete-time leaky integrate-and-fire simulator."""

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


def simulate_lif(
    node_ids: Sequence[int],
    body_pre: Sequence[int],
    body_post: Sequence[int],
    synapse_counts: Sequence[float],
    signs: Sequence[float],
    *,
    input_nodes: Sequence[int] = (),
    config: LIFConfig | None = None,
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
    cfg.validate()
    ids = tuple(int(body_id) for body_id in node_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("node_ids must be unique")
    node_index = {body_id: index for index, body_id in enumerate(ids)}

    pre = np.asarray([node_index[int(body_id)] for body_id in body_pre], dtype=np.int64)
    post = np.asarray([node_index[int(body_id)] for body_id in body_post], dtype=np.int64)
    counts = np.asarray(synapse_counts, dtype=np.float64)
    edge_signs = np.asarray(signs, dtype=np.float64)
    if not (len(pre) == len(post) == len(counts) == len(edge_signs)):
        raise ValueError("edge arrays must have equal length")
    if np.any(counts < 0):
        raise ValueError("synapse counts must be non-negative")
    if any(int(body_id) not in node_index for body_id in input_nodes):
        missing = [int(body_id) for body_id in input_nodes if int(body_id) not in node_index]
        raise ValueError(f"input node(s) are not in node_ids: {missing}")

    n_steps = max(1, int(round(cfg.duration_ms / cfg.dt_ms)))
    times = np.arange(n_steps, dtype=np.float64) * cfg.dt_ms
    voltage = np.full(len(ids), cfg.rest_mv, dtype=np.float64)
    voltages = np.empty((n_steps, len(ids)), dtype=np.float64)
    spikes = np.zeros((n_steps, len(ids)), dtype=bool)
    synaptic_currents = np.empty((n_steps, len(ids)), dtype=np.float64)
    refractory_steps = int(round(cfg.refractory_ms / cfg.dt_ms))
    refractory = np.zeros(len(ids), dtype=np.int64)
    edge_current = counts * edge_signs * cfg.mv_per_synapse * cfg.synaptic_gain
    synaptic_state = np.zeros(len(ids), dtype=np.float64)
    decay_factor = (
        None
        if cfg.synaptic_tau_ms is None
        else float(np.exp(-cfg.dt_ms / cfg.synaptic_tau_ms))
    )
    input_indices = np.asarray([node_index[int(body_id)] for body_id in input_nodes], dtype=np.int64)

    for step, time_ms in enumerate(times):
        if decay_factor is None:
            synaptic_current = np.zeros(len(ids), dtype=np.float64)
        else:
            synaptic_state *= decay_factor
            synaptic_current = synaptic_state
        if step > 0 and len(pre):
            active_pre = spikes[step - 1, pre]
            if active_pre.any():
                if decay_factor is None:
                    np.add.at(synaptic_current, post[active_pre], edge_current[active_pre])
                else:
                    np.add.at(synaptic_state, post[active_pre], edge_current[active_pre])
                    synaptic_current = synaptic_state
        synaptic_currents[step] = synaptic_current

        in_pulse = cfg.input_start_ms <= time_ms < (cfg.input_start_ms + cfg.input_duration_ms)
        external_current = np.zeros(len(ids), dtype=np.float64)
        if in_pulse and len(input_indices):
            external_current[input_indices] = cfg.input_current_mv

        is_refractory = refractory > 0
        voltage[is_refractory] = cfg.reset_mv
        refractory[is_refractory] -= 1
        free = ~is_refractory
        voltage[free] += (cfg.dt_ms / cfg.tau_ms) * (
            (cfg.rest_mv - voltage[free]) + synaptic_current[free] + external_current[free]
        )
        fired = free & (voltage >= cfg.threshold_mv)
        spikes[step, fired] = True
        voltage[fired] = cfg.reset_mv
        refractory[fired] = refractory_steps
        voltages[step] = voltage

    return SimulationResult(
        times_ms=times,
        voltages_mv=voltages,
        spikes=spikes,
        node_ids=ids,
        synaptic_currents=synaptic_currents,
    )

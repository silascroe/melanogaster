"""Whole-brain leaky integrate-and-fire model with Shiu et al. (2024) settings.

A NumPy reimplementation of the dynamics in philshiu/Drosophila_brain_model
(`model.py`, Brian2). The connectome supplies who connects to whom and how
many synapses; every number below is a modelling assumption from that paper.

    dv/dt = (v_0 - v + g) / t_mbr      (not integrated while refractory)
    dg/dt = -g / tau                   (not integrated while refractory)
    presynaptic spike -> g_post += signed_synapses * w_syn after t_dly
    spike when v > v_th; reset v = v_rst, g = 0; refractory t_rfc
    stimulated neurons: Poisson events add w_syn * f_poi to v; no refractory
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class BrainParams:
    dt_ms: float = 0.1
    v_0_mv: float = -52.0
    v_rst_mv: float = -52.0
    v_th_mv: float = -45.0
    t_mbr_ms: float = 20.0
    tau_ms: float = 5.0
    t_rfc_ms: float = 2.2
    t_dly_ms: float = 1.8
    w_syn_mv: float = 0.275
    f_poi: float = 250.0


# Paper convention plus two decisions recorded in docs/whole_brain_protocol.md.
TRANSMITTER_SIGN = {
    "acetylcholine": 1.0, "dopamine": 1.0, "serotonin": 1.0, "octopamine": 1.0,
    "gaba": -1.0, "glutamate": -1.0, "histamine": -1.0,
}


@dataclass
class Connectome:
    """Synapses grouped by presynaptic neuron (CSC-like) for fast spike delivery."""
    n_neurons: int
    indptr: np.ndarray          # int64, length n_neurons + 1
    post: np.ndarray            # int32, postsynaptic index per connection
    weight_mv: np.ndarray       # float32, signed synapses * w_syn

    @classmethod
    def from_edges(cls, n_neurons: int, pre: np.ndarray, post: np.ndarray,
                   signed_synapses: np.ndarray, w_syn_mv: float) -> "Connectome":
        pre = np.asarray(pre, dtype=np.int64)
        order = np.argsort(pre, kind="stable")
        counts = np.bincount(pre, minlength=n_neurons)
        indptr = np.zeros(n_neurons + 1, dtype=np.int64)
        np.cumsum(counts, out=indptr[1:])
        return cls(n_neurons, indptr,
                   np.asarray(post, dtype=np.int32)[order],
                   (np.asarray(signed_synapses, dtype=np.float64)[order] * w_syn_mv).astype(np.float32))


@dataclass
class TrialResult:
    spike_counts: np.ndarray
    duration_ms: float
    spike_times_ms: dict[int, list[float]] = field(default_factory=dict)

    def rate_hz(self, indices) -> np.ndarray:
        return self.spike_counts[np.asarray(indices)] / (self.duration_ms / 1000.0)


def simulate(connectome: Connectome, *, duration_ms: float, poisson_targets=(),
             poisson_rate_hz: float = 150.0, seed: int = 0,
             params: BrainParams = BrainParams(), record=()) -> TrialResult:
    p = params
    n = connectome.n_neurons
    steps = int(round(duration_ms / p.dt_ms))
    delay = int(round(p.t_dly_ms / p.dt_ms))
    refractory_steps = int(round(p.t_rfc_ms / p.dt_ms))
    rng = np.random.default_rng(seed)
    v = np.full(n, p.v_0_mv, dtype=np.float64)
    g = np.zeros(n, dtype=np.float64)
    refractory_left = np.zeros(n, dtype=np.int32)
    no_refractory = np.zeros(n, dtype=bool)
    targets = np.asarray(poisson_targets, dtype=np.int64)
    no_refractory[targets] = True
    # Ring buffer of conductance increments waiting out the synaptic delay.
    pending = np.zeros((delay + 1, n), dtype=np.float64)
    counts = np.zeros(n, dtype=np.int64)
    record = set(int(i) for i in record)
    times: dict[int, list[float]] = {i: [] for i in record}
    v_decay = p.dt_ms / p.t_mbr_ms
    g_decay = p.dt_ms / p.tau_ms
    poisson_p = poisson_rate_hz * p.dt_ms / 1000.0
    kick = p.w_syn_mv * p.f_poi
    indptr, post, weight = connectome.indptr, connectome.post, connectome.weight_mv
    for step in range(steps):
        slot = step % (delay + 1)
        g += pending[slot]
        pending[slot] = 0.0
        active = refractory_left == 0
        # Forward Euler, as Brian2 uses for these linear equations by default.
        dv = (p.v_0_mv - v + g) * v_decay
        dg = -g * g_decay
        v[active] += dv[active]
        g[active] += dg[active]
        refractory_left[~active] -= 1
        if len(targets):
            hit = targets[rng.random(len(targets)) < poisson_p]
            v[hit] += kick
        fired = np.flatnonzero(v > p.v_th_mv)
        if len(fired):
            v[fired] = p.v_rst_mv
            g[fired] = 0.0
            refractory_left[fired] = np.where(no_refractory[fired], 0, refractory_steps)
            counts[fired] += 1
            for i in record.intersection(fired.tolist()):
                times[i].append(step * p.dt_ms)
            starts = indptr[fired]
            lengths = indptr[fired + 1] - starts
            total = int(lengths.sum())
            if total:
                # Flattened ranges [start, start + length) for every fired neuron.
                offsets = np.repeat(starts - (np.cumsum(lengths) - lengths), lengths)
                idx = np.arange(total, dtype=np.int64) + offsets
                out_slot = (step + delay) % (delay + 1)
                if total < n // 8:
                    np.add.at(pending[out_slot], post[idx], weight[idx])
                else:
                    pending[out_slot] += np.bincount(post[idx], weights=weight[idx], minlength=n)
    return TrialResult(counts, duration_ms, times)

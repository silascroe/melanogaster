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


try:  # Optional compiled engine; the NumPy loop below is the fallback.
    import numba
except ImportError:  # pragma: no cover - depends on the environment
    numba = None


def _step_kernel_py(v, g, w, refractory_left, pending, slot, out_slot, v_0, v_decay, g_decay,
                    w_decay, w_jump, hits, kick, v_th, v_rst, no_refractory, refractory_steps,
                    indptr, post, weight, counts, fired, scratch):
    """One 0.1 ms step. Mirrors the NumPy loop operation by operation, including
    the order in which conductance increments are summed, so results match exactly."""
    n = v.shape[0]
    for i in range(n):
        g[i] += pending[slot, i]
        pending[slot, i] = 0.0
        if refractory_left[i] == 0:
            dv = (v_0 - v[i] + g[i] - w[i]) * v_decay
            dg = g[i] * (-g_decay)
            v[i] += dv
            g[i] += dg
        else:
            refractory_left[i] -= 1
        w[i] += w[i] * (-w_decay)
    for k in range(hits.shape[0]):
        v[hits[k]] += kick
    fired_count = 0
    total = 0
    for i in range(n):
        if v[i] > v_th:
            v[i] = v_rst
            g[i] = 0.0
            refractory_left[i] = 0 if no_refractory[i] else refractory_steps
            w[i] += w_jump
            counts[i] += 1
            fired[fired_count] = i
            fired_count += 1
            total += indptr[i + 1] - indptr[i]
    if total == 0:
        return fired_count
    if total < n // 8:
        # np.add.at: sequential adds straight into the pending slot.
        for k in range(fired_count):
            i = fired[k]
            for e in range(indptr[i], indptr[i + 1]):
                pending[out_slot, post[e]] += np.float64(weight[e])
    else:
        # np.bincount: sum this step's increments first, then add to the slot.
        for k in range(fired_count):
            i = fired[k]
            for e in range(indptr[i], indptr[i + 1]):
                scratch[post[e]] += np.float64(weight[e])
        for j in range(n):
            pending[out_slot, j] += scratch[j]
            scratch[j] = 0.0
    return fired_count


_step_kernel = numba.njit(cache=True)(_step_kernel_py) if numba is not None else None


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
    # Spike-frequency adaptation (our addition; 0 = the published model).
    # AdEx "tonic" values (Brette & Gerstner 2005): b = 0.0805 nA x 10 MOhm.
    adapt_mv: float = 0.0
    adapt_tau_ms: float = 144.0


ADAPTIVE = BrainParams(adapt_mv=0.805)


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


class BrainRunner:
    """A persistent brain: state carries over between advance() calls, so a game
    can feed changing inputs and read outputs frame by frame.

    `input_neurons` are every neuron that may ever receive Poisson input; like the
    paper's stimulated neurons, they have no refractory period.
    """

    def __init__(self, connectome: Connectome, *, input_neurons=(), seed: int = 0,
                 params: BrainParams = BrainParams(), engine: str = "auto", record=()) -> None:
        p = self.params = params
        n = self.n = connectome.n_neurons
        self.connectome = connectome
        self.delay = int(round(p.t_dly_ms / p.dt_ms))
        self.refractory_steps = int(round(p.t_rfc_ms / p.dt_ms))
        self.rng = np.random.default_rng(seed)
        self.v = np.full(n, p.v_0_mv, dtype=np.float64)
        self.g = np.zeros(n, dtype=np.float64)
        self.w = np.zeros(n, dtype=np.float64)
        self.refractory_left = np.zeros(n, dtype=np.int32)
        self.no_refractory = np.zeros(n, dtype=bool)
        self.no_refractory[np.asarray(input_neurons, dtype=np.int64)] = True
        # Ring buffer of conductance increments waiting out the synaptic delay.
        self.pending = np.zeros((self.delay + 1, n), dtype=np.float64)
        self.counts = np.zeros(n, dtype=np.int64)
        self.step_index = 0
        self.v_decay = p.dt_ms / p.t_mbr_ms
        self.g_decay = p.dt_ms / p.tau_ms
        self.w_decay = p.dt_ms / p.adapt_tau_ms
        self.kick = p.w_syn_mv * p.f_poi
        if engine == "auto":
            engine = "numba" if _step_kernel is not None else "numpy"
        if engine == "numba" and _step_kernel is None:
            raise RuntimeError("engine='numba' requested but numba is not installed")
        self.engine = engine
        self.record = set(int(i) for i in record)
        self.spike_times_ms: dict[int, list[float]] = {i: [] for i in self.record}
        self._fired = np.empty(n, dtype=np.int64)
        self._scratch = np.zeros(n, dtype=np.float64)
        self._dv = np.empty(n, dtype=np.float64)
        self._dg = np.empty(n, dtype=np.float64)
        self._active = np.empty(n, dtype=bool)
        self._no_hits = np.empty(0, dtype=np.int64)

    def advance(self, duration_ms: float, inputs=()) -> np.ndarray:
        """Run for duration_ms with Poisson inputs [(neuron_indices, rate_hz), ...].
        Returns spike counts per neuron during this call."""
        p = self.params
        steps = int(round(duration_ms / p.dt_ms))
        groups = [(np.asarray(idx, dtype=np.int64), rate * p.dt_ms / 1000.0)
                  for idx, rate in inputs if rate > 0 and len(idx)]
        before = self.counts.copy()
        for _ in range(steps):
            if not groups:
                hits = self._no_hits
            elif len(groups) == 1:
                idx, prob = groups[0]
                hits = idx[self.rng.random(len(idx)) < prob]
            else:
                hits = np.concatenate([idx[self.rng.random(len(idx)) < prob] for idx, prob in groups])
            if self.engine == "numba":
                fired_count = self._step_numba(hits)
            else:
                fired_count = self._step_numpy(hits)
            if self.record and fired_count:
                for i in self.record.intersection(self._fired[:fired_count].tolist()):
                    self.spike_times_ms[i].append(self.step_index * p.dt_ms)
            self.step_index += 1
        return self.counts - before

    def _step_numba(self, hits: np.ndarray) -> int:
        p, d = self.params, self.delay
        c = self.connectome
        return _step_kernel(
            self.v, self.g, self.w, self.refractory_left, self.pending,
            self.step_index % (d + 1), (self.step_index + d) % (d + 1),
            p.v_0_mv, self.v_decay, self.g_decay, self.w_decay, p.adapt_mv,
            hits, self.kick, p.v_th_mv, p.v_rst_mv,
            self.no_refractory, self.refractory_steps, c.indptr, c.post, c.weight_mv,
            self.counts, self._fired, self._scratch)

    def _step_numpy(self, hits: np.ndarray) -> int:
        p, d, n = self.params, self.delay, self.n
        v, g, rl, pending = self.v, self.g, self.refractory_left, self.pending
        dv, dg, active = self._dv, self._dg, self._active
        slot = self.step_index % (d + 1)
        g += pending[slot]
        pending[slot] = 0.0
        np.equal(rl, 0, out=active)
        # Forward Euler, as Brian2 uses for these linear equations by default.
        # Multiplying by the 0/1 mask is bit-identical to updating only active
        # neurons, without the cost of boolean indexing.
        np.subtract(p.v_0_mv, v, out=dv)
        dv += g
        dv -= self.w
        dv *= self.v_decay
        np.multiply(g, -self.g_decay, out=dg)
        dv *= active
        dg *= active
        v += dv
        g += dg
        rl -= ~active
        self.w += self.w * (-self.w_decay)
        if len(hits):
            v[hits] += self.kick
        fired = np.flatnonzero(v > p.v_th_mv)
        if not len(fired):
            return 0
        v[fired] = p.v_rst_mv
        g[fired] = 0.0
        rl[fired] = np.where(self.no_refractory[fired], 0, self.refractory_steps)
        self.w[fired] += p.adapt_mv
        self.counts[fired] += 1
        self._fired[:len(fired)] = fired
        indptr, post, weight = self.connectome.indptr, self.connectome.post, self.connectome.weight_mv
        starts = indptr[fired]
        lengths = indptr[fired + 1] - starts
        total = int(lengths.sum())
        if total:
            # Flattened ranges [start, start + length) for every fired neuron.
            offsets = np.repeat(starts - (np.cumsum(lengths) - lengths), lengths)
            idx = np.arange(total, dtype=np.int64) + offsets
            out_slot = (self.step_index + d) % (d + 1)
            if total < n // 8:
                np.add.at(pending[out_slot], post[idx], weight[idx])
            else:
                pending[out_slot] += np.bincount(post[idx], weights=weight[idx], minlength=n)
        return len(fired)


def simulate(connectome: Connectome, *, duration_ms: float, poisson_targets=(),
             poisson_rate_hz: float = 150.0, seed: int = 0,
             params: BrainParams = BrainParams(), record=(),
             engine: str = "auto") -> TrialResult:
    """Run one trial from rest. engine: "numba" (compiled), "numpy", or "auto"
    (numba if installed). Both engines give bit-identical results for the same seed."""
    targets = np.asarray(poisson_targets, dtype=np.int64)
    runner = BrainRunner(connectome, input_neurons=targets, seed=seed, params=params,
                         engine=engine, record=record)
    runner.advance(duration_ms, [(targets, poisson_rate_hz)])
    return TrialResult(runner.counts, duration_ms, runner.spike_times_ms)

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


# Parallel engine. Loops index array views from zero and use unsigned indices,
# so the compiler can drop negative-index checks and vectorize the neuron update.

def _update_view(v, g, w, refractory_left, pending_row, v_0, v_decay, g_decay, w_decay):
    for i in range(v.shape[0]):
        g[i] += pending_row[i]
        pending_row[i] = 0.0
        if refractory_left[i] == 0:
            dv = (v_0 - v[i] + g[i] - w[i]) * v_decay
            dg = g[i] * (-g_decay)
            v[i] += dv
            g[i] += dg
        else:
            refractory_left[i] -= 1
        w[i] += w[i] * (-w_decay)


def _threshold_view(first, v, g, w, refractory_left, v_th, v_rst, no_refractory, refractory_steps,
                    w_jump, counts, fired):
    m = 0
    for i in range(v.shape[0]):
        if v[i] > v_th:
            v[i] = v_rst
            g[i] = 0.0
            refractory_left[i] = 0 if no_refractory[i] else refractory_steps
            w[i] += w_jump
            counts[i] += 1
            fired[m] = first + i
            m += 1
    return m


def _neuron_chunk(c, lo, hi, length, first, done, ring, v, g, w, refractory_left, pending, v_0,
                  v_decay, g_decay, w_decay, w_jump, kicks, kick_cells, kick, v_th, v_rst,
                  no_refractory, refractory_steps, counts, fired_buf, fired_n):
    vv, gg, ww, rr = v[lo:hi], g[lo:hi], w[lo:hi], refractory_left[lo:hi]
    nr, cc = no_refractory[lo:hi], counts[lo:hi]
    for k in range(length):
        _update_view(vv, gg, ww, rr, pending[(first + k) % ring, lo:hi], v_0, v_decay, g_decay, w_decay)
        # Poisson kicks after every neuron's update and before the threshold, as in
        # the serial step; repeated cells get repeated sequential adds.
        for r in range(kick_cells.shape[0]):
            i = kick_cells[r]
            if lo <= i and i < hi:
                for _ in range(kicks[done + k, r]):
                    v[i] += kick
        fired_n[c, k] = _threshold_view(lo, vv, gg, ww, rr, v_th, v_rst, nr, refractory_steps,
                                        w_jump, cc, fired_buf[c, k])


def _deliver_part(part, length, first, delay, pending, part_indptr, part_post, part_weight,
                  fired_buf, fired_n):
    starts = part_indptr[part]
    for k in range(length):
        row = pending[(first + k + delay) % (delay + 1)]
        for c in range(fired_n.shape[0]):
            for j in range(fired_n[c, k]):
                i = fired_buf[c, k, j]
                for e in range(starts[i], starts[i + 1]):
                    row[part_post[e]] += np.float64(part_weight[e])


def _advance_blocks_py(steps, step_index, delay, v, g, w, refractory_left, pending, v_0, v_decay,
                       g_decay, w_decay, w_jump, kicks, kick_cells, kick, v_th, v_rst,
                       no_refractory, refractory_steps, chunk_bounds, part_indptr, part_post,
                       part_weight, counts, fired_buf, fired_n):
    """Many 0.1 ms steps on several cores, bit-identical to _step_kernel.

    A spike reaches its targets `delay` steps later, so within a block of up to
    `delay` steps no neuron affects another: each core advances its own range of
    neurons through the block. Spike delivery is then split by postsynaptic
    neuron, and every core adds increments in the serial order (fired neurons
    ascending, connections in order), so each sum is the same floating-point sum."""
    chunks = chunk_bounds.shape[0] - 1
    parts = part_indptr.shape[0]
    done = 0
    while done < steps:
        length = min(delay, steps - done)
        first = step_index + done
        for c in numba.prange(chunks):
            _neuron_chunk(c, chunk_bounds[c], chunk_bounds[c + 1], length, first, done, delay + 1,
                          v, g, w, refractory_left, pending, v_0, v_decay, g_decay, w_decay, w_jump,
                          kicks, kick_cells, kick, v_th, v_rst, no_refractory, refractory_steps,
                          counts, fired_buf, fired_n)
        for part in numba.prange(parts):
            _deliver_part(part, length, first, delay, pending, part_indptr, part_post, part_weight,
                          fired_buf, fired_n)
        done += length


if numba is not None:
    _update_view = numba.njit(cache=True)(_update_view)
    _threshold_view = numba.njit(cache=True)(_threshold_view)
    _neuron_chunk = numba.njit(cache=True)(_neuron_chunk)
    _deliver_part = numba.njit(cache=True)(_deliver_part)
    _advance_blocks = numba.njit(parallel=True, cache=True)(_advance_blocks_py)
else:  # pragma: no cover - depends on the environment
    _advance_blocks = None


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
    _parts: dict = field(default_factory=dict, repr=False, compare=False)

    def partitioned(self, parts: int, block: int = 64) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Connections split into `parts` sets of postsynaptic neurons, dealt out in
        blocks of `block` neurons so busy regions spread over every part; each part
        keeps connections grouped by presynaptic neuron in the original order.
        Returns (indptr[parts, n + 1] into the arrays, post, weight)."""
        if parts not in self._parts:
            n = self.n_neurons
            part_of = (self.post // block) % parts
            pre = np.repeat(np.arange(n), np.diff(self.indptr))
            indptr = np.zeros((parts, n + 1), dtype=np.uint64)
            posts, weights, offset = [], [], 0
            for part in range(parts):
                keep = part_of == part
                indptr[part, 1:] = offset + np.cumsum(np.bincount(pre[keep], minlength=n))
                indptr[part, 0] = offset
                posts.append(self.post[keep])
                weights.append(self.weight_mv[keep])
                offset += int(keep.sum())
            self._parts[parts] = (indptr, np.concatenate(posts).astype(np.uint32),
                                  np.concatenate(weights))
        return self._parts[parts]

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
            engine = "parallel" if _advance_blocks is not None else "numpy"
        if engine not in ("numpy", "numba", "parallel"):
            raise ValueError(f"unknown engine {engine!r}")
        if engine != "numpy" and _step_kernel is None:
            raise RuntimeError(f"engine={engine!r} requested but numba is not installed")
        self.engine = engine
        self.record = set(int(i) for i in record)
        self.spike_times_ms: dict[int, list[float]] = {i: [] for i in self.record}
        self._fired = np.empty(n, dtype=np.int64)
        self._scratch = np.zeros(n, dtype=np.float64)
        self._dv = np.empty(n, dtype=np.float64)
        self._dg = np.empty(n, dtype=np.float64)
        self._active = np.empty(n, dtype=bool)
        self._no_hits = np.empty(0, dtype=np.int64)
        if engine == "parallel":
            threads = numba.get_num_threads()
            self._chunk_bounds = np.linspace(0, n, threads + 1).round().astype(np.int64)
            self._parts = connectome.partitioned(threads)
            widest = int(np.diff(self._chunk_bounds).max())
            self._fired_buf = np.empty((threads, max(self.delay, 1), widest), dtype=np.uint32)
            self._fired_n = np.zeros((threads, max(self.delay, 1)), dtype=np.int64)

    def advance(self, duration_ms: float, inputs=()) -> np.ndarray:
        """Run for duration_ms with Poisson inputs [(neuron_indices, rate_hz), ...].
        Returns spike counts per neuron during this call."""
        p = self.params
        steps = int(round(duration_ms / p.dt_ms))
        groups = [(np.asarray(idx, dtype=np.int64), rate * p.dt_ms / 1000.0)
                  for idx, rate in inputs if rate > 0 and len(idx)]
        before = self.counts.copy()
        if self.engine == "parallel" and not self.record and self.delay >= 1:
            self._advance_parallel(steps, groups)
            return self.counts - before
        for _ in range(steps):
            if not groups:
                hits = self._no_hits
            elif len(groups) == 1:
                idx, prob = groups[0]
                hits = idx[self.rng.random(len(idx)) < prob]
            else:
                hits = np.concatenate([idx[self.rng.random(len(idx)) < prob] for idx, prob in groups])
            if self.engine != "numpy":  # recording spike times uses the one-core step
                fired_count = self._step_numba(hits)
            else:
                fired_count = self._step_numpy(hits)
            if self.record and fired_count:
                for i in self.record.intersection(self._fired[:fired_count].tolist()):
                    self.spike_times_ms[i].append(self.step_index * p.dt_ms)
            self.step_index += 1
        return self.counts - before

    def _advance_parallel(self, steps: int, groups) -> None:
        p = self.params
        indptr, post, weight = self._parts
        if groups:
            cells = np.concatenate([idx for idx, _ in groups])
            probs = np.concatenate([np.full(len(idx), prob) for idx, prob in groups])
            unique, column_row = np.unique(cells, return_inverse=True)
        else:
            unique = self._no_hits
        # At most 1000 steps (100 ms) of random draws in memory at a time.
        while steps > 0:
            batch = min(steps, 1000)
            if groups:
                # The same draws as the per-step loop: one row per step, groups in
                # order, so drawing all rows at once gives the identical stream.
                hit = self.rng.random((batch, len(cells))) < probs
                kicks = np.zeros((batch, len(unique)), dtype=np.int64)
                for column, row in enumerate(column_row):
                    kicks[:, row] += hit[:, column]
            else:
                kicks = np.zeros((batch, 0), dtype=np.int64)
            _advance_blocks(
                batch, self.step_index, self.delay, self.v, self.g, self.w, self.refractory_left,
                self.pending, p.v_0_mv, self.v_decay, self.g_decay, self.w_decay, p.adapt_mv,
                kicks, unique, self.kick, p.v_th_mv, p.v_rst_mv, self.no_refractory,
                self.refractory_steps, self._chunk_bounds, indptr, post, weight, self.counts,
                self._fired_buf, self._fired_n)
            self.step_index += batch
            steps -= batch

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
    """Run one trial from rest. engine: "parallel" (compiled, all cores), "numba"
    (compiled, one core), "numpy", or "auto" (parallel if numba is installed). All
    engines give bit-identical results for the same seed."""
    targets = np.asarray(poisson_targets, dtype=np.int64)
    runner = BrainRunner(connectome, input_neurons=targets, seed=seed, params=params,
                         engine=engine, record=record)
    runner.advance(duration_ms, [(targets, poisson_rate_hz)])
    return TrialResult(runner.counts, duration_ms, runner.spike_times_ms)

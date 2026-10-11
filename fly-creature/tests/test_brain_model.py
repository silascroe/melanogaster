import math

import numpy as np

from fly_creature.brain_model import BrainParams, Connectome, simulate


def _pair(signed_synapses: float) -> Connectome:
    # Neuron 0 (driven) -> neuron 1, with a third unconnected neuron.
    return Connectome.from_edges(3, np.array([0]), np.array([1]),
                                 np.array([signed_synapses]), BrainParams().w_syn_mv)


def test_silent_without_input():
    result = simulate(_pair(500), duration_ms=200)
    assert result.spike_counts.sum() == 0


def test_poisson_target_fires_at_roughly_input_rate():
    result = simulate(_pair(0), duration_ms=2000, poisson_targets=[0], seed=1)
    assert 250 <= result.spike_counts[0] <= 350  # 150 Hz for 2 s, each event crosses threshold


def test_spike_arrives_after_synaptic_delay():
    result = simulate(_pair(1000), duration_ms=100, poisson_targets=[0], seed=3, record=[0, 1])
    first_pre = result.spike_times_ms[0][0]
    first_post = result.spike_times_ms[1][0]
    assert 1.8 <= first_post - first_pre <= 2.5


def test_single_input_threshold_matches_analytic_peak():
    # Continuous solution for one conductance kick w from rest:
    # v - v_0 = w * tau / (t_mbr - tau) * (exp(-t/t_mbr) - exp(-t/tau)), peak ~0.1575 w.
    p = BrainParams()
    t_peak = math.log(p.t_mbr_ms / p.tau_ms) * p.t_mbr_ms * p.tau_ms / (p.t_mbr_ms - p.tau_ms)
    gain = p.tau_ms / (p.t_mbr_ms - p.tau_ms) * (math.exp(-t_peak / p.t_mbr_ms) - math.exp(-t_peak / p.tau_ms))
    w_needed = (p.v_th_mv - p.v_0_mv) / gain
    below = w_needed * 0.93 / p.w_syn_mv
    above = w_needed * 1.07 / p.w_syn_mv
    # Find a low-rate trial with exactly one presynaptic spike early enough for
    # its full effect on neuron 1 (peak ~9 ms after arrival) to fit in the window.
    def post_spikes(synapses: float) -> int:
        conn = _pair(synapses)
        for seed in range(500):
            probe = simulate(conn, duration_ms=60, poisson_targets=[0], seed=seed,
                             poisson_rate_hz=15.0, record=[0])
            times = probe.spike_times_ms[0]
            if len(times) == 1 and times[0] < 30:
                return int(probe.spike_counts[1])
        raise AssertionError("No isolated presynaptic spike found")
    assert post_spikes(below) == 0
    assert post_spikes(above) >= 1


def test_inhibition_prevents_spiking():
    result = simulate(_pair(-1000), duration_ms=200, poisson_targets=[0], seed=2)
    assert result.spike_counts[1] == 0


def test_numba_engine_matches_numpy_exactly():
    import pytest
    from fly_creature import brain_model
    if brain_model._step_kernel is None:
        pytest.skip("numba not installed")
    rng = np.random.default_rng(5)
    n, m = 400, 12000
    pre, post = rng.integers(0, n, m), rng.integers(0, n, m)
    signed = rng.integers(1, 40, m) * np.where(rng.random(m) < 0.25, -1, 1)
    conn = Connectome.from_edges(n, pre, post, signed, BrainParams().w_syn_mv)
    a = simulate(conn, duration_ms=300, poisson_targets=np.arange(40), seed=9, engine="numpy")
    b = simulate(conn, duration_ms=300, poisson_targets=np.arange(40), seed=9, engine="numba")
    assert a.spike_counts.sum() > 1000
    assert np.array_equal(a.spike_counts, b.spike_counts)


def test_runner_in_frames_matches_one_long_run():
    from fly_creature.brain_model import BrainRunner
    rng = np.random.default_rng(6)
    n, m = 300, 8000
    conn = Connectome.from_edges(n, rng.integers(0, n, m), rng.integers(0, n, m),
                                 rng.integers(1, 40, m), BrainParams().w_syn_mv)
    targets = np.arange(30)
    whole = simulate(conn, duration_ms=200, poisson_targets=targets, seed=4)
    runner = BrainRunner(conn, input_neurons=targets, seed=4)
    for _ in range(4):  # four 50 ms game frames
        runner.advance(50, [(targets, 150.0)])
    assert whole.spike_counts.sum() > 500
    assert np.array_equal(whole.spike_counts, runner.counts)


def test_adaptation_engines_match_and_reduce_firing():
    import pytest
    from fly_creature import brain_model
    from fly_creature.brain_model import ADAPTIVE
    rng = np.random.default_rng(8)
    n, m = 300, 9000
    conn = Connectome.from_edges(n, rng.integers(0, n, m), rng.integers(0, n, m),
                                 rng.integers(1, 40, m), BrainParams().w_syn_mv)
    plain = simulate(conn, duration_ms=300, poisson_targets=np.arange(30), seed=2)
    adapted = simulate(conn, duration_ms=300, poisson_targets=np.arange(30), seed=2,
                       params=ADAPTIVE, engine="numpy")
    assert adapted.spike_counts.sum() < plain.spike_counts.sum()
    if brain_model._step_kernel is not None:
        compiled = simulate(conn, duration_ms=300, poisson_targets=np.arange(30), seed=2,
                            params=ADAPTIVE, engine="numba")
        assert np.array_equal(adapted.spike_counts, compiled.spike_counts)

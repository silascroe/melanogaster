import numpy as np
import pytest

from flytest.simulation import LIFConfig, simulate_lif


def test_excitatory_and_inhibitory_edges_use_transmitter_sign() -> None:
    result = simulate_lif(
        node_ids=[1, 2, 3],
        body_pre=[1, 1],
        body_post=[2, 3],
        synapse_counts=[10, 10],
        signs=[1, -1],
        input_nodes=[1],
        config=LIFConfig(
            dt_ms=1,
            duration_ms=4,
            tau_ms=1,
            rest_mv=0,
            threshold_mv=1,
            reset_mv=0,
            refractory_ms=0,
            mv_per_synapse=0.2,
            input_current_mv=2,
            input_start_ms=0,
            input_duration_ms=1,
        ),
    )

    counts = result.spike_counts()
    assert counts[1] == 1
    assert counts[2] == 1
    assert counts[3] == 0


def test_configurable_pulse_can_drive_one_neuron() -> None:
    result = simulate_lif(
        node_ids=[7],
        body_pre=[],
        body_post=[],
        synapse_counts=[],
        signs=[],
        input_nodes=[7],
        config=LIFConfig(
            dt_ms=1,
            duration_ms=3,
            tau_ms=10,
            rest_mv=-65,
            threshold_mv=-60,
            reset_mv=-65,
            refractory_ms=0,
            input_current_mv=60,
            input_start_ms=0,
            input_duration_ms=1,
        ),
    )
    assert result.spike_events()[0]["body_id"] == 7


def test_explicit_legacy_synapse_settings_match_default_behavior() -> None:
    kwargs = {
        "node_ids": [1, 2],
        "body_pre": [1],
        "body_post": [2],
        "synapse_counts": [10],
        "signs": [1],
        "input_nodes": [1],
    }
    default = simulate_lif(
        **kwargs,
        config=LIFConfig(
            duration_ms=8,
            input_current_mv=80,
            input_start_ms=0,
            input_duration_ms=1,
        ),
    )
    explicit = simulate_lif(
        **kwargs,
        config=LIFConfig(
            duration_ms=8,
            input_current_mv=80,
            input_start_ms=0,
            input_duration_ms=1,
            synaptic_gain=1.0,
            synaptic_tau_ms=None,
        ),
    )
    np.testing.assert_array_equal(default.voltages_mv, explicit.voltages_mv)
    np.testing.assert_array_equal(default.spikes, explicit.spikes)
    np.testing.assert_array_equal(default.synaptic_currents, explicit.synaptic_currents)


def test_exponential_synaptic_current_preserves_delay_and_decays() -> None:
    result = simulate_lif(
        node_ids=[1, 2],
        body_pre=[1],
        body_post=[2],
        synapse_counts=[1],
        signs=[1],
        input_nodes=[1],
        config=LIFConfig(
            dt_ms=1,
            duration_ms=4,
            tau_ms=10,
            rest_mv=0,
            threshold_mv=1,
            reset_mv=0,
            refractory_ms=2,
            mv_per_synapse=1,
            synaptic_gain=3,
            synaptic_tau_ms=5,
            input_current_mv=10,
            input_start_ms=0,
            input_duration_ms=1,
        ),
    )

    assert result.spikes[0, 0] is True or bool(result.spikes[0, 0]) is True
    assert result.synaptic_currents is not None
    assert result.synaptic_currents[0, 1] == 0.0
    assert result.synaptic_currents[1, 1] == 3.0
    assert result.synaptic_currents[2, 1] == pytest.approx(3.0 * np.exp(-1.0 / 5.0))


def test_synaptic_parameters_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="synaptic_gain"):
        simulate_lif(
            node_ids=[1],
            body_pre=[],
            body_post=[],
            synapse_counts=[],
            signs=[],
            config=LIFConfig(synaptic_gain=-1),
        )
    with pytest.raises(ValueError, match="synaptic_tau_ms"):
        simulate_lif(
            node_ids=[1],
            body_pre=[],
            body_post=[],
            synapse_counts=[],
            signs=[],
            config=LIFConfig(synaptic_tau_ms=0),
        )

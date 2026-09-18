from flytest.propagation_diagnostic import PropagationDiagnosticConfig, run_propagation_matrix


def test_permissive_edge_spikes_one_step_and_conservative_edge_stays_silent() -> None:
    report = run_propagation_matrix(
        [10732, 10968],
        [{"body_pre": 10732, "body_post": 10968, "weight": 234, "sign": 1.0}],
        config=PropagationDiagnosticConfig(duration_ms=30),
    )
    rows = {(row["sign_mode"], row["coupling_mv_per_synapse"]): row for row in report["results"]}

    conservative = rows[("native", 0.05)]
    permissive = rows[("forced_excitatory", 1.5)]

    assert conservative["source_spike_count"] == 1
    assert conservative["target_spike_count"] == 0
    assert conservative["one_step_target_spike"] is False
    assert permissive["source_spike_count"] == 1
    assert permissive["target_spike_count"] == 1
    assert permissive["target_first_spike_ms"] == permissive["source_first_spike_ms"] + 1.0
    assert permissive["one_step_target_spike"] is True

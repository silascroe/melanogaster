import csv
import math

import pytest

from flytest.synaptic_dynamics_diagnostic import (
    DiagnosticGraph,
    SynapticDynamicsConfig,
    _write_artifacts,
    run_synaptic_dynamics_matrix,
)


def test_synaptic_dynamics_matrix_reports_gain_and_decay(tmp_path) -> None:
    graph = DiagnosticGraph(
        name="fixture_path",
        node_ids=(1, 2, 3),
        edges=(
            {"body_pre": 1, "body_post": 2, "weight": 1, "sign": 1},
            {"body_pre": 2, "body_post": 3, "weight": 1, "sign": 1},
        ),
        source_id=1,
        intermediate_id=2,
        target_id=3,
    )
    report, traces = run_synaptic_dynamics_matrix(
        [graph],
        config=SynapticDynamicsConfig(
            mv_per_synapse=1.0,
            dt_ms=1.0,
            duration_ms=6.0,
            tau_ms=1.0,
            rest_mv=0.0,
            threshold_mv=1.0,
            reset_mv=0.0,
            refractory_ms=2.0,
            input_current_mv=2.0,
            input_start_ms=0.0,
            input_duration_ms=1.0,
        ),
        gain_values=[1.0, 3.0],
        tau_values=[None, 1.0],
    )

    assert len(report["results"]) == 4
    assert len(traces) == 4 * 6 * 3
    exponential_gain_three = [
        row
        for row in traces
        if row["synaptic_mode"] == "exponential"
        and row["synaptic_gain"] == 3.0
        and row["body_id"] == 2
    ]
    assert exponential_gain_three[0]["synaptic_current"] == 0.0
    assert exponential_gain_three[1]["synaptic_current"] == pytest.approx(3.0)
    assert exponential_gain_three[2]["synaptic_current"] == pytest.approx(3.0 * math.exp(-1.0))

    output_dir = tmp_path / "diagnostics"
    _write_artifacts(report, traces, output_dir)
    with (output_dir / "synaptic_dynamics_matrix.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert (output_dir / "synaptic_dynamics_traces.csv").is_file()

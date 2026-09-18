import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather

from flytest.circuit_story import run_circuit_story
from flytest.data import (
    ANNOTATION_FILENAME,
    NEUROTRANSMITTER_FILENAME,
    WEIGHTS_FILENAME,
    MaleCNSPaths,
)
from flytest.pathway_slice import PathwaySliceConfig


def _write_circuit_fixture(tmp_path: Path) -> MaleCNSPaths:
    data_dir = tmp_path / "male-cns-v1.0"
    data_dir.mkdir()
    feather.write_feather(
        pa.table(
            {
                "bodyId": [1, 2, 3, 4, 5],
                "type": ["SN", "IN", "DN", "SN", "IN"],
                "instance": ["SN_L", "IN_L", "DN_L", "SN_R", "IN_R"],
                "status": ["Traced", "Traced", "Traced", "Traced", "Orphan"],
                "superclass": [
                    "vnc_sensory",
                    "vnc_intrinsic",
                    "descending_neuron",
                    "vnc_sensory",
                    "vnc_intrinsic",
                ],
                "class": [None, None, None, None, None],
                "somaSide": ["L", "L", "L", "R", "R"],
            }
        ),
        data_dir / ANNOTATION_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body": [1, 2, 3, 4, 5],
                "cell_type": ["SN", "IN", "DN", "SN", "IN"],
                "predicted_nt": ["acetylcholine", "acetylcholine", "gaba", "gaba", "acetylcholine"],
                "predicted_nt_confidence": [0.9, 0.9, 0.9, 0.9, 0.9],
                "consensus_nt": ["acetylcholine", "acetylcholine", "gaba", "gaba", "acetylcholine"],
                "total_nt_predictions": [10, 10, 10, 10, 10],
            }
        ),
        data_dir / NEUROTRANSMITTER_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body_pre": [1, 2, 4, 2, 3, 5, 3],
                "body_post": [2, 3, 2, 1, 1, 3, 2],
                "weight": [10, 10, 100, 5, 6, 100, 2],
            }
        ),
        data_dir / WEIGHTS_FILENAME,
    )
    return MaleCNSPaths(data_dir)


def _story_config(duration_ms: float = 6.0) -> PathwaySliceConfig:
    return PathwaySliceConfig(
        duration_ms=duration_ms,
        tau_ms=1.0,
        rest_mv=0.0,
        threshold_mv=1.0,
        reset_mv=0.0,
        refractory_ms=2.0,
        input_current_mv=2.0,
        input_start_ms=0.0,
        input_duration_ms=1.0,
    )


def test_circuit_story_writes_explainable_key_conditions(tmp_path: Path) -> None:
    output_dir = tmp_path / "circuit-story"
    summary = run_circuit_story(
        _write_circuit_fixture(tmp_path),
        output_dir=output_dir,
        coupling_values=[0.01, 0.2],
        config=_story_config(),
    )

    assert summary["path"] == {
        "source_id": 1,
        "intermediate_id": 2,
        "target_id": 3,
        "path_edge_keys": [[1, 2, 10], [2, 3, 10]],
    }
    assert summary["trace_selection"] == [
        {
            "label": "conservative_reference",
            "coupling_mv_per_synapse": 0.01,
            "run_index": 0,
        },
        {
            "label": "first_complete_path",
            "coupling_mv_per_synapse": 0.2,
            "run_index": 1,
        },
    ]
    assert summary["runs"][0]["complete_path"] is False
    assert summary["runs"][1]["complete_path"] is True
    assert summary["runs"][1]["source_first_spike_ms"] == 0.0
    assert summary["runs"][1]["intermediate_first_spike_ms"] == 1.0
    assert summary["runs"][1]["target_first_spike_ms"] == 2.0

    written_summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert written_summary["synaptic_parameters"] == {
        "sign_mode": "native stored signs",
        "synaptic_gain": 1.0,
        "synaptic_tau_ms": None,
    }
    story = (output_dir / "story.md").read_text(encoding="utf-8")
    assert "first complete condition" in story
    assert "Native transmitter signs are used" in story

    with (output_dir / "runs.csv").open(newline="", encoding="utf-8") as handle:
        runs = list(csv.DictReader(handle))
    assert len(runs) == 2
    assert runs[1]["complete_path"] == "True"

    with (output_dir / "key_traces.csv").open(newline="", encoding="utf-8") as handle:
        traces = list(csv.DictReader(handle))
    assert {row["condition_label"] for row in traces} == {
        "conservative_reference",
        "first_complete_path",
    }
    assert len(traces) == 2 * 6 * 3
    assert (output_dir / "nodes.csv").is_file()
    assert (output_dir / "edges.csv").is_file()
    assert (output_dir / "key_edge_contributions.csv").is_file()

    with (output_dir / "edges.csv").open(newline="", encoding="utf-8") as handle:
        edges = list(csv.DictReader(handle))
    path_edges = {
        (int(row["body_pre"]), int(row["body_post"])): row
        for row in edges
        if row["is_path_edge"] == "True"
    }
    assert path_edges[(1, 2)]["weight"] == "10"
    assert path_edges[(1, 2)]["sign"] == "1.0"
    assert path_edges[(2, 3)]["weight"] == "10"
    assert path_edges[(2, 3)]["sign"] == "1.0"


def test_circuit_story_uses_highest_coupling_when_path_stays_silent(tmp_path: Path) -> None:
    summary = run_circuit_story(
        _write_circuit_fixture(tmp_path),
        output_dir=tmp_path / "silent-story",
        coupling_values=[0.01],
        config=_story_config(duration_ms=4.0),
    )

    assert summary["trace_selection"] == [
        {
            "label": "conservative_reference",
            "coupling_mv_per_synapse": 0.01,
            "run_index": 0,
        }
    ]
    assert summary["runs"][0]["complete_path"] is False

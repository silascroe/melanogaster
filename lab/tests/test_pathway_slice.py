import csv
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather

from flytest.analysis import select_native_pathway
from flytest.data import (
    ANNOTATION_FILENAME,
    NEUROTRANSMITTER_FILENAME,
    WEIGHTS_FILENAME,
    MaleCNSPaths,
)
from flytest.pathway_slice import PathwaySliceConfig, run_pathway_slice


def _write_pathway_fixture(tmp_path: Path) -> MaleCNSPaths:
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


def test_selector_uses_native_positive_two_hop_path(tmp_path: Path) -> None:
    selection = select_native_pathway(_write_pathway_fixture(tmp_path))

    assert (selection.source_id, selection.intermediate_id, selection.target_id) == (1, 2, 3)
    assert selection.path_edge_keys == ((1, 2, 10), (2, 3, 10))
    assert {node.body_id for node in selection.nodes} == {1, 2, 3}
    assert {(edge.body_pre, edge.body_post) for edge in selection.edges} == {
        (1, 2),
        (2, 3),
        (2, 1),
        (3, 1),
    }
    assert selection.selection["candidate_count"] == 1


def test_pathway_slice_records_silent_and_complete_conditions(tmp_path: Path) -> None:
    output_dir = tmp_path / "pathway-slice"
    summary = run_pathway_slice(
        _write_pathway_fixture(tmp_path),
        output_dir=output_dir,
        coupling_values=[0.01, 0.2],
        config=PathwaySliceConfig(
            duration_ms=6,
            tau_ms=1.0,
            rest_mv=0.0,
            threshold_mv=1.0,
            reset_mv=0.0,
            refractory_ms=2.0,
            input_current_mv=2.0,
            input_start_ms=0.0,
            input_duration_ms=1.0,
        ),
    )

    runs = {row["coupling_mv_per_synapse"]: row for row in summary["runs"]}
    assert runs[0.01]["source_spike_count"] == 1
    assert runs[0.01]["intermediate_spike_count"] == 0
    assert runs[0.01]["complete_path"] is False
    assert runs[0.2]["source_first_spike_ms"] == 0.0
    assert runs[0.2]["intermediate_first_spike_ms"] == 1.0
    assert runs[0.2]["target_first_spike_ms"] == 2.0
    assert runs[0.2]["complete_path"] is True

    with (output_dir / "edge_contributions.csv").open(newline="", encoding="utf-8") as handle:
        contributions = list(csv.DictReader(handle))
    source_leg = [row for row in contributions if row["path_leg"] == "source_to_intermediate"]
    assert any(row["arrival_time_ms"] == "1.0" for row in source_leg)

    written_summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert written_summary["node_count"] == 3
    assert (output_dir / "runs.csv").is_file()
    assert (output_dir / "voltages.csv").is_file()

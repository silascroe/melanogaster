from pathlib import Path

import pyarrow as pa
import pyarrow.feather as feather
import pytest

from flytest.data import (
    ANNOTATION_FILENAME,
    NEUROTRANSMITTER_FILENAME,
    WEIGHTS_FILENAME,
    MaleCNSPaths,
)
from flytest.sensorimotor import SensorimotorConfig
from flytest.visual_simulation import VisualModel


def _write_visual_fixture(tmp_path: Path) -> MaleCNSPaths:
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


def test_visual_model_returns_context_graph_and_body_trajectory(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    payload = model.run(
        SensorimotorConfig(
            duration_ms=6.0,
            tau_ms=1.0,
            rest_mv=0.0,
            threshold_mv=1.0,
            reset_mv=0.0,
            refractory_ms=2.0,
            coupling_mv_per_synapse=0.2,
            input_current_mv=2.0,
            input_start_ms=0.0,
            input_duration_ms=1.0,
            turn_degrees_per_target_spike=20.0,
            forward_step_per_target_spike=2.0,
        )
    )

    assert payload["network"]["node_count"] >= 3
    assert payload["network"]["edge_count"] >= 2
    assert {node["role"] for node in payload["nodes"]} >= {"source", "intermediate", "target"}
    assert len(payload["trajectory"]) == 6
    assert payload["outcome"]["target_spike_count"] == 1
    assert payload["outcome"]["final_heading_degrees"] == 20.0
    assert payload["outcome"]["final_position"] == [
        pytest.approx(2.0 * 0.9396926208),
        pytest.approx(2.0 * 0.3420201433),
    ]

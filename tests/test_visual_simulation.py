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
from flytest.visual_simulation import VisualModel, VisualRunConfig


def _write_visual_fixture(tmp_path: Path) -> MaleCNSPaths:
    data_dir = tmp_path / "male-cns-v1.0"
    data_dir.mkdir()
    body_ids = [1, 2, 3, 10, 11, 12]
    feather.write_feather(
        pa.table(
            {
                "bodyId": body_ids,
                "type": ["SN", "IN", "DN", "LC", "OL", "DN"],
                "instance": ["SN_L", "IN_L", "DN_L", "LC_R", "OL_R", "DN_R"],
                "status": ["Traced"] * len(body_ids),
                "superclass": [
                    "vnc_sensory",
                    "vnc_intrinsic",
                    "descending_neuron",
                    "visual_projection",
                    "ol_intrinsic",
                    "descending_neuron",
                ],
                "class": [None] * len(body_ids),
                "somaSide": ["L", "L", "L", "R", "R", "R"],
            }
        ),
        data_dir / ANNOTATION_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body": body_ids,
                "cell_type": ["SN", "IN", "DN", "LC", "OL", "DN"],
                "predicted_nt": ["acetylcholine"] * len(body_ids),
                "predicted_nt_confidence": [0.9] * len(body_ids),
                "consensus_nt": ["acetylcholine"] * len(body_ids),
                "total_nt_predictions": [10] * len(body_ids),
            }
        ),
        data_dir / NEUROTRANSMITTER_FILENAME,
    )
    feather.write_feather(
        pa.table(
            {
                "body_pre": [1, 2, 2, 10, 11, 11],
                "body_post": [2, 3, 1, 11, 12, 10],
                "weight": [10, 10, 5, 10, 10, 5],
            }
        ),
        data_dir / WEIGHTS_FILENAME,
    )
    return MaleCNSPaths(data_dir)


def test_visual_model_runs_touch_and_vision_into_one_body(tmp_path: Path) -> None:
    model = VisualModel(_write_visual_fixture(tmp_path), neighbor_limit=4, max_edges=50)
    payload = model.run(
        VisualRunConfig(
            neural=SensorimotorConfig(
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
            ),
            visual_contrast=1.0,
            visual_coupling_mv_per_synapse=0.2,
            visual_target_x=7.0,
            visual_target_y=4.0,
        )
    )

    assert payload["network"]["node_count"] >= 6
    assert payload["network"]["edge_count"] >= 4
    assert payload["network"]["channels"].keys() == {"touch", "vision"}
    assert {node["channel"] for node in payload["nodes"]} == {"touch", "vision"}
    assert len(payload["trajectory"]) == 6
    assert payload["outcome"]["touch_target_spike_count"] == 1
    assert payload["outcome"]["visual_target_spike_count"] == 1
    assert payload["outcome"]["target_spike_count"] == 2
    assert payload["outcome"]["turn_event_count"] == 1
    assert payload["outcome"]["final_heading_degrees"] == pytest.approx(40.0)
    assert payload["outcome"]["final_position"] == [
        pytest.approx(2.0 * 0.7660444431),
        pytest.approx(2.0 * 0.6427876097),
    ]

    active = payload["spikes_by_time"]
    assert any(event["channel"] == "touch" for frame in active for event in frame)
    assert any(event["channel"] == "vision" for frame in active for event in frame)

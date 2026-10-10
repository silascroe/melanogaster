import csv
import json
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
from flytest.sensorimotor import SensorimotorConfig, run_sensorimotor


def _write_sensorimotor_fixture(tmp_path: Path) -> MaleCNSPaths:
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


def _config(*, coupling: float = 0.2) -> SensorimotorConfig:
    return SensorimotorConfig(
        duration_ms=6.0,
        coupling_mv_per_synapse=coupling,
        tau_ms=1.0,
        rest_mv=0.0,
        threshold_mv=1.0,
        reset_mv=0.0,
        refractory_ms=2.0,
        input_current_mv=2.0,
        input_start_ms=0.0,
        input_duration_ms=1.0,
        turn_degrees_per_target_spike=20.0,
        forward_step_per_target_spike=2.0,
    )


def test_descending_spikes_move_the_toy_body(tmp_path: Path) -> None:
    output_dir = tmp_path / "sensorimotor"
    summary = run_sensorimotor(_write_sensorimotor_fixture(tmp_path), output_dir=output_dir, config=_config())

    assert summary["outcome"]["target_spike_count"] == 1
    assert summary["outcome"]["turn_event_count"] == 1
    assert summary["outcome"]["final_heading_degrees"] == 20.0
    assert summary["outcome"]["final_position"] == [
        pytest.approx(2.0 * 0.9396926208),
        pytest.approx(2.0 * 0.3420201433),
    ]

    with (output_dir / "trajectory.csv").open(newline="", encoding="utf-8") as handle:
        trajectory = list(csv.DictReader(handle))
    turn_rows = [row for row in trajectory if row["target_spike"] == "True"]
    assert len(turn_rows) == 1
    assert turn_rows[0]["turn_command_degrees"] == "20.0"

    written = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert written["action_decoder"]["output"].startswith("one fixed turn")
    assert (output_dir / "story.md").is_file()


def test_no_descending_spike_means_no_body_action(tmp_path: Path) -> None:
    summary = run_sensorimotor(
        _write_sensorimotor_fixture(tmp_path),
        output_dir=tmp_path / "silent-sensorimotor",
        config=_config(coupling=0.01),
    )

    assert summary["outcome"]["target_spike_count"] == 0
    assert summary["outcome"]["turn_event_count"] == 0
    assert summary["outcome"]["final_heading_degrees"] == 0.0
    assert summary["outcome"]["final_position"] == [0.0, 0.0]

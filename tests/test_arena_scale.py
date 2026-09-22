import importlib
from pathlib import Path

import pytest


def _load_scale_module():
    try:
        return importlib.import_module("flytest.arena_scale")
    except ModuleNotFoundError as error:
        pytest.fail(f"arena scale diagnostic is missing: {error}")


class _FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    def step(self, payload: dict[str, object]) -> dict[str, object]:
        step_index = self.calls
        self.calls += 1
        body = dict(payload["body"])
        return {
            "step_index": step_index,
            "next_time_ms": float(payload["time_ms"]) + 1.0,
            "next_body": body,
            "next_lights": list(payload.get("lights", [])),
            "next_threats": list(payload.get("threats", [])),
            "frame": {
                "retina": [0.5],
                "input_currents": {"visual_center": 1.0},
                "active_spikes": [],
                "action": "forward",
                "position_x": float(body["x"]),
                "position_y": float(body["y"]),
            },
        }


class _FakeModel:
    def __init__(self, actual_node_count: int = 1024) -> None:
        self.actual_node_count = actual_node_count

    def run_arena(self, config):
        assert config.network_stage == 1024
        return {
            "network": {
                "stage": 1024,
                "requested_node_count": 1024,
                "target_node_count": 1024,
                "actual_node_count": self.actual_node_count,
                "edge_count": 2048,
                "unified": True,
                "input_group_details": {"large": list(range(2000))},
                "selection": {"large": list(range(2000))},
            },
            "replay_digest": "same-digest",
            "trajectory": [
                {
                    "retina": [0.5],
                    "input_currents": {"visual_center": 1.0},
                    "active_spikes": [],
                    "action": "forward",
                    "position_x": 0.0,
                    "position_y": 0.0,
                },
                {
                    "retina": [0.6],
                    "input_currents": {"visual_center": 1.0},
                    "active_spikes": [],
                    "action": "forward",
                    "position_x": 1.0,
                    "position_y": 0.0,
                },
            ],
        }

    def create_arena_session(self, config):
        assert config.network_stage == 1024
        return _FakeSession()


def test_arena_scale_writes_compact_1024_acceptance_evidence(tmp_path: Path) -> None:
    module = _load_scale_module()

    summary = module.run_arena_scale(
        _FakeModel(),
        output_dir=tmp_path / "arena-1024",
        config=module.ArenaScaleConfig(),
    )

    assert summary["result"]["success"] is True
    assert summary["network"]["actual_node_count"] == 1024
    assert summary["result"]["replay_digest_match"] is True
    assert summary["live"]["step_count"] == 2
    assert "input_group_details" not in summary["network"]
    assert "selection" not in summary["network"]
    assert len((tmp_path / "arena-1024" / "summary.json").read_bytes()) < 50_000
    assert (tmp_path / "arena-1024" / "summary.json").is_file()
    assert (tmp_path / "arena-1024" / "report.md").is_file()


def test_arena_scale_rejects_a_sub_1000_graph(tmp_path: Path) -> None:
    module = _load_scale_module()

    with pytest.raises(ValueError, match="at least 1000"):
        module.run_arena_scale(
            _FakeModel(actual_node_count=999),
            output_dir=tmp_path / "arena-1024",
            config=module.ArenaScaleConfig(),
        )

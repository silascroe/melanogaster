from __future__ import annotations

import csv
from pathlib import Path

import pytest

from flytest.arena_simulation import ArenaRunConfig
from flytest.threat_crossing import (
    ThreatCrossingConfig,
    _causal_trace_summary,
    _stage_metrics,
    run_threat_crossing,
)


def _frame(
    *,
    time_ms: float,
    threat_active: bool,
    escaped: bool,
    touch_spike: bool | None = None,
) -> dict[str, object]:
    threat_id = "crossing-threat" if threat_active else None
    action = "escape_left" if escaped else "forward"
    action_source = "touch" if escaped else "vision"
    threat_payload = (
        {
            "id": "crossing-threat",
            "x": 0.0,
            "y": 0.5,
            "radius": 0.65,
            "trigger": "collision",
            "active_start_ms": 0.0,
            "active_end_ms": 60.0,
            "vx": 0.1,
            "vy": 0.0,
        }
        if threat_active
        else None
    )
    world_cause = {
        "touch_source": "threat" if threat_active else None,
        "touch_id": threat_id,
        "threat_id": threat_id,
        "touch_urgency": 0.8 if threat_active else 0.0,
    }
    return {
        "time_ms": time_ms,
        "position_x": 0.5 if escaped else 0.25,
        "position_y": 0.5,
        "heading_degrees": 45.0 if escaped else 0.0,
        "retina": [0.5],
        "input_currents": {"threat_urgency": 2.0 if threat_active else 0.0},
        "active_spikes": [{"body_id": 1}],
        "action": action,
        "action_source": action_source,
        "touch_stimulus_active": threat_active,
        "touch_target_spike": escaped if touch_spike is None else touch_spike,
        "threat_id": threat_id,
        "touch_source": "threat" if threat_active else None,
        "touch_urgency": 0.8 if threat_active else 0.0,
        "world_cause": world_cause,
        "neural_cause": {"input_groups": {"threat_urgency": 2.0 if threat_active else 0.0}},
        "threats": [threat_payload] if threat_payload else [],
        "escape_marker": escaped,
    }


def test_threat_crossing_compares_stages_and_writes_causal_artifacts(tmp_path: Path) -> None:
    class StubArenaModel:
        def __init__(self) -> None:
            self.calls: list[ArenaRunConfig] = []

        def run_arena(self, config: ArenaRunConfig) -> dict[str, object]:
            self.calls.append(config)
            assert config.mode == "sandbox"
            assert config.lights[0].light_id == "beacon"
            assert config.obstacles == ()
            has_threat = bool(config.threats)
            return {
                "dataset": {"release": "fixture"},
                "network": {
                    "stage": config.network_stage,
                    "requested_node_count": config.network_stage,
                    "actual_node_count": config.network_stage,
                    "edge_count": 12,
                    "unified": config.network_stage != 54,
                },
                "replay_digest": f"fixture-{config.network_stage}-{has_threat}",
                "trajectory": [
                    _frame(time_ms=0.0, threat_active=False, escaped=False),
                    _frame(time_ms=1.0, threat_active=has_threat, escaped=has_threat),
                ],
            }

    model = StubArenaModel()
    output_dir = tmp_path / "threat-crossing"
    summary = run_threat_crossing(
        model,
        output_dir=output_dir,
        config=ThreatCrossingConfig(duration_ms=2.0),
    )

    assert [call.network_stage for call in model.calls] == [
        54,
        54,
        250,
        250,
        1024,
        1024,
        1024,
        1024,
    ]
    assert summary["experiment"] == "deterministic threat crossing"
    assert summary["result"]["success"] is True
    assert summary["result"]["response_detected_stage_count"] == 3
    assert summary["stages"]["1024"]["crossing"]["escape_action_count"] == 1
    assert summary["stages"]["1024"]["geometries"]["right-lane"]["response_detected"] is True
    assert summary["stages"]["1024"]["control"]["escape_action_count"] == 0
    assert summary["stages"]["1024"]["causal_trace_complete"] is True
    assert summary["result"]["geometry_variant_response_count"] == 2
    assert (output_dir / "summary.json").is_file()
    assert (output_dir / "report.md").is_file()
    with (output_dir / "trajectory.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 16
    assert {row["condition"] for row in rows} == {
        "control",
        "crossing",
        "crossing:right-lane",
        "crossing:late-crossing",
    }
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Threat crossing" in report
    assert "response detected" in report
    assert "Geometry generalization" in report


def test_threat_crossing_config_uses_collision_triggered_moving_threat() -> None:
    scenario = ThreatCrossingConfig()

    control = scenario.to_arena_config(250, include_threat=False)
    crossing = scenario.to_arena_config(250, include_threat=True)

    assert control.threats == ()
    assert len(crossing.threats) == 1
    threat = crossing.threats[0]
    assert threat.threat_id == "crossing-threat"
    assert threat.trigger == "collision"
    assert threat.vx != 0.0 or threat.vy != 0.0
    assert crossing.lights == control.lights
    assert crossing.obstacles == ()


def test_default_threat_crosses_the_early_beacon_route() -> None:
    scenario = ThreatCrossingConfig()

    assert scenario.threat_start_x == pytest.approx(0.6)
    assert scenario.threat_start_y == pytest.approx(-0.3)
    assert scenario.threat_vx == pytest.approx(0.0)
    assert scenario.threat_vy == pytest.approx(0.1)


def test_causal_trace_requires_threat_fields_used_by_the_score() -> None:
    frame = _frame(time_ms=0.0, threat_active=True, escaped=True)
    frame.pop("touch_target_spike")

    summary = _causal_trace_summary([frame])

    assert summary["complete"] is False


def test_threat_crossing_metrics_report_first_causal_response_times() -> None:
    payload = {
        "network": {
            "stage": 1024,
            "actual_node_count": 1024,
            "edge_count": 12,
        },
        "trajectory": [
            _frame(time_ms=0.0, threat_active=False, escaped=False),
            _frame(time_ms=2.0, threat_active=True, escaped=False, touch_spike=False),
            _frame(time_ms=4.0, threat_active=True, escaped=False, touch_spike=True),
            _frame(time_ms=7.0, threat_active=True, escaped=True, touch_spike=True),
        ],
    }

    metrics, _ = _stage_metrics(
        payload,
        stage=1024,
        condition="crossing",
        geometry_id="centerline",
    )

    assert metrics["threat_detected_first_time_ms"] == pytest.approx(2.0)
    assert metrics["threat_touch_output_first_time_ms"] == pytest.approx(4.0)
    assert metrics["threat_escape_first_time_ms"] == pytest.approx(7.0)
    assert metrics["touch_response_latency_ms"] == pytest.approx(2.0)
    assert metrics["escape_response_latency_ms"] == pytest.approx(5.0)

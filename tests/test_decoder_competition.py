from __future__ import annotations

import csv
import importlib
from pathlib import Path

import pytest

from flytest.arena_simulation import (
    ArenaLight,
    ArenaRunConfig,
    ArenaThreat,
    ArenaWorld,
    _ArenaMemoryState,
    _decode_population_action,
)


def _frame(
    time_ms: float,
    *,
    votes: dict[str, float],
    action: str,
    source: str,
    before_x: float,
    after_x: float,
) -> dict:
    return {
        "time_ms": time_ms,
        "neural_cause": {"output_votes": votes},
        "input_currents": {"visual_left": 1.0, "threat_urgency": 1.0},
        "retina": [0.1, 0.4, 0.1],
        "body_before": {"x": before_x, "y": 0.0, "heading_degrees": 0.0},
        "body_after": {"x": after_x, "y": 0.0, "heading_degrees": 0.0},
        "action": action,
        "action_source": source,
        "touch_stimulus_active": True,
        "escape_cooldown_remaining_ms": 12.0 if action.startswith("escape") else 0.0,
    }


def _paired_frames() -> tuple[list[dict], list[dict]]:
    common = _frame(
        0.0, votes={"turn_left": 1.0}, action="turn_left", source="vision",
        before_x=0.0, after_x=0.0,
    )
    priority = [common, _frame(
        1.0, votes={"escape_right": 3.0, "turn_left": 6.0},
        action="escape_right", source="touch", before_x=0.0, after_x=0.25,
    )]
    strongest = [common, _frame(
        1.0, votes={"escape_right": 3.0, "turn_left": 6.0},
        action="turn_left", source="vision", before_x=0.0, after_x=0.0,
    )]
    return priority, strongest


def test_strongest_vote_changes_action_only_when_visual_vote_wins() -> None:
    config = ArenaRunConfig(
        mode="sandbox",
        lights=(ArenaLight("beacon", 2.0, 2.0),),
        threats=(ArenaThreat("threat", 0.5, 0.0, 1.0),),
    )
    observation = ArenaWorld(config).observe(
        0.0, position_x=0.0, position_y=0.0, heading_degrees=0.0
    )
    votes = {"escape_right": 1.0, "turn_left": 6.0}

    priority = _decode_population_action(
        votes, observation=observation, memory=_ArenaMemoryState(), config=config
    )
    strongest = _decode_population_action(
        votes,
        observation=observation,
        memory=_ArenaMemoryState(),
        config=config,
        decoder_policy="strongest_vote",
    )

    assert priority.name == "escape_right"
    assert priority.source == "touch"
    assert strongest.name == "turn_left"
    assert strongest.source == "vision"


def test_paired_replay_attributes_first_divergence_to_competing_votes() -> None:
    diagnostic = importlib.import_module("flytest.decoder_competition")
    priority, strongest = _paired_frames()

    result = diagnostic.compare_replays(priority, strongest)

    assert result["status"] == "decoder_changed_action"
    assert result["first_action_divergence_ms"] == 1.0
    assert result["votes_at_divergence"] == {"escape_right": 3.0, "turn_left": 6.0}
    assert result["priority_action"] == "escape_right"
    assert result["strongest_action"] == "turn_left"
    assert result["escape_cooldown_before_ms"] == 0.0


def test_paired_replay_rejects_unmatched_neural_input_before_decision() -> None:
    diagnostic = importlib.import_module("flytest.decoder_competition")
    priority, strongest = _paired_frames()
    strongest[1]["input_currents"] = {"visual_left": 2.0}

    with pytest.raises(ValueError, match="unmatched pre-decision state"):
        diagnostic.compare_replays(priority, strongest)


def test_diagnostic_runs_control_and_paired_policies_and_writes_trace(tmp_path: Path) -> None:
    diagnostic = importlib.import_module("flytest.decoder_competition")

    class StubModel:
        def __init__(self) -> None:
            self.calls = []

        def run_arena(self, config, *, decoder_policy="touch_priority"):
            self.calls.append((config, decoder_policy))
            priority, strongest = _paired_frames()
            if not config.threats:
                frames = [
                    _frame(0.0, votes={"turn_left": 1.0}, action="turn_left", source="vision", before_x=0.0, after_x=0.0),
                    _frame(1.0, votes={"turn_left": 1.0}, action="turn_left", source="vision", before_x=0.0, after_x=0.0),
                ]
            else:
                frames = priority if decoder_policy == "touch_priority" else strongest
            return {
                "network": {"stage": 1024, "actual_node_count": 1024, "edge_count": 24807},
                "trajectory": frames,
            }

    model = StubModel()
    summary = diagnostic.run_decoder_competition(model, output_dir=tmp_path)

    assert summary["comparison"]["status"] == "decoder_changed_action"
    assert summary["comparison"]["first_action_divergence_ms"] == 1.0
    assert summary["strongest_matches_control_action_body_frames"] == 2
    assert [policy for _, policy in model.calls] == ["touch_priority", "touch_priority", "strongest_vote"]
    assert [bool(config.threats) for config, _ in model.calls] == [False, True, True]
    assert model.calls[1][0] is model.calls[2][0]
    assert model.calls[1][0].threats[0].active_start_ms == 2.0
    with (tmp_path / "trajectory.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "report.md").is_file()
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Final body positions" in report
    assert "0.25" in report

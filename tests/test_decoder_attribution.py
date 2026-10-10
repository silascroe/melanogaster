from __future__ import annotations

import csv
import importlib
from pathlib import Path


def _frame(time_ms: float, votes: dict[str, float], action: str, source: str) -> dict:
    return {
        "time_ms": time_ms,
        "neural_cause": {"output_votes": votes},
        "action": action,
        "action_source": source,
        "touch_stimulus_active": source == "touch",
    }


def test_vote_comparison_exposes_priority_without_changing_live_action() -> None:
    diagnostic = importlib.import_module("flytest.decoder_attribution")
    frames = [
        _frame(0, {"escape_left": 1, "turn_right": 3}, "escape_left", "touch"),
        _frame(1, {"escape_right": 4, "turn_left": 2}, "escape_right", "touch"),
        _frame(2, {"escape_right": 2, "turn_left": 2}, "escape_right", "touch"),
        _frame(3, {"turn_left": 1}, "turn_left", "vision"),
    ]

    result, rows = diagnostic.analyze_vote_trace(frames, condition="crossing")

    assert result["competitive_frames"] == 3
    assert result["policy_sensitive_vote_frames"] == 1
    assert result["realized_priority_override_frames"] == 1
    assert rows[0]["shadow_action"] == "turn_right"
    assert rows[0]["actual_action"] == "escape_left"
    assert rows[1]["shadow_action"] == "escape_right"
    assert rows[2]["shadow_action"] == "escape_right"  # stable tie order
    assert result["attribution"] == "observed_priority_override"


def test_no_competition_cannot_establish_decoder_attribution() -> None:
    diagnostic = importlib.import_module("flytest.decoder_attribution")
    result, rows = diagnostic.analyze_vote_trace(
        [_frame(0, {"escape_left": 1}, "escape_left", "touch")],
        condition="crossing",
    )
    assert result["competitive_frames"] == 0
    assert result["attribution"] == "untested_no_competition"
    assert rows[0]["shadow_action"] == "escape_left"


def test_vote_sensitivity_is_not_claimed_as_realized_during_cooldown() -> None:
    diagnostic = importlib.import_module("flytest.decoder_attribution")
    result, rows = diagnostic.analyze_vote_trace(
        [_frame(0, {"escape_left": 1, "turn_right": 3}, "turn_right", "vision")],
        condition="crossing",
    )
    assert result["policy_sensitive_vote_frames"] == 1
    assert result["realized_priority_override_frames"] == 0
    assert result["attribution"] == "latent_priority_sensitivity"
    assert rows[0]["priority_vote_action"] == "escape_left"


def test_diagnostic_runs_exactly_two_stage_1024_conditions_and_writes_votes(tmp_path: Path) -> None:
    diagnostic = importlib.import_module("flytest.decoder_attribution")

    class StubModel:
        def __init__(self) -> None:
            self.calls = []

        def run_arena(self, config):
            self.calls.append(config)
            has_threat = bool(config.threats)
            return {
                "network": {"stage": 1024, "actual_node_count": 1024, "edge_count": 24807},
                "trajectory": [
                    _frame(0, {"forward": 1}, "forward", "vision"),
                    _frame(
                        1,
                        {"escape_left": 1, "turn_right": 3} if has_threat else {"forward": 1},
                        "escape_left" if has_threat else "forward",
                        "touch" if has_threat else "vision",
                    ),
                ],
            }

    model = StubModel()
    summary = diagnostic.run_decoder_attribution(model, output_dir=tmp_path)

    assert len(model.calls) == 2
    assert [bool(call.threats) for call in model.calls] == [False, True]
    assert all(call.network_stage == 1024 for call in model.calls)
    assert summary["conditions"]["crossing"]["attribution"] == "observed_priority_override"
    assert summary["conditions"]["control"]["attribution"] == "untested_no_competition"
    with (tmp_path / "votes.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert rows[3]["shadow_action"] == "turn_right"
    assert (tmp_path / "report.md").is_file()
    assert (tmp_path / "summary.json").is_file()
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "1.0 ms" in report
    assert "turn_right" in report
    assert "not alternate closed-loop" in report

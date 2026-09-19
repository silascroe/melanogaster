import json
from pathlib import Path

import pytest

from flytest.discord_bridge import (
    DiscordBridgeError,
    DiscordConfig,
    append_event,
    format_event,
    watch_once,
)


class _RecordingClient:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_message(self, content: str) -> dict[str, str]:
        self.messages.append(content)
        return {"id": str(len(self.messages))}


def test_config_requires_token_and_channel() -> None:
    with pytest.raises(DiscordBridgeError, match="BOT_TOKEN"):
        DiscordConfig.from_env({})
    with pytest.raises(DiscordBridgeError, match="CHANNEL_ID"):
        DiscordConfig.from_env({"FLYTEST_DISCORD_BOT_TOKEN": "secret"})


def test_format_event_is_compact_and_flattens_user_text() -> None:
    message = format_event(
        {
            "status": "success",
            "job": "arena replay",
            "summary": "34 tests passed\nsecond line",
            "artifacts": ["outputs/a.json", "outputs/b.md"],
        }
    )

    assert message == (
        "[FLYTEST SUCCESS] arena replay\n"
        "Summary: 34 tests passed second line\n"
        "Artifacts: outputs/a.json, outputs/b.md"
    )


def test_watch_delivers_events_once_and_persists_offset(tmp_path: Path) -> None:
    spool = tmp_path / "events.jsonl"
    state = tmp_path / "events.offset"
    append_event(spool, {"status": "started", "job": "first"})
    append_event(spool, {"status": "failure", "job": "second", "summary": "boom"})
    client = _RecordingClient()

    assert watch_once(spool, state, client) == 2
    assert watch_once(spool, state, client) == 0
    assert client.messages == [
        "[FLYTEST STARTED] first",
        "[FLYTEST FAILURE] second\nSummary: boom",
    ]
    assert state.read_text(encoding="utf-8").strip() == "2"


def test_watch_rejects_invalid_event_without_advancing(tmp_path: Path) -> None:
    spool = tmp_path / "events.jsonl"
    state = tmp_path / "events.offset"
    spool.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(DiscordBridgeError, match="invalid JSON"):
        watch_once(spool, state, _RecordingClient())
    assert not state.exists()


def test_emit_payload_shape_is_json_serializable(tmp_path: Path) -> None:
    spool = tmp_path / "events.jsonl"
    append_event(spool, {"status": "success", "job": "smoke", "tests": "34 passed"})
    record = json.loads(spool.read_text(encoding="utf-8").strip())

    assert record["status"] == "success"
    assert record["job"] == "smoke"
    assert record["emitted_at"]

import base64
import json
import subprocess
from pathlib import Path

import pytest

from flytest.discord_bridge import (
    DiscordBridgeError,
    DiscordConfig,
    append_event,
    append_event_remote,
    format_event,
    run_and_report,
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


def test_append_event_remote_sends_encoded_event_without_discord_secret() -> None:
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    append_event_remote(
        {"status": "success", "job": "title; touch /tmp/nope", "summary": "done"},
        runner=fake_run,
    )

    command = calls[0][0][-1]
    assert "FLYTEST_DISCORD_BOT_TOKEN" not in command
    assert "touch /tmp/nope" not in command
    encoded = command.rsplit(" ", 1)[-1].strip("'")
    assert json.loads(base64.b64decode(encoded)) == {
        "status": "success",
        "job": "title; touch /tmp/nope",
        "summary": "done",
    }


def test_run_and_report_preserves_child_failure_when_notification_fails() -> None:
    events = []

    def failing_notify(event, host_alias="first-droplet"):
        events.append(event)
        raise DiscordBridgeError("ssh unavailable")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 7)

    assert (
        run_and_report(["fake-job"], "wrapper smoke", notify=failing_notify, runner=fake_run)
        == 7
    )
    assert [event["status"] for event in events] == ["started", "failure"]


def test_run_and_report_attempts_failure_when_command_cannot_start() -> None:
    events = []

    def record_notify(event, host_alias="first-droplet"):
        events.append(event)

    def missing_command(command, **kwargs):
        raise FileNotFoundError("missing command")

    assert run_and_report(["missing-job"], "start failure", notify=record_notify, runner=missing_command) == 127
    assert [event["status"] for event in events] == ["started", "failure"]

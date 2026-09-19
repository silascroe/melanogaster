"""Small report-only bridge from FlyTest run events to a Discord channel.

The bridge intentionally uses Discord's HTTP API instead of opening a Gateway
connection. The first milestone only posts run notifications, so it does not
need privileged intents or a third-party Discord client library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SPOOL = Path("outputs/discord/events.jsonl")
DEFAULT_API_BASE = "https://discord.com/api/v10"
MAX_MESSAGE_LENGTH = 2_000


class DiscordBridgeError(RuntimeError):
    """Raised when bridge configuration, event data, or delivery fails."""


@dataclass(frozen=True)
class DiscordConfig:
    """Runtime configuration loaded from environment variables."""

    token: str
    channel_id: str
    api_base: str = DEFAULT_API_BASE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "DiscordConfig":
        values = os.environ if environ is None else environ
        token = values.get("FLYTEST_DISCORD_BOT_TOKEN", "").strip()
        channel_id = values.get("FLYTEST_DISCORD_CHANNEL_ID", "").strip()
        if not token:
            raise DiscordBridgeError(
                "FLYTEST_DISCORD_BOT_TOKEN is not set; enter it on the host running the bridge"
            )
        if not channel_id:
            raise DiscordBridgeError(
                "FLYTEST_DISCORD_CHANNEL_ID is not set; use the target Discord channel ID"
            )
        api_base = values.get("FLYTEST_DISCORD_API_BASE", DEFAULT_API_BASE).strip().rstrip("/")
        return cls(token=token, channel_id=channel_id, api_base=api_base or DEFAULT_API_BASE)


class DiscordClient:
    """Minimal Discord REST client for posting one channel message."""

    def __init__(self, config: DiscordConfig, timeout_seconds: float = 15.0) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def send_message(self, content: str) -> dict[str, Any]:
        message = _truncate(content, MAX_MESSAGE_LENGTH)
        payload = {
            "content": message,
            # Run data can contain branch names, issue text, or pasted output.
            # Never let a report turn into an accidental mass mention.
            "allowed_mentions": {"parse": []},
        }
        request = urllib.request.Request(
            f"{self.config.api_base}/channels/{self.config.channel_id}/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bot {self.config.token}",
                "Content-Type": "application/json",
                "User-Agent": "FlyTest-Discord-Bridge/0.1",
            },
            method="POST",
        )

        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    status = int(response.status)
                if not 200 <= status < 300:
                    raise DiscordBridgeError(f"Discord returned HTTP {status}")
                if not raw:
                    return {}
                decoded = json.loads(raw)
                return decoded if isinstance(decoded, dict) else {}
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                if error.code == 429 and attempt == 0:
                    retry_after = _retry_after_seconds(detail)
                    time.sleep(min(max(retry_after, 0.0), 10.0))
                    continue
                raise DiscordBridgeError(
                    f"Discord message failed with HTTP {error.code}: {detail}"
                ) from error
            except urllib.error.URLError as error:
                raise DiscordBridgeError(f"Discord connection failed: {error.reason}") from error

        raise DiscordBridgeError("Discord message delivery failed after retry")


def format_event(event: Mapping[str, Any]) -> str:
    """Format one event as a compact, mention-safe Discord message."""

    if not isinstance(event, Mapping):
        raise DiscordBridgeError("event must be a JSON object")
    status = str(event.get("status", "info")).strip().upper() or "INFO"
    job = str(event.get("job", event.get("title", "FlyTest run"))).strip() or "FlyTest run"
    lines = [f"[FLYTEST {status}] {job}"]

    for label, key in (
        ("Agent", "agent"),
        ("Branch", "branch"),
        ("Commit", "commit"),
        ("Tests", "tests"),
        ("Duration", "duration"),
    ):
        value = event.get(key)
        if value not in (None, ""):
            lines.append(f"{label}: {_display(value)}")

    summary = event.get("summary", event.get("message"))
    if summary not in (None, ""):
        lines.append(f"Summary: {_display(summary)}")

    artifacts = event.get("artifacts")
    if artifacts:
        if isinstance(artifacts, (list, tuple)):
            artifact_text = ", ".join(_display(value) for value in artifacts)
        else:
            artifact_text = _display(artifacts)
        lines.append(f"Artifacts: {artifact_text}")

    return _truncate("\n".join(lines), MAX_MESSAGE_LENGTH)


def append_event(spool: Path, event: Mapping[str, Any]) -> None:
    """Append an event to the small local JSONL spool."""

    if not isinstance(event, Mapping):
        raise DiscordBridgeError("event must be a JSON object")
    spool.parent.mkdir(parents=True, exist_ok=True)
    record = dict(event)
    record.setdefault("emitted_at", datetime.now(timezone.utc).isoformat())
    with spool.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def watch_once(
    spool: Path,
    state_file: Path,
    client: DiscordClient | Any,
    *,
    dry_run: bool = False,
) -> int:
    """Deliver pending events and advance the line offset after success."""

    if not spool.exists():
        return 0
    lines = spool.read_text(encoding="utf-8").splitlines()
    offset = _read_offset(state_file)
    if offset > len(lines):
        offset = 0
    pending = lines[offset:]
    delivered = 0
    for line_number, line in enumerate(pending, start=offset + 1):
        if not line.strip():
            offset = line_number
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise DiscordBridgeError(f"invalid JSON in {spool}:{line_number}: {error}") from error
        if not isinstance(event, dict):
            raise DiscordBridgeError(f"event in {spool}:{line_number} is not an object")
        message = format_event(event)
        if dry_run:
            print(message)
        else:
            client.send_message(message)
        offset = line_number
        delivered += 1
        _write_offset(state_file, offset)
    return delivered


def _read_offset(state_file: Path) -> int:
    try:
        return max(0, int(state_file.read_text(encoding="utf-8").strip()))
    except (FileNotFoundError, ValueError):
        return 0


def _write_offset(state_file: Path, offset: int) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(f"{offset}\n", encoding="utf-8")


def _display(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 24].rstrip() + "\n[message truncated]"


def _retry_after_seconds(detail: str) -> float:
    try:
        payload = json.loads(detail)
        return float(payload.get("retry_after", 1.0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1.0


def _event_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload is not None:
        try:
            payload = json.loads(args.payload.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DiscordBridgeError(f"could not read JSON payload {args.payload}: {error}") from error
        if not isinstance(payload, dict):
            raise DiscordBridgeError("payload JSON must be an object")
        event = payload
    else:
        event = {"status": args.status, "job": args.job, "agent": args.agent}
        for key in ("summary", "branch", "commit", "tests", "duration"):
            value = getattr(args, key)
            if value not in (None, ""):
                event[key] = value
        if args.artifact:
            event["artifacts"] = args.artifact
    event.setdefault("status", args.status)
    event.setdefault("job", args.job)
    event.setdefault("agent", args.agent)
    return event


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge FlyTest run events to Discord")
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit = subparsers.add_parser("emit", help="append one run event to the local JSONL spool")
    emit.add_argument("--spool", type=Path, default=DEFAULT_SPOOL)
    emit.add_argument("--payload", type=Path, help="read the complete event from a JSON file")
    emit.add_argument("--status", choices=("started", "success", "failure", "blocked"), default="success")
    emit.add_argument("--job", default="FlyTest run")
    emit.add_argument("--agent", default="flytest")
    emit.add_argument("--summary")
    emit.add_argument("--branch")
    emit.add_argument("--commit")
    emit.add_argument("--tests")
    emit.add_argument("--duration")
    emit.add_argument("--artifact", action="append")

    send = subparsers.add_parser("send", help="send one message immediately")
    send.add_argument("content")
    send.add_argument("--dry-run", action="store_true")

    watch = subparsers.add_parser("watch", help="deliver new events from the local JSONL spool")
    watch.add_argument("--spool", type=Path, default=DEFAULT_SPOOL)
    watch.add_argument("--state-file", type=Path)
    watch.add_argument("--poll-seconds", type=float, default=2.0)
    watch.add_argument("--once", action="store_true")
    watch.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "emit":
            append_event(args.spool, _event_from_args(args))
            return 0

        if args.command == "send":
            if args.dry_run:
                print(_truncate(args.content, MAX_MESSAGE_LENGTH))
            else:
                DiscordClient(DiscordConfig.from_env()).send_message(args.content)
            return 0

        state_file = args.state_file or args.spool.with_suffix(args.spool.suffix + ".offset")
        client = None if args.dry_run else DiscordClient(DiscordConfig.from_env())
        while True:
            delivered = watch_once(args.spool, state_file, client, dry_run=args.dry_run)
            if args.once:
                return 0
            if delivered == 0:
                time.sleep(max(0.2, args.poll_seconds))
    except KeyboardInterrupt:
        return 130
    except DiscordBridgeError as error:
        print(f"flytest-discord: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

# FlyTest Discord bridge

The first Discord integration is intentionally report-only. It appends small
JSON events to `outputs/discord/events.jsonl` and a separate watcher posts them
to one configured Discord channel through the bot REST API. It does not read
channel history, open a Gateway connection, or require privileged intents.

## Local configuration

Set these variables only in the shell running the watcher:

```powershell
$env:FLYTEST_DISCORD_BOT_TOKEN = "paste-the-token-in-the-shell-that-runs-the-bridge"
$env:FLYTEST_DISCORD_CHANNEL_ID = "target-channel-id"
```

The token is never written by the bridge. Keep it out of Git, event files,
terminal transcripts, and chat. The channel ID is not secret, but keeping it in
the environment makes it easy to point a local test at a private report channel.

## Emit and watch

Append a completion event:

```powershell
.\.venv\Scripts\python.exe -m flytest.discord_bridge emit `
  --status success `
  --job "arena collision smoke" `
  --agent codex `
  --tests "34 passed" `
  --summary "Python arena and Godot scene checks completed" `
  --commit 77be5fb
```

Run the local watcher in another terminal:

```powershell
.\.venv\Scripts\python.exe -m flytest.discord_bridge watch
```

Use `watch --dry-run --once` to inspect pending messages without a token or
network call. The watcher stores only a line offset beside the spool and uses
at-least-once delivery: a process crash around a successful send can produce a
duplicate after restart, but it will not silently discard an event.

For a one-off formatting check:

```powershell
.\.venv\Scripts\python.exe -m flytest.discord_bridge send --dry-run "bridge test"
```

Remove `--dry-run` only after the token and channel variables are set.

## Droplet handoff

The same watcher can run under systemd later. The droplet should provide
`FLYTEST_DISCORD_BOT_TOKEN` through a root-owned, mode-600 environment file and
provide `FLYTEST_DISCORD_CHANNEL_ID` alongside it. The service should run as a
dedicated unprivileged user, restart on failure, and log to the system journal.

The bridge currently reports explicit events. It does not guess when an
unrelated process or Codex task has finished; job wrappers will emit events at
the point where they know the result. Later commands such as `/status` can be
added as a separate Gateway/interaction layer without changing this report
spool or exposing the bot token to the repository.

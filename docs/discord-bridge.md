# FlyTest Discord bridge

The first Discord integration is intentionally report-only. It appends small
JSON events to `outputs/discord/events.jsonl` and a separate watcher posts them
to one configured Discord channel through the bot REST API. It does not read
channel history, open a Gateway connection, or require privileged intents.

The repository is the source of truth. The droplet receives only the bridge
module, its package marker, and the systemd unit; it does not receive the full
FlyTest runtime, connectome data, Godot files, or the local virtual environment.

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

## Report a local job through the droplet

The deployed watcher is reachable from the local Windows workspace through the
existing `first-droplet` SSH alias. These commands never need the Discord token
locally; they append an event to the droplet spool as the unprivileged `flybot`
user.

Send one event manually:

```powershell
\.venv\Scripts\python.exe -m flytest.discord_bridge notify `
  --status success `
  --job "manual smoke" `
  --summary "reported from the local workspace"
```

Wrap a real local command:

```powershell
\.venv\Scripts\python.exe -m flytest.discord_bridge run --job "FlyTest verification" -- .\.venv\Scripts\python.exe -m flytest.verify
```

`run` streams the child command's normal output and returns its exit code. It
reports `started` and then `success` or `failure`. If SSH or FlyBot is down,
the wrapper prints a warning but preserves the local command's result. This is
an explicit wrapper, not automatic Codex task detection.

## Droplet operation

The always-on watcher runs on the DigitalOcean host under `flybot.service`.
Before deploying, provision both variables in the root-owned, mode-600 file
`/etc/flytest/flybot.env`. The deployment script checks that file remotely but
never accepts or prints either value. It creates the unprivileged `flybot`
account if needed, preserves the remote event spool, and restarts only
`flybot.service`.

From the repository root on Windows:

```powershell
powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet
ssh first-droplet "systemctl status flybot.service --no-pager"
ssh first-droplet "journalctl -u flybot.service -n 50 --no-pager"
ssh first-droplet "runuser -u flybot -- env PYTHONPATH=/opt/flytest-discord/src /usr/bin/python3 -m flytest.discord_bridge emit --spool /var/lib/flytest-discord/events.jsonl --status success --job 'remote job' --agent codex --summary 'completed'"
```

The service code lives under `/opt/flytest-discord/src`, and its durable spool
and line offset live under `/var/lib/flytest-discord`. The systemd unit loads
the secret file as an environment file, runs as `flybot`, restarts on failure,
and logs to the journal. Re-running the deployment is safe and does not erase
the spool or offset.

The bridge currently reports explicit events. It does not guess when an
unrelated process or Codex task has finished; job wrappers will emit events at
the point where they know the result. Later commands such as `/status` can be
added as a separate Gateway/interaction layer without changing this report
spool or exposing the bot token to the repository. DomainPatrol is a separate
agent and is not modified by this deployment.

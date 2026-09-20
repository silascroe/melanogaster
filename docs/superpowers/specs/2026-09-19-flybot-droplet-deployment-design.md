# FlyBot Droplet Bridge Deployment Design

**Status:** Approved in conversation on 2026-09-19; implementation follows the
written-spec review gate.

## Goal

Run the existing report-only FlyTest Discord bridge continuously on the
DigitalOcean droplet while keeping the FlyTest repository as the source of
truth, keeping the Discord bot token out of Git and chat, and leaving the
existing DomainPatrol agent untouched.

## Context and constraints

The bridge already exists as `flytest.discord_bridge`. It uses only the Python
standard library, reads `FLYTEST_DISCORD_BOT_TOKEN` and
`FLYTEST_DISCORD_CHANNEL_ID`, watches a JSONL event spool, and posts through
Discord's HTTP API. It deliberately does not open a Gateway connection or
infer when an unrelated job has completed.

The target host is the existing `first-droplet` DigitalOcean machine. It runs
Ubuntu 24.04, Python 3.12, an active DomainPatrol agent under the separate
`domainpatrol` account, and a scheduled `domainpatrol.timer`. Its existing
`/etc/domainpatrol.env` contains that agent's credentials and Discord webhook
configuration; it must not be modified by this deployment.

The droplet has limited resources, so the deployment must not copy the full
FlyTest repository, connectome data, Godot client, NumPy, or PyArrow. The
bridge is the only FlyTest code that belongs on the host for this milestone.

## Architecture

The repository remains local and authoritative. Deployment copies only the
bridge module and its package marker to `/opt/flytest-discord/src/flytest/`.
The running watcher uses the system Python already installed on the droplet;
it does not install project dependencies.

The bridge runs as a dedicated unprivileged `flybot` system user through a new
`flybot.service`. It reads the already-created root-owned
`/etc/flytest/flybot.env` through systemd's `EnvironmentFile` support. The
service writes its JSONL event spool and delivery offset under
`/var/lib/flytest-discord/`.

The data flow is:

```text
explicit job wrapper
        -> /var/lib/flytest-discord/events.jsonl
        -> flybot.service watcher
        -> Discord REST API -> configured #fly-bot channel
```

Events remain explicit. A future job wrapper can invoke the deployed module's
`emit` command, but this milestone does not claim to detect arbitrary Codex
task completion.

## Deployment assets

The repository will contain:

- `deploy/flybot/flybot.service`: a hardened systemd unit with network-online
  startup, automatic restart, journal logging, an unprivileged user, a narrow
  writable path, and no dependency on DomainPatrol.
- `deploy/flybot/deploy.ps1`: an idempotent Windows/OpenSSH deployment script
  that uploads the two bridge files and unit manifest, creates only the
  `flybot` account and directories it owns, refuses to overwrite the protected
  environment file, reloads systemd, and starts the service.
- `docs/discord-bridge.md`: the operator handoff describing the droplet paths,
  deployment command, explicit event command, status/log commands, and secret
  handling.

The deployment script must not accept the bot token as an argument, print it,
read it into local state, or replace `/etc/flytest/flybot.env`. It may verify
that the file exists, has mode `600`, and contains both required variable
names without revealing values.

## Security and failure behavior

The existing DomainPatrol unit and environment file are outside the deployment
surface. The new service runs with `NoNewPrivileges`, private temporary
storage, read-only system paths, and a restricted writable state directory.
The service restarts on failure and reports failures to journald. The bridge's
existing at-least-once offset behavior is preserved: a crash around a
successful Discord send can duplicate a message, but a failed send does not
advance the offset.

The deployment is additive and idempotent. Rerunning it updates the bridge
files and unit, preserves the secret file and event spool, and does not delete,
restart, or alter DomainPatrol.

## Verification

Local verification will run the focused Discord bridge tests and the full
project suite. The remote verification will confirm:

1. `/etc/flytest/flybot.env` remains mode `600` and its values are never
   printed.
2. `flybot.service` is loaded, enabled, and active as the `flybot` user.
3. A controlled success event is appended to the remote spool.
4. The service delivers that event to Discord and advances its offset.
5. DomainPatrol's timer and service remain loaded and unchanged.

## Non-goals

This deployment does not add Discord slash commands, Gateway intents,
interactive control, local-to-remote event forwarding, automatic Codex task
detection, or a full FlyTest runtime on the droplet.

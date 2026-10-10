# FlyBot Droplet Bridge Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the existing standard-library FlyTest Discord bridge as an isolated, restartable systemd service on `first-droplet` without changing DomainPatrol or exposing the Discord token.

**Architecture:** Keep the repository and full FlyTest runtime local. Copy only `flytest.discord_bridge` and its package marker to `/opt/flytest-discord`, run it as `flybot`, keep state under `/var/lib/flytest-discord`, and load the already-installed secret file through systemd's `EnvironmentFile` support. Use a Windows/OpenSSH deployment script so the remote installation is repeatable and does not accept secrets as arguments.

**Tech Stack:** Python 3.12 standard library, systemd, Ubuntu 24.04, PowerShell, OpenSSH, pytest, Discord REST API v10.

**Spec:** `docs/superpowers/specs/2026-09-19-flybot-droplet-deployment-design.md`

## Global Constraints

- Never read, print, copy, overwrite, or accept as an argument the value in `/etc/flytest/flybot.env`.
- Never modify `/etc/domainpatrol.env`, `domainpatrol.service`, `domainpatrol.timer`, or the DomainPatrol source/state.
- Do not copy `data/`, `.venv/`, Godot files, connectome artifacts, NumPy, or PyArrow to the droplet.
- The remote service must run as the dedicated unprivileged `flybot` user.
- The service must use `/var/lib/flytest-discord/events.jsonl` and `/var/lib/flytest-discord/events.jsonl.offset` for durable event state.
- The deployment must be safe to rerun and must preserve the remote event spool and offset.
- Local verification uses `\.venv\Scripts\python.exe -m pytest`, `\.venv\Scripts\python.exe -m flytest.verify`, `git diff --check`, and `git status`.

## Review Focus

- Missing or incorrectly-permissioned secret file: deployment aborts before installing or starting the service; covered by the deployment script's remote guard and its static test.
- Secret leakage through arguments or output: token never appears in script parameters, staged files, or verification output; covered by the deployment-script safety test.
- Existing DomainPatrol interference: deployment changes only new FlyBot paths and unit; covered by the remote before/after service-state comparison.
- Service starts but cannot write state: the service user owns the state directory and the remote smoke event must advance the offset.
- Discord delivery succeeds but the process dies or duplicates endlessly: systemd restart policy and the bridge's existing at-least-once offset behavior are verified by service status and the delivered-event check.

### Task 1: Add and test the hardened systemd unit

**Files:**
- Create: `deploy/flybot/flybot.service`
- Test: `tests/test_flybot_deployment.py`

**Interfaces:**
- Consumes: `flytest.discord_bridge` executed with `PYTHONPATH=/opt/flytest-discord/src`.
- Produces: a systemd unit named `flybot.service` that owns no DomainPatrol resources and writes only under `/var/lib/flytest-discord`.

- [ ] **Step 1: Write the failing unit-contract tests**

```python
from pathlib import Path


SERVICE_PATH = Path(__file__).parents[1] / "deploy" / "flybot" / "flybot.service"


def test_flybot_unit_has_isolated_runtime_and_state_paths():
    text = SERVICE_PATH.read_text(encoding="utf-8")
    required = (
        "User=flybot",
        "Group=flybot",
        "EnvironmentFile=/etc/flytest/flybot.env",
        "Environment=PYTHONPATH=/opt/flytest-discord/src",
        "WorkingDirectory=/var/lib/flytest-discord",
        "--spool /var/lib/flytest-discord/events.jsonl",
        "--state-file /var/lib/flytest-discord/events.jsonl.offset",
        "Restart=on-failure",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/lib/flytest-discord",
    )
    assert all(item in text for item in required)


def test_flybot_unit_does_not_reference_domainpatrol_or_embed_a_secret():
    text = SERVICE_PATH.read_text(encoding="utf-8").lower()
    assert "domainpatrol" not in text
    assert "discord.com/api" not in text
    assert "token=" not in text
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_flybot_deployment.py -q`

Expected: FAIL because `deploy/flybot/flybot.service` does not exist yet.

- [ ] **Step 3: Add the minimal unit**

```ini
[Unit]
Description=FlyTest Discord report bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=flybot
Group=flybot
WorkingDirectory=/var/lib/flytest-discord
EnvironmentFile=/etc/flytest/flybot.env
Environment=PYTHONPATH=/opt/flytest-discord/src
ExecStart=/usr/bin/python3 -m flytest.discord_bridge watch --spool /var/lib/flytest-discord/events.jsonl --state-file /var/lib/flytest-discord/events.jsonl.offset --poll-seconds 2
Restart=on-failure
RestartSec=5s
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictAddressFamilies=AF_INET AF_INET6
ReadWritePaths=/var/lib/flytest-discord

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_flybot_deployment.py -q`

Expected: all focused deployment-contract tests pass.

- [ ] **Step 5: Commit the unit and test**

```powershell
git add -- deploy/flybot/flybot.service tests/test_flybot_deployment.py
git commit -m "Add isolated FlyBot systemd unit"
```

### Task 2: Add the repeatable OpenSSH deployment script

**Files:**
- Create: `deploy/flybot/deploy.ps1`
- Modify: `tests/test_flybot_deployment.py`

**Interfaces:**
- Consumes: the current repository's `src/flytest/discord_bridge.py`, `src/flytest/__init__.py`, `deploy/flybot/flybot.service`, and SSH alias `first-droplet`.
- Produces: an idempotent command `powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet`.

- [ ] **Step 1: Extend the tests with script safety checks**

```python
DEPLOY_PATH = Path(__file__).parents[1] / "deploy" / "flybot" / "deploy.ps1"


def test_deploy_script_requires_existing_secret_and_never_accepts_token_value():
    text = DEPLOY_PATH.read_text(encoding="utf-8")
    assert "/etc/flytest/flybot.env" in text
    assert "FLYTEST_DISCORD_BOT_TOKEN" in text
    assert "FLYTEST_DISCORD_CHANNEL_ID" in text
    assert "param(" in text
    assert "Token" not in text.split("param(", 1)[1].split(")", 1)[0]
    assert "/etc/domainpatrol.env" not in text
    assert "systemctl restart flybot.service" in text
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_flybot_deployment.py -q`

Expected: FAIL because `deploy/flybot/deploy.ps1` does not exist yet.

- [ ] **Step 3: Implement the deployment script**

The script must:

1. Accept only `-HostAlias` (default `first-droplet`) and an optional
   repository-root override; never accept a token or channel value.
2. Resolve and validate the two bridge source files and the unit manifest.
3. Stage only those three files in a uniquely named local temporary directory.
4. Create a uniquely named remote `/tmp/flybot-deploy-*` directory through
   `ssh`, upload files with `scp`, and remove that explicit staging directory
   in a guarded `finally` path.
5. Run a remote `bash -s` script that first checks the existing env file is
   present, mode `600`, and contains both required variable names with nonempty
   values; it must never print the values.
6. Create `flybot` only if it does not already exist, create the two remote
   directories with explicit owners and modes, install the bridge files and
   unit, run `systemctl daemon-reload`, `systemctl enable flybot.service`, and
   `systemctl restart flybot.service`.
7. End by printing only `systemctl is-enabled` and `systemctl is-active` output
   for `flybot.service`. It must not read or print `/etc/domainpatrol.env`.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_flybot_deployment.py -q`

Expected: all deployment-contract and script-safety tests pass.

- [ ] **Step 5: Commit the deployment script**

```powershell
git add -- deploy/flybot/deploy.ps1 tests/test_flybot_deployment.py
git commit -m "Add repeatable FlyBot droplet deployment"
```

### Task 3: Document remote operation and event emission

**Files:**
- Modify: `docs/discord-bridge.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the deployment script and `flybot.service` paths from Tasks 1–2.
- Produces: operator commands for deployment, status, logs, and explicit event emission that do not expose the token.

- [ ] **Step 1: Add the operator contract**

Document these exact commands:

```powershell
powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet
ssh first-droplet "systemctl status flybot.service --no-pager"
ssh first-droplet "journalctl -u flybot.service -n 50 --no-pager"
ssh first-droplet "runuser -u flybot -- env PYTHONPATH=/opt/flytest-discord/src /usr/bin/python3 -m flytest.discord_bridge emit --spool /var/lib/flytest-discord/events.jsonl --status success --job 'remote job' --agent codex --summary 'completed'"
```

State plainly that the token remains only in `/etc/flytest/flybot.env`, that
the full FlyTest runtime is not deployed, and that event emission is explicit.

- [ ] **Step 2: Inspect the documentation for contradictions**

Run: `rg -n -i "local watcher|droplet|flybot.service|domainpatrol|token" README.md docs/discord-bridge.md`

Expected: documentation consistently distinguishes local source code, the
remote watcher, the protected secret file, and the untouched DomainPatrol
agent.

- [ ] **Step 3: Commit the documentation**

```powershell
git add -- README.md docs/discord-bridge.md
git commit -m "Document FlyBot droplet operation"
```

### Task 4: Deploy and verify the live droplet service

**Files:**
- Modify: remote `/opt/flytest-discord/src/flytest/discord_bridge.py`
- Modify: remote `/opt/flytest-discord/src/flytest/__init__.py`
- Modify: remote `/etc/systemd/system/flybot.service`
- Create: remote `/var/lib/flytest-discord/events.jsonl` and offset state as produced by the smoke event

**Interfaces:**
- Consumes: the committed deployment assets and the already-installed protected env file.
- Produces: an active `flybot.service` and one verifiable Discord delivery.

- [ ] **Step 1: Capture pre-deployment DomainPatrol state**

Run over SSH without reading its secret file:

```powershell
ssh first-droplet "systemctl show domainpatrol.timer -p LoadState -p ActiveState -p SubState -p NextElapseUSecRealtime --no-pager"
ssh first-droplet "systemctl show domainpatrol.service -p LoadState -p ActiveState -p SubState -p ExecMainStatus --no-pager"
```

Expected: the existing timer is loaded and waiting; the one-shot service is
not modified by the deployment.

- [ ] **Step 2: Run the deployment script**

Run: `powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet`

Expected: the command exits 0 and reports `enabled` and `active` for
`flybot.service` without printing secret values.

- [ ] **Step 3: Verify service identity and secret permissions**

Run:

```powershell
ssh first-droplet "systemctl show flybot.service -p User -p Group -p MainPID -p ExecMainStatus --no-pager"
ssh first-droplet "stat -c '%a %U:%G %n' /etc/flytest/flybot.env /opt/flytest-discord/src/flytest/discord_bridge.py /var/lib/flytest-discord"
```

Expected: service user/group are `flybot`, the service has a main process with
exit status 0, env mode remains `600`, code is root-owned and non-writable by
the service, and state is writable by `flybot`.

- [ ] **Step 4: Emit one controlled event as the service user**

Run:

```powershell
ssh first-droplet "runuser -u flybot -- env PYTHONPATH=/opt/flytest-discord/src /usr/bin/python3 -m flytest.discord_bridge emit --spool /var/lib/flytest-discord/events.jsonl --status success --job 'FlyBot systemd smoke test' --agent codex --summary 'remote watcher delivery verification'"
```

Expected: the command exits 0 and appends one event without needing the token
in the emitting shell.

- [ ] **Step 5: Verify the watcher advanced state and Discord received it**

Run a remote check that reads the protected token only in memory, queries the
configured channel's recent messages, and prints only whether the unique smoke
job text exists. Also verify the event offset is `1` and the service remains
active.

Expected: `discord_smoke=found`, offset `1`, and `flybot.service` active.

- [ ] **Step 6: Re-check DomainPatrol state**

Run the same two `systemctl show domainpatrol...` commands from Step 1.

Expected: the relevant state fields match the pre-deployment capture; no
DomainPatrol service or timer was restarted or altered.

- [ ] **Step 7: Run the complete local verification suite**

Run:

```powershell
\.venv\Scripts\python.exe -m pytest
\.venv\Scripts\python.exe -m flytest.verify
git diff --check
git status
```

Expected: all tests pass, provenance verification passes with original and
working data byte-identical, diff check is clean, and only the intended
deployment/spec/documentation commits are present.

- [ ] **Step 8: Commit any final verification/documentation adjustment**

```powershell
git add -- README.md docs/discord-bridge.md deploy/flybot tests/test_flybot_deployment.py
git commit -m "Verify FlyBot droplet bridge deployment"
```

## Final review checklist

- Confirm the repository contains no token, env file, spool, backup, or raw
  connectome artifact.
- Confirm `git diff --check` and the full suite were run after the last change.
- Confirm the remote service is active and the unique smoke message was found in
  `#fly-bot`.
- Confirm DomainPatrol's timer/service state was unchanged.
- Report the remote paths, service status, message result, and any deferred
  limitation: explicit events only; no automatic Codex completion detection.

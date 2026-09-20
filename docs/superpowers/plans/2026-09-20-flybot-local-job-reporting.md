# FlyBot Local Job Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give local Windows commands a small, useful end-to-end path to report job completion through the already-deployed FlyBot bridge.

**Architecture:** Extend the existing standard-library bridge with a safe SSH transport for one event and a local command wrapper that reports start and terminal status. The SSH transport sends only base64-encoded event data to a fixed remote Python append operation; the Discord token stays in `/etc/flytest/flybot.env` on the droplet.

**Tech Stack:** Python 3.12 standard library, OpenSSH, PowerShell/Windows shell, pytest, existing FlyBot systemd service.

**Spec:** `docs/superpowers/specs/2026-09-20-flybot-local-job-reporting-design.md`

## Global Constraints

- The Discord token is never a local argument, environment variable, payload, log line, or repository file.
- Existing local `emit` and `watch` behavior remains unchanged.
- Remote event writes run as the unprivileged `flybot` user and append only to `/var/lib/flytest-discord/events.jsonl`.
- Notification failures warn but do not change the wrapped command's exit code.
- Do not add a Discord Gateway, slash commands, arbitrary remote command execution, or job queue.
- Use the existing secret-blind deployer to update the droplet after local code passes.

## Review Focus

- Shell metacharacters in job titles and summaries must remain data, not remote commands; test the encoded transport command.
- An unavailable droplet must not turn a successful local job into a failure; test fail-open notification behavior.
- A failing or missing local command must still produce a terminal failure attempt and return a nonzero code.
- The remote module must be deployed before the live smoke test; do not mistake local unit tests for end-to-end proof.
- The token must not appear in source, event payloads, command arguments, or output.

### Task 1: Add tested remote notification and command wrapper

**Files:**
- Modify: `src/flytest/discord_bridge.py`
- Modify: `tests/test_discord_bridge.py`

**Interfaces:**
- Produces `append_event_remote(event, host_alias="first-droplet", runner=subprocess.run) -> None`.
- Produces `run_and_report(command, job, host_alias="first-droplet", agent="codex", cwd=None, notify=append_event_remote, runner=subprocess.run) -> int`.
- Adds CLI commands `notify` and `run` while preserving `emit`, `send`, and `watch`.

- [ ] **Step 1: Write failing transport and wrapper tests**

Add tests that first describe the public behavior:

```python
def test_append_event_remote_sends_encoded_event_without_discord_secret(monkeypatch):
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


def test_run_and_report_preserves_child_failure_when_notification_fails():
    events = []

    def failing_notify(event, host_alias="first-droplet"):
        events.append(event)
        raise DiscordBridgeError("ssh unavailable")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 7)

    assert run_and_report(["fake-job"], "wrapper smoke", notify=failing_notify, runner=fake_run) == 7
    assert [event["status"] for event in events] == ["started", "failure"]
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `\.venv\Scripts\python.exe -m pytest tests/test_discord_bridge.py -q`

Expected: FAIL because `append_event_remote` and `run_and_report` do not exist.

- [ ] **Step 3: Implement the minimal standard-library transport and wrapper**

Use `base64`, `shlex`, and `subprocess`. The remote command must be built from
the fixed code below, with `shlex.quote` around both the code and encoded event:

```python
remote_code = (
    "import base64,json,sys;"
    "from pathlib import Path;"
    "from flytest.discord_bridge import append_event;"
    "append_event(Path('/var/lib/flytest-discord/events.jsonl'), "
    "json.loads(base64.b64decode(sys.argv[1])))"
)
```

Run the focused tests again; expected: all pass. Then run the complete suite;
expected: all tests pass with no changes to existing bridge behavior.

- [ ] **Step 4: Commit the tested implementation**

```powershell
git add -- src/flytest/discord_bridge.py tests/test_discord_bridge.py
git commit -m "Add local FlyBot job reporting"
```

### Task 2: Document the useful local workflow

**Files:**
- Modify: `docs/discord-bridge.md`
- Modify: `README.md`

**Interfaces:**
- Documents `notify` for one event and `run` for a local command.
- States that the helper uses SSH, keeps the token remote, fails open for
  notifications, and is explicit rather than automatic.

- [ ] **Step 1: Add exact usage examples**

Document commands equivalent to:

```powershell
\.venv\Scripts\python.exe -m flytest.discord_bridge notify `
  --status success `
  --job "manual smoke" `
  --summary "reported from the local workspace"

\.venv\Scripts\python.exe -m flytest.discord_bridge run `
  --job "FlyTest verification" `
  -- .\.venv\Scripts\python.exe -m flytest.verify
```

Explain that `run` returns the child command's exit code and only warns if
Discord reporting is unavailable.

- [ ] **Step 2: Check docs for contradictions and secrets**

Run: `rg -n -i "notify|run --job|token|ssh|explicit|Gateway" README.md docs/discord-bridge.md`

Expected: local helper, remote secret location, explicit-event limitation, and
no Gateway claim are consistent.

- [ ] **Step 3: Commit documentation**

```powershell
git add -- README.md docs/discord-bridge.md
git commit -m "Document local FlyBot job reporting"
```

### Task 3: Deploy and prove the end-to-end loop

**Files:**
- Modify remote: `/opt/flytest-discord/src/flytest/discord_bridge.py`

**Interfaces:**
- Consumes the checked-in bridge and existing `/etc/flytest/flybot.env`.
- Produces a Discord message from a local command without a local token.

- [ ] **Step 1: Deploy the checked-in bridge**

Run: `powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet`

Expected: `enabled` and `active`; no secret output.

- [ ] **Step 2: Run a local notify smoke event**

Run `notify` with a uniquely named job and verify the remote offset advances.

- [ ] **Step 3: Run the local wrapper with a harmless successful command**

Run `run` around a short Python command; verify it returns `0`, emits start and
success events, and the unique terminal message appears in Discord.

- [ ] **Step 4: Run the final local verification suite**

Run:

```powershell
\.venv\Scripts\python.exe -m pytest
\.venv\Scripts\python.exe -m flytest.verify
git diff --check
git status
```

Expected: all tests and provenance checks pass, the repository is clean, and no
secret or remote spool is tracked.

## Final review checklist

- The remote service remains active as `flybot`.
- The final Discord message proves a local command reached the droplet.
- The wrapped command's exit code is preserved.
- Notification failure is explicitly fail-open.
- The implementation remains report-only and does not add Gateway behavior.

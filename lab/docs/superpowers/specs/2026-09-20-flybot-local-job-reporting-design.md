# FlyBot Local Job Reporting Design

## Goal

Make the deployed FlyBot bridge useful from the Windows project workspace by
letting local commands append report events to the droplet over the existing
SSH alias, without moving the Discord token off the droplet.

## Scope

The bridge gains two local-facing operations:

- `notify` sends one structured event to the remote FlyBot spool.
- `run` executes a local command, sends best-effort `started` and terminal
  `success`/`failure` events, and returns the wrapped command's exit code.

The remote service remains a report-only REST watcher. This change does not
add a Discord Gateway, slash commands, arbitrary remote command execution, job
queue, or automatic Codex lifecycle detection.

## Interface and transport

`append_event_remote(event, host_alias="first-droplet")` invokes the existing
OpenSSH client in batch/no-TTY mode. It serializes the event as JSON, encodes
that JSON as base64, and passes it to a fixed remote Python command. The remote
command runs as `flybot` and calls `append_event` on
`/var/lib/flytest-discord/events.jsonl`. Shell quoting is applied to the fixed
Python program and encoded payload; user text is never interpolated as shell
syntax.

`run_and_report(command, job, ...)` streams the child command's normal output,
does not capture or alter it, and treats notification failure as a warning
only. The child exit code is the wrapper's exit code. A missing command returns
the normal command-start failure code and still attempts a failure event.

## Security and operational constraints

- The Discord token is never a local argument, environment variable, payload,
  log line, or repository file.
- The local helper needs only the user's existing `first-droplet` SSH access.
- Remote event writes occur as the unprivileged `flybot` user.
- The deployed bridge is updated through the existing secret-blind deployer.
- Existing local `emit` and `watch` behavior remains unchanged.

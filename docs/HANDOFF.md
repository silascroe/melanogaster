# FlyTest handoff

Updated 2026-09-19 for the next Codex chat.

## What this project is

FlyTest is a local-first, inspectable experiment around the official FlyEM
Male CNS v1.0 release. The connectome wiring and annotations are real release
data. The retina, LIF parameters, memory, motor mapping, point-mass body, and
3D world are explicit simulator scaffolding. This is not a complete biological
fly or a validated behavior model.

Never edit `data/original-data/`. Keep the original and working copies
byte-identical. Do not commit Feather files, backups, `.venv/`, Godot caches,
or bulky movie/timestep artifacts.

## Current milestones

The browser baseline remains intact:

- `GET /api/run` is the regression control.
- `POST /api/arena/run` is schema version 2 and supports stages 54, 100, and
  250, moving lights/threats, the 9x5 retina, touch priority, descending
  population votes, memory, causal traces, and deterministic replay digests.

The standalone `arena3d/` project is now a live Godot client rather than a
replay viewer:

- `POST /api/arena/session` creates a persistent Python neural session.
- `POST /api/arena/session/{session_id}/step` accepts Godot's current body,
  light, and threat state and returns retina features, persistent LIF spikes,
  memory, descending votes, the chosen action, and the next deterministic
  state.
- Godot applies the returned action and sends the resulting world state back
  on the next tick.
- The scene defaults to stage 250. `SPACE` pauses; `R` creates a fresh neural
  session; right-drag orbits; the mouse wheel zooms.

This 3D lab is intentionally standalone. It is not part of the public website
yet, and no Cloudflare configuration is needed for it.

## Important files

- `src/flytest/arena_simulation.py`: arena configuration, retina/world model,
  batch replay, and stateful `ArenaSession`.
- `src/flytest/arena_circuit.py`: staged graph runtime and named sensory/output
  populations.
- `src/flytest/visual_simulation.py`: public server, `/api/run`, arena batch
  endpoint, and live session endpoints.
- `arena3d/main.gd`: 3D lab, world rendering, live tick loop, HUD, trail, and
  retina display.
- `arena3d/arena_bridge.gd`: Godot HTTP transport for the live loop.
- `tests/test_visual_simulation.py`: arena, staged graph, retina, memory, and
  live-session coverage.
- `docs/decisions.md`: provenance/model-boundary decisions.

## Run it again

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m flytest.visual_simulation --host 127.0.0.1 --port 8767
```

The first request for a larger graph stage can take a while while the official
working data is scanned and cached. The live Godot bridge has a 120-second
request timeout for that reason.

Use the installed Godot executable with the Windows compatibility renderer:

```powershell
& 'C:\Users\ringd\CodexProjects\Godot-GaulRTS\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe' --path 'arena3d' --display-driver windows --rendering-method gl_compatibility --audio-driver Dummy
```

The bundled portable editor is under `tools/godot/4.7/` and is ignored by
Git. In this environment the compatibility renderer is the reliable path;
headless/default rendering can fail for environment reasons unrelated to the
scene scripts.

## Last verification

The last completed checks were:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flytest.verify
git diff --check
```

Result: 30 tests passed; provenance verification passed; `git diff --check`
reported only existing line-ending warnings. Godot script parsing passed, and
a real stage-250 live capture showed `LIVE CLOSED LOOP`, neural visual action,
active spikes, the retina, moving beacon, threat, and trail.

## What is deliberately unfinished

The live session store is in-memory and local-only. Restarting the Python
server destroys sessions. The 3D body is still a simple point-mass controller;
there is no collision physics, flight dynamics, learning, webcam input, or
biological muscle model. The next useful work is probably improving the world
and observation interface—real Godot collision geometry, richer 3D stimuli,
and an inspector for the live causal chain—before adding more neurons or
putting the 3D lab on the public site.

## Worktree note

The worktree is intentionally dirty. Earlier FlyTest/Arena work and the
standalone Godot project are present as working changes. Do not reset or clean
the tree blindly. Review `git status`, inspect the staged file list, and make a
focused commit only after separating the desired project changes from any
other user work.

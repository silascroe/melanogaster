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

The first embodied world slice is now present:

- scripted demo requests include two explicit static obstacles; sandbox
  requests remain obstacle-free unless they provide an `obstacles` array;
- Python resolves the circular toy body with swept circle/AABB contacts and
  returns requested versus actual motion, collision IDs, boundary contacts,
  and obstacle touch features in every frame;
- Godot renders matching `StaticBody3D` shapes, probes the next move with a
  `ShapeCast3D`, and shows a causal HUD from world contact through sensory
  features, input currents, spikes, descending votes, and action;
- set `FLYTEST_ARENA_ENDPOINT` to point the Godot bridge at a non-default local
  server during a smoke test.

This 3D lab is intentionally standalone. It is not part of the public website
yet, and no Cloudflare configuration is needed for it.

The first bounded arena diagnostic now exists as
`src/flytest/beacon_approach.py`. It runs a static-beacon, no-threat,
no-obstacle sandbox replay against the existing stage-54 visual context and
writes compact `report.md`, `summary.json`, and `trajectory.csv` artifacts.
Its deliberately modest pass criterion is a reduced minimum distance that
also crosses the configured threshold; it is not a sustained tracking or
biological-behavior claim.

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
- `src/flytest/beacon_approach.py`: bounded beacon diagnostic and compact
  artifact writer.
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

Result: 50 tests passed; provenance verification passed; `git diff --check`
reported only line-ending warnings. The real stage-54 beacon-approach replay
also passed: the body went from 2.828 m to a minimum of 1.416 m, crossing the
1.5 m threshold in a 30-frame causal trace. Godot script parsing passed, and a
real compatibility-renderer live capture completed against a fresh Python
stage-54 server. The headless Godot runner still crashes in this environment
while trying to write its `user://` log/settings files; that is an environment
limitation, not a scene parse error.

## What is deliberately unfinished

The live session store is in-memory and local-only. Restarting the Python
server destroys sessions. The 3D body is still a simple circular point-mass
controller; there is no full character-body physics, flight dynamics, learning,
webcam input, or biological muscle model. The next useful work is to add the
remaining small deterministic scenarios around the new geometry—wall blocking
and threat crossing—and inspect their causal traces before adding more neurons
or putting the 3D lab on the public site.

## Worktree note

The bounded beacon slice is committed on `experiment/beacon-approach` as
`fef7836`; `main` remains the known working baseline. The worktree is clean.
Continue by reviewing the branch before adding the wall-blocking or
threat-crossing scenarios. Do not reset or clean the tree blindly.

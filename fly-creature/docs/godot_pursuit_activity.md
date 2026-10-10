# Experimental pursuit in Godot

The reviewed delay/center candidate now runs through the live Python service
and Godot body, behind an explicit `activity_v1` option. The earlier LIF
controller remains the startup default. Press `B` for experimental pursuit,
`C` for disconnected/intact comparison, and `B` again for baseline pursuit.

## Contract and result

The packaged circuit has 281 cells and 366 recorded selected edges. The
registered visual map, normalized activity adapter, 15-degree aperture
crossfade, gain 0.65, 1.2 rad/s cap and 200 ms command queue are modelling
choices. These outputs are neither simulated membrane voltages nor spikes.
The giant-fiber jump pathway remains a separate LIF implementation.

Godot advances world state by 10 ms, sends the resulting geometry to Python,
and applies its returned turn command to the next world tick. The adapter
queues commands for 20 ticks. The synchronous loopback prototype preserves
logical timing under load; real-time rendering can slow. It is not yet a
production transport design.

Two graphics-enabled runs of the already evaluated harmonic path each
completed 800 live service steps. Mean absolute target bearing was 2.350
degrees intact versus 12.296 disconnected, matching the offline results
within 0.01 degrees. The disconnected fly received no turning commands.
Every motor command was checked against the activity from 20 ticks earlier.
This establishes integration parity on one known path, not new biological
validation or generalization. The offline wiring controls are documented in
[the delay diagnosis](pursuit_delay_result.md).

Frame inspection revealed an existing visual yaw sign mismatch: the body's
rendered direction opposed the world heading during turns. The actor rotation
now agrees with the world forward vector. Recorded telemetry checks their dot
product stays within 1e-6 of one. The HUD sits below the fly in HD recordings.

Compact measured evidence is in
[godot_pursuit_activity_v1.json](evidence/godot_pursuit_activity_v1.json).
18 creature tests and 69 lab tests pass; original/working data verification
passes. Integration checks use actual rendered-run logs and FFprobe metadata.

## Reproduce

From the workspace root, after installing the creature package in the root
virtual environment:

```powershell
.\fly-creature\tools\capture_pursuit_activity.ps1
.\.venv\Scripts\python.exe fly-creature/tools/check_godot_pursuit.py
```

The capture script uses existing portable Godot 4.7 and FFmpeg 9.0.2 in
`C:\Users\ringd\.codex\tools\`. It starts an isolated loopback service on
18769, records intact and disconnected versions, and stops its own service.
A temporary `godot/override.cfg` sets the actual movie viewport to 1920x1080;
the script refuses an existing override and removes its own in `finally`.
Window resolution alone does not change MovieWriter's internal viewport.

Generated MP4s are under `outputs/pursuit_activity/`, each 8.1 seconds at
1920x1080, 60 fps. AVI sources, logs and frame previews stay local and ignored.
The clips contain eight seconds of simulation plus startup frames.

For interactive use, start `python -m fly_creature.server`, run `godot/`, and
press `B`. For scripted use, pass `--pursuit-experimental`; optional flags are
`--pursuit-seconds=8`, `--pursuit-trace`, `--pursuit-control`, and
`--pursuit-path=step_hold`. The default experimental path is harmonic.

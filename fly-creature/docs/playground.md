# Interactive pursuit comparison playground

This is a steering-only scene. Four independent bodies start from identical
positions and receive the same authored target trajectory: intact activity
wiring, disconnected wiring, an ordinary proportional controller with a
200 ms queue, and the same ordinary rule with no queue. Walking speed is
authored at 0.55 m/s. There is no neural forward-speed control, stopping,
search, jump or physical flight in this scene. The existing creature demo
retains those separately labelled demonstrations.

## Play locally

From the workspace root in PowerShell:

```powershell
.\fly-creature\tools\run_playground.ps1
```

The launcher uses the existing portable Godot under
`C:\Users\ringd\.codex\tools\godot\4.7\` and a project virtual environment.
It shows a local interactive game window. If it starts Python, it stops only
that service after the game closes. If a compatible service already owns the
port, it reuses it and leaves it running. Use `-Port 8769` for another port.
It does not install apps or change PATH. Agent-generated captures are previews;
run this launcher on your computer to interact with the scene.

Alternatively, start `python -m fly_creature.server` and run
`godot --path godot res://playground.tscn` from this folder using your Godot
executable. Set `FLY_CREATURE_ENDPOINT` if the server uses another local port.
Press **P** in the original creature scene to open this playground; **Esc**
returns to that scene.

## Controls and interpretation

The target menu provides gentle following, fast lateral motion, repeated
reversals, brief disappearance, reappearance elsewhere, stationary depth,
and manual placement. Manual mode lets you click/drag the floor to place
the shared target. The camera holds still while dragging.

The inspection menu changes which body uses the detailed fly model. Other
bodies appear as colored dots/trails. All four continue running; changing
the inspected controller does not change their results. Cards show mean
absolute target bearing, active-target visibility, current sensor status and
the last turn command. Mean error includes active but unseen targets and
excludes inactive targets. A low error alone does not establish neural work.

Depth and starting-heading sliders reset and replay the world, including
keyboard adjustments. Mirror reflects the initial heading and preset X
trajectory (or the current manual target). Reset clears all histories and
statistics, but retains your selected configuration and target visibility.
Each run ends at exactly ten simulated seconds; reset to replay.

Pause freezes the world after any already-submitted batch completes, at most
five ticks. Hide clears queued turning on the next simulation tick; while
paused, changes to simulation inputs take effect on resume. Space toggles
pause, R resets, and F switches close/wide cameras. Presets are demonstration
replays; adjusting a slider is not a new validation experiment.

The ordinary gain is fixed at 4 rad/s per radian, selected in the previous
[stress experiment](pursuit_stress_result.md). Both queued controllers use
the tested 200 ms delay. The activity outputs are model activity units, not
membrane voltages or measured spikes. The immediate ordinary controller
has deliberately different delay and is labelled accordingly.

## Timing and transport

Python `PlaygroundSession` owns this comparison's bodies and stimulus.
Every controller advances in exactly 10 ms logical ticks. Godot sends
asynchronous requests of one to five ticks, with one request in flight.
`HTTPRequest.use_threads` keeps socket polling off the rendering loop. The
body applies the prior command before reading the next target, matching the
frozen stress runner. One- versus five-tick batches produce identical states.

Each step has an ordered sequence number. Repeating the same request returns
its cached response without advancing time; conflicting/out-of-order requests
are rejected before mutation. Reset during a pending request discards that
response and creates a new world. Inspection is entirely client-side.
The service retains one comparison world at a time, separately from its
original creature-session store. Two simultaneous playground clients are
not supported.

The HUD shows request latency and accumulated simulation backlog. Under load
the logical simulation may run behind wall time; it does not enlarge the
neural timestep or drop already-generated ticks. The first frame-polled HTTP
capture accumulated lag. Threaded requests produced the final 8.05-second
clip with 8.01 simulated seconds. Recorded mean service compute was about
0.24 ms/request and mean request round trip about 83 ms during MovieWriter
capture. Recording slows wall-clock rendering; those numbers are not a
benchmark of normal interactive play on the user's desktop.

## Verification and preview

[Compact evidence](evidence/playground_v1.json) records the actual Godot
interaction checks and preview metadata. Godot checked pause, hiding,
mouse input through the engine dispatcher, view switching, preset reset,
sliders, mirror, controller clocks and reset during an in-flight request.
The injected mouse test converts viewport coordinates into window coordinates
before dispatch, as described in the
[Godot coordinate documentation](https://docs.godotengine.org/en/stable/tutorials/2d/2d_transforms.html).

The preview's 482 snapshots reached tick 801; all controller clocks and final
body/error states match a direct Python replay. The MP4 is 1920x1080 at
60 fps, 8.05 seconds. Extracted frames were inspected for HUD clipping and
scene visibility. 28 creature tests and 69 lab tests pass. Frozen stress
hashes/traces and original/working release verification pass. No frozen
neural, map, graph or stress-protocol file was changed.

```powershell
# From the workspace root:
.\fly-creature\tools\capture_playground.ps1
# Faster control check without recording:
.\fly-creature\tools\capture_playground.ps1 -ChecksOnly
.\.venv\Scripts\python.exe fly-creature/tools/check_playground.py
```

The capture script starts an isolated service on 18771, runs the actual
graphical interaction check, records the scene, and cleans up its own service
and temporary viewport override. AVI/MP4, logs and frames stay ignored under
`outputs/playground/`. The compact evidence is tracked. No new application
or Python dependency was installed.

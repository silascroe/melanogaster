# Fly Creature

A playable 3D fruit fly whose reactions run on the recorded wiring of a real
fly: subsets of the FlyEM Male CNS connectome, driven by a reimplementation of
the Shiu et al. (2024) whole-brain spiking model. It jumps from looming objects,
steers toward targets, feeds on sugar and refuses bitter drops, grooms dusty
antennae, sings to a female, and backs away when its forelegs hit an obstacle.
Each reaction passed a whole-brain test against shuffled wiring before it went
into the game. Walking, animation, sensing and action thresholds are
engineered, and each sense runs its own brief brain copy, so this is not one
integrated neural fly. A browser version of one reaction is live at
https://silascroe.github.io/melanogaster/.

Everything needed to run it is inside this folder: copy `fly-creature/`
elsewhere and follow the setup below. No connectome download is needed to play.

## Play

**Easiest (Windows):** double-click `Play-Fly-Creature.cmd`. It finds Python
and Godot, starts the brain service in the background, opens the game, and stops
the service when you close the window. Problems appear in a pop-up. Options:
`tools\play.ps1 -Scene playground` or `-Port <number>`; set `FLY_CREATURE_GODOT`
if Godot is somewhere unusual.

**By hand,** from this folder in PowerShell (Python 3.12+, Godot 4):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[fast-brain]"
.\.venv\Scripts\python.exe -m fly_creature.server
```

Then open `godot/` in Godot 4 and run its main scene. The `fast-brain` extra
installs Numba, which the brain needs to run in real time. The service listens
only on `127.0.0.1:8768`; set `FLY_CREATURE_ENDPOINT` before starting Godot if
you change the port.

| Input | What happens |
|---|---|
| (nothing) | the fly roams the table on its own (engineered wandering) |
| left-click floor | place a target; LC10a input steers the fly to it, singing as it turns |
| right-click floor | drop sugar; the fly walks over and feeds |
| Shift + right-click | drop bitter-laced sugar; the fly does not feed |
| `SPACE` | throw an object at the fly; looming input makes it jump |
| `E` | dust the antennae; the fly stops and grooms |
| `O` | put a sugar cube in its path; foreleg touch makes it back up |
| `M` | add a wandering female; the male follows and courts her |
| `C` | cut the wiring onto the action neurons (control); press again to restore |
| `N` | show or hide the neuron map; drag on it to turn it |
| `R` | reset the brain and world |
| `WASD` | walk the fly yourself while held |
| `G` / `T` / `F` | roaming on/off, take off or land (animation only), close/wide camera |
| `B` | cycle to the older hand-built circuits (see below) |
| `V` / `P` | older moving-target pursuit demo / comparison playground |

A brain panel at the top right shows the input and action neurons for every
circuit, and which actions are on. The neuron map on the left draws all 28,584
neurons of the packaged subsets in 3D, each at its cell body in the MaleCNS
release, and lights the ones that fired in the last fraction of a second in the colour of
the sense whose brain copy fired them. The action neurons are ringed and
labelled. 1,407 sensory neurons (taste, antenna, leg bristles) have their cell
bodies outside the scanned tissue; they are drawn near the neurons they connect
to, and that position is approximate (`tools/export_brain_map.py`). Glow time,
colours and dot sizes are display choices. When many thousands of neurons light
up at once, that is the published model's runaway firing
([about 13,500 neurons](docs/whole_brain_result.md#problem-found-in-live-use-and-two-failed-fixes)),
not a display effect.

## What each reaction uses

All reactions run in whole-brain mode, the default. The packaged subsets were
chosen from whole-brain activity (`src/fly_creature/data/brain_subset_v*.npz`);
`SENSE_PACKAGE` in `brain_session.py` says which subset each sense uses. Every
sense drives its own copy, which resets after 500 ms without input.

- **Jump:** an approaching object's apparent size and expansion speed drive
  LC4 and LPLC2; any giant-fibre (DNp01) spike outside a 1.2 s cooldown
  triggers the jump animation.
- **Steer and sing:** the target's bearing drives LC10a on one side. The DNa02
  left/right difference becomes a turn rate, and a smoothed pIP10 rate above
  30 Hz swings out the wing on the target's side. The female (`M`) is the same
  target channel in a costume; her look, wandering and his stopping distance are
  presentation only (`godot/capture_female.gd` compares intact and cut wiring).
- **Feed and refuse bitter:** contact with a drop drives the LB3 sugar neurons,
  plus the LB1 bitter neurons for a bitter drop. A smoothed MN9 (proboscis motor
  neuron) rate of 20 Hz or more means feeding; bitter input suppresses it.
- **Groom:** dust drives Johnston's organ zones C and E; smoothed aDN activity
  above 30 Hz plays the foreleg sweep until the engineered dust timer clears.
- **Back up:** foreleg contact with the cube drives the foreleg touch bristles;
  smoothed MDN activity of 8 Hz or more reverses the fly. The 0.8 s minimum
  back-up, the turn away and a give-up turn after 1.5 s are engineered
  (`godot/capture_backup.gd` compares intact and cut wiring).

`godot/capture_autonomy.gd` is a scripted check of roaming, jumping, target
approach, feeding, grooming and bitter refusal in the scene;
`godot/capture_map.gd` takes neuron-map screenshots for each sense. What was tested,
what failed and what is engineered, reaction by reaction:
[the whole-brain result](docs/whole_brain_result.md), written against
[the protocol](docs/whole_brain_protocol.md). Design choices are in
[decisions](docs/decisions.md) and the code layout is in
[architecture](docs/ARCHITECTURE.md).

## Showcase page

`site/` is a static web page that runs the obstacle copy (subset v4, 4,871
neurons) live in the browser while a cartoon fly walks into a sugar cube;
cutting the wiring onto MDN is one button. `site/brain.js` is a JavaScript port
of `brain_model.py` that gives the same spikes as the Python engine on a
recorded input (`tests/web/check_web_brain.mjs`), and `tests/web/check_web_demo.mjs`
runs the page's loop with intact and cut wiring. Preview it with
`python -m http.server --directory site` and open `http://localhost:8000`.
`.github/workflows/pages.yml` at the repository root publishes it to GitHub
Pages from `main`. Rebuild its data with `tools/export_web_brain.py` (needs the
release and the `build-circuit` extra).

## The visual fly

`godot/fly_actor.tscn` is the reusable Godot fly. It contains the imported model,
its textured materials, wing and leg pivots, tripod gait, jump, and a separate
takeoff, cruising, and landing animation. The current room instantiates this
scene; future rooms can instance the same file. Set its root position on the floor and its Y rotation to the
desired heading, then call `advance(delta, walking, speed)` each frame. Call
`request_jump()` to start a jump, `request_takeoff()` and `request_landing()` for
flight, `is_flying()` to query that state, `is_recovering()` to pause walking
during jump preparation and landing, and `reset_actor()` when resetting a world. The fly scene does
not choose destinations, interpret sensors, or contain the neural circuit.
Flight height, wingbeats, and leg tucking are animation rules; this is not
three-dimensional flight physics or a neural flight controller.

The playable scene uses the textured male fly in `godot/assets/male_drosophila.glb`.
The editable Blender source is
`art/male_drosophila_v2.blend`; its image maps are packed inside. v2 is built
from the preserved original (`art/versions/v1-original/`) by
`tools/refine_fly_model.py`, which gives the fly segmented, tapering legs with
Drosophila-like proportions (a tarsus about as long as the tibia, resting on
the ground), leg bristles, claws and pulvilli, the male sex comb, a reshaped
head (short front-to-back, eyes forming its sides, a broad frons, paired
antennae hanging in a shallow facial recess, mouthparts on the underside), and
matte compound eyes. Godot's
asset is a self-contained glTF with simpler realtime materials, converted
bristles/veins, and separate wing, hip, knee, and ankle pivots. Godot adds small idle wing
motion, a procedural six-leg tripod gait with foot targets and leg IK that keeps the tarsi flat,
body bob, and distinct takeoff and landing poses. These animations are
visual engineering, not outputs from the connectome. The Godot camera has a
close follow view so the model is actually visible; `F` restores the wide
room view. The kitchen-table dressing (`godot/kitchen_world.gd`) is presentation
only and does not affect movement or the brain.

To rebuild v2 and the glTF from this folder with Blender on your path:

```powershell
blender -b art/versions/v1-original/male_drosophila_v1.blend --python tools/refine_fly_model.py
blender -b art/male_drosophila_v2.blend --python tools/export_fly_model.py
```

Godot re-imports the changed `.glb` the next time the editor opens (or run
`godot --headless --path godot --import`). The actor still accepts the v1 asset,
whose legs have no ankle pivot; it reads the proboscis base from whichever
model's nub it finds.

The generated `art/export_maps/` contains the color variants, normal maps, and
subtle leg-cuticle map used by that export; the `.glb` embeds them. The export
script does not modify the `.blend`. This is a first realtime asset, not a
finished character rig: feet are held near their ground targets during stance, but turns, reach limits,
and the stylized body motion can still produce small placement errors. Blender
studio lighting and Godot lighting will not match exactly.

For an animation-only recording, Godot can drive a seeded roaming route and
scripted flight without keyboard input or the Python service. From this folder, run a
graphics-enabled Godot build (not `--headless`):

```powershell
godot --path godot --write-movie fly_animation.avi --fixed-fps 30 --quit-after 300 -- --animation-demo
```

The resulting AVI is ten seconds at 30 frames per second. The route and flight
are scripted presentation motion; this mode does not run the neural circuit.
Godot needs a real graphics renderer to capture the scene. A portable FFmpeg
build can convert the AVI to MP4 for easier playback.

For a focused, head-first walking clip with a slow straight walk and stop:

```powershell
godot --path godot --write-movie fly_forward_walk.avi --fixed-fps 60 --quit-after 540 -- --walking-demo
```

This records nine seconds at the project's default 1280 × 720 viewport. Set
the viewport width and height in `godot/project.godot` to 1920 and 1080 for a
1080p recording, then restore them if you want the normal 720p editor window.
The timing and foot paths are authored to resemble observed fruit-fly walking;
see [the gait research and real-fly videos](docs/real_fly_walking_references.md).

## Older hand-built circuits and the paused research

Before the whole-brain model, the creature ran small hand-picked circuits, and
`B` still cycles to them. The **loom escape** circuit
(`src/fly_creature/data/loom_escape_v1.json`) has 313 traced neurons (LC4, LPLC2
and the two DNp01 giant fibres) and their 311 direct connections, run with a
simplified one-step LIF. The **LIF pursuit** reads a side-specific DNa02 voltage
bias from a selected LC10a-to-AOTU-to-DNa02 route as an analog turn command,
because DNa02 did not spike at those settings. The **activity pursuit**
(`activity_v1`) is a later source-inspired candidate with a 200 ms motor queue
([integration report](docs/godot_pursuit_activity.md)). The whole-brain model
replaced them because signals could not cross relay neurons at the old settings.

From late September to 10 October 2026, a validation campaign compared the
pursuit circuit with recorded fly neural responses. In short: the intact wiring
helped in particular situations and beat shuffled wiring on aggregate, but it
did not clear its practical gates against simple controls, and fast motion
exposed clear limits. The campaign is paused and its frozen records stay in
`docs/`. Start with the [pursuit milestone](docs/pursuit_milestone.md), the
[trust audit](docs/pursuit_trust_audit.md), the
[stress test](docs/pursuit_stress_result.md), the
[recorded-AOTU benchmark](docs/lc10a_recorded_benchmark_result.md), its
[diagnosis](docs/lc10a_response_diagnosis.md) and the
[downstream readiness report](docs/pursuit_downstream_readiness.md).

Tools from that period still run. The [comparison playground](docs/playground.md)
(`tools/run_playground.ps1`, or `P` in the game) races intact wiring,
disconnected wiring and ordinary rules against one target. Without Godot,
`python -m fly_creature.diagnostic` compares the loom circuit intact and
disconnected, and `python -m fly_creature.pursuit_diagnostic` runs the
closed-loop pursuit comparison. With the service running, `--pursuit-demo` and
`--pursuit-control` record the intact and bridge-removed pursuit:

```powershell
godot --path godot --write-movie pursuit_intact.avi --fixed-fps 60 --quit-after 480 -- --pursuit-demo
godot --path godot --write-movie pursuit_disconnected.avi --fixed-fps 60 --quit-after 480 -- --pursuit-control
```

## Data and provenance

All circuit data comes from the official [FlyEM Male CNS v1.0 release](https://male-cns.janelia.org/download/).
MaleCNS is a collaboration between FlyEM at HHMI Janelia, the University of
Cambridge Department of Zoology, the MRC Laboratory of Molecular Biology and
Google Research, and is licensed CC-BY. The packaged files are filtered
derivatives: the brain subsets keep signed connection counts for the selected
neurons, and the older JSON circuits keep selected annotations, predicted
transmitters and direct weighted edges. No release file is needed at runtime.

The neuron model uses the settings of Shiu et al. (2024), *A Drosophila
computational brain model reveals sensorimotor processing*
([code](https://github.com/philshiu/Drosophila_brain_model)), reimplemented
here, not the authors' code. Transmitter signs follow the release's
predictions; a predicted sign is a modelling convention, not a measurement. The
older loom circuit's choice of LC4/LPLC2 inputs follows
[Ache et al., *Current Biology* (2019)](https://doi.org/10.1016/j.cub.2019.01.079).

Rebuilding needs a local release and the `build-circuit` extra
(`pip install -e ".[build-circuit]"`). `tools/build_whole_brain.py` builds the
whole-brain cache, the `tools/run_*_test(s).py` scripts repeat the whole-brain
tests, `tools/build_brain_subset.py` and `tools/build_mdn_subset.py` rebuild the
subsets, and `tools/export_circuit.py` rebuilds the old loom circuit. The tools
only read the release Feather tables; review any regenerated file before
replacing a shipped one.

## Project boundary

This folder owns its Python package, Godot project, compact data, site and
instructions. It has no runtime imports from `../lab/src/flytest/` and no runtime
reads from `../data/`. The older FlyTest lab remains a separate record outside
this folder.

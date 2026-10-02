# Fly Creature

A standalone, local 3D creature with two inspectable connectome-backed reactions. A fly can be moved around a small room or allowed to roam with an engineered controller; an approaching object supplies visual features to a recorded MaleCNS pathway and giant-fiber activity triggers a jump. A separate moving target can drive a selected LC10a-to-DNa02 route whose modeled voltage difference turns the walking fly. This is a playable slice of a larger creature project, not an autonomous neural fly or a biological flight simulator.

## Direction

Build the creature by adding well-understood sensory-to-action pathways one at
a time. Each pathway should earn its place through controlled comparisons:
which recorded fly connections matter, what behavior they change, and whether
that result survives new situations and suitable non-connectome controls.
More neurons alone are not progress. The long-term aim is a creature whose
behavior depends in an identifiable way on *which fly neurons connect to
which*, while keeping simulated neural dynamics, sensory inputs, and body
rules plainly labeled as our engineering choices.

The pursuit research has connected a verified reference to our
MaleCNS v1.0 circuit. The [reference contract](docs/pursuit_reference_contract.md)
pins the authors' code and chosen protocol. An offline Python implementation
matches the authors' numerical core on static and step cases; the
[comparison report](docs/pursuit_reference_result.md) gives its limits.
The [v1.0 mapping audit](docs/pursuit_mapping_result.md) found that all 16
published downstream partner IDs retain their types, but the response curves
already incorporate connection strength and cannot be fed directly into our
individual v1.0 edges. A portable, offline v1.0 activity projection now
exposes the selected path without reusing those curves. The original 5°–60°
input map missed the lateral AOTU025 field, as the
[field-gap diagnosis](docs/pursuit_field_gap_diagnosis.md) shows. A new
[registered eye-map candidate](docs/pursuit_registered_eye_map_result.md)
transfers a published FAFB eye map through the MaleCNS column coordinates;
it passes the fixed-fly field check and wiring-shuffle control. The
[frozen Step 4 evaluation](docs/pursuit_step4_result.md) then tested a
source-inspired activity adaptation on eight held-out target paths. Its
specific wiring helped relative to bridge removal and shuffles, but the
controller failed continuous settling and gain-sensitivity gates. It remains
offline; Step 5 Godot integration was not warranted for that candidate.
The earlier LIF implementation remains the startup default; the later activity
candidate described below has a separate opt-in integration.

The subsequent [timing and center-field diagnosis](docs/pursuit_delay_result.md)
reproduces the failure and separates visual-history delay, motor delay, and
center input. A declared 200 ms motor-effect / smooth-overlap candidate settles
and passes a six-path offline review gate with wiring controls and gain
sensitivity. It now has an opt-in [experimental Godot integration](docs/godot_pursuit_activity.md);
the timing and overlap remain explicit modelling hypotheses.

The [frozen stress test](docs/pursuit_stress_result.md) now checks 48 new
conditions without retuning the working controller. Intact wiring meets the
declared envelope on 32/36 supported-task cases and beats all 32 shuffled
circuits on aggregate error. It modestly improves on a calibrated ordinary
controller with the same delay, but an ordinary controller without that delay
tracks better overall. Fast motion, wide initial headings, and walking past
nearby stationary targets expose clear limits. These are model results, not
validated fly biology; the Godot controller remains unchanged.

The subsequent [motion-rule diagnosis](docs/pursuit_motion_result.md) isolates
a direction-rule tradeoff and a strong motor-delay limit. Removing direction
sensitivity helps fast paths but worsens gentle tracking; no input candidate
qualifies. On 12 fresh fast/mixed-motion paths, the current model beats only
1/32 shuffled circuits on aggregate, so its wiring advantage is limited to
particular situations. Production settings remain unchanged. The subsequent
[timing audit and next benchmark contract](docs/pursuit_timing_contract.md)
confirms a published 200 ms feedback delay and shows that redistributing it
through our static adapter gives identical commands. The next implementation
should compare the reference and our adaptation under matched retinal inputs.

The [LC10a source review](docs/lc10a_visual_input_research.md) explains why
our MaleCNS annotations do not directly supply individual visual fields.
The [first skeleton-derived input experiment](docs/visual_input_experiment.md)
found wiring-specific alignment but worse tracking than the current input.

The [fixed-fly pathway probe](docs/visual_pathway_probe.md) shows that the
experimental input creates a coarse frontal/lateral split in the two AOTU
branches, but no consistent motion-direction preference or stronger DNa02
steering signal. Its charts and compact pulse data are linked from the report.

The [upstream visual-map and motion experiment](docs/visual_motion_experiment.md)
uses MaleCNS medulla-column inputs to orient the LC10a map without consulting
its steering outputs. This independently supports the skeleton axis, but the
retinal degrees remain approximate. A simple motion-sensitive input suppressed
static responses and made pursuit substantially worse: 17.102° mean bearing
error versus 9.903° for the playable input and 9.088° for a direct rule on five
paths. It remains offline; the playable default is unchanged.

Everything required from this workspace is inside this folder. Copy `fly-creature/` elsewhere and use its own setup instructions. Python 3.12+, Godot 4, and the Python dependencies still need to be installed on the destination computer.

## Run

For the [interactive comparison playground](docs/playground.md), run
`tools/run_playground.ps1` from this folder, or press `P` in the original
creature scene. Four controllers run together against one shared target:
intact wiring, disconnected wiring, and ordinary rules with/without delay.
Choose presets or drag a manual target; inspect the colored trails and live
error cards. [Architecture](docs/ARCHITECTURE.md) explains the two scene/world
ownership boundaries. The frozen neural controller settings are unchanged.

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m fly_creature.server
```

Open `godot/` as a project in Godot 4 and run its main scene. The Python service listens only on `127.0.0.1:8768` by default. Set `FLY_CREATURE_ENDPOINT` to another local base URL before starting Godot if you change the port.

`WASD` moves the fly across the room. `V` starts a moving-target neural pursuit demonstration; the fly walks forward and its heading follows the DNa02 voltage readout. `C` restarts the same scene with its AOTU-to-DNa02 bridge removed (and disconnects the independent jump circuit); press it again to restore the connections. `G` toggles simple roaming between nearby goals. `T` toggles authored flight and landing. `SPACE` sends an object toward its current heading. `F` toggles between close and wide cameras. `R` resets the neural session and world. The target path, visual feature encoding, walking speed, and voltage-to-turn rule are engineered. See the [pursuit milestone](docs/pursuit_milestone.md).

## Visual fly

Press `B` to start the revised experimental activity pursuit mode, and `C`
to compare disconnected wiring. `B` again returns to the older LIF pursuit.
The experimental mode advances Python and the world in exact 10 ms ticks,
with a 200 ms motor queue and 15-degree input overlap. Its HUD reports activity
units, not voltage or spikes. Under load this synchronous local prototype can
slow rendering rather than drop simulation ticks. See the
[integration report and recording commands](docs/godot_pursuit_activity.md).

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

The playable scene now uses the textured male fly in `godot/assets/male_drosophila.glb`
instead of the first primitive placeholder. The editable Blender source is
`art/male_drosophila_textured.blend`; its image maps are packed inside. Godot's
asset is a self-contained glTF with simpler realtime materials, converted
bristles/veins, and separate wing, hip, and knee pivots. Godot adds small idle wing
motion, a procedural six-leg tripod gait with foot targets and two-segment leg IK,
body bob, and distinct takeoff and landing poses. These animations are
visual engineering, not outputs from the connectome. The Godot camera has a
close follow view so the new model is actually visible; `F` restores the wide
room view.

To rebuild the glTF from this folder with Blender on your path:

```powershell
blender -b art/male_drosophila_textured.blend --python tools/export_fly_model.py
```

The generated `art/export_maps/` contains the color variants, normal maps, and
subtle leg-cuticle map used by that export; the `.glb` embeds them. The export
script does not modify the `.blend`. This is a first realtime asset, not a
finished character rig: feet are held near their ground targets during stance, but turns, reach limits,
and the stylized body motion can still produce small placement errors. Blender
studio lighting and Godot lighting will not match exactly. The neural service
and circuit data are still entirely inside this project and unchanged by the visual swap.

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

The small circuit-level diagnostic can be run without Godot:

```powershell
.\.venv\Scripts\python.exe -m fly_creature.diagnostic
```

It prints a fixed approach for intact and disconnected conditions. In the recorded local run, the intact circuit first requested a jump at frame 24; the disconnected condition had no giant-fiber spikes or jump. That is one configured comparison, not a claim about general behavior.

## What is running

The packaged `src/fly_creature/data/loom_escape_v1.json` contains 313 traced neurons: 126 LC4, 185 LPLC2, and two DNp01 giant fibers, plus 311 recorded direct weighted connections from LC4/LPLC2 to DNp01. It is a **selected direct path**, not the whole fly brain. The release's predicted neurotransmitter for the selected presynaptic neurons is acetylcholine; the simulator treats it as excitatory by convention.

Python converts object distance and motion into apparent angular size and expansion speed. LC4 receives an engineered expansion-speed current; LPLC2 receives an engineered size-during-expansion current. A simplified, one-step-delayed leaky integrate-and-fire model updates the selected cells. A DNp01 spike outside the animation cooldown requests a jump. The 3D scene and the labels show this chain.

The input encoder, model parameters, jump rule, and body physics were made for this project. This implementation does not process camera pixels, simulate the retina, drive fly muscles, or establish that the selected wiring outperforms another controller. Disconnecting the edges shows that the current demo uses them; it does not establish a unique advantage of fly anatomy. See [decisions](docs/decisions.md).

A separate [visual steering circuit investigation](docs/steering_candidate.md)
checks a possible LC10a-to-DNa02 route in the Male CNS release. Its matched
neural-activity probe produces a side-specific DNa02 voltage bias but no DNa02
spikes under the fixed settings. The playable pursuit mode reads that voltage
bias as an analog turn command and labels the readout as engineered.

The [pursuit trust audit](docs/pursuit_trust_audit.md) compares the current
controller with wiring interventions and a simple direct-bearing tracker across
target paths, input strengths, and update intervals. It documents where the
connectome claim stops.

The [visual input/readout audit](docs/input_readout_audit.md) tests the
upstream-derived LC10a map and motion feature offline on identical trajectories.
The motion feature weakens sensory drive and pursuit. The model's DNa02 cells
do not spike in these trials, so the playable voltage-to-turn rule remains an
explicit software proxy. Neither experimental alternative is enabled in Godot.
The [fixed-fly DNa02 firing experiment](docs/fixed_fly_dn_firing.md) further
shows that full-strength moving-object pulses do not elicit DNa02 spikes at
the current LIF settings; tonic drive can expose bridge-dependent firing but
is an uncalibrated model assumption.
The [local-motion input experiment](docs/local_motion_experiment.md) keeps
total visual drive fixed while redistributing it across individual LC10a
cells as the target crosses their putative fields. It changed neural
responses but did not improve pursuit on five new paths, so it remains an
offline candidate.

For an automatic eight-second Godot recording while the Python service is
running, use `--pursuit-demo`; `--pursuit-control` records the matching
bridge-removed condition. For example:

```powershell
godot --path godot --write-movie pursuit_intact.avi --fixed-fps 60 --quit-after 480 -- --pursuit-demo
godot --path godot --write-movie pursuit_disconnected.avi --fixed-fps 60 --quit-after 480 -- --pursuit-control
```

Godot needs a graphics-enabled renderer for movie recording. The compact
closed-loop comparison runs without Godot:

```powershell
python -m fly_creature.pursuit_diagnostic --output docs/evidence/pursuit_closed_loop_v1.json
```

## Data and provenance

The compact JSON circuits were exported from the official [FlyEM Male CNS v1.0 release](https://male-cns.janelia.org/download/) using `tools/export_circuit.py` and `tools/probe_steering_circuit.py`. MaleCNS is a collaboration between FlyEM at HHMI Janelia, the University of Cambridge Department of Zoology, the MRC Laboratory of Molecular Biology, and Google Research, and is licensed under CC-BY. These JSON files are filtered derivatives: they keep selected body annotations, predicted transmitters, and direct weighted edges. The source manifest and files in the FlyTest lab were read during development; no full release file is needed at runtime. The direct LC4/LPLC2-to-giant-fiber choice is motivated by [Ache et al., *Current Biology* (2019)](https://doi.org/10.1016/j.cub.2019.01.079), which studied looming size and velocity inputs to escape. The paper's measured physiology is separate from this project's toy neuron dynamics.

To regenerate the compact file from a MaleCNS v1.0 download, install the optional `build-circuit` dependency and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[build-circuit]'
.\.venv\Scripts\python.exe tools\export_circuit.py --release-dir PATH_TO_RELEASE --output src\fly_creature\data\loom_escape_v1.json
```

The exporter only reads the three official Feather tables. It does not edit them. Any regenerated circuit should be reviewed before replacing the shipped artifact.

## Project boundary

This folder owns its Python package, Godot project, compact data, and instructions. It has no runtime imports from `../src/flytest/` and no runtime reads from `../data/`. The older FlyTest arena remains an independent experimental record outside this folder.

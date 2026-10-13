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
through our static adapter gives identical commands. The completed
[matched retinal benchmark](docs/pursuit_retinal_result.md) finds shared
fast-sweep weakness and task-dependent adaptation/wiring differences.
The playable controller remains unchanged.

The [response-contribution diagnosis](docs/pursuit_response_result.md) locates
the wide-angle signal deficit mainly in the hypothesized input profiles, with
additional nonlinear attenuation. Output weights and DN quantization have much
smaller effects. No diagnostic probe is promoted; the author field itself is
an anatomical image-derived approximation, not measured visual physiology.

The [column-footprint candidate](docs/pursuit_footprint_result.md) now preserves
upstream spatial distributions for 164 cells with unchanged fallback inputs,
gain and timing. It passes input/normalization checks but does not improve
tracking and weakens some wiring ranks. It remains a portable offline alternative;
the playable controller is unchanged.

The refreshed [sensory source review](docs/lc10a_visual_input_research.md)
identifies downloadable AOTU recordings and verifies two sample schemas.
LC10a studies constrain object size, direction and state, but do not supply
per-MaleCNS visual-field widths. The completed
[measured-response benchmark](docs/pursuit_physiology_result.md) compares
13,038 pulses from 24 NoP1 recordings with frozen models and equally calibrated
controls. Footprints barely change the errors; simple spatial predictions are
close and a constant predictor exposes weak AOTU019 benefit in this condition.
The completed [P1 extension](docs/pursuit_p1_result.md) compares another
55,252 pulses from 47 recordings. Spatial benefit is clearer, but anatomy
barely improves on a simple spatial curve. Its audit finds a duplicated
recording across conditions and an unverified hemisphere-label association;
condition effects and side-specific claims remain provisional. Production is
unchanged. The completed [causal response-memory experiment](docs/pursuit_temporal_result.md)
uses nested recording holdouts, complete-trial history and matched timing budgets.
It improves primary errors by less than 1%, fails its frozen benefit criteria
and transfers inconsistently across speeds. No temporal candidate is promoted.
The completed [response-repeatability audit](docs/pursuit_repeatability_result.md)
finds repeatable P1 stimulus structure and recording differences alongside
substantial trial variation. Same-recording templates reduce errors about
10–11% against other-recording templates; descriptive movement adds 4.47%/0.85%.
These are pulse-mean results, not causal motor evidence or a model noise ceiling.
The completed [matched population-tuning comparison](docs/pursuit_population_result.md)
excludes whole recordings and uses identical pulse-mean coverage/calibration.
An empirical other-recording template improves P1 errors about 2.2% against
anatomy; anatomy beats simple spatial by only 0.24%/0.53%. Anatomy captures some
019 field shape, while outer-field tails, direction-dependent peaks and
below-reference responses expose specific mismatches. The subsequent
[improvement cycle](docs/pursuit_goal_result.md) audited history/reference choices
and rejected a bounded direction-skew/negative-offset correction: P1 errors
improved only 0.058% for AOTU019 and worsened 0.164% for AOTU025. Below-reference
025 responses persist across paired baselines, but missing long-gap coverage
prevents a history-independent inhibition claim. Production remains unchanged.
The [replacement plan](docs/pursuit_replacement_plan.md) now has a completed
[finite-object LC10a input contract](docs/lc10a_sensor_contract.md) and 68 reproducible
probe specifications. A fresh source check recovered the paper's actual bar size,
but archive-specific stimulus metadata and quantitative LC10a response laws remain
incomplete. The [renderer and probe runner](docs/lc10a_sensor_renderer.md) now
produce inspectable retinal movies, traces and summaries. The frozen image-to-
LC10a hypothesis is now implemented and passes all 68 six-second probes,
independent pooling/envelope checks, raster convergence, and a byte-identical
full repeat; see the [result](docs/lc10a_response_result.md). It emits
dimensionless per-cell activity for the existing 275 LC10a IDs. A separate
offline recorded-AOTU runner now replays it through the LC10a-to-AOTU contacts;
the completed [recorded-AOTU benchmark result](docs/lc10a_recorded_benchmark_result.md)
includes the compact scores and independent checks. It has not been
integrated into Godot. The spatial and direction constants remain synthetic,
and the published-model envelope is not a measured LC10a spike response. The
current assay is the separate offline AOTU benchmark with frozen wiring controls.
Its [reviewed implementation contract](docs/lc10a_response_benchmark_protocol.md)
now pins all 69 recording folds, calibration rows, explicit shuffle permutations,
native movie history and activation/pooling order. Raw target reconstruction
matches exactly and previous calibrated predictions match to floating-point
precision. `lc10a_response_benchmark.py` and its independent checker are
implemented; the independent checker passed, but the practical prediction
gates failed for both AOTU types. Intact wiring strictly beat all 32 shuffles
on aggregate error, but it did not clear the frozen practical-advantage
thresholds. The result report records the scores, assumptions, and limits.
The checkpoint assembler
`tools/assemble_lc10a_benchmark.py` audits the six worker ledgers and preserves
condition-specific caches because 23 names recur across NoP1/P1 archives.
Run the assembler without flags for an audit, or with `--run` after all 69 units
finish; then run `tools/check_lc10a_response_benchmark.py`.
Full activity traces stay in ignored outputs.
The [bounded diagnosis](docs/lc10a_response_diagnosis.md) now identifies the
transferred temporal envelope as the main recoverable loss. Removing it returns
fit only to roughly legacy performance and does not qualify a replacement.
The primary candidate is retired from promotion; frozen evidence and useful
renderer/anatomy components remain available.
The [next downstream contract](docs/pursuit_downstream_contract.md) bypasses
that uncertain sensory model: measured AOTU inputs would test the selected
AOTU→DNa02 bridge against recorded DNa02 responses. First comes a metadata and
common-coverage audit. The [completed Phase A report](docs/pursuit_downstream_readiness.md)
verifies the files and adequate common coverage (18 stimulus cells across all
11 DNa02 units), but stops before response fitting because target/stimulation
metadata is incomplete. No DNa02 response has been read or scored and no new
controller was built.
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

**Whole-brain mode (default):** jump, turn, feeding, antennal grooming and courtship song are driven by subsets of the real MaleCNS brain chosen from whole-brain activity (27,956 neurons; turning uses an earlier 25,151-neuron subset), with one copy per sense. Right-click the floor to drop sugar; Shift + right-click drops a bitter-laced drop the fly will not feed on; `E` dusts the antennae and the fly grooms them. While it turns toward a target, its song command neurons (pIP10) fire and it sings with the wing on that side. `M` adds a wandering female fly that the male follows and courts through the same target channel; she, her wandering and his stopping distance are presentation only (`godot/capture_female.gd` checks song with intact versus cut wiring). `B` cycles to the older hand-built circuits. See [the whole-brain result](docs/whole_brain_result.md) for what was tested and what is engineered.

**Easiest:** double-click `Play-Fly-Creature.cmd` in this folder. It finds Python and Godot, starts the neural service in the background, opens the game, and stops the service when you close the game window. Problems appear in a pop-up. Options: `tools\play.ps1 -Scene playground` or `-Port <number>`; set `FLY_CREATURE_GODOT` if Godot is somewhere unusual.

To run the pieces by hand, from this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m fly_creature.server
```

Open `godot/` as a project in Godot 4 and run its main scene. The Python service listens only on `127.0.0.1:8768` by default. Set `FLY_CREATURE_ENDPOINT` to another local base URL before starting Godot if you change the port.

The fly now roams the room on its own (engineered wandering, not neural). Click the floor to place a target: the fly turns until it is in view, then its LC10a-to-AOTU-to-DNa02 circuit steers it there, and it resumes roaming on arrival. `SPACE` throws an object that homes in on the fly and triggers the jump circuit. A live brain panel in the top-right shows per-group activity for the jump circuit (LC4, LPLC2, giant fiber) and turn circuit (LC10a, AOTU, DNa02 by side) plus the engineered turn readout; bar scaling is a display choice. `godot/capture_autonomy.gd` is a scripted check of these behaviors (see its header). `WASD` takes over from roaming while held. The scene is dressed as a fly-scale kitchen table (gingham placemat as the walkable area, a giant apple, mug, orange and sugar cubes beyond it) by `godot/kitchen_world.gd`; it is presentation only and does not affect movement or the circuit. `V` starts a moving-target neural pursuit demonstration; the fly walks forward and its heading follows the DNa02 voltage readout. `C` restarts the same scene with its AOTU-to-DNa02 bridge removed (and disconnects the independent jump circuit); press it again to restore the connections. `G` toggles simple roaming between nearby goals. `T` toggles authored flight and landing. `SPACE` sends an object toward its current heading. `F` toggles between close and wide cameras. `R` resets the neural session and world. The target path, visual feature encoding, walking speed, and voltage-to-turn rule are engineered. See the [pursuit milestone](docs/pursuit_milestone.md).

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
close follow view so the new model is actually visible; `F` restores the wide
room view.

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

This folder owns its Python package, Godot project, compact data, and instructions. It has no runtime imports from `../lab/src/flytest/` and no runtime reads from `../data/`. The older FlyTest arena remains an independent experimental record outside this folder.

# Technical decisions

## Release selection

The source is the official Male CNS project download page and its public bucket prefix:

`https://male-cns.janelia.org/download/`

`gs://flyem-male-cns/v1.0/connectome-data/flat-connectome/`

The selected files are the curated body annotations, body-level neurotransmitter predictions, and the complete segment-to-segment weight table. The synapse-point, synaptic-partner, t-bar neurotransmitter, volume, skeleton, and database downloads are intentionally deferred because they are much larger and are not required for this first analysis/simulation loop.

## Raw versus working data

The raw files are preserved byte-for-byte in `data/original-data/male-cns-v1.0/`. The working copy is separate so future normalization, filtering, or format conversion cannot mutate the evidence used for provenance checks. `data/metadata/source_manifest.json` records provider MD5 values and locally recomputed SHA-256 values for both copies.

## Why `Traced` is the default node filter

The full weight table is a segment-level graph, not a clean table of only the 166k curated neurons. Its endpoint populations are therefore not symmetric. The release annotations expose a `status` field; the 165,122 rows labelled `Traced` form a defensible first-pass neuron population. The loader applies this filter to both `body_pre` and `body_post` by default and exposes `--include-untraced` only for deliberate experiments.

## Sign convention

The release gives neurotransmitter predictions, not a universal excitatory/inhibitory label for every synapse. The simulator maps consensus transmitter labels to a fast-effect sign only when a conservative convention is available:

| consensus transmitter | default fast sign |
| --- | ---: |
| acetylcholine | +1 |
| gaba | -1 |
| glutamate | -1 |
| histamine | -1 |
| dopamine, octopamine, serotonin, tyramine, unclear | 0 |

The sign is assigned from the presynaptic body and then multiplied by the positive synapse-count weight. A zero sign means “not modelled as a fast current,” not “biologically absent.” The mapping is a configuration surface because receptor context and neuromodulation matter.

## Simulator scope

The simulator is a deliberately small discrete-time leaky integrate-and-fire reference implementation. It is useful for checking that data selection, directionality, weights, signs, pulse input, refractory periods, and inspectable outputs work end-to-end. It is not a biophysical model of the fly and should not be treated as one.

## Native-sign pathway slice

The pathway diagnostic selects one traced `vnc_sensory -> vnc_intrinsic -> descending_neuron` path. Both presynaptic neurons on the forward path must have a positive sign under the configured transmitter convention. Candidates are ranked by the product of their two edge weights, then by the weaker edge, total weight, and ascending body IDs. The selected three-node induced graph retains every edge among those nodes, rather than deleting reverse or inhibitory edges.

The diagnostic keeps the production LIF defaults unchanged and runs the same single pulse at five explicit coupling values: `0.05`, `0.5`, `1.5`, `3.0`, and `4.0 mV/synapse`. These values are a small calibration sweep for the toy current-based model. They should not be interpreted as fitted or biologically realistic synaptic strengths.

## Optional synaptic dynamics

The production-compatible LIF mode uses `synaptic_gain=1.0` and
`synaptic_tau_ms=None`. In that mode, a presynaptic spike contributes the same
one-step delayed current as the original implementation. A positive
`synaptic_tau_ms` enables an aggregate synaptic-current state that decays by
`exp(-dt / synaptic_tau_ms)` between delayed spike arrivals. `synaptic_gain`
multiplies the existing raw-count current after transmitter sign is applied;
this pass does not introduce a normalized-weight definition.

The synaptic-dynamics diagnostic keeps the conservative `0.05 mV/synapse`
coupling fixed and tests gains `1`, `3`, `6`, and `12` in both legacy mode and
the `5 ms` exponential-decay mode. This isolates the effect of gain and
temporal current persistence from the earlier coupling experiment.

## Input-to-output circuit story

The circuit-story diagnostic is separate from the pathway-slice production
baseline. It reuses the deterministic traced
`vnc_sensory -> vnc_intrinsic -> descending_neuron` selector, stimulates only
the selected sensory source, and keeps native transmitter signs,
`synaptic_gain=1.0`, and `synaptic_tau_ms=None`. It compares the existing
coupling probes while holding timestep, membrane parameters, pulse timing,
and topology fixed.

Its purpose is explanatory: show where a real connectome-backed signal dies or
propagates, with the selected neurons, signed edges, spike times, and key
voltage/current traces in one small report. The first complete path condition
is selected for comparison automatically; if none exists, the highest tested
coupling is used instead. Coupling values remain calibration probes for this
simplified model, not biological synaptic-strength estimates. The diagnostic
does not claim to reproduce a named behavior or provide FlyDoom I/O.

## Sensorimotor reflex demo

The first behavior-facing experiment keeps the deterministic traced
vnc_sensory -> vnc_intrinsic -> descending_neuron selection and uses the
selected SNta30 source as the recipient of a synthetic sensory pulse. A
longer pulse produces repeated spikes in the calibrated toy network. Each
selected descending-neuron spike is decoded as a fixed turn impulse and one
forward step for a point-mass body. Heading and position are arbitrary toy
state variables; they are not claims about the biological function of the
selected descending neuron.

This is intentionally a sensorimotor reflex rather than a learned fly. The
adult connectome is used as a mature wiring scaffold; no developmental history,
plasticity, memory, or realistic body mechanics are simulated. The output
trajectory is useful because it makes the interface inspectable: the external
stimulus enters the selected source, the real induced edges carry activity, the
descending target spikes, and only then does the body state change.

## Dual sensory local-circuit simulation

The browser demo caches two separate local contexts from the traced Male CNS
release, each with a 24-neighbor limit and a 500-edge cap. The touch context is
the existing `vnc_sensory -> vnc_intrinsic -> descending_neuron` path and has
27 nodes and 288 edges. The visual context is selected independently as
`visual_projection -> ol_intrinsic -> descending_neuron` and has 27 nodes and
147 edges in the current release. The selected paths remain emphasized while
nearby ascending, optic-lobe, intrinsic, sensory, and descending-labelled nodes
provide activity context.

The server replays the two cached graphs independently with the existing LIF
simulator and feeds both target populations into one deliberately tiny body.
Touch target spikes apply a fixed turn quantum. Visual target spikes steer
toward a synthetic visual beacon, capped at that same quantum. The two local
contexts are kept disjoint so a body ID cannot be mistaken for activity in the
wrong channel, and the UI exposes channel labels in the spike log.

This is an intentional next step toward a fly-like scaffold, not a retina
model, a complete visual pathway, or a claim that the selected descending
neurons implement a named behavior. The visual source label comes from the
official annotations; the beacon, contrast-to-current mapping, body, and
action decoder are modelling assumptions.

## Scalable closed-loop arena

The arena now has a compatibility stage and two explicit expansion stages:
54 keeps the separate touch and visual local contexts, while 100 and 250 merge
deduplicated multi-hop expansions into one induced graph. Expansion starts from
the existing sensory/intrinsic/descending seed paths, prefers annotated route
classes, and then ranks frontier candidates by incident weight, edge count, hop,
and body ID. If the official release cannot supply an exact requested stage,
selection fails instead of quietly filling the graph with unrelated neurons.

The stateful `LIFNetwork` runner shares the batch update's one-step synaptic
delay, transmitter signs, and refractory behavior. A cached arena runtime
precomputes body-ID indices, sparse edge currents, input populations, and
descending output populations; each replay receives fresh mutable state. The
baseline `GET /api/run` response remains the control condition, while
`POST /api/arena/run` accepts schema-version-2 arena requests. The API defaults
to stage 54 for compatibility; the browser explicitly asks for stage 250.

The 9x5 retina exposes left, center, right, motion, and looming features. Touch
and threat features expose left, right, and urgency populations. Actions come
from descending spikes, not a direct centroid-to-turn shortcut: visual left,
right, and center populations vote for turn-left, turn-right, and forward;
touch populations vote for the opposite escape turn and take priority. On the
54-node stage, missing side-specific populations may share nodes and the
payload records that fallback. Those mappings, the sensor projection, and the
action decoder are simulator scaffolding, not biological claims.

Lights and threats move with deterministic velocity and boundary reflection.
Each replay resets target persistence, escape cooldown, post-escape recovery,
and threat habituation. These values affect sensory drive and action priority,
never synaptic weights, and are returned frame by frame alongside retina cells,
currents, spikes, votes, object positions, and a replay digest. Scripted mode
keeps a moving beacon and timed threat; sandbox mode accepts moving user-placed
objects and reruns from neural rest.

## Godot live-loop boundary

The standalone `arena3d` project is a world client, not a second connectome
simulator. A `POST /api/arena/session` call creates a fresh stage-250 Python
runtime. Each subsequent `POST /api/arena/session/{id}/step` sends Godot's
current body, light, and threat state to Python. Python renders the synthetic
retina, advances the persistent LIF state, applies memory and descending
population decoding, and returns the action, spikes, causal trace, and the
deterministic next state. Godot applies that result to its visible body and
objects on the next tick.

This separation makes the closed loop inspectable and keeps the public batch
replay as a regression control. The world integration, timing, and 3D body are
still explicit experiment scaffolding; the official dataset supplies the
connectome wiring and annotations, not a complete physical fly or a biological
motor command protocol.

## Embodied arena collision slice

The next arena slice gives the existing controller a small physical
consequence without changing the connectome stage or the public baseline API.
Scripted demo requests receive two explicit axis-aligned obstacles; sandbox
requests remain empty unless they provide their own obstacle list. The body is
represented as a circle in the arena plane with a configured radius. Python
resolves each proposed forward move with small swept substeps and
axis-separated circle/AABB contact, which prevents tunnelling and allows the
toy body to slide along a wall. The resulting requested body, actual body,
collision IDs, boundary contacts, and obstacle proximity are returned in every
frame.

Obstacle proximity is routed through the existing touch input groups so the
controller can produce an escape vote from a world obstacle, while threat
proximity remains a separate measured stimulus. Godot renders the same
rectangles as `StaticBody3D` collision shapes and probes the next motion with a
`ShapeCast3D`; Python remains the deterministic authority for replay and live
session state. This is collision-aware experiment scaffolding, not flight
dynamics, contact mechanics, or a biological body model.

The live HUD now exposes a compact causal chain: world touch/contact, retina
features, named input currents, active spikes, descending votes, and the chosen
action. This makes a blocked move inspectable instead of silently clamping the
body at a coordinate.

The visible body is a procedural stylized fly shell kept separate from the
collision shape. A spherical `ShapeCast3D` remains the authoritative toy body,
while the shell adds a segmented abdomen, wings, eyes, antennae, and legs for
readability. This is a deliberate presentation boundary: improving the model
must not silently alter body radius, collision tests, or the controller's
world-state contract.

World-object defaults are mode-dependent at the configuration boundary. An
omitted value uses the selected mode's defaults: demo receives its scripted
lights, threat, and obstacles, while sandbox receives empty collections. An
explicit empty collection always disables that object type. Direct Python
construction and JSON parsing therefore produce the same world for the same
mode and inputs.

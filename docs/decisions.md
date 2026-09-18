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

## Visual local-circuit simulation

The browser demo caches a 27-node, 288-edge local context around the selected
sensory -> intrinsic -> descending path. The context is selected from the same
traced Male CNS release with a 24-neighbor limit and a 500-edge cap. The
selected path remains visually emphasized, while nearby ascending, intrinsic,
sensory, and descending-labelled nodes provide activity context.

The server replays the cached graph with the existing LIF simulator and exposes
only parameterized toy runs over localhost. The page renders a point-mass body,
spike-driven heading changes, a trajectory, and the active network graph. This
is deliberately a runnable visual scaffold rather than a claim that the local
neighborhood is a complete fly brain or that the action decoder is biological.

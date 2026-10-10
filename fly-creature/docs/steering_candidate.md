# Candidate visual steering circuit

## The question

Can a lateral visual signal reach the left and right steering-related descending
neurons through recorded Male CNS connections, with a side-specific bias? This
is a circuit inspection, not a creature behavior or a simulation of seeing.

The candidate comes from [Collie et al. (2026)](https://doi.org/10.1016/j.neuron.2026.01.001),
who study parallel visual object-pursuit pathways, and
[Rayshubskiy et al. (2025)](https://doi.org/10.7554/eLife.102230), who find that
the difference between left and right DNa02 activity predicts walking turns.
The published object-pursuit connectome analysis used a different fly dataset;
the connections below were checked anew in our Male CNS v1.0 release. This
route is associated with object pursuit, not a general obstacle-avoidance rule.

## What is recorded in our release

The traced selection has 275 LC10a neurons (135 left, 140 right), plus one
AOTU019, one AOTU025, and one DNa02 on each side: 281 neurons total. The
four named connection classes contain 366 neuron-to-neuron edges. The table
counts synapses, not effective electrical strength.

| Recorded path | Left stimulus side | Right stimulus side |
| --- | ---: | ---: |
| LC10a to same-side AOTU019 | 6,615 | 7,595 |
| LC10a to same-side AOTU025 | 3,303 | 3,728 |
| AOTU019 to opposite-side DNa02 | 289 | 297 |
| AOTU025 to same-side DNa02 | 205 | 196 |

The release's transmitter annotations call both AOTU019 neurons GABA and both
AOTU025 neurons acetylcholine. Treating those as inhibitory and excitatory,
respectively, is a modeling convention; receptor-specific effects were not
measured here. All selected LC10a cells are annotated acetylcholine.

## Small structural probe

[`probe_steering_circuit.py`](../tools/probe_steering_circuit.py) reads the
official working copy, retains only the four named connection classes, and
writes neuron IDs, edges, annotations, aggregates, and the probe to
[`evidence/steering_candidate_v1.json`](evidence/steering_candidate_v1.json).
It does not modify the release or the playable creature. Reproduce from the
FlyTest root with its Python environment:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/probe_steering_circuit.py --release-dir data/working/male-cns-v1.0 --output fly-creature/docs/evidence/steering_candidate_v1.json
```

The arithmetic gives every LC10a neuron on one side one abstract input unit.
For each two-edge route to DNa02, it multiplies the two recorded synapse counts
and the AOTU transmitter sign, then adds contributions to the left or right
DNa02 side. The resulting units are **synapse-count products**, not membrane
voltage, spikes, torque, or degrees per second.

| Input | Recorded bridge: left minus right | Bridge removed | Bridge destinations swapped |
| --- | ---: | ---: | ---: |
| Left LC10a | +2,588,850 | 0 | −2,588,850 |
| Right LC10a | −2,986,403 | 0 | +2,986,403 |

The bridge-removed control zeroes all selected AOTU-to-DNa02 edges. The swap
keeps their synapse counts and transmitter signs but sends each edge to the
opposite DNa02 side. This isolates the side assignment of the four output
edges. Both controls are synthetic alterations, not alternate animal data.
The positive and negative scores confirm the structural opponent motif under
the stated sign convention. Their unequal magnitudes cannot be read as a
measured left/right behavioral difference.

## Matched neural-activity probe

The compact [candidate circuit](../src/fly_creature/data/visual_steering_v1.json)
is a standalone copy of those 281 selected neurons and 366 recorded edges.
[`steering_diagnostic.py`](../src/fly_creature/steering_diagnostic.py) runs it in
the creature's 1 ms, one-step-delayed LIF reference model. GABA edges receive
negative current under a stated model assumption; the existing acetylcholine
jump circuit keeps its previous positive weights. From `fly-creature/`, with
its package installed or `src` on `PYTHONPATH`, run:

```powershell
python -m fly_creature.steering_diagnostic --output docs/evidence/steering_lif_v1.json
```

The input is deliberately explicit and crude: a 50 ms resting baseline,
90 mV model current into **every** LC10a neuron on the chosen side for 200 ms,
then 100 ms without input. Both sides receive the same per-neuron current,
though there are 135 left cells and 140 right cells. Every condition uses the
same model parameters. The `bridge_removed` control keeps LC10a-to-AOTU
connections and removes only AOTU-to-DNa02 connections. The
`bridge_side_swapped` control keeps those four output weights and signs but
exchanges their DNa02 destinations. The [full result](evidence/steering_lif_v1.json)
includes 10 ms spike and voltage bins.

| Input | Recorded DNa02 L−R mean voltage | Bridge removed | Bridge sides swapped | DNa02 spikes |
| --- | ---: | ---: | ---: | ---: |
| Left LC10a | +2.6413 mV | 0 | −2.6413 mV | 0 |
| Right LC10a | −2.9267 mV | 0 | +2.9267 mV | 0 |

The selected AOTU cells do spike: for a left stimulus, AOTU019_L spikes 33
times and AOTU025_L 11 times; for a right stimulus, their right counterparts
spike 33 and 16 times. DNa02 remains below threshold in **all** conditions.
The observed DNa02 difference is a modeled membrane-voltage bias, not a
firing-rate difference or a turn. An all-at-once LC10a pulse is also not a
measured response to a real visual object. The 0.05 mV-per-synapse coupling,
transmitter signs, 90 mV input, and cell parameters are software choices.

## Embodied follow-up

The [pursuit milestone](pursuit_milestone.md) now uses this same candidate
circuit in a visible Godot scene. Its input maps object bearing to whole-side
LC10a current, and its motor decoder maps DNa02 **voltage difference** to turn
rate. Those are plainly engineered choices made to build a usable interactive
slice. The earlier no-spike result still holds for the fixed square-pulse
probe; the new scene does not claim measured neural firing or a real fly's
natural visual tuning. Receptor-specific effects, downstream leg motor circuit,
and biological steering calibration remain unknown.

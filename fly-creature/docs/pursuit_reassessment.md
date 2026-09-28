# Pursuit reassessment — 2026-09-26

## Decision

Stop the sequence of improvised LC10a motion filters. Establish a published
pursuit-model reference, then reconcile its visual mapping and response rules
with our packaged MaleCNS v1.0 circuit. This is a research direction, not a
claim that a replacement has been implemented or validated. Playable defaults
remain unchanged.

## What our results actually establish

The existing pursuit has scripted forward speed and connectome-dependent
steering. Removing its AOTU-to-DNa02 bridge disrupts tracking. The latest
local-motion input beats the median shuffled wiring on all five paths, but
does worse than the existing input. This supports a causal contribution from
the modeled wiring; it does not validate its physiology.

Inspection of `src/fly_creature/lif.py` confirms identical membrane rules for
all cells, an arbitrary synapse-count-to-current conversion, one-step current
pulses, and a silent initial state. The connectome did not supply those rules.
Our fixed-fly experiments show that assumed background drive changes whether
DNa02 fires. Failure to spike under the original settings is therefore a
failure of that configuration, not evidence that this biological route cannot
steer. More objects in Godot would not resolve this ambiguity.

## Better primary-source starting point

Collie and colleagues' [final 2026 paper](https://pubmed.ncbi.nlm.nih.gov/41713413/)
describes peripheral and frontal pursuit pathways, with the frontal pathway's
response changing with motion direction, running speed, and arousal. It also
reports a forward-velocity contribution. These provide specific biological
responses to reproduce before adding creature behaviors.

Their [released model](https://github.com/wilson-lab/CollieWilson/tree/main/Modeling_Code)
includes numerical receptive-field tables and MATLAB code. The inspected
`aotu_steering_model.m` uses response curves, pathway delays, signed bilateral
combination, and a DNa02 input/output mapping. It does not simulate individual
action potentials. Its direction selectivity is supplied explicitly, so we
must not describe that property as emerging from wiring alone.

The current [settings](https://github.com/wilson-lab/CollieWilson/blob/main/Modeling_Code/support/modelSettings.m)
include a 100 Hz update rate and configurable delays and direction penalties.
Those defaults are not automatically the settings of every published figure;
the calling experiment must be traced before claiming a reproduction.

The repository also contains [MaleCNS analysis](https://github.com/wilson-lab/CollieWilson/tree/main/Connectomics_Code/AOTU_MaleCNS).
Direct inspection of `lc10_to_dn_male.R` and `lc10_heatmap_male.R` shows
`male-cns:v0.9` queries. The model runner labels an update to a male model.
Earlier references to the [older preprint](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/)
must not be used to conclude that only female-connectome resources exist.
The exact derivation of the shipped `Pursuit_RFs.csv`, and correspondence to
our v1.0 cells, still require tracing. Published estimates are not measured
visual fields for each of our 275 LC10a cells.

## Next implementation and acceptance

1. Pin the authors' source revision and identify the exact figure protocol,
   parameters, response-table provenance, and reuse terms. Reproduce a small
   reference response and target-centering example before modifying it.
2. Build a separate Python activity-based candidate with an explicit ledger
   of data-derived weights, measured response constraints, and assumptions.
   Preserve the LIF baseline. Do not silently substitute a population lookup
   table for the existing cell-level circuit and call it the same model.
3. Check frontal/peripheral response profiles, outward/inward responses,
   delays, and pathway-specific removal effects. Then assess pursuit stability
   on new trajectories and compare with suitable wiring controls.
4. Bring a supported candidate into Godot with its assumptions visible. Only
   then extend stopping, speed regulation, or search behavior with defined
   inputs and outputs.

The direct-bearing controller remains an engineering comparison. Beating it
is not a prerequisite for biological usefulness: our software already knows
the target bearing exactly. Success requires supported neural responses and
predictable effects of wiring interventions, alongside usable behavior.
This corrects the overly broad promotion criterion used in earlier reports;
their measured results and original criteria remain preserved.

This reassessment involved source inspection and literature research. No new
simulation was run and no improved performance is claimed.

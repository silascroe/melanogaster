# Fixed-fly DNa02 firing: a sensitivity experiment

**Result:** the current selected model does **not** produce DNa02 spikes from
these moving-object pulses. A modeled tonic DNa02 drive can expose a
bridge-dependent firing difference, but its value is unmeasured, and this
experiment does not reproduce the measured motion-direction selectivity.
Keep the playable voltage readout and input unchanged while treating them as
engineered demonstration machinery.

## Question and stimulus

The previous [input/readout audit](input_readout_audit.md) found that the
playable turn command reads DNa02 membrane voltage although the selected LIF
model emitted no DNa02 spikes. We asked whether this was merely a weak
visual pulse, or whether the model also needed a background firing state.

[Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) presented
small-object sweeps spanning **22.5°** at **25°/s** and **75°/s** to walking,
aroused male flies, and recorded responses in AOTU cells and DNa02. We used
those span and speed values with a **fixed** virtual fly. We chose 25° and
45° centers as frontal/lateral model probes, mirrored each on both sides,
and ran outward, inward, and duration-matched static stimuli. Those center
choices, the 100 ms baseline, our LC10a angle assignment, and our current
waveform are model choices. The paper's P1-induced arousal, full visual
stimulus, receptor physiology, and measured responses are not simulated.

We compared two full-strength LC10a inputs: the upstream-map position input
and the previously tested magnitude-only motion gate. “Full” means the
project's existing **90 mV current-equivalent mean side input** before the
per-cell spatial distribution; it is not a physiological current estimate.
This intentionally removes the playable bearing-amplitude envelope as a
reason for a negative result. The motion gate has a 20% static floor and
saturates at 25°/s, so it cannot encode a difference between 25°/s and
75°/s after the first 20 ms world step. It also cannot encode inward versus
outward direction by itself.

## Declared neural sensitivity range

The original LIF circuit uses its recorded MaleCNS edges and a **0.05
current-equivalent mV per synapse** coupling. We held the LC10a-to-AOTU
stage and all LIF timing/thresholds fixed. Only the four AOTU-to-DNa02 edge
currents were multiplied by **1, 2, or 4**, and equal tonic external drive
was added to both DNa02 cells at **0, 16, or 20 mV**. The 16 and 20 values
straddle the LIF model's approximately 15 mV steady-state firing threshold.
They are sensitivity probes, not values measured in a fly. Every combination
also had the four AOTU-to-DNa02 edges removed as a matched control.

In the selected MaleCNS route, AOTU019 is predicted GABAergic and crosses to
the opposite DNa02; AOTU025 is predicted cholinergic and reaches same-side
DNa02. This matches the broad [crossover-inhibition and ipsilateral-excitation
motif](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) described in
physiology and a different connectome. The simple LIF sign convention does
not establish receptor-specific effects in this animal.

## Results

There are **16 moving trials per input/parameter combination**: two speeds,
two center positions, two sides, and two directions. Pulse duration is
900 ms at 25°/s or 300 ms at 75°/s. The same number of static trials was
used as a control for each combination.

| AOTU→DNa02 scale | Tonic DNa02 drive | Moving trials with any DNa02 spike | Moving trials with bridge-dependent toward-side spike bias |
|---:|---:|---:|---:|
| 1× | 0 mV | 0/16 for either input | 0/16 |
| 2× | 0 mV | 0/16 for either input | 0/16 |
| 4× | 0 mV | 0/16 for either input | 0/16 |
| 1× | 16 mV | 16/16 for either input | 16/16 |
| 1× | 20 mV | 16/16 for either input | 16/16 |

All nine scale/tonic combinations and every path are in the
[compact result JSON](evidence/fixed_fly_dn_firing_v1.json). Increasing only
the selected bridge current as far as 4× did not make a silent DNa02 fire.
At **1×/16 mV**, the 100 ms baseline produced one DNa02 spike on each side;
the same bridge-removed control kept left and right pulse counts equal. For a
representative right-side 25° outward pulse at 25°/s with motion input, the
intact route emitted **19 right / 1 left** DNa02 spikes over 900 ms, versus
**16 / 16** after removing the AOTU bridge. The right-side AOTU019 and
AOTU025 cells emitted **124** and **46** spikes, respectively. The firing
difference therefore depends on the selected model bridge **given the
invented tonic drive**. Its earliest DNa02 pulse spike is not a response
latency: tonic activity was already present before the visual pulse.

This is not yet the response shape we need. With the **position** input at
1×/16 mV, all eight static trials also had a toward-side spike bias; their
combined bias was **103 spikes**, compared with **100 outward** and **101
inward** over the corresponding moving trials. The motion gate reduced the
static bias to **4 spikes** in four of eight static trials, but moving
outward and inward produced the same combined bias (**92** each). In paired
outward/inward comparisons under 1×/16 mV motion input, six of eight pairs
were identical; the other two differed by one spike in opposite directions.
That is no consistent directional preference. The gate's static suppression
was engineered into the input rather than learned from the connectome.

## What this establishes

The present absence of DNa02 firing is **not** just a weak playable input:
even full-strength visual drive and a fourfold bridge-current increase did
not produce spikes without tonic DNa02 drive. A tonic state makes the known
crossed inhibition meaningful as a firing-rate difference and lets the
recorded bridge affect a spike-based signal. But we have no MaleCNS or
physiology measurement that calibrates that tonic current to **16 mV**, and
the tested input still misses key motion selectivity. No parameter from this
grid should be promoted merely because it yields spikes.

The next useful constraint is a **measured baseline and pulse-response
comparison**, including DNa02 and AOTU rates, response timing, and
motion-direction preference. Until then, the fly's playable turn remains an
inspectable voltage-driven software behavior, not a validated neural motor
command.

Reproduce from `fly-creature/`:

```powershell
$env:PYTHONPATH="src"
..\.venv\Scripts\python.exe -m fly_creature.fixed_fly_dn_firing --output docs/evidence/fixed_fly_dn_firing_v1.json
```

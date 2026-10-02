# Matched retinal comparison: shared fast-motion limit, mixed adaptation gap

2026-10-02. [Frozen protocol](pursuit_retinal_protocol.md),
[JSON](evidence/pursuit_retinal_v1.json), [CSV](evidence/pursuit_retinal_v1.csv).
22 mirrored conditions, 71 variants, 1,562 comparisons. No parameter search
or production changes. These are simulated errors, not fly measurements.

## Results

The source-inspired reference also tracks the fast sweep poorly. Our adaptation
has additional differences: worse stationary acquisition, better slow sweeps
and these smooth paths, and inconsistent advantage over shuffled wiring.
This narrows the diagnosis without validating the creature's biology.

Mean absolute retinal error after the one-second hold, degrees (lower is better):

| Task family | Reference, direction on | Adaptation, direction on | Reference, direction off | Adaptation, direction off | Ordinary P, same delay |
| --- | ---: | ---: | ---: | ---: | ---: |
| Stationary steps | 4.665 | 6.310 | 3.875 | 7.744 | 3.520 |
| 25 degrees/s sweep | 8.981 | 6.267 | 8.431 | 5.572 | 7.804 |
| 75 degrees/s sweep | 23.823 | 25.241 | 28.218 | 28.271 | 28.188 |
| New smooth paths | 8.655 | 7.875 | 9.446 | 7.819 | 9.553 |
| Previously examined motion | 6.390 | 7.180 | 7.255 | 6.519 | 7.685 |

The fast sweep exceeds the shared 68.755 degrees/s engineering cap. Reference
commands saturate on 77.8% of scored samples; adaptation commands on 65.1%.
But uncapping the reference leaves error at 23.847 degrees versus 23.823 capped.
The cap alone does not explain this failure. Both share 200 ms queues and the
subsequent body interval. This supports a shared operating-range limitation
under this contract, without isolating delay, response shape or direction
switching as the sole cause. Our bounded sweep differs from the paper's
low-pass random target-motion experiment.

All direction-on reference/adaptation samples remain visible. Visibility loss
cannot explain their differences here. Step means include acquisition transients.
Both settle within 10 degrees for a full consecutive second on all six steps.
The widest 105-degree step starts that interval at 1.52 seconds after release
for the reference, versus 2.24/2.50 seconds for our original/mirrored adaptation.
Ordinary P gives 1.38 seconds.

## Recorded wiring

| Family | Direction-on intact beats shuffle aggregates | Direction-off intact beats shuffle aggregates |
| --- | ---: | ---: |
| Stationary steps | 32/32 | 32/32 |
| 25 degrees/s sweep | 26/32 | 32/32 |
| 75 degrees/s sweep | 32/32 | 32/32 |
| Smooth paths | 15/32 | 32/32 |
| Previously examined motion | 23/32 | 32/32 |

Bridge removal yields zero turning and larger aggregate error in every family.
Specific wiring helps on several tasks; direction-on advantage is not robust
across regimes. Direction removal improves wiring rank but worsens step and
fast-sweep error. It is not a blanket improvement or a promoted change.
Shuffle counts are descriptive ranks, not independent statistical trials;
mirrors and three smooth paths form a small diagnostic sample.

## Checks and limitations

The unchanged 450 ms source-port default remains intact. A separately labelled
200 ms override matches an independently structured delayed Eq6 recurrence
exactly on direction on/off crossed with stationary/smooth moving inputs,
each mirrored. It shares lookup helpers: this checks history/update wiring,
not an independent derivation of every nonlinearity. Previous MATLAB fixtures
supply numerical-core evidence. This is a source-inspired article-method
variant, not an exact published figure reproduction. Minor AOTU pathways are
excluded in both selected routes.

Matched comparisons use rotation only, not translation. Exogenous world angles
are identical; retinal histories differ because bodies turn differently.
Warmup fills queues while holding rotation. The body applies the previous
delivered command, preserving runtime convention. The separate Eq6 check
applies delayed-history responses directly. These time contracts are distinct.
Author RF already includes output strength; our adaptation instead uses recorded
edges with hypothesized retinal fields and normalization. Their joint difference
does not identify which adaptation assumption is wrong.

Three new tests cover mirrored inputs/hold/sweep slopes, bridge removal,
queue/body timestamps and command equivalence against the actual activity
controller. All 104 lab/creature tests pass. Two complete reports are byte-identical.
Fourteen local traces independently reproduce error and delivery timing; all
22 input hashes and 17 pinned source hashes match. Original/working release data
pass verification. No licensed author table or bulky traces were added to Git.

## Reproduce

From the workspace root, with the pinned external source checkout available:

```powershell
.\.venv\Scripts\python.exe -m fly_creature.pursuit_retinal_benchmark fly-creature/outputs/research/CollieWilson/Modeling_Code/Pursuit_RFs.csv
.\.venv\Scripts\python.exe -m pytest tests fly-creature/tests -q
```

The external CSV hash must match the manifest; no runtime dependency is added.
Exact input bytes and timestamped traces remain under ignored
`outputs/research/retinal-benchmark/`. Trace AOTU order is recorded in JSON;
DNa02 is always left/right. Rates use true 10 ms steps; the old source's
20 ms reporting quirk remains only in its unchanged port.

## Next question

Inspect stationary and direction-conditioned steering curves: where does our
adaptation lose restoring strength or introduce asymmetry, and how do input
fields, normalization and recorded output edges contribute? Keep gain/delay
fixed and inspect factors separately. Sol medium suits the diagnostic design.
Any later fix needs fresh reserved trajectories plus the prior regression set;
these paths have been consumed. New neurons, shorter delay, Godot changes or
automatic promotion are not justified by this benchmark alone.

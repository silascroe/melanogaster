# Causal response-memory experiment

2026-10-02. Implemented offline; hypothesis does not meet the frozen benefit gate.
Read the [protocol](pursuit_temporal_protocol.md),
[compact report](evidence/pursuit_temporal_v1.json),
[complete summary table](evidence/pursuit_temporal_summary_v1.csv),
[wiring ranks](evidence/pursuit_temporal_ranks_v1.csv),
[checks](evidence/pursuit_temporal_checks_v1.json), and
[held-recording response figure](evidence/pursuit_temporal_v1.png).

## Design implemented

`src/fly_creature/pursuit_temporal.py` replays native full-trial inputs through
the frozen AOTU predictors, adds a unity-gain causal first-order response
state and pure lag, and retains the fixed 50 ms observation filter. Memory
choices are 0/40/100/200 ms; nominal lag choices 0/40/80 ms resolve to
0/40.5/79.5 ms on the native grid. Previously presented targets can affect
later pulses. The known duplicated recording is excluded from both archives.
Primary predictions pool the two model hemispheres in ipsilateral coordinates;
all-left and all-right are separate sensitivity scenarios.

The 69 usable recordings contribute **35,484 quiescent pulses** (7,450 NoP1,
28,034 P1). All 65,416 accepted intervals and 158 rejected intervals in the
retained recordings are accounted for. No singleton visual segments occurred
in replayed trials. Neither physical hemisphere nor per-trial stimulation
labels are treated as recovered ground truth.

Baseline anatomy, 32 fixed-seed wiring shuffles, simple spatial and zero-evoked
controls receive identical timing and gain budgets. Each outer held recording
is excluded from all training. Inner leave-recording-out validation selects
among 12 timing combinations, then one nonnegative gain is refitted on the
outer training recordings. Static controls fit their own gain. Evaluation
uses every seventh native sample (10.5 ms); simulation/filtering remain native.

The objective is baseline-subtracted **response shape over time**, giving each
pulse equal weight within its recording and each recording equal weight.
Pre-stimulus baseline is an observed electrophysiological reference, not a
sensor available to Godot. These errors are not directly comparable to the
earlier raw pulse-mean calibration. No spatial width, direction rule, edge,
production gain, motor delay or body rule changes.

## Primary P1 result

Mean held-recording evoked-window RMSE in spikes/s. Lower is better.

| Type | Recordings/pulses | Static anatomy | Temporal anatomy | Reduction | Recordings improved | Temporal simple |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| AOTU019 |24/15365|12.4402|12.3393|0.81%|13/24|12.3940|
| AOTU025 |22/12669|15.2460|15.2039|0.28%|13/22|15.2491|

The frozen criterion was at least 5% error reduction and at least 60% of
recordings improved for both types. **Both types fail.** Paired recording
improvements are 0.1009 (SEM 0.0577) and 0.0421 (SEM 0.0246) spikes/s.
These are descriptive changes, not a significance claim.

Every P1 anatomy fold selects 100 ms memory/no added lag for AOTU019 and
40 ms/no added lag for AOTU025. The simple spatial model selects the same
choices and improves 0.62%/0.25%. Stable choices do not identify biological
time constants. Anatomy's remaining advantage over temporally adapted simple
spatial is only 0.44%/0.30%.

Anatomy beats 7/32 shuffled aggregates for AOTU019 and 32/32 for AOTU025.
This is a different objective and population than the earlier raw-rate
benchmark; ranks across those experiments are not direct comparisons.
Within this experiment, the AOTU025 rank accompanies only a small advantage
over the simple control. No substantial circuit-specific benefit is established.

All-left/all-right sensitivities give AOTU019 reductions 0.82%/0.80% and
AOTU025 0.28%/0.27%; neither rescues the criterion. NoP1 receives negligible
benefit: AOTU019 is slightly worse (-0.004% reduction), while AOTU025 selects
static in all matched folds. These are separate archive-conditional fits,
not causal comparisons of stimulated and unstimulated internal states.

## Transfer and temporal inspection

Training on other recordings' slow sweeps and predicting held fast sweeps
improves P1 anatomy errors by 1.39% (019) and 0.60% (025). Reversing the
direction worsens errors by 0.97% and 0.48%. The small benefit is not reliably
speed-general. Neither speed from the held recording participates in training.

The inspected figure shows better early rise/peak alignment in some AOTU019
examples. Measured activity still persists longer after disappearance than
the predictions, particularly for AOTU025. Across all positions/directions,
tail RMSE changes only 14.252 to 14.022 (019) and 16.958 to 16.900 (025).
A better-looking example does not override the held-recording aggregate.
The post-offset window stops at 250 ms and cannot identify a complete long tail.

## Checks and reproduction

From `fly-creature/`, using the existing `physiology-research` dependencies:

```powershell
python -m fly_creature.pursuit_temporal --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-temporal-v1
python -m fly_creature.pursuit_temporal --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-temporal-repeat
```

Published archive MD5 and read-member CRC checks pass. Native direct/optimized
observation arithmetic, explicit recurrence and direct-vs-moment errors are
checked during replay; causal/observation filter-order error is 7.78e-16 and
the explicit recurrence error is zero. Full-trial static observation errors
are at most 1.12e-15. Two independent native-trial replays produce byte-identical
report JSON, 43,470-row fold CSV, summary/rank CSVs and PNG. Matched fold
training/held-pulse counts, nonnegative gains, static zero timings and duplicate
exclusion were checked independently from saved folds. Original production, source benchmark
and input-data hashes are unchanged. The old evidence is preserved.
Full folds remain ignored; compact summaries, provenance and plots are tracked.
No unit or gameplay test suite was run; this validates the requested diagnostic.

## Decision and next question

Keep this implementation as an inspectable failed-to-qualify hypothesis.
Do not promote its fitted memory into Godot, expand the grid to chase the
current dataset, or treat it as a fix for pursuit. Temporal response alone is
not the main missing ingredient under this assay. A first-order kernel also
cannot distinguish sensory persistence, spatial mismatch, motor/state-related
activity and animal-to-animal variation.

The next useful diagnostic is **response repeatability and residual variation**:
for matching position, direction and speed, measure how consistently the same
recording responds across repeated trials; separate within-recording variation
from across-recording differences and audit continuous forward/turning signals
inside the coarse quiescent class. Motor correlation is descriptive and can
reflect neuronal output or a shared cause; it is not automatically a new neural
input. Define this audit before another sensory rewrite. Sol medium for the
design/interpretation; Luna Max for a fixed implementation.

**TL;DR:** The implementation and checks work. Bounded response memory gives
less than 1% improvement, gains almost equally help the simple control, and
speed transfer is inconsistent. Preserve production and investigate what
remaining recording variability the visual-only model is being asked to predict.

# Frozen AOTU temporal-response experiment

2026-10-02. Freeze this protocol before response fitting. Offline only.

## Question and boundaries

Does a bounded causal response-memory hypothesis improve held-recording
evoked time-course predictions, and does anatomy benefit more than an equally
flexible simple spatial predictor? No neural, input-field, direction, motor,
production or body parameter changes. This is a phenomenological response
model, not an identified neuronal mechanism or a causal P1-effect estimate.

Reuse the checksum-verified NoP1/P1 archives, native stimulus positions,
extraction gates, 250 ms pre/post windows and locomotor definitions from
`pursuit_physiology_protocol.md`. Prospectively exclude the numerically
duplicated identity `AOTU019/2023_06_15_fly03` from BOTH conditions. Primary
population is quiescent pulses. NoP1 is a separate condition comparison;
running/mixed are not additional tuning opportunities in this experiment.

## Temporal hypothesis

Replay complete trials, including visible stimuli outside retained pulses,
with zero initial state. For each contiguous finite position segment, infer
motion direction by its fitted slope; a singleton has zero drive and is
counted. Replay native positions and frozen AOTU lookup tables. Never infer
direction from adjacent quantized position differences. Previously rejected
segments may contribute visual history; retain their audit separately.

The only response-state hypothesis is a unity-DC-gain first-order causal
filter: `s[n] = alpha*s[n-1] + (1-alpha)*u[n]`,
`alpha = exp(-dt/tau)`. Candidate tau values are 0, 40, 100 and 200 ms.
Apply a causal pure lag of 0, 40 or 80 ms, rounded to native samples;
report realized timing. The 12 fixed combinations include static (0,0).
These are engineering hypotheses, not values measured from the connectome.
Do not enlarge the grid after seeing results or choose per-speed/position
time constants. Apply the same native 50 ms Gaussian observation filter,
truncated at 250 ms, to every candidate. Measured rates are already smoothed
and are never smoothed again. Linear filters may commute computationally:
pad native inputs by the observation radius before observation filtering,
then apply the causal filter/lag on that padded sequence. Verify this against
explicit causal-then-observation convolution with sufficient zero extension.

Primary anatomy prediction averages the left/right model responses after
aligning both to ipsilateral-positive coordinates. This defines a pooled
model response; it does not estimate an unknown hemisphere assignment.
Separately repeat all-left and all-right scenarios. No scenario is selected
for its fit. Include baseline anatomy, 32 existing seeded within-side input-
bundle shuffles, the fixed simple spatial curve and zero-evoked predictor.
Footprints are not reintroduced after two negligible-effect diagnostics.
Every nonzero predictor gets the same 12 temporal choices and gain budget.

## Objective, calibration and holdouts

Evaluate traces on the recording's global every-seventh-sample grid
(10.5 ms at the native 1.5 ms interval); retain native simulation/filtering.
Each pulse's observed baseline is its existing -250..-100 ms mean. Subtract
the predicted mean over that SAME native interval from each predicted trace.
The target is baseline-subtracted rate, not raw spontaneous rate. Fit one
nonnegative gain to evoked trace squared error. There is no fitted intercept
after baseline subtraction and no held-recording response used for gain or
timing selection. A held pulse's pre-stimulus baseline is an observation used
to define evoked response, not a sensor available to the game.

Average squared-error moments within each pulse, then pulses within each
recording; give recordings equal weight. Hold out each recording in turn.
Within its training recordings, leave one recording out again to choose the
timing combination minimizing mean validation recording RMSE. Break ties in
fixed grid order: tau ascending, then lag ascending. Refit the gain on all
outer-training recordings for the chosen combination. Compare with separately
calibrated static (0,0), using the same observations and animal weights.
The chosen grid can return static; report that rather than force a change.

Primary metric: mean recording evoked-window RMSE [-250 ms, offset+250 ms].
Secondary metrics: visible-pulse mean error and post-offset tail RMSE over
50..250 ms. Report paired recording changes, SEM, fraction improved, selected
timing/gains and all shuffle ranks. Descriptive uncertainty is not a
significance claim; shared cross-validation training sets are dependent.

Predeclared speed-transfer check: for each held recording, select timing/gain
using only other recordings' nominal 25 deg/s pulses and evaluate its 75 deg/s
pulses, then reverse. Require at least three eligible training recordings.
This tests speed transfer, not a fresh animal cohort or unseen behavior.
Never reuse the held recording's other speed for training.

## Interpretation and checks

Call temporal benefit promising only if P1 pooled anatomy reduces primary
mean error by at least 5% and improves at least 60% of held recordings for
both types. Report other outcomes without retuning. A claim of anatomy-specific
benefit additionally requires better errors than temporally adapted simple
spatial controls and suitable wiring ranks; temporal benefit alone does not
qualify. No promotion gate to Godot is defined here.

Check native filter-order arithmetic, static lookup/observation equivalence,
moment-vs-direct error, gain fitting, holdout exclusions, duplicate exclusion,
count accounting, fixed source/data hashes and repeat numerical artifacts.
Keep raw archives, caches and full folds/traces under ignored outputs; track
compact report/table/plots. Preserve old frozen protocols and evidence.

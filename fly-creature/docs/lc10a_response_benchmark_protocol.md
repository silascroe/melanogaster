# Recorded-AOTU comparison: reviewed implementation contract

2026-10-04. Frozen before new recorded-response scores. This specifies the
next offline runner; it does not report a physiology result. It carries forward
the [response design](lc10a_response_design.md), its unchanged rule and all
predictive/wiring thresholds. The [contract audit](evidence/lc10a_benchmark_contract_v1.json)
pins native input counts, exact fold signatures, calibration weights and the
actual 32 shuffle permutations. The [assay manifest](evidence/lc10a_benchmark_protocol_v1.json)
pins this document and that audit. Historical response-design manifest status
and protocol hash describe its earlier freeze; they are not current status.

## Question and target

Does the frozen image-response construction predict recorded AOTU pulse means
better than the legacy point-input construction? With the same new sensory
vectors and calibration allowance, do the particular LC10a-to-AOTU contacts
improve prediction relative to ordinary spatial weights and wiring shuffles?
These questions have separate gates. The primary result is the predeclared
rule, not the best ablation or stimulus-association variant.

Use the four existing MD5-verified archives, ZIP-member CRC and SHA-256 checks,
the unchanged `read_recording` and `extract` functions, and exclusion of
`AOTU019/2023_06_15_fly03` in both archive conditions. There are 69 retained
condition/type/recording units, 35,484 quiet pulses/trial-cell observations,
and exactly 34,554 scored trial-cells. Primary P1 has 24 AOTU019 and 22 AOTU025
recordings; NoP1 has 11 and 12. Filename recordings are the grouping units;
do not claim they establish independent animals or randomized P1 pairing.

## Native movie and history boundary

For each trial containing any quiet scored/extracted pulse, replay its entire
`int_panelps` column from sample zero. Render every finite position, including
running, mixed, rejected, boundary and singleton pulses. Scoring eligibility
must not decide what the sensory system sees. NaNs render uniform luminance 1
while motion and response history continue. Reset only at trial boundaries.
There is no synthetic rest before sample zero and no pulse-by-pulse reset.

At sample n use the actual unsnapped position. Pass a stationary rectangle
description to the existing renderer with velocity zero, instantaneous center
equal to that sample, onset zero and duration extending beyond the last sample.
For a NaN use `target_present=False` and a finite placeholder center. Primary
geometry is width 11.25 degrees, height 60, elevation zero, contrast -1, uniform
background. The archive does not establish that per-recording association.
Positions beyond the displayed panel are clipped by the renderer's geometry,
not wrapped, clamped to an angle bin or discarded. The legacy predictor alone
retains its old rounding and segment-direction calculation.

Elapsed native timestamps are `time - time[0]`; the audited native step is
`0.0015000000000000568` s and the worst elapsed-versus-uniform-grid discrepancy
is `3.681e-12` s. The uniform FFT path is allowed only after the full trial
passes a maximum grid error of 1e-9 s. Keep the actual position samples and
native sample count; do not resample to 2 ms or use the synthetic probe timing.
Future data failing this gate require an explicit irregular-time implementation
and separate parity checks, not silent conversion to a uniform grid.

Input association variants change only width to 5.625 or 22.5 degrees, height
to 30, or contrast to -0.5. Each is a one-factor change from primary. Do not
combine them, infer state gain from P1 filenames or substitute paper cadence.
Gain passed to the LC10a rule is always one. Log scored pulses within the first
three seconds and observation windows touching trial padding; retain them in
the original coverage and label the unobserved earlier history.

## Projection, activation and observation order

Sort the same 275 IDs as the packaged projection. Keep 164 mapped/111 fallback
labels. For every movie compute the frozen per-cell features and causal
envelope, then `raw = activity @ W`. No AOTU-to-DNa02 edge enters this assay.

Replay the canonical positions and their sign-negated mirror separately using
the same anatomical map. For a type k, use its right AOTU column from the
canonical movie and its left AOTU column from the mirrored movie:

```
u_k[n] = (ELU_k(raw_canonical[n, column(k,R)])
          + ELU_k(raw_mirror[n, column(k,L)])) / 2
```

Activate each hemisphere before averaging. Averaging raw drives before ELU
changes the model. Never mirror recorded rates, reorder anatomy to force
left/right equality, infer a physical side from missing metadata, or apply
the legacy AOTU019 direction multiplier to a new-rule predictor.

Use the existing 1,000-point nearest ELU lookup and the fixed legacy type peaks
in the audit, without recomputing them from new features or shuffles. Check
all four AOTU columns on both movie replays, all used full-trial samples and
all new wiring controls. Save maxima and every excess before any lookup.
An excess above peak + 1e-9 fails the affected sensory configuration's
representation gate: write the failure artifact and do not fit or score that
configuration. A <=1e-9 floating-point endpoint excess may be explicitly logged
and snapped to the endpoint; no larger clipping is permitted. Primary requires
all its new controls to pass. Diagnostic configuration failures are retained
and cannot be chosen as a replacement primary result.

Count final-bin occupancy separately from true overflow. Also report the
fraction of positive raw samples mapping to zero, distinct occupied bins,
raw/peak ranges and gains. Synthetic bar checks use only approximately 0.06%
to 3.40% of the legacy range, so lookup quantization is a material limitation.
Some type/hemisphere/bar combinations occupy only the zero bin. A gain after
activation cannot recover information already quantized away. This is a
diagnostic to report, not authorization to rescale peaks or change interpolation.

Apply the unchanged 50 ms symmetric Gaussian observation kernel, with 250 ms
support and the existing zero padding, to the full native activated trace.
Measured rates are already filtered and must not be filtered again. Compute
predicted baseline over the original inclusive [-250,-100] ms native sample
mask, subtract it from the mean over the complete visible pulse, then aggregate
within the original trial/stimulus cell. Actual center binning, pulse bounds,
state classification and targets must reproduce the prior observations exactly.
Causality checks address features, raw activity and raw contact drive before
the symmetric observation filter; that filter can move predictions before onset.

## Controls and the fixed fitting budget

The actual within-side full output-bundle row permutations are in the audit.
Use those indices rather than relying only on seed 20261006 or changing NumPy
versions. Verify each resulting float64 matrix hash. The sorted sensory vector,
map centers and provenance labels stay fixed. All four weights for a cell
move together; no row crosses a hemisphere and no shuffle is renormalized.

Matched spatial weights use the same-side centers and
`q=exp(-0.5*((mu-p_type)/20)**2)`, with p019=35 and p025=65 degrees.
Normalize q to the intact contact total of that AOTU column. Flat weights
divide the same column total equally across same-side LC10a cells. Pin the
resulting matrix hashes and totals. These controls receive exactly the same
LC10a response vectors, aperture, activation and observation treatment.

| Configuration | New wiring predictors | Role |
| --- | --- | --- |
| Primary geometry/rule | Intact, matched spatial, flat, 32 shuffles | Primary and wiring gates |
| Each of five frozen ablations | Intact, matched spatial, 32 shuffles | Explain the primary rule; no winner selection |
| Each of four association variants | Intact, matched spatial, flat, 32 shuffles | Metadata sensitivity; no winner selection |

This is 345 new predictors. Preserve the two legacy anatomy/simple predictors
with their original direction rules, plus training-only constant and zero:
349 predictor/configuration results in total. The ablations are `no_surround`,
`direction_neutral`, `no_static`, `vertical_mean`, and `instantaneous` exactly as
implemented by the frozen component. No geometry-by-ablation cross-product,
time-lag search, kernel search, fitted offset or new P1 state law is permitted.

Each condition/type is a separate pool. For each held recording, a cell is
eligible if it has >=4 trials in that recording and >=3 other eligible
recordings. A training cell must additionally have >=3 eligible recordings
after excluding both the outer held recording and its own training recording.
This preserves the earlier common inner-eligible budget even though no
empirical template is fitted here. Sort row signatures with the audit's order;
held/train signature, target and weight hashes must match for every fold.

Fit one nonnegative gain with no intercept to each predictor/configuration on
exactly those training rows: `g=max(0,sum(w*x*y)/sum(w*x*x))`. Exact zero
denominator yields gain zero and a reported degenerate fit. No arbitrary small
denominator threshold or gain cap may be introduced. Audited legacy denominators
are >1e-14, so this agrees with their historical numerical guard. The gain is
after ELU, observation filtering and baseline subtraction. It is an observation
calibration, not a sensory state gain or synaptic-strength estimate. Refit each
fixed diagnostic configuration on the same training budget. Cells, trials and
recordings have the same hierarchical equal weighting as the prior assay.
The constant is the training-only weighted mean target, including negative
values; zero has no fitted parameters. Never train across NoP1/P1 or AOTU types.

## Scores, gates and interpretation

Reuse unrounded equal-cell/equal-trial per-recording RMSE, then mean recordings
equally. Primary P1 gates must pass for both types: >=5% reduction against
legacy anatomy and >=60% recording wins (15/24 for 019, 14/22 for 025).
The wiring gate also requires >=1% lower RMSE than new matched spatial and
strictly lower RMSE than at least 30/32 new shuffles. Ties are not wins.
Source, coverage, numerical and representation checks must pass first.

Report all configuration scores, negative-evoked coverage, direction/speed
residuals, gains, quantization, per-recording changes and correlations. Plot
out-of-fold P1 curves with the previous >=3-recording coverage and equal
recording means/SEM. Compare new spatial versus old spatial to describe the
input contribution, and new intact versus new spatial/shuffles to describe
wiring. Their difference is not a causal mediation estimate.

An association-sensitive anatomy advantage (loss of a positive advantage
over matched spatial or fewer than 30 shuffle wins) requires metadata recovery
before biological interpretation. An ablation may diagnose a weakness but
cannot retroactively become the primary. These reused recording holdouts
remain exploratory; passing does not supply independent confirmation or
authorize an interactive-controller upgrade.

## Runner layout, efficiency and verification

Implement `src/fly_creature/lc10a_response_benchmark.py` with separate functions
for native rendering/features, fixed contact/control construction, extraction,
fold assembly, scoring and reporting. Keep `lc10a_response.py`, renderer,
selection, existing physiological extraction and production modules unchanged.
Do not call `simulate_movie` with the synthetic trajectory generator for native
recordings; stream the explicit recorded positions instead.

There are 76,786,718 native frames in the relevant full trials before mirrored
replays. Compute shared sensory information once per movie/configuration,
project all wiring controls together and process one trial at a time. Do not
render the scene or rerun the sensory function separately for each shuffle.
Cache keys may use full stimulus/timestamp bytes, fixed geometry and source
hashes; never measured rates, eligibility, fitted gains or response labels.

The fixed uniform-background rectangles have separable vertical coverage.
An optimized one-dimensional motion/pooling path is permitted only after
comparison with the public two-dimensional component for actual native
staircase/jitter samples, NaNs, mirrors, both heights/contrasts and all five
ablations. Keep the nonlinear per-cell rectification and vertical pooling
before projection. Full-height vertical-mean and primary features should agree
apart from roundoff; height 30 still needs the declared vertical pooling.
Front-end filtering must use the previous held frame and empty sample-zero
history, including across chunk boundaries. A scipy vectorized delay recurrence
may replace frame loops if checked against the public front end.

Linear envelope and contact projection may commute *after* the nonlinear
per-cell feature calculation, before ELU; validate raw-drive agreement first.
Neither ELU nor max pooling may commute through a projection or hemisphere
average. Numerical shortcuts must agree to 1e-10 absolute plus 1e-9 relative
on features and raw drives, and produce identical nearest-lookup bin indices
on the checked samples. If a threshold-near sample crosses bins, use the
canonical path there and log it. An approximation that changes output is not
an allowed performance optimization. Profile before a full run and report
actual costs without trading away the native sample grid.

Before candidate scoring, rerun the contract audit, verify new source/protocol
hashes, and independently rebuild all prior targets/folds and legacy predictions.
The completed review reconstructs targets exactly and legacy predictions to
`1.07e-14`; hashes pin the current matrices and calibrations. An implementation
checker must separately reconstruct every fitted gain, membership/exclusion,
weight, recording loss and gate from saved features/folds, and compare selected
native complete trials against the canonical sensory path. Include a future
prefix-change check before filtering, mirrored motion checks, one-pass/chunked
agreement, and zero/constant inputs. Do not score candidates with a failing
parity or representation gate.

Store full per-trial inputs/activity and full observation/fold tables only
under ignored outputs. Save all raw pulse predictions needed by the independent
checker; avoid a giant pixel movie. Track compact summary, primary recording
results, all configuration/rank summaries, check report and figure. A second
complete evaluation from identical saved, hash-verified sensory predictions
must reproduce scoring/gates; independently replay at least one complete trial
per condition/type. This separates scored-output reproducibility from actual
sensor replay evidence instead of claiming two scoring passes are two sensor runs.

Implementation order: immutable preflight and native/optimized parity; primary
and its matched controls; fixed diagnostics and independent reconstruction;
result/claim-boundary documentation. Freeze the runner's source hashes before
opening candidate score tables. A failed result is a completed experiment.

**Recommended settings:** Luna Max for this fixed runner/checker implementation;
Sol medium for interpreting the recorded result or resolving a protocol failure.

## Reproduce this review

From the workspace root, with the previously verified archives and population
artifacts in their documented ignored directories:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/review_lc10a_benchmark.py
```

The review audits inputs, targets, legacy calibration, control matrices and
synthetic lookup behavior. It does not generate new recorded LC10a responses
or fit/score a new physiological prediction.

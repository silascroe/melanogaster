# Repeated-response and residual-variation audit

2026-10-02. Completed offline. Read the [frozen protocol](pursuit_repeatability_protocol.md),
[report](evidence/pursuit_repeatability_v1.json),
[69-recording table](evidence/pursuit_repeatability_recordings_v1.csv),
[independent checks](evidence/pursuit_repeatability_checks_v1.json) and
[figure](evidence/pursuit_repeatability_v1.png).

## What this answers

When a recording sees nominally matching target sweeps again, do its other
trials help predict the response? Does knowing which recording it is matter?
Do continuous walking/turning measurements describe some remaining variation?
This audit scores baseline-subtracted **pulse-mean firing**, not the full
response-shape objective of the preceding temporal experiment. It does not
re-evaluate the connectome adapter or establish a biological noise ceiling.

## Method and coverage

Unchanged extraction yields 35,484 quiescent pulses from 69 retained recordings.
The known numeric duplicate is excluded from both archives. Match nominal
speed, direction and center on an 11.25 degree grouping grid. Native measured
centers differ from the group center by at most 1.47 degrees; these are
matching nominal stimuli, not perfectly identical recorded trajectories.
Within-trial matching pulses would be averaged; here each trial-cell contains
one pulse. Require at least four trials per recording/stimulus cell and three
other recordings for the cross-recording prediction.

The common scoring subset contains **34,554 trial-cells** (97.4% of the extracted
quiescent pulses), in 1,560 held-whole-trial folds. All predictors score the
same subset. Hold out an entire acquisition trial within its recording;
stimulus-specific means and motor coefficients use only its other trials.
The across-recording predictor excludes the entire held recording. Weight
cells equally within trial, trials equally within recording, and recordings
equally in the summary. Different recordings do not have identical coverage.

The motor extension uses four fixed covariates: mean signed forward and mean
absolute angular velocity during stimulation and during the preceding
[-250,-100] ms reference window. Remove training-only stimulus-cell means,
scale by training residual RMS and fit fixed ridge 0.1; there is no tuning.
Units are mm/s and deg/s, documented by the pinned authors' `processSettings.m`.
Canonical ipsilateral orientation is already in the recordings; no physical
hemisphere assignment is inferred from the ambiguous metadata ordering.

## Held-trial results

Mean recording RMSE in spikes/s. Lower is better. Same-recording templates
have access to other measured responses from that recording, so their advantage
over other-recording prediction is not held-animal model validation.

| Archive/type | Recordings | Scored/available | Other recordings | Same recording | Stimulus blind | Same recording + motion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NoP1 / 019 | 11 | 3493/3594 | 6.626 | 6.943 | 6.545 | 6.723 |
| NoP1 / 025 | 12 | 3531/3856 | 9.264 | 9.845 | 9.448 | 9.997 |
| P1 / 019 | 24 | 15198/15365 | 10.794 | 9.605 | 11.210 | 9.175 |
| P1 / 025 | 22 | 12332/12669 | 14.167 | 12.687 | 15.229 | 12.579 |

In P1, stimulus-specific same-recording templates beat the stimulus-blind
mean by **14.3% / 16.7%**, improving 21/24 and 18/22 recordings. They beat
matching other-recording means by **11.0% / 10.4%**, improving 22/24 and 20/22.
There is reproducible stimulus structure and recording-specific information.
This does not prove why recordings differ: individual tuning, state, recording
conditions, drift and other unmeasured factors remain possible.

In NoP1, the same-recording stimulus templates are **worse** than the blind
mean by 6.1% / 4.2%, and worse than other-recording means by 4.8% / 6.3%.
An unregularized cell-specific template can lose when repeatable structure is
weak relative to trial variation and estimation error. This is not proof of
absent visual information or a causal P1 activation effect. Archive labels
remain imperfectly verified, and conditions do not form a certified paired
or randomized experiment.

## Remaining variation and movement

Average within-stimulus trial SD is 5.95/8.29 spikes/s (NoP1 019/025) and
8.59/11.18 (P1). Average matched-cell SD between recording means is
2.49/3.59 and 5.59/7.35, respectively. These are descriptive SDs with different
aggregation and unequal coverage, not additive variance components. Trial
variation includes state, measurement noise, finite-window baseline noise,
unmeasured stimulus differences and possible drift; do not label it all random
biological noise.

The old quiescent label requires low absolute forward velocity for at least
half the pulse; it does not constrain turning. In P1, **38.0% / 39.6%** of
quiescent pulses have at least one forward sample above 0.5 mm/s in absolute
value. Median pulse-mean absolute angular velocity is 3.23/3.75 deg/s, with
90th percentiles 39.80/39.05 deg/s. Near-zero average signed forward movement
is not equivalent to strict immobility. NoP1 shows the same broad limitation
of the coarse label (33.0%/34.8% with some above-threshold forward movement).

Descriptive motion improves P1 same-recording RMSE by **4.47% for 019** and
**0.85% for 025**, improving 21/24 and 18/22 recordings. NoP1 changes are
3.17% better for 019 and 1.54% worse for 025. These percentages are reductions
in prediction RMSE, not percentages of biological variance explained.
Concurrent movement may be a neural output or a shared-state consequence.
The association does not authorize treating it as sensory input or establish
the direction of causation. Four simple motion summaries are not a complete
test of every possible motor/state relationship.

## Checks and reproduction

From the workspace root, using its existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m fly_creature.pursuit_repeatability --output-dir fly-creature/outputs/research/aotu-repeatability-v1
.\.venv\Scripts\python.exe -m fly_creature.pursuit_repeatability --output-dir fly-creature/outputs/research/aotu-repeatability-repeat
.\.venv\Scripts\python.exe fly-creature/tools/check_repeatability.py fly-creature/outputs/research/aotu-repeatability-v1 fly-creature/outputs/research/aotu-repeatability-repeat
```

Archive MD5/member CRC and finite signal/shape checks pass. All retained
65,416 accepted and 158 rejected intervals are accounted for. Two full runs
produce byte-identical JSON, observation/fold/recording CSVs and PNG. Independent
saved-data arithmetic checks all 34,554 predictions and recording losses;
maximum mean-prediction discrepancy is 5.33e-15. A separate augmented
least-squares solution checks a held-trial motor fit in each of 69 recordings,
maximum discrepancy 4.18e-14. Held-trial and held-recording exclusions and
duplicate exclusion pass. Full observations/folds remain ignored.
No unit/gameplay suite was run; these checks validate the authorized diagnostic.
Production code, raw archives, old extraction and previous evidence are preserved.

## Decision

Keep the production model unchanged. There is a learnable visual response in
the P1 assay, but a universal visual-only curve is being asked to predict
both recording differences and substantial trial variation. That explains
part of the target's difficulty; it does **not** exonerate our adapter or
prove that the recent failures were unavoidable. Same-recording templates
are estimates, not optimal predictors.

The next bounded question is a **matched population-tuning comparison**:
compare the frozen anatomy and simple spatial predictors with an empirical
stimulus template from other recordings, using the same pulse-mean target,
coverage, calibration and recording holdouts. Inspect where their mean visual
field shapes differ. This separates missing repeatable visual structure from
individual-trial variation before another sensory rewrite. Sol medium for
design and interpretation; Luna Max for a frozen implementation.

**TL;DR:** Repeated P1 responses have usable visual structure and recording
differences, alongside large trial variation. Simple movement summaries help
modestly. None of this establishes a new neural input or fixes the model.

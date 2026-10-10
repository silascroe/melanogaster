# Matched held-recording population tuning

2026-10-02. Completed offline; production unchanged. Read the
[frozen protocol](pursuit_population_protocol.md),
[report](evidence/pursuit_population_v1.json),
[recording table](evidence/pursuit_population_recordings_v1.csv),
[population cell table](evidence/pursuit_population_cells_v1.csv),
[independent checks](evidence/pursuit_population_checks_v1.json) and
[response-field figure](evidence/pursuit_population_v1.png).

## Question and comparison

How much repeatable population-level visual structure do our frozen anatomy
and simple spatial predictors miss, when every prediction excludes the scored
recording? This uses the previous audit's exact 34,554 common trial-cells from
35,484 quiescent pulses and 69 recordings. Same stimulus grouping, duplicate
exclusion, baseline subtraction and equal cell/trial/recording weights.
It scores evoked pulse means, not the earlier full-trace or raw-rate objectives.

Anatomy pools model hemispheres in canonical coordinates. Simple spatial is
the existing 35/65-degree peak, 20-degree-width Gaussian. Both replay actual
native full-trial positions through the frozen 50 ms observation filter and
subtract their predicted pre-stimulus baseline. No width, peak, direction
rule, timing, state or connection is changed.

Each outer recording holdout fits one nonnegative gain/no intercept per
predictor on other recordings. The empirical template learns a response mean
for each stimulus from other recordings. Its gain uses inner recording
cross-fits, excluding both the outer held recording and the inner predicted
recording; at least three contributors per inner cell. All three gains use
that same eligible training subset and weights. Rebuild the held template
from all eligible outer training recordings. The empirical reference has
many cell-specific learned values: equal final gain allowance does not
equalize model complexity. Constant and zero-evoked controls are included.

## Held-recording errors

Mean recording pulse-mean RMSE in spikes/s. Lower is better.

| Archive/type | Recordings | Anatomy | Simple spatial | Empirical | Unscaled empirical | Constant | Zero |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NoP1 / 019 | 11 | 6.633 | 6.631 | 6.595 | 6.626 | 6.590 | 6.676 |
| NoP1 / 025 | 12 | 9.294 | 9.294 | 9.251 | 9.264 | 9.465 | 9.479 |
| P1 / 019 | 24 | 11.028 | 11.055 | 10.792 | 10.794 | 11.769 | 12.556 |
| P1 / 025 | 22 | 14.518 | 14.595 | 14.200 | 14.167 | 15.532 | 15.856 |

P1 anatomy beats the constant by 6.29%/6.53%. Its advantage over simple
spatial remains only **0.24%/0.53%**, with 9/24 and 13/22 recordings improved.
The empirical template beats anatomy by **2.15%/2.19%**, improving 17/24 and
13/22 recordings. It beats simple spatial by 2.38%/2.71%.
The unscaled empirical sensitivity is practically identical for 019 and
slightly better for 025; fitting its training-only gain does not manufacture
the aggregate advantage. P1 empirical gain ranges are 0.970–1.006 and
1.017–1.066, respectively.

The empirical reference helps, but does not remove most held-recording error.
It is not an optimal predictor or a noise ceiling. Its improvement does not
show that a particular connectome route is beneficial; this audit has no new
wiring-shuffle causal comparison. NoP1 anatomy and simple spatial are almost
identical; the empirical gain is only 0.56%/0.47% over anatomy, and NoP1 019
constant prediction still wins in aggregate.

## Response-field structure

Median within-held-recording equal-cell Pearson correlations:

| P1 type | Anatomy | Simple spatial | Empirical |
| --- | ---: | ---: | ---: |
| AOTU019 | 0.802 | 0.688 | 0.768 |
| AOTU025 | 0.661 | 0.672 | 0.762 |

AOTU019 has 23 defined correlations; the remaining recording has a constant
measured cell-response curve. AOTU025 has 22. Anatomy improves correlation
against simple in 13/23 and 15/22 paired recordings; medians are separate
distribution summaries, not paired effect estimates. Anatomy captures some
019 direction-dependent shape that the direction-independent simple curve
misses. Its higher 019 correlation does not guarantee lower RMSE: amplitude
and recording-specific differences still matter. Empirical does not dominate
every shape metric.

The inspected P1 figure separates type, direction and speed. Each point
weights contributing recordings equally; 019 points contain 20–23 recordings,
025 points 17–21. Error bars are SEM of recording means. The figure shows:

- Both frozen predictors often decay too sharply at larger ipsilateral
  angles, particularly for fast sweeps. Measured mean responses remain elevated
  where predicted response approaches zero.
- AOTU025 direction -1 measured peaks occur at 78.75 degrees at both speeds,
  while anatomy/simple peak at 56.25. Direction +1 measured and modeled peaks
  occur at 56.25. This is one sampled 22.5-degree step, not an inferred exact
  receptive-field displacement. Plateau uncertainty, response history and
  traversal direction can affect pulse-mean peaks. Do not globally shift the
  LC10a map on this evidence.
- Measured 025 evoked responses are below the pre-stimulus reference in several
  nonpreferred regions; the frozen predictions are near zero there. These are
  baseline-subtracted observations, not identified inhibitory synapses. Baseline
  history, state and other mechanisms remain possible. 019 also shows smaller
  below-reference regions and amplitude/direction mismatches.

The plotted empirical population average closely follows the measured mean
partly by construction: averaging leave-one-recording-out cell means can
nearly reproduce the full population mean algebraically. **Green/black curve
agreement is not an additional validation result.** Predictive evidence comes
from the individual held-recording errors above; the plot locates candidate
shape mismatches for subsequent independent hypotheses.

## Checks and reproduction

From the workspace root with the existing research dependencies:

```powershell
.\.venv\Scripts\python.exe -m fly_creature.pursuit_population --output-dir fly-creature/outputs/research/aotu-population-v1
.\.venv\Scripts\python.exe -m fly_creature.pursuit_population --output-dir fly-creature/outputs/research/aotu-population-repeat
.\.venv\Scripts\python.exe fly-creature/tools/check_population.py fly-creature/outputs/research/aotu-population-v1 fly-creature/outputs/research/aotu-population-repeat
```

The runner requires the previous repeatability observations/folds as a
coverage/provenance reference (override with `--repeatability-dir`); if absent,
reproduce that audit first. Previous prediction values never train this model.
Archive MD5/member CRC pass; all 65,416 accepted and 158 rejected intervals
are accounted for. Zero singleton segments. Compact hemisphere lookups equal
the existing full physiology builder exactly; FFT/direct full-trial observation
error is at most 1.12e-15. Extracted responses and held coverage exactly match
the previous assay. Frozen source/component hashes remain current.

Two complete native replays produce byte-identical report, all five CSVs and
PNG. Independent reconstruction checks all 69 outer fits, 34,554 held
predictions, inner/outer exclusions, training/scoring coverage, hierarchical
weights, recording losses, correlations and plot means. Maximum gain/prediction
discrepancy is 1.78e-14; loss/correlation/plot discrepancies are zero. Full
observations, folds and recording-cell tables stay ignored; compact reports,
recording/population tables, checks and figure are tracked. No unit/gameplay
suite was run; these checks validate the requested diagnostic. Production,
raw data and earlier frozen evidence are preserved.

## Decision

Keep production unchanged. Broad visual tuning is present, and anatomy has
some useful 019 shape structure; its small aggregate advantage over a simple
curve still does not establish a substantial circuit-specific benefit.
Population templates improve prediction modestly and locate outer-field,
direction and below-reference discrepancies. Do not add neurons, shift fields
or reinterpret below-baseline firing as inhibition merely to fit this figure.

Next isolate whether below-reference responses and direction-dependent peaks
survive accounting for previous-target history and baseline choice. Use a
frozen, recording-blocked audit of stimulus intervals and pre/on rate traces;
distinguish a genuine missing response feature from a measurement/reference
artifact before changing the sensory circuit. Sol medium for design and
interpretation; Luna Max for a fixed implementation.

**TL;DR:** The empirical reference is about 2.2% better than anatomy in P1.
Anatomy captures some visual shape, but misses broad tails and certain
direction/below-reference features. Diagnose those features' provenance before
rewriting the circuit.

# Pursuit improvement cycle: history audit and candidate decision

2026-10-02. Autonomous goal authorized. Preserve production and old evidence.
This protocol freezes the first audit before its results; a justified candidate
and its evaluation must be frozen separately after the audit, before fitting.

## Baseline/history audit

Same four archives, duplicate exclusion, unchanged quiescent pulse extraction
and nominal stimulus grouping. Read full native trial rates/positions. For
each pulse, record previous visible segment end and hidden gap, previous
segment center/direction, trial onset time and observed pulse mean rate.
Record rate baselines in three fixed windows: near [-250,-100], early
[-550,-400] and far [-950,-800] ms. An alternative is valid only if its full
window is in the recording and hidden. Do not impute unavailable baselines.
Record post-offset mean rate in [100,250] ms to describe persistence.

Primary sensitivity compares all three evoked means on the same pulses with
all valid baselines and >=1 second of preceding hidden time. For first stimuli,
hidden time is time since trial start, not an infinite gap. Secondary >=2 s
and first-stimulus-only strata report coverage even if too small to compare.
Also retain the original near-baseline population as a context reference.
Within each stratum require four distinct trials per recording/stimulus cell;
population cells require three recordings. Equal trial means within recording/
cell and equal recording means within population cell. Report individual
recording negative nonpreferred responses (center<=0 degrees, 025 primary),
baseline drift and coarse P1 peak positions by type/direction/speed. Paired
baseline comparisons must use identical observations; no causal or significance
claim from pulse counts. No field shift or inhibition is inferred from peaks.

Compare near-baseline source signatures/counts to prior extracted observations.
Enforce MD5/CRC, finite values, boundary and visible-window validity, interval
accounting and duplicate exclusion. Independently reconstruct saved aggregates
and repeat all artifacts. This audit neither alters targets in previous
experiments nor re-scores them to improve their reported errors.

## Candidate stage

After the audit, state what survived and what remains uncertain. Freeze one
bounded, explicitly labelled offline candidate with a mechanistic rationale
or a clearly identified engineering assumption. Fit only training recordings;
compare with unchanged anatomy, matched simple non-neural controls and fixed
seed wiring shuffles. Candidate and controls receive the same fitted nuisance
terms. Keep spatial map, output gains, motor queue and production unchanged.
Record an adopt/revise/reject decision using predeclared criteria. A failed
candidate must lead to a specific supported replacement plan, not another
unbounded parameter sweep. Completion means the cycle and decision are
supported, not that a biological improvement is guaranteed.

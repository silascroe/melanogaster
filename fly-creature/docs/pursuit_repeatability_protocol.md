# Frozen response-repeatability audit

2026-10-02. Freeze before reading response-repeatability results. This is a
target/data diagnostic, not another sensory adapter or promotion gate.

Use the four previously checksum-verified NoP1/P1 motion-pulse archives and
unchanged `pursuit_physiology.extract`. Exclude AOTU019/2023_06_15_fly03 from
both archives. Analyze each archive condition and AOTU type separately;
physical side and causal P1 effects remain unverified. Canonical ipsilateral
coordinates are already present in the distributed recordings.

Primary target: baseline-subtracted pulse-mean firing, in spikes/s. This
bounded audit does not score the previous temporal experiment's full trace
objective. Match nominal speed, direction and center snapped to the native
11.25 degree grid for grouping only. Preserve actual position diagnostics.
Use the existing coarse quiescent class; describe continuous motion rather
than quietly redefining rest. Aggregate multiple matching pulses within one
acquisition trial to one observation. Retain stimulus cells with at least four
distinct trials. Trial numbers are blocks within each recording, not animals.

For each held whole trial, predict its matched cells from other trials in
that recording (at least three training trials per cell). Compare with a
stimulus-blind mean of eligible observations from that recording's training
trials. Separately predict from the matching stimulus-cell mean in at least
three other recordings, weighting each other recording equally. Report the
three predictors on their common eligible observations, with equal cell
weight within trial and equal trial weight within recording; aggregate with
equal recording weight. Report coverage and unmatched exclusions. No timing,
amplitude, spatial or direction parameters are fitted to rescue predictions.
Same-recording prediction has access to that recording's other responses;
it is a distinct assay, not comparable held-animal model validation or a
biological noise ceiling.

Secondary descriptive motor prediction adds four fixed covariates to the
same-recording stimulus template: mean signed forward and mean absolute
angular velocity during the pulse, and their means in the preceding
[-250,-100] ms baseline window. Units come from pinned author processSettings
(mm/s and deg/s). Residualize responses and covariates against training-only
stimulus-cell means; scale using training residual RMS and fit a fixed ridge
with objective mean squared residual + 0.1 * squared standardized coefficients.
No intercept, no tuning. Refit in each held whole-trial fold. Concurrent motion
may reflect neuronal output or a common cause: predictive association does
not establish a sensory input, motor cause, or justified production change.

Report within-cell trial SD, within-recording held-trial RMSE, matched
across-recording RMSE, individual recording improvements and continuous
motion distributions in quiescent pulses. Recordings and stimulus coverage
are heterogeneous; SDs are descriptive, not a clean variance decomposition.
No significance test or independent-animal inference from pulse counts.

Read numeric arrays one recording at a time; enforce finite angular values,
consistent shape, accepted/rejected interval accounting and archive/member
checksums. Check holdout disjointness and predictor arithmetic. Repeat the
complete run and compare artifact bytes. Full trial observations remain
ignored; compact recording tables, report and plot may be committed.
Preserve production code, old extraction/protocols/evidence and raw data.

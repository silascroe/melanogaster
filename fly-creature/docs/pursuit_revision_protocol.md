# Frozen directional-skew and visible-offset candidate

2026-10-02. Candidate design informed by the history and population audits.
This is exploratory reuse of these recordings, not independent confirmation.
Freeze before fitting or observing candidate results. No production change.

## Rationale and limits

The history audit's paired one-second subset retains below-reference AOTU025
responses with all three baselines (19/22 negative recording means for near
and early, 20/22 for far). Near-baseline direction -1 peaks remain at78.75
degrees, compared with the frozen model's56.25; direction +1 peaks depend on
baseline. Two-second 025 and first-stimulus strata have no coverage, so this
does not establish complete history independence or synaptic inhibition.

Test one bounded phenomenological correction to the frozen visual response:
allow direction-dependent spatial skew and a visible-target negative offset.
This is an engineering assumption motivated by measured residuals. It does
not add inhibitory synapses or claim LC10a has these measured fields.

For frozen static field f(theta,d), compute its numerical angular derivative
on the existing one-degree lookup grid. Features are f+22.5*d*df/dtheta,
f-22.5*d*df/dtheta and -visibility. Replay each through the same native trial
and 50 ms observation filter, subtract predicted pre-reference and average
the visible pulse. Fit three nonnegative coefficients u,v,q on training
recordings only. Equivalently, g=u+v>=0, angular skew h=22.5*(u-v),
|h/g|<=22.5 degrees, and a nonpositive visible offset -q. No parameter grid,
intercept, motor input or response-memory fit. A derivative correction is
not literally a shifted field; report equivalent skew only as a parameter.

Keep previous trial-cell coverage and calibration subsets exactly as in
the population comparison. Outer holdout excludes an entire recording.
Equal cells within trial/trials within recording/recordings. Fit static
one-gain baseline on the same subset, and candidate on the same targets.
Original near-baseline pulse means remain the target; do not substitute a
different baseline to improve scores.

Frozen intact anatomy, 32 existing fixed-seed within-side input-bundle wiring
shuffles, and the same simple spatial Gaussian all receive identical candidate
features, bound and fitted coefficient budget. Add a flat visible response
control with the same nuisance machinery. Record losses/parameters and
anatomy-vs-simple/shuffle ranks. Offsets/skew may improve ordinary models too;
do not credit common calibration improvement to recorded wiring.

## Decision criteria and checks

An offline predictive candidate qualifies only if primary P1 mean-recording
RMSE falls >=5% versus static anatomy and >=60% of recordings improve, for
both types. A circuit-specific qualification additionally requires >=1%
advantage over equally corrected simple spatial and better aggregate error
than >=30/32 corrected wiring shuffles, for both types. These are practical
predeclared gates, not significance tests. No gate permits production or
biological validation because the dataset informed the design.

If gates fail, preserve the candidate/evidence, identify which requirements
failed and choose a concrete replacement direction instead of extending the
same parameter grid. No arbitrary feature sweep. If correction helps but
wiring controls do not, classify it as a generic calibration improvement.

Check lookup/derivative formulas, native direct convolution, source hashes,
unchanged observations/coverage, constrained fitting by independent NNLS,
held recording exclusion, bounds, gains/ranks and repeat artifacts. Keep raw
feature arrays/observations/folds ignored; publish compact summary, intact
recording table, shuffle ranks, checks and result. Save and privately back up
checkpoints. Original production, raw data and previous evidence remain fixed.

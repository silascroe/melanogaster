# Motion-rule diagnosis protocol

Declared 2026-10-02 before ablation results. No production files or frozen
stress artifacts change. Reproduce the 3 rad/s stress failure (mean error
12.050346 degrees) through the actual session. The 1.7 rad/s case passes the
error gate, but loses to median shuffled wiring; these are different failures.

## One-factor interventions

Keep the recorded circuit, eye map, normalization, 15-degree overlap, gain,
turn cap, 10 ms tick and walking speed fixed. Compare baseline with:
position-only (disable AOTU019 direction penalty), reversed direction (sign
negative control), target-only motion (hold the current body fixed when
computing target displacement; an oracle diagnostic, not a biological sensor),
continuous-visible motion (wrapped angle differences, no history across loss
of visibility), and zero motor queue (delay sensitivity, not an input fix).

Baseline must reproduce every old stress case's saved metrics. Re-run all
48 old cases for diagnosis. Score the existing envelope unchanged. Report
wrong-way applied turns relative to current visible bearing separately from
their original command-time bearing; delayed commands can become stale.

Candidate selection uses only old cases and only the position-only or
continuous-visible interventions. A candidate must reduce aggregate error
on speed 1.7/3 and reversal period 2 by at least 5%, increase supported-task
aggregate error by at most 1%, and worsen no supported case by more than 10%.
Do not search gains, penalties, filters or new neurons. Reversed direction,
target-only motion and zero delay are explanatory controls, not candidates.

## Fresh validation

After recording the selection decision, run 12 mirrored cases: lateral
chirps, smooth asymmetric reversals, and amplitude-modulated oscillations,
each at depths 5 and 7 m. Equations are frozen in the runner before execution.
Target retreats at 0.55 m/s, duration 10 seconds, heading zero. Compare
baseline, position-only, disconnected and ordinary proportional gain 4 with
200/0 ms delays. If continuous-visible is selected, include it as well.
Run 32 within-side LC10a bundle shuffles, seed 20261003, with intact
normalizers, for baseline and position-only (and any additional selected
candidate). These are deterministic model controls, not biological samples.

A selected candidate additionally needs >=5% fresh aggregate improvement,
no >10% per-case deterioration, no loss of passing envelope cases, zero
inactive turns/lookup clipping, and lower aggregate error than every shuffle.
If no candidate qualifies, report that result and preserve runtime settings.

## Source interpretation

[Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) describes
AOTU019 preference for ipsiversive motion and dependence on the sign of
retinal error change, not world-frame target speed. The
[authors' repository](https://github.com/wilson-lab/CollieWilson) models
nonpreferred-direction suppression. Our imposed 0.66 factor is a
source-inspired approximation, not direction selectivity discovered from
our graph. Including the fly's own movement in retinal motion is intentional;
target-only motion is not presumed more biologically accurate.

Save compact JSON/CSV and a report; detailed traces stay ignored. Record
protocol/source hashes, baseline parity, source-rule and geometry probes,
selection decision and fresh outcomes. Repeat to confirm determinism.

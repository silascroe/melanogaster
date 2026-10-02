# P1 archive: measured AOTU comparison

2026-10-02. Completed offline extension; production remains unchanged.
Read the [frozen protocol](pursuit_p1_protocol.md),
[P1 response report](evidence/pursuit_p1_v1.json),
[condition comparison](evidence/pursuit_p1_comparison_v1.json),
[error table](evidence/pursuit_p1_comparison_v1.csv),
[spatial figure](evidence/pursuit_p1_overview_v1.png), and
[time courses](evidence/pursuit_p1_temporal_v1.png).

## What ran

The two additional [public archives](https://zenodo.org/records/15474938)
total 2,293,639,419 bytes and pass the published MD5 checks. Their 47 recordings
(25 AOTU019, 22 AOTU025) yield **55,252 accepted pulses and 141 rejected
intervals**. Every finite interval is accounted for; sample interval remains
1.5 ms. Recorded positions, extraction rules, state strata, model parameters,
observation filter, training-only affine calibration, equal-recording weights
and 32 wiring controls are unchanged. No motor decoder or pursuit behavior
participates. P1 denotes archive/source provenance, not a verified stimulation
marker in every trial.

## Held-out prediction

Mean recording pulse RMSE in spikes/s; lower is better. The side association
used in this primary table is provisional, as explained below.

| Type/state | Recordings/pulses | Baseline | Footprint | Simple spatial | Constant |
| --- | --- | ---: | ---: | ---: | ---: |
| AOTU019 quiescent |25/16331|13.1233|13.1242|13.2570|14.2022|
| AOTU019 running |25/6738|18.0947|18.1005|18.0198|19.5253|
| AOTU025 quiescent |22/12669|15.6369|15.6300|15.6811|16.5765|
| AOTU025 running |21/4203|18.7253|18.7199|18.7015|19.2989|

Baseline error reduction versus the constant is 7.60%, 7.33%, 5.67% and 2.97%,
respectively. The within-recording mean improvement and SEM are 1.079/0.334,
1.431/0.505, 0.940/0.384 and 0.574/0.606 spikes/s. These descriptive uncertainty
estimates are not a multiplicity-corrected significance claim.

The anatomy's advantage versus the simple spatial curve is only 1.01% and
0.28% in the quiescent groups; the simple curve is slightly better in both
running groups. Footprints again make negligible changes. Baseline wiring
ranks are 21/32 and 25/32 for AOTU019, 32/32 for AOTU025. Mixed-state AOTU019
beats 0/32, demonstrating that this rank is not a general property of the
circuit. Absolute errors are larger than NoP1, but response amplitude and
animal variability also differ; that alone does not show a worse model.

The archive supports stronger spatial responses than the previous sample,
but it still does not establish a substantial circuit-specific advantage.
Independent condition calibration absorbs gain/intercept changes rather than
predicting an arousal mechanism.

## Data-quality audit

All 24 NoP1 date/fly names appear in the P1 archive; 23 further names occur
only in P1. No matching MAT container has identical bytes. However,
**AOTU019/2023_06_15_fly03 contains the same 40 numeric trials in both**.
An independent check confirms exact equality, including NaNs, of all seven
distributed variables: time, position, firing rate, voltage and three movement
signals. Other shared identities have no exact four-signal trial match and
no identical firing-rate/forward trial pair. Their stimulation labels still
cannot be certified without per-trial metadata. Matching names omit cell
identity and acquisition order; they do not establish a randomized paired
experiment. No causal P1 effect is estimated here.

There are **11 discordant hemisphere assignments** under the original
sorted-filename association: 4 AOTU019 and 7 AOTU025. Pinned
`load_targetpulse.m` saves `trackLR` in tracker spreadsheet order; those sheets
are absent from the cloned release. The source preprocessing has already
made measured positions ipsilateral-positive, so the uncertainty concerns
which model hemisphere receives each recording. It does not justify mirroring
the measurements again. Neither label list is treated as verified ground truth.
This also qualifies the previous NoP1 report's hemisphere claim.

The [sensitivity table](evidence/pursuit_p1_sensitivity_v1.csv) repeats both
conditions under metadata, opposite, all-left and all-right model assignments.
These scenarios were declared before P1 fitting; they do not exhaust arbitrary
per-recording associations. A separate, explicitly post-hoc diagnostic excludes
the duplicated identity from both conditions and refits training calibration.
No spatial, neural or motor parameter is selected using these diagnostics.

Across all four hemisphere scenarios, P1 quiescent AOTU019's improvement over
the constant stays 6.74%–7.60%; its benefit over the simple curve stays only
0.09%–1.01%. Quiescent AOTU025 stays 5.64%–5.81% versus constant and
0.25%–0.44% versus simple. Removing the duplicate gives AOTU019 8.14% versus
constant but only 1.14% versus simple; AOTU025 is unaffected. The broad spatial
benefit and small circuit-specific benefit survive these checks. Some shuffle
ranks and running comparisons change substantially with hemisphere assignment,
so those finer claims are not robust enough to interpret biologically.

## Direction and time

For quiescent recordings, the descriptive mean ipsiversive-minus-contraversive
response over available ipsilateral positions below 90 degrees is 4.13
(SEM 1.43) spikes/s for AOTU019, versus the model's 4.81. The comparable NoP1
measurement is 0.10 (SEM 0.30). These are unequal-cohort, unequal-coverage
descriptions, not a causal state effect or proof of the model's fixed penalty.
AOTU025's measured difference is 1.98 (SEM 0.65), while the model gives about
0.009: this adapter has almost no AOTU025 direction selectivity.
Full per-recording position/speed pairs remain in ignored direction CSVs.

The inspected temporal figure exposes a more useful next question: measured
responses rise and persist differently from the filtered static predictions,
especially after stimulus disappearance. The model contains no intrinsic
temporal response dynamics. These examples cannot uniquely identify a time
constant or separate sensory persistence from motor/state contributions.

## Reproduce

From `fly-creature/`, with the optional `physiology-research` extra installed:

```powershell
python tools/fetch_aotu_recordings.py --condition P1 --data-dir outputs/research/aotu-recordings
python -m fly_creature.pursuit_physiology --condition NoP1 --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-nop1-regression
python -m fly_creature.pursuit_physiology --condition P1 --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-p1-v1
python -m fly_creature.pursuit_p1_comparison --nop1-dir outputs/research/aotu-nop1-regression --p1-dir outputs/research/aotu-p1-v1 --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-condition-comparison
python -m fly_creature.pursuit_physiology_sensitivity --data-dir outputs/research/aotu-recordings --comparison-dir outputs/research/aotu-condition-comparison --output-dir outputs/research/aotu-p1-sensitivity
```

NoP1's five CSVs, two PNGs and original numerical summaries remain exactly
unchanged. Two P1 evaluations produce byte-identical five CSVs, two PNGs and
report JSON. Frozen production/input hashes stay unchanged; the first P1
observation filter agrees with direct convolution to 6.94e-17. No unit or
gameplay test suite ran; these checks cover the requested offline experiment.
Raw recordings and full traces remain ignored; compact evidence is tracked.
Tracked text uses LF newlines; stored condition-report hashes identify the
original evaluation output bytes before Git text normalization.

## Next

The [bounded temporal-response experiment](pursuit_temporal_result.md) is
now implemented and evaluated. It fails the frozen benefit criteria; read
its held-recording and speed-transfer results before introducing response
memory into production. The next diagnostic question is response repeatability
and remaining within/across-recording variation. Better condition/hemisphere
provenance is still required for biological state/side claims.

**TL;DR:** Spatial responses are clearer in the P1 archive, but the detailed
connectome barely adds to a simple spatial curve. Data labels need caution;
temporal response shape is now a concrete, measured mismatch to investigate.

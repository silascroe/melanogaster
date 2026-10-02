# P1 extension of the measured AOTU benchmark

2026-10-02. Frozen before P1 response fits. Inherit the complete extraction,
state strata, observation filter, model parameters, 32-shuffle seed, simple
spatial control, intercept diagnostic, equal-animal weighting and leave-one-
recording-out calibration from [the NoP1 protocol](pursuit_physiology_protocol.md).
Do not alter the old report or its fingerprints.

Use Collie et al.'s Zenodo version 15474938 archives `AOTU019 Motion Pulse.zip`
(1,333,343,141 bytes; MD5 848680fbccbb80353d05f828cc6feef1) and
`AOTU025 Motion Pulse.zip` (960,296,278 bytes; MD5 eae5a827f7e75b373c95b1ce9ee76c9b).
The pinned author loader distinguishes these from the No P1 folders. The
distributed int_* files may not embed stimulation markers; label condition
from archive/source provenance and report that limitation.

Audit side metadata, sample intervals, pulse spans/slopes/durations, position
coverage and rejection counts before interpreting fits. Identify overlapping
recording names and exact member hashes between conditions. Matching names
alone do not establish a randomized paired experiment; neither treat all
recordings as independent across conditions nor assume they are all paired.
No cross-condition training is used for primary fits.

Evaluate P1 independently with the identical calibration budget. Compare
absolute held-out errors, benefit over intercept-only/simple-spatial controls,
wiring ranks, training gains/intercepts, baseline-subtracted position/direction
curves and fixed-position time courses. Report recording-level uncertainty,
coverage and locomotor-stratum composition. Do not call a lower absolute error
an improvement if response amplitude/variance changed. Condition-specific
calibration can absorb a gain change; it is not an independently predicted
arousal mechanism. These are conditional response tests, not causal estimates
of P1's effect or a change to production.

Re-run NoP1 through the extended loader and require exact equality of prior
primary numerical summaries and CSVs. Confirm frozen controller/model/data
hashes, independent observation-filter arithmetic and repeated P1 results.
Save compact reports/plots under docs/evidence and full data/traces only in
ignored outputs. No fresh pursuit paths or behavioral promotion.

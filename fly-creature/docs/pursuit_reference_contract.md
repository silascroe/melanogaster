# Pursuit reference contract — source and protocol

Status: Step 1 source/protocol audit, 2026-09-26. This document records the
pre-implementation contract; the subsequent Octave/Python comparison is in
[the Step 2 result](pursuit_reference_result.md). See the compact
[source manifest](evidence/pursuit_reference_source_v1.json) and
[protocol input specification](evidence/pursuit_reference_protocol_v1.json).

## Pinned source and scope

The reference is the authors' [CollieWilson repository](https://github.com/wilson-lab/CollieWilson/tree/65d72773121ffe148b56b8ba4f594a7a51c51789),
commit `65d72773121ffe148b56b8ba4f594a7a51c51789`, associated with
[Collie et al., Neuron (2026)](https://pubmed.ncbi.nlm.nih.gov/41713413/),
DOI `10.1016/j.neuron.2026.01.001`. The clean clone lives in ignored
`fly-creature/outputs/research/CollieWilson/`. The manifest records SHA-256
hashes of the files used below. Only our source metadata and protocol
description are in this project; the authors' code and numerical table are
not copied into tracked creature files.

The repository README states CC BY-NC-ND 4.0, cites the paper, and asks users
to cite it when using the code or dataset. There is no root LICENSE file in
this pinned checkout. Treat porting or redistributing source/data as a
separate reuse decision before shipping the standalone creature. This
contract describes the algorithm for local study; it grants no additional
rights.

No `matlab` or `octave` executable was available on this machine's PATH at
the time of this audit. The README specifies MATLAB 2023b+ for its MATLAB
work. This source uses
MATLAB-specific APIs including `matlab.desktop.editor.getActiveFilename`,
`lowpass`, `wrapTo180`, and `tiledlayout`. The repository contains a model
settings image but no saved numerical step-response trace. Step 2 later
established Octave compatibility for the core functions with external shims;
MATLAB parity and the full filtered-noise experiment remain open.

## Data lineage and what is known

`runAOTUmodel.m` reads `Modeling_Code/Pursuit_RFs.csv`, then
`processRFdata.m` sums columns other than AOTU019/025 into a third, minor
pathway. It first mirrors the AOTU002_a and AOTU002_c fields because they
project contralaterally. The CSV has 361 azimuth rows from -180° to 180° and 14 response
columns. It represents modeled AOTU pathway receptive fields, **not** 275
measured LC10a fields.

The repository's `Connectomics_Code/heatmap_analysis.m` points to
`AOTU_MaleCNS`, estimates retinal positions from lobula heatmap images,
normalizes each cell's DNa02 output weight, and writes
`AOTU_MaleCNS/rf/weighted_rf_by_cell.csv`. Its companion R scripts query
`male-cns:v0.9`. The model runner marks a 2025 update to a male model.
The male weighted table contains 465 rows over -15° to 165°; the model CSV
contains its 14 corresponding columns on a 1° grid with zero-padded outer
space and simplified column names. Direct comparison found exact values,
within 1e-12, for all 14 columns at five shared grid angles: -15°, 30°,
75°, 120°, and 165°. No checked-in script explicitly constructs
`Pursuit_RFs.csv` from that male table, so interpolation and padding are
strongly indicated but not proved byte-for-byte. This is also not a mapping
from the authors' v0.9 neuron IDs to our MaleCNS v1.0 IDs.

As source-table anchors, right AOTU019 peaks at 26° with value
0.999985699805799; right AOTU025 peaks at 72° with value
0.68417983570978. The former is more frontal and the latter more
peripheral. These are model input table values, not recorded firing rates.

## Selected static protocol

Use `processRFdata(Pursuit_RFs)` and
`support/aotu_steering_model_position.m` with the default -180°..180°
grid, `AOTU019synapse="inhibitory"`, and `alpha=1`. Keep the summed minor
pathway for this diagnostic. Right response fields are read from the table;
left fields are reversed across azimuth. The function combines right AOTU025
with **left** AOTU019 inhibition, and vice versa; then it applies the
`adjELU` downstream lookup and returns DNa02 right-minus-left activity
across azimuth. The output is in arbitrary model activity units. This is a
fixed-fly spatial response calculation, without simulation time or movement.

The static function uses `adjELU`, whereas the dynamic function below uses
`ELU` for AOTU input/output and a default **linear** DNa02 lookup. Their
outputs must not be compared as though one were a time slice of the other.
Symmetry about 0°, frontal/peripheral peaks, signs, and lookup samples are
the Step 2 static checks. No numerical static output fixture from MATLAB has
yet been captured.

## Selected closed-loop protocol

Follow the active call path
`runAOTUmodel.m` → `modelPerformance_step(restricted_RF,
'dirselective')` → `aotu_steering_model.m`. The runner sets the minor-pathway
sum to zero before the step comparison. `modelPerformance_step` loads fresh
`modelSettings`, uses inhibitory contralateral AOTU019 and ipsilateral
AOTU025, and compares three conditions: neither direction selective,
AOTU019 direction selective, and AOTU025 direction selective. For the main
start-position sweep it uses 0°..140° in 10° steps. Its representative
fixed-start sensitivity sweep uses 120° while varying the AOTU019
nonpreferred-motion penalty from 0 to 1.

The main sweep's effective values are 100 Hz; 16 s; 100 held samples before
release; `k=0.65`; noise level 0.01; 20,000 runs from the unmodified default;
RNG seed 13; AOTU019 penalty 0.66; AOTU025 penalty 1; 2° settling band.
Starting side alternates positive and negative across runs. The right AOTU
curves are mirrored for left; AOTU019/AOTU025 and minor-pathway delays both
resolve to 45 samples (450 ms). Nonpreferred motion multiplies the selected
pathway input by its penalty. The DNa02 lookup spans -2.25 to 4 over 1,000
points and is linear in the active default. The turn command is `k` times
DNa02 right-minus-left activity, subtracted from retinal object azimuth at
each step; independent low-pass Gaussian movement is then added. Both
interpolations use nearest lookup. Positions are rounded to degree bins and
wrapped to ±180°. For this 16 s protocol, the function's optional 20 s jumps
never occur.

Two source quirks must remain visible in any comparison. The function's
timebase is `linspace(0, 16, 1600)` rather than exact 0.01 s increments,
and it reports rotational velocity after dividing its per-step turn by
`2/fs` (0.02 s), despite updating at 100 Hz. Separately, the setting
`visuomotor_delay=200 ms` appears in analysis code; the dynamic model
function uses its explicit 450 ms pathway delays. Do not silently change
either convention when checking source parity.

The `calculateAverageSettlingTime.m` helper describes a continuous one-second
stay within ±2°, but its counter is cumulative across distinct in-range
segments. It can therefore report a settlement after repeated brief visits.
Step 2 should reproduce that helper only as a **source metric**, and compute
a separately labeled continuous-settling metric for interpretation. This
audit has not measured how much that discrepancy changes the authors' results.

The chosen author-code protocol is relevant to the preprint's pursuit
step-response analysis, but the older [preprint methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/)
give different illustrative values (including 200 ms, a 0.7 direction
penalty, and a 100° example). The final article's precise figure-to-code
mapping could not be confirmed from its accessible abstract. Therefore call
this an **author-code protocol**, not an exact reproduction of a numbered
published figure.

## Comparison contract for Step 2

First obtain author-code traces from the pinned revision. A minimal
deterministic subcase sets `numRuns=2` and `noiseLevel=0` with held 120°
starts, 100 held samples, 16 s, and conditions 0/1/2. These two overrides
isolate equations and timing; they are not the paper's aggregate experiment.
Compare individual azimuth, AOTU channel activity, and reported rotational
velocity at every step. Proposed numerical tolerance: absolute 1e-6 in each
output's native units, after matching MATLAB's nearest interpolation and
rounding. Record any unavoidable difference, rather than changing parameters
to hide it.

Then check the full noisy protocol at the original settings. Since Python
and MATLAB random streams/filters may differ, compare specified aggregates:
mean/median position trace, time within ±2°, settling time and its spread,
and the ranking of the three direction-selectivity conditions. State sample
count and uncertainty; no numerical tolerance for these aggregates is set
until author outputs can be captured. The expected qualitative result from
the paper is that AOTU019 selectivity improves settling more than the same
selectivity placed on AOTU025. Do not score this expectation as matched until
the actual author-code result is obtained. Report the source helper's
settling metric and the corrected continuous-stay metric separately.

Step 1 is complete as a pinned, inspectable source and input contract.
Numerical reference output capture and any model implementation belong to
Step 2. The data lineage is strongly supported but retains the explicit
CSV-construction gap above.

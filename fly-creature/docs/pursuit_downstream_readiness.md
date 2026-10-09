# Downstream comparison: Phase A readiness

Codex, 2026-10-09. **STOP before Phase B: required metadata remains unresolved.**

This is a metadata result, not a failed neural prediction. No DNa02 neural
response values were opened, no predictor was fitted, and no production
controller changed. The [frozen contract](pursuit_downstream_contract.md)
retains its original coverage and performance requirements.

## What was checked

Verified five public archive MD5 values and every ZIP member CRC; retained 80
recording units (11 DNa02 and 69 AOTU). The two copies of the previously
excluded AOTU019/2023_06_15_fly03 remain excluded. Archive and retained
member SHA-256 values are in the [compact evidence](evidence/pursuit_downstream_readiness_v1.json).
Numerical reads were limited to time, target position and forward movement
(plus an optostimulation indicator if present). Neural and other movement
dataset shapes/dtypes were inspected without reading their values.

| DNa02 recording | Trials | Accepted pulses | Quiet 25°/s pulses | Cells with ≥4 distinct trials |
| --- | ---: | ---: | ---: | ---: |
| 2024_07_30_fly01 | 32 | 576 | 275 | 18 |
| 2024_07_30_fly02 | 23 | 414 | 275 | 18 |
| 2024_08_02_fly01 | 40 | 719 | 615 | 18 |
| 2024_08_02_fly02 | 19 | 341 | 215 | 18 |
| 2024_08_02_fly03 | 40 | 717 | 254 | 18 |
| 2024_08_05_fly01 | 20 | 360 | 326 | 18 |
| 2024_08_05_fly02 | 12 | 216 | 74 | 15 |
| 2024_08_06_fly03 | 40 | 719 | 454 | 18 |
| 2024_08_12_fly01 | 30 | 540 | 277 | 18 |
| 2024_08_12_fly02 | 20 | 360 | 254 | 18 |
| 2024_08_13_fly01 | 40 | 720 | 287 | 18 |

## Common coverage

Each retained cell requires ≥4 distinct trials within a recording and
support in ≥4 recordings per neuron type. Inhibitory crossover also requires
AOTU019 support at the mirrored center/direction; same-side controls retain
the unmirrored cell. At least six DNa02 recording units are required.

| AOTU comparison cohort | Joint stimulus cells | Eligible DNa02 units | Coverage gate |
| --- | ---: | ---: | --- |
| P1 | 18 | 11 | pass |
| NoP1 | 18 | 11 | pass |

P1 at 25°/s is the prospective source-supported comparison. NoP1 counts
are an inventory sensitivity, not an alternative selected by response fit.
Cell/recording/trial IDs and the mirrored-input support are saved as metadata
candidates; no Phase B fold manifest is approved while required gates are unresolved.

## Timing and signal checks

All 80 time axes have 1.5 ms steps; maximum uniform-grid discrepancy is 3.68e-12 seconds.
Every accepted pulse has 100 native samples in the inclusive baseline window.
DNa02 accepted absolute slopes span 24.467–24.550°/s; 25°/s is the nominal speed class, not an assertion of exact measured speed.
Largest DNa02 center deviation from its 11.25° bin is 0.895°.
Typical hidden gaps are about one second. Short artifact fragments occur in
the all-segment inventory; duration and hidden-margin exclusions remain active.
Eligible-quiet gap distributions are retained separately. No optostimulation
channel is present in any of the 80 saved recordings.

## Source constraints and readiness

The [primary-source audit](pursuit_downstream_metadata_sources.md) supports P1
treatment and identical 50 ms Gaussian spike-rate smoothing for all three
types. Saved rates must not be smoothed a second time. Coordinates have
already been normalized to the recorded cell's side. Use canonical population
assumptions rather than assigning physical sides from an unverified tracker order.

Target dimensions/contrast and per-member stimulation timing are not retained
in the interpolated arrays. External pattern lookup files, original recording
metadata and tracker associations are unavailable in the pinned checkout.
The known acquisition defect assigning sweep range to sweepRate also means
actual position chronology, not that metadata field, determines speed.

Native steps, baseline sample counts, direction slopes, center-bin errors and
all-segment/eligible-quiet gap distributions are in the evidence. These checks
preserve actual chronology; they do not insert the paper's nominal cadence.
Stored physical units follow depositor/source conventions, not per-file calibration.
Byte-identical member groups: 0; cross-cohort
DNa02/AOTU date-fly filename overlap: 0.
Filename labels are recording units, not independently certified animal IDs.

**Decision:** Required stimulus/state provenance is unresolved; do not access
DNa02 responses or fit Phase B. Recover pattern/recording metadata or an explicit
author mapping first. If unavailable, leave this physiological comparison stopped
rather than substituting a better-fitting cohort or tuning a new neural model.

## Reproduce and check

From the workspace root, with physiology-research dependencies:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/audit_downstream_recordings.py --fetch --write-evidence
.\.venv\Scripts\python.exe fly-creature/tools/check_downstream_metadata_audit.py --report fly-creature/outputs/research/downstream-readiness-v1/audit.json
```

The synthetic checker traps neural numerical reads, matches reference pulse
exclusions and verifies distinct-trial coverage/first-pulse gaps. Its real-artifact
check independently reconstructs every recording's coverage from saved metadata
and checks the no-response-access declarations. Full metadata pulse files and
downloads remain ignored; compact provenance and coverage are committed.

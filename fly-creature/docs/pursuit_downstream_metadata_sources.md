# Downstream comparison: metadata source audit

Codex, 2026-10-09. Phase A only. No DNa02 or AOTU numerical response
arrays were opened, fitted or scored. This note identifies prospective
cohort constraints; it does not certify the downloaded archive members.

## Verified from primary sources

The [April 26, 2025 preprint](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/)
(DOI `10.1101/2025.04.23.650240`, Results near Figure 2; genotype section
"Fig. 2, S4") explicitly describes DNa02 motion-pulse recordings in male
flies with P1 optogenetic activation, matching the arousal treatment of the
AOTU recordings. Figure 2's legend identifies P1 stimulation. This supports
choosing **P1, not NoP1**, prospectively. It does not prove every archive
member belongs to that cohort. The final Neuron article is DOI
`10.1016/j.neuron.2026.01.001`; its lab PDF and publisher full text were
inaccessible in this audit. Do not silently upgrade these preprint details
to a fresh final-article verification.

The clean pinned [author code](https://github.com/wilson-lab/CollieWilson/tree/65d72773121ffe148b56b8ba4f594a7a51c51789)
provides stronger cell-type-specific protocol information:

| Source | Verified operation |
| --- | --- |
| `Data_Analysis_Code/load_targetpulse.m:30-79` | AOTU019/025 motion cohorts include 25 and 75 deg/s; DNa02 `a02_motion` uses **25 deg/s only**, tracker sheet 1. Separate `a02_none` uses a No P1 folder and sheet 2. |
| `Data_Acquisition_Code/runExptBattery.m:276-287,330-353` | All relevant motion batteries select pattern 2, described as a dark bar. Standard/extended/one-speed batteries use different function IDs and trial durations. One-speed trials last 36 s with 5 s breaks; stimulated battery 14 uses stimulation throughout. Battery 15 mixes unstimulated/stimulated halves. These are available configurations, not proof of a recording's selected battery. |
| `Data_Acquisition_Code/experiment types/batteryStimG4PanelsFictracEphys.m:42-54,72-81` | Active stimulation branch delivers opto output throughout the trial. Pattern metadata stores object size and object/background grayscale; function metadata stores name/range. `sweepRate` is assigned `funlookup.sweepRange`, a source metadata defect: do not trust that field alone as speed. |
| `Data_Analysis_Code/pipelines/preprocess_motionpulse.m:99-133,157-174` | Same routine processes all types, mirrors panel/angular/sideway signals for left cells, masks hidden positions/jumps, omits detected current-injection trials, calculates Gaussian spike rate, then retains every 30th native sample. |
| `Data_Acquisition_Code/support scripts/convolveSpikeRate_input.m:41-98` | Gaussian sigma is 1,000 native samples for every type. `ephysSettings.m:44` sets 20 kHz: **50 ms sigma**, symmetric `conv(...,'same')`, before downsampling. Detection differs: AOTU019 prominence 5 mV/minimum distance 1.5 ms; AOTU025/DNa02 prominence 2 mV/minimum distance 10 microseconds. Both use 0.5 ms minimum/50 ms maximum peak width. |

The [depositor's dataset methods](https://zenodo.org/records/15474938)
independently describe 20 kHz acquisition, factor-30 storage downsampling,
stimulus/movement/state channels and estimated spike rates. Thus the expected
stored time step is approximately 1.5 ms. The saved `spikert` is already
smoothed; do not filter it again, or apply a second 50 ms kernel to predictions
unless the comparison contract explicitly requires that observation operation.
The source pipeline allows reuse of already-existing interpolated files, so
code alone does not prove every released file used this exact revision.

Units are source conventions, not attributes recovered from each saved neural
array. The Gaussian kernel is normalized by its integral divided by acquisition
sample rate (`convolveSpikeRate_input.m:73-98`), giving spikes/s.
`preprocess_motionpulse.m:128,156` preserves `forwardVelocity` as `int_forward`;
`Data_Analysis_Code/settings/processSettings.m:43,119` labels it mm/s.
`dsFiltFictrac.m:79-85` explicitly converts that velocity to degrees/s for a
separate total-speed calculation. This supports the existing quiet threshold;
it is not an independent ball-calibration measurement for every recording.

## Supported inference

The strongest prospective candidate is **25 deg/s P1 motion pulses**, matched
by actual stimulus chronology and movement eligibility. The shared pattern
number and preprocessing favor comparability, but do not establish identical
physical target dimensions, contrast, pulse timing or trial state.
Different trial lengths are not themselves disqualifying; compare eligible
pulses with their recorded history rather than whole trial indices.

## Unresolved gates before response access

Exact DNa02 target width/height, grayscale contrast and pattern/function
lookup payloads are not in the pinned code checkout. Numerical dimensions
from our prior AOTU benchmark must not be inherited by filename. The existing
[sensor contract](lc10a_sensor_contract.md) records a prior final-paper inspection
giving 11.25-by-60-degree bars and a nominal three-second onset cadence. That
historical inspection is not a fresh source verification here and explicitly
did not establish archive-by-archive parity; it does not clear this gate.
The acquisition
code requires external `patt_lookup_0002` and `func_lookup_*` files; inspect
recording metadata equivalents if present. The missing Excel trackers also
prevent identifying original inclusion decisions and side/state for every
archive member from this source alone.

Require archive metadata or an explicit author/source mapping to establish
P1 cohort membership, side convention, target geometry and stimulation timing.
If a saved opto channel was discarded by interpolation, its absence is not
evidence for NoP1. Shared figure-level P1 treatment plus matching actual
metadata can justify cohort selection; folder names alone cannot.
The main Phase A chronology audit must verify matching speeds, direction,
angular span, visibility, baseline windows and movement units without viewing
neural values. Stop before fitting if a material state/geometry mismatch
cannot be resolved. Separate-animal population comparisons cannot identify a
simultaneous synaptic transfer, even if these gates pass.

## Local source integrity

Clone: `outputs/research/CollieWilson/`; HEAD verified as
`65d72773121ffe148b56b8ba4f594a7a51c51789`, clean. SHA-256:

| File (relative to clone) | SHA-256 |
| --- | --- |
| `Data_Analysis_Code/load_targetpulse.m` | `06b9aa52df8b5fcbdad4d4ed67e6ec7016e6456b68e0d32ba2ead292497718ea` |
| `Data_Analysis_Code/pipelines/preprocess_motionpulse.m` | `b1c13df523171e5977412efe63847abac5f66723b78a891e1a18ab8b2a390c93` |
| `Data_Acquisition_Code/support scripts/convolveSpikeRate_input.m` | `edfac377bd21bb04d4b7c47df3de79242c2b84111f67b509cd29c4ce43d859ab` |
| `Data_Acquisition_Code/ephysSettings.m` | `256bd10a87fa923d32a7d29e215b189ab682205325ce7a347a583757cfa06c10` |
| `Data_Acquisition_Code/runExptBattery.m` | `5d3a396bc7783b924683d58eddef335699e213fdc2591b2760dffa2d90c2441b` |
| `Data_Acquisition_Code/experiment types/batteryStimG4PanelsFictracEphys.m` | `c4d0143a117aae2fe8f4e8a7d374724a7b2883bb4e2174631d2de7f1041c2b71` |

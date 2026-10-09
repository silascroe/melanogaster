# Next question: measured AOTU input to the DNa02 bridge

Codex, 2026-10-09. **Design complete; data compatibility is not yet established.**
No DNa02 recording response has been opened or scored for this design. This
replaces further tuning of the [retired input candidate](lc10a_response_diagnosis.md).
The next execution is the metadata/coverage audit below, not a new simulator.

## Question and why it is worth asking

**With measured AOTU population responses supplied as input, does the selected
MaleCNS AOTU→DNa02 contact pattern predict DNa02 visual pulse responses better
than a simple equally weighted signed route?**

This removes the unmeasured retinal→LC10a transformation from this experiment.
It tests one downstream link, not the entire pursuit loop. A positive result
would justify studying that bridge further; it would not validate natural
vision, synaptic conductance, individual-neuron transfer, or useful locomotion.
Different recording cohorts are not simultaneous observations of this circuit.
Other inputs to DNa02 are omitted, so a failure is a failure of the selected
linear two-pathway prediction, not evidence that the biological route is absent.

## Primary sources checked and alternatives rejected

The [Collie dataset](https://zenodo.org/records/15474938) lists
`DNa02 Motion Pulse.zip`, 260,077,425 bytes, MD5
`a650c298d8e5368109f9c295b01c7171`. The
[archive preview](https://zenodo.org/records/15474938/preview/DNa02%20Motion%20Pulse.zip?include_deleted=0)
lists 11 `*_int.mat` recordings and `trackLR.mat`. File availability is verified;
their actual arrays, valid pulse coverage and cohort conditions are not.

The existing [pinned author repository](https://github.com/wilson-lab/CollieWilson/tree/65d72773121ffe148b56b8ba4f594a7a51c51789)
provides two critical interpretation checks:

- `Data_Analysis_Code/load_targetpulse.m`: `a02_motion` selects DNa02 Motion
  Pulse and `25deg/sec` only; a separate `a02_none` case names No P1.
- `Data_Analysis_Code/pipelines/preprocess_motionpulse.m`: panel position and
  angular/sideways velocity are already flipped for left cells so positive is
  ipsilateral. Saved arrays include position, forward/angular/sideway movement,
  rate, voltage and time, but **not an optostimulation indicator**. They are
  already spike-rate filtered. The source uses tracker/experiment metadata
  outside the saved arrays. Code intent alone does not prove each archive's P1
  condition, geometry or metadata ordering.

Pinned local file SHA-256 values are
`06b9aa52df8b5fcbdad4d4ed67e6ec7016e6456b68e0d32ba2ead292497718ea`
for the loader and
`b1c13df523171e5977412efe63847abac5f66723b78a891e1a18ab8b2a390c93`
for preprocessing. No author pipeline was executed during this design.

The [published LC10 spiking model](https://github.com/rutalaboratory/LC10NetworkModel)
uses estimated equal spatial partitions and a hemisphere spike-difference
readout. A full input-current→LIF reproduction would be a separate source-parity
exercise, not an independent MaleCNS wiring test. We already have an AOTU
[source reference reproduction](pursuit_reference_result.md); repeating that
does not constrain the missing LC10a sensory transfer.

Direct AOTU current-injection archives offer causal turning-sign tests, but
correct signs alone follow from the signed bridge and do not demonstrate the
value of its particular contact strengths. Keep that as a possible later
physiology constraint, not a substitute success criterion.

## Phase A: data compatibility and identifiability audit

Implement a small standalone audit under `tools/`, with compact JSON/Markdown
evidence and full downloads under ignored `outputs/research/`. Reuse existing
read-only archive/extraction code where its checks fit; do not change frozen
readers or force DNa02 into their previous AOTU assumptions.

Obtain the DNa02 archive once, stream-verify exact size and published MD5,
verify member CRCs and save SHA-256 hashes. Inventory all 11 recordings before
excluding any. Open one filename-selected recording to establish schema, then
audit position/time/locomotion coverage in every recording. Inspect rate/voltage
dataset shapes and units only; do not view rate values, response means or fits
before the protocol/coverage manifest is frozen. Reject accidental numerical
target access as a prospective-boundary failure and label later work exploratory.

The audit must answer these questions explicitly:

| Boundary | Required evidence / stopping condition |
| --- | --- |
| Side and coordinates | Confirm preprocessing normalization and metadata association. Never apply a second left/right flip. If original side is unavailable, use the explicitly canonical population comparison; no side-specific inference. |
| State | Establish the DNa02 stimulation cohort from paper/acquisition metadata and match AOTU P1 or NoP1 accordingly. Do not pick the better-fitting cohort. Unknown or incompatible state stops the comparison. |
| Stimulus | Match actual 25°/s slopes, 22.5° sweep span, directions and sweep-center cells from positions. Establish target dimensions/contrast from source protocol or metadata; unknown relevant geometry stops physiological comparison. No fast-stimulus claim. |
| Stored signals | Verify uniform native time, dimensions and filtering conventions. Do not filter stored measured rates again; do not assume the deposit's general variable description proves each file's schema. |
| Movement | Apply the existing quiet-pulse rule identically (at least half the visible samples have absolute forward speed <=0.5 mm/s). Do not substitute a running cohort when quiet coverage is weak. |
| Baseline/history | Retain the original inclusive [-250,-100] ms baseline and pulse mean, hidden margins and exclusion accounting. Audit gap distributions across cohorts; incompatible chronology cannot be patched with a fitted offset/kernel. |
| Coverage | Require >=6 eligible DNa02 recording units, >=4 trial repeats per scored cell per recording, and support in >=4 DNa02 recordings and >=4 AOTU recordings of each type. Restrict to the common stimulus/state cells; record exclusions from metadata only. These are practical minimums, not power guarantees. |
| Independence | Check duplicate payloads and available animal IDs across AOTU/DNa02 cohorts. Filenames identify recording units, not automatically independent animals. Group known shared animals together. |
| Missing pathways | State that the selected four edges are not all DNa02 input. Archive compatibility allows a selected-pathway prediction, not identification of a complete biological transfer function. |

Save a **pass / stop / unresolved** readiness decision with precise reasons,
the comparable cohort, eligible cell/recording IDs, source hashes and exclusions.
No fit, new LIF constants or full benchmark if any required boundary is unresolved.
An unresolved metadata audit is a useful stop, not permission to assume parity.

## Phase B: conditional, small recorded-response comparison

Only after Phase A passes, freeze its coverage and the following calculation
before opening any DNa02 response values. Finish the protocol with exact input
hashes, dataset ordering, grouped fold membership and controls. Phase A is the
next implementation scope; this comparison is the subsequent conditional task.

Build AOTU019/025 stimulus-cell templates from the matched existing recordings:
the mean evoked pulse rate relative to the same baseline, averaged first within
trial, then recording, then across recordings. Preserve signed evoked values;
a negative change in an inhibitory neuron can represent disinhibition. These
are measured population templates, not 275 LC10a fields or the already
connectome-weighted `Pursuit_RFs.csv`. No retuning of sensory fields or type gains.
Exclude known animal overlap with the held DNa02 recording when constructing
templates. If this destroys coverage, stop rather than leak between folds.

Use the existing packaged four signed connections exactly once:

| Recorded source | Destination | Signed contact coefficient |
| --- | --- | ---: |
| AOTU019 R, 10005 | DNa02 L | -297 |
| AOTU019 L, 10070 | DNa02 R | -289 |
| AOTU025 L, 516361 | DNa02 L | +205 |
| AOTU025 R, 519926 | DNa02 R | +196 |

Counts come from MaleCNS v1.0; transmitter-to-sign conversion is the existing
model convention. Counts are not measured conductances. Templates expressed
in an ipsilateral coordinate frame are mirrored to construct the opposite-side
input, under an explicit population-symmetry assumption. For physical right
DNa02, the uncalibrated prediction is
`196*m025(theta,d) - 289*m019(-theta,-d)`; for left, use the actual left matrix
entries and reversed physical coordinates. If physical side cannot be assigned,
average the two canonical predictions with equal hemisphere weight and label
the bilateral population assumption. Do not choose the side that fits best.

Output is signed contact-weighted change, not spikes/s until calibration. Fit
one nonnegative common gain, no intercept, per held-recording fold on all other
eligible DNa02 recordings. Weight recording means equally, then stimulus cells
equally. Fit no time constant, delay, independent pathway gain, field shift,
rectifier or motor conversion. This is a pulse-mean linear response hypothesis;
it does not simulate spiking or predict millisecond latency.

Use the same templates, target coverage and fitting budget for these controls:

| Control | Purpose |
| --- | --- |
| Equal-strength signed bridge | Same inhibitory/excitatory signs and crossover/ipsilateral routes; split each destination's total absolute contacts equally between its two inputs. Tests whether particular contact strengths help beyond simple signed routing. |
| Magnitudes exchanged | Exchange inhibitory/excitatory magnitudes at each destination, preserving sign, route and total absolute weight. Tests the frozen balance. |
| Same-side inhibition | Move AOTU019 inhibition ipsilaterally, keeping magnitudes and AOTU025 routes. Tests crossover architecture separately from strength. |
| Bridge removed / zero evoked | Establishes whether the selected bridge helps at all. |
| Constant evoked | Training-only mean with the same one-scalar budget; prevents calling mean response prediction a circuit success. |

There are four selected bridge edges; do not manufacture 32 nominal shuffles
from a tiny matrix or count duplicate controls as independent circuits.

Primary metric: average recording-level RMSE of trial-averaged stimulus-cell
evoked rates. Require intact >=5% better than equal strength and constant, with
strict wins in >=60% of eligible recording units against both. Require the
95% paired recording-bootstrap interval for intact-minus-equal-strength error
to remain below zero (2,000 resamples, seed 20261009); this is recording-level
uncertainty, not animal/population inference when independence is unknown.
Report all controls, direction-specific residuals and coverage. The 5%/60%
thresholds are project practical criteria, not biological laws. Do not lower
them when there are only eleven files. Record source-template uncertainty as
a separate sensitivity using recording resampling, without selecting a favorable
template or changing the primary fit.

## Decision and stopping rule

If metadata/coverage fails: stop at Phase A, state the missing constraint, and
do not build a new model to hide it. If intact fails Phase B: retire this
selected linear bridge-prediction candidate, preserve the anatomical route,
and do not begin a gain/delay/threshold search. If equal strength ties or wins:
report that the particular counts add no demonstrated predictive value here.

If it passes: report a population-level compatibility result for a smaller
downstream link, with omitted-input and cohort limitations. The next question
would be independent perturbation evidence or a genuinely fresh stimulus/state
comparison. It does not automatically authorize Godot integration or restart
the retired pixel-to-LC10a rule.

**Execution recommendation:** Luna Max for Phase A; the audit is tightly scoped
and its pass/stop outputs are explicit. Sol medium for interpreting compatibility
gaps and freezing Phase B. Do not launch another open-ended goal or overnight
replay from this document.

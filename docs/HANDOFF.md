# FlyTest handoff

## 2026-10-02: repeated-response audit complete; production preserved

Read [result](../fly-creature/docs/pursuit_repeatability_result.md) and
[frozen protocol](../fly-creature/docs/pursuit_repeatability_protocol.md).
Branch `experiment/aotu-response-repeatability`; protocol `8a074db`, initial
implementation `3805c9a`. New offline `pursuit_repeatability.py` reads the same
four archives, excludes the known duplicate and scores baseline-subtracted
pulse means in the old quiescent class. Group speed/direction/11.25-degree
center cells, require four trials and three other recordings. Hold whole
trials; all comparisons score 34,554 common trial-cells from 35,484 quiet
pulses / 69 recordings. Equal cell/trial/recording scoring; no physical-side
or causal P1 assumption.

P1 same-recording templates beat blind means by 14.3%/16.7% and other-recording
templates by 11.0%/10.4%; NoP1 same-recording templates lose to blind means.
Fixed training-only residualized ridge 0.1 using four pre/on forward/absolute
angular covariates adds 4.47%/0.85% P1 held-trial RMSE reduction. Quiescent
does not mean immobile: 38.0%/39.6% of P1 pulses contain some above-threshold
forward motion; turning is unconstrained. Large residual trial variation is
not all noise, and these predictors are not a noise ceiling. Motor association
can reflect neural output/shared causes, not an input justified for production.

Two runs reproduce report, observations/folds/recording CSVs and PNG bytes.
`tools/check_repeatability.py` independently checks all 34,554 saved means,
weights, count/exclusion rules and recording losses; augmented least squares
checks motor fits for one held trial in each of 69 recordings. Maximum
mean discrepancy 5.33e-15, motor-fit discrepancy 4.18e-14. Raw inputs and
old extraction/evidence preserved. No unit/gameplay suite ran. Full observations
and folds ignored; compact report, recording table, checks and figure tracked.

Next: matched population-tuning comparison of frozen anatomy, simple spatial
and empirical other-recording templates, same pulse-mean objective, coverage,
calibration budget and recording holdouts. Diagnose mean visual field shapes
before a sensory rewrite. Sol medium design/interpretation; Luna Max once fixed.

## 2026-10-02: causal response-memory diagnostic complete; benefit gate failed

Read [result](../fly-creature/docs/pursuit_temporal_result.md) and
[frozen protocol](../fly-creature/docs/pursuit_temporal_protocol.md).
Branch `experiment/aotu-temporal-response`; protocol checkpoint `ac50707`,
implementation checkpoint `5b82713`. Production and prior evidence unchanged.
New `pursuit_temporal.py` replays native full trials and visual history, adds
unity-gain first-order memory (0/40/100/200 ms) and lag (0/40/80 ms nominal;
0/40.5/79.5 ms realized), with the fixed 50 ms observation filter.
Pooled model hemispheres primary; all-left/all-right sensitivities. Known
numeric duplicate excluded from both archives prospectively. 69 recordings,
35,484 quiescent pulses (7,450 NoP1; 28,034 P1); all 65,416 accepted and 158
rejected intervals in retained recordings accounted for, no singleton drives.

Baseline anatomy, 32 seeded wiring controls, simple spatial and zero-evoked
predictors get equal timing/gain allowances. Evoked trace objective differs
from prior raw pulse-mean fit. Nested recording CV chooses timing exclusively
within outer training; one nonnegative gain, no intercept after recorded
pre-stimulus baseline subtraction. Native simulation/filtering, every-seventh-
sample scoring (10.5 ms). Speed transfer excludes entire held recording.
P1 pooled 019 RMSE 12.4402 to12.3393 (0.81%; 13/24 improve), 025 15.2460
to15.2039 (0.28%;13/22). Both fail frozen 5%/60% criteria. Simple improves
0.62/0.25%; anatomy-over-simple advantage only0.44/0.30%. Wiring ranks7/32
and32/32. Hemisphere sensitivity does not rescue it; NoP1 negligible gain.
Slow-to-fast helps1.39/0.60%; fast-to-slow worsens0.97/0.48%.
Examples improve some onset/peak shapes; post-offset persistence remains.
Do not promote memory into Godot or expand the grid based on these results.

Two independent complete runs reproduce report, all three CSVs and PNG bytes;
43,470 full fold rows ignored. Filter-order/recurrence/direct-moment checks,
archive MD5/member CRC, count accounting, saved-fold gain/timing/count checks,
source/protocol and frozen production/input hashes pass. No unit/gameplay
suite ran. Compact report/table/ranks/checks/figure tracked; full report retains
all shuffle timing distributions. Source unchanged after validated runs.
Next: design a response-repeatability/residual-variation audit for repeated
same position/direction/speed, separating within/across-recording variation
and auditing continuous forward/turning covariates in coarse quiescent pulses.
Motor correlation may be neural output/shared cause, not automatically an
input. This distinguishes the prediction target before another sensory rewrite.
Sol medium for design/interpretation, Luna Max for a fixed implementation.

## 2026-10-02: frozen P1 physiology comparison and data-quality sensitivities complete

Read [result](../fly-creature/docs/pursuit_p1_result.md) and
[protocol](../fly-creature/docs/pursuit_p1_protocol.md). Branch
`experiment/p1-aotu-responses` preserves production and old NoP1 evidence.
Two extra public archives (2.29 GB), MD5/CRC verified, contain 47 recordings;
55,252 accepted pulses and 141 rejected intervals fully accounted for.
Same native-position replay, strata, 68 variants, filter, training-only affine
calibration and equal-recording LOO. P1 baseline beats constant by 7.60/7.33%
(019 quiet/running) and 5.67/2.97% (025); advantage over simple spatial is only
1.01/0.28% in quiescent groups, negative in primary running groups.
Footprint effect remains negligible. NoP1 CSV/PNG/numerics exactly preserved;
P1 complete repeat CSV/PNG/report bytes identical; model/input hashes unchanged.

Important audit: all 24 NoP1 names overlap P1, with 23 additional P1 names.
019/2023_06_15_fly03 has identical 40 trials across all seven numeric variables
in both archives, despite differing MAT bytes; no other exact numeric trial
matches found. Eleven assigned-side labels disagree (019=4, 025=7).
Author loader saves trackLR in spreadsheet order, not explicitly filename order;
tracker sheets absent. Already-ipsilateral-positive measurements remain fixed.
Primary model hemisphere assignment is provisional, including old NoP1 result.
Do not infer randomized pairing, causal P1 gain or verified side-specific fit.
Four pre-fit hemisphere scenarios and post-hoc duplicate exclusion preserve
broad spatial benefit/small anatomy-over-simple benefit; some finer wiring
ranks shift substantially. Metadata sensitivity summaries exactly reproduce
primary summaries. Full diagnostics ignored, compact evidence tracked.

Inspected time courses show measured persistence/delayed shape missing from
static adapters. Next: design a bounded causal temporal-response hypothesis,
exclude known duplicate prospectively, handle hemisphere/condition uncertainty,
freeze training-only choices, compare held-out evoked/time errors with equally
calibrated static anatomy and simple controls. Better provenance remains needed
for biological state/side claims. Sol medium for design, Luna Max for scoped
implementation after protocol. No production promotion/fresh pursuit paths;
no unit/gameplay suite ran in this task.

## 2026-10-02: measured NoP1 AOTU benchmark implemented and evaluated

Read [result](../fly-creature/docs/pursuit_physiology_result.md) and
[protocol](../fly-creature/docs/pursuit_physiology_protocol.md). Branch
`experiment/measured-aotu-responses` preserves all production settings.
Two public NoP1 archives (499 MB) pass MD5; 24 recordings yield 13,038 pulses,
25 rejected intervals fully accounted for. Optional h5py/scipy readers restore
MATLAB dimensions; side metadata and already-mirrored measurements are explicit.
LOO by recording/type/state with training-only, equal-animal affine calibration.
Frozen baseline/footprint and 32 shuffles each; simple fixed spatial control;
post-hoc intercept-only diagnostic labelled. Footprint has negligible effect.
Quiescent AOTU019 baseline error 7.0391 vs constant 7.0395; AOTU025 9.2049 vs 9.3756.
Running AOTU019 constant beats anatomy; simple spatial controls are close.
High shuffle ranks do not establish substantial empirical or pursuit benefit.
Stimulus duration gate was corrected before fitting from actual staircases;
the model still lacks finite-object encoding and intrinsic temporal dynamics.
Two complete evaluations reproduce CSV/PNG bytes and numerical report fields;
filter and independent error arithmetic agree. No unit/gameplay tests ran.
Raw datasets/full CSVs ignored; compact JSON/table/plots tracked. Next: same
frozen comparison on P1 recordings, auditing state/protocol differences before
another kernel revision (Sol medium). No fresh pursuit paths consumed.

## 2026-10-02: measured sensory research complete; empirical benchmark next

Read the refreshed [sensory review](../fly-creature/docs/lc10a_visual_input_research.md)
and [sample/source audit](../fly-creature/docs/evidence/pursuit_sensory_source_audit_v1.json).
Branch `research/pursuit-sensory-constraints` changes documentation only.
LC10a primary studies constrain finite object size, direction and state, not
per-MaleCNS Gaussian widths. Schretter's RF-labelled matrices are object-size
matrices; the public Fig3 workbook omits its calcium-size panel. Collie's actual
AOTU recordings are accessible at Zenodo version 15474938 (concept 15474937).
Each NoP1 archive contains 12 recordings plus side metadata. Two smallest actual
recordings downloaded with ZIP CRC32 checks and local SHA256, loaded in existing
portable Octave; 1.5 ms samples, seven int_* signals, intentional position NaNs.
Full archives/checksums and representative response estimates remain untested.
Source preprocessing already mirrors left data; source “peak” summaries use
pulse means; Gaussian 35/65 centers and 20-degree spread are fixed predictors.
Production/source/data unchanged; no physiological fit, behavioral replay or
fresh validation ran. Next: offline measured AOTU pulse-response benchmark with
matched stimuli/state, raw units, animal-level holdouts and equally calibrated
controls (Sol medium). Locate the empirical mismatch before an input rewrite.

## 2026-10-02: offline column-footprint candidate complete, not promoted

Read [result](../fly-creature/docs/pursuit_footprint_result.md) and
[protocol](../fly-creature/docs/pursuit_footprint_protocol.md). Branch
`experiment/pursuit-column-footprints` preserves production settings and old map.
New packaged data retain 979 cell-column entries (517 coordinates) for the same
164 directly mapped LC10a; 111 fallback cells are exactly unchanged. Source
derivation reproduces saved moments and hashes; offline NumPy adapter preserves
fixed type peaks, ELU, edges, gain, aperture and motor timing. Signed footprint,
signed mean and recentered spread controls separate position from spread.
Fixed-fly fields are bounded, unclipped and retain 42.5-degree AOTU peak split,
beating 32/32 spatial shuffles. Right 105-degree turn rises only 14.36 to 15.11
degrees/s. Primary footprint slightly worsens all five behavioral aggregates;
smooth-path wiring rank falls 15/32 to 2/32. No promotion or fresh validation.
Left 105-degree AOTU025 drive remains 90.1% fallback, a significant coverage limit.
1,496 replays; all baseline/shuffle metrics reproduce; 112 tests, release hashes,
repeat data/report/plot bytes and standalone source-copy checks pass. Next:
research measured LC10a/AOTU sensory constraints before another rewrite (Sol medium).
Do not blindly widen kernels, renormalize peaks or chase the source-image curve.

## 2026-10-02: response-contribution investigation complete

Read [response result](../fly-creature/docs/pursuit_response_result.md) and
[protocol](../fly-creature/docs/pursuit_response_protocol.md). Branch
`experiment/pursuit-response-diagnosis` leaves production unchanged. At right
105 degrees, adapted stationary signal 0.221 versus reference 0.870. Canonical
output edges recover only 0.010; linear activation reaches 0.347. Raw normalized
right AOTU025 field is 0.343 versus reference 0.772: the main gap precedes
decoding. Input symmetrization reduces mirror mismatch 0.288 to 0.036; output
symmetrization does not help that metric. Per-channel normalization/linear
activation help four replay families but regress fast sweeps; no promotion.
The reference's heatmap pipeline assigns anatomical image extent linearly to
-15..165 degrees, while our model uses registered centers and fixed 18-degree
Gaussians. Neither is measured physiology. Saved upstream spreads are ignored
by runtime, but most are smaller than 18 degrees; do not blindly replace width.
176 replays; prior baselines reproduce exactly. 108 tests, 17 source hashes,
release verification and byte-identical JSON/CSV/PNG pass. Next proposed build:
offline upstream-column footprint input, preserving kernel/fallback uncertainty,
fixed-fly checks first (Sol medium). Fresh validation remains reserved.

## 2026-10-02: matched retinal reference benchmark complete

Read [result](../fly-creature/docs/pursuit_retinal_result.md) and
[protocol](../fly-creature/docs/pursuit_retinal_protocol.md). Branch
`experiment/matched-retinal-reference` preserves playable settings.
22 mirrored cases, 71 variants, 1,562 comparisons. A 200 ms source-core override
matches a separate Eq6 recurrence exactly in four mirrored conditions; 450 ms
defaults remain intact. Matched models share warmup, queue, cap, visibility,
gain and rotation-only body conventions. Fast-sweep errors: reference 23.823,
adaptation 25.241; uncapping the reference does not help (23.847). Adaptation
is worse on stationary steps but better on slow sweeps and tested smooth paths.
Direction-on intact beats 15/32 shuffles on smooth paths; direction-off beats
32/32 but regresses other families. No change promoted. All 104 tests and
source/data hashes pass; reports repeat identically and 14 traces verify metrics.
Next: fixed-delay/gain response-curve contribution diagnosis (Sol medium), then
a bounded fix with fresh validation if justified. These paths are consumed;
do not claim exact paper parity or broad biological validation.

## 2026-10-02: final-paper timing audit and benchmark contract complete

Read [timing contract](../fly-creature/docs/pursuit_timing_contract.md).
Branch `experiment/pursuit-timing-contract` preserves production code.
The final paper is now readable from the authors' lab: it explicitly uses
200 ms steering feedback, distinct from roughly 40 ms visual-response latency.
The pinned author code still uses 450 ms history delay; its separate 200 ms
setting only shifts an analysis. Preserve that verified reference. The audit
checks 600 active/visible samples: total-200-ms sensory/motor splits 0/200,
40/160, 100/100 and 200/0 give identical commands. Redistribution is not a fix.
Actual queue timing and independent target speeds are recorded; the extra
body sample interval is an explicit endpoint convention, not a shortening fix.
Source hashes and compact audit evidence are saved. No controller or data
changed. Next build is the matched retinal reference benchmark specified in
the contract, with a separately labelled 200 ms article-method variant, fixed
gain/caps, wiring controls and reserved fresh validation. Sol medium fits
the comparison design/implementation. The benchmark above implements this contract.

## 2026-10-02: motion-rule diagnosis complete; no input fix promoted

Read [motion result](../fly-creature/docs/pursuit_motion_result.md) and
[protocol](../fly-creature/docs/pursuit_motion_protocol.md). Branch
`experiment/pursuit-motion-diagnosis` preserves the playground/runtime.
An offline diagnostic reproduces all 48 frozen stress cases and matches the
actual session tick for tick. Direction removal improves six hard cases by
11.0% but worsens supported aggregate error by 17.7%; history correction has
no hard-case effect. Zero motor delay cuts fastest error 12.050 to 5.851
degrees, but is an explanatory control, not a promoted biological setting.
Including self-motion matches retinal geometry and the source model.
Twelve fresh cases: intact mean 6.459 degrees, all pass the coarse envelope,
but intact beats only 1/32 shuffle aggregates. Position-only gets 6.218 and
beats 32/32 shuffles but does not qualify given prior regressions. The earlier
wiring advantage is motion-regime dependent. Two complete reports are
byte-identical; 24 traces/hashes/aggregates independently checked. 32 creature
and 69 lab tests and release verification pass. No production setting changed.
Next proposed work: review visual-response versus end-to-end motor timing
before another revision; Sol medium for the source/model distinction.

## 2026-10-02: interactive comparison playground implemented

Read [playground.md](../fly-creature/docs/playground.md) and
[architecture](../fly-creature/docs/ARCHITECTURE.md). Branch
`experiment/comparison-playground` adds a separate steering-only Godot scene.
P enters it from the existing creature demo; Esc returns. The user launcher
is `fly-creature/tools/run_playground.ps1`. Four independent bodies run
intact/disconnected activity and ordinary proportional steering with 200/0 ms
delay. Python owns this world's 10 ms ticks; Godot batches at most five via
threaded asynchronous HTTP, preserving prior-command body updates and queues.
Sequence validation/cache prevents duplicate advancement. Reset during an
in-flight request discards stale results. Presets/manual dragging, pause,
hiding, inspection, starting depth/heading and mirror controls are checked
through actual Godot execution. The preview is 1080p60, 8.05 seconds for
8.01 simulated seconds. Exact final states match direct Python replay.
28 creature tests, 69 lab tests, frozen stress checks and data verification
pass. Compact evidence is tracked; recordings/logs remain ignored. Frozen
neural controller, stress runner, protocol, map and graph are unchanged.
The playground is single-client, has no neural search/stopping/flight, and
may lag wall time under load. Inspecting another body does not restart it.

## 2026-10-02: frozen pursuit stress envelope evaluated

Read [the result](../fly-creature/docs/pursuit_stress_result.md) and
[protocol](../fly-creature/docs/pursuit_stress_protocol.md). Branch
`experiment/pursuit-stress-envelope` starts from the working Godot integration
`1d27daa`; protocol/runner were committed as `53d28d9` before results. The
controller and Godot are unchanged. Forty-eight mirrored cases include 36
supported tasks and 12 range/stationary-depth challenges. Intact meets the
envelope on 32/36 supported cases: 4.352-degree mean case error versus 22.509
disconnected, 4.918 calibrated matched-delay proportional, and 3.645 same
ordinary controller without delay. Intact beats all 32 shuffles on aggregate
and the median shuffle on 30/36 cases. It loses to median shuffles on some
fast/reversing paths. Fast motion and 105-degree starting headings fail the
error gate; the wide headings eventually recover. Nearby stationary targets
are walked past; unseen targets are not searched for. All dropout/reentry
cases recover, with no inactive turns or lookup clipping. Full repeat JSON
is identical; 96 traces checked independently. 22 creature tests, 69 lab
tests, and data provenance pass. These cases are now consumed evaluation
material. Next proposed work is a comparison playground; Sol medium is
recommended to preserve logical timing while integrating interactive controls.

## 2026-09-30: experimental Godot activity pursuit runs

Read [the integration report](../fly-creature/docs/godot_pursuit_activity.md).
The reviewed candidate is an opt-in `activity_v1` controller selected with
`B`; startup retains the earlier LIF controller. `C` compares disconnection.
Two actual graphics-enabled runs completed 800 exact 10 ms service ticks:
mean bearing error 2.350 degrees intact and 12.296 disconnected, matching
the prior offline harmonic result. Commands preserve the 200 ms queue.
HD 60 fps clips and full logs are ignored local outputs; compact evidence is
tracked. A rendered yaw sign mismatch was fixed and facing/travel alignment
is checked in every recorded tick. 18 creature and 69 lab tests pass, as does
release provenance verification. This is integration on an already evaluated
path, not additional generalization evidence. Synchronous HTTP can slow
rendering under load; all timing and input assumptions remain explicit.

## 2026-09-30: delay/center diagnosis passes offline review

Read [the result](../fly-creature/docs/pursuit_delay_result.md),
[frozen protocol](../fly-creature/docs/pursuit_delay_protocol.md), and evidence.
On `experiment/pursuit-delay-diagnosis`, a separate runner reproduces Step 4
and isolates delays and center encoding in 16 configurations, including
rotation-only controls. A 450 ms feedback delay causes large oscillations;
overlap alone does not fix them. The predeclared 0 ms visual-history / 200 ms
motor-effect / 15-degree total smooth-overlap candidate settles on both
mirrored steps. Six new paths give median error 2.373 degrees versus 11.033
original, 12.296 bridge removal, 5.698 direct rule and 8.567 playable LIF;
intact beats all 32 shuffles on aggregate mean. Gain robustness passes.
Final-second jitter remains below one degree in both step cases. This is a
model intervention, not measured timing, calibrated LC10a fields, or source
parity. Godot and frozen Step 4 remain unchanged. 15 creature tests, 69 lab
tests and data verification pass. Next is a separate review/integration
decision; these evaluation paths are no longer unseen.

The private GitHub origin is `silascroe/fly-test`; the prior workspace and
all existing branches were backed up. Dirty-worktree statements below are
historical snapshots, not the current state.

## 2026-09-27: pursuit Step 4 ran; do not integrate this candidate

Read the [frozen protocol](../fly-creature/docs/pursuit_step4_protocol.md),
[result](../fly-creature/docs/pursuit_step4_result.md), and compact JSON. The
v3 input map was combined with source-inspired delayed AOTU dynamics and the
selected v1.0 AOTU→DNa02 edges in a portable, offline adapter. On eight
new target paths, intact median error was 12.123° versus 18.526° with the
output bridge removed, and intact beat the median of 32 within-side wiring
shuffles on every path. But it failed the predeclared Step 5 gate: neither
step-hold case stayed within ±10° for one second, and a 20% lower gain moved
median error by more than the allowed 25%. Direct bearing and the playable
LIF controller both tracked better. The old source-reference parity check,
10 creature tests, 69 root tests, and original/working data verification
passed. Keep Godot on the earlier LIF controller. A revision needs a causal
explanation for the delayed oscillation and fresh held-out paths; do not tune
on these eight. The intentionally dirty worktree and raw data were preserved.

## 2026-09-26: pursuit Step 3 eye-map candidate; Step 4 may begin offline

Read the [registered eye-map result](../fly-creature/docs/pursuit_registered_eye_map_result.md)
and its compact audit. A public FAFB eye map was transferred using the
MaleCNS hex-to-p/q coordinate transform, without using the target AOTU
curves in the derivation. The packaged v3 candidate passes the fixed-fly
frontal/lateral field check on both sides; 500 within-side output-bundle
shuffles do not match its spatial split. This resolves the prior 45° versus
72° mismatch enough to start Step 4's bounded offline experiment. The
cross-specimen registration is not unique, and left-side branches mostly
depend on skeleton fallback. Carry nominal and declared one-column shifts,
test motion and held-out paths, and retain the hard-hemisphere input caveat.
The playable Godot/LIF controller remains separate and unchanged. Earlier
handoff sections below record the prior failed map and diagnosis.

## 2026-09-26: pursuit Step 3 field-gap diagnosis

Read the [diagnosis](../fly-creature/docs/pursuit_field_gap_diagnosis.md) and
its compact JSON before moving toward Step 4. The current AOTU025 mismatch
comes primarily from our assumed 5°–60° LC10a visual-angle conversion;
width, hemisphere, contact threshold, and cap controls do not fix it. A
broader mapping from the same upstream medulla coordinate improves the curve
shape but is not independently calibrated. Do not tune against the authors'
output peaks or enable the offline adapter in Godot yet. Obtain an
independent column-to-bearing calibration first.

## 2026-09-26: pursuit reference Step 3 mapping audit

Read [pursuit_mapping_result.md](../fly-creature/docs/pursuit_mapping_result.md)
and its compact JSON before attempting a new pursuit controller. All 16
published v0.9 downstream partner IDs persist with the same traced types in
v1.0, but the authors' curves already include connection-weight information.
The portable offline `pursuit_activity.py` projects the packaged v1.0 LC10a
position hypothesis through each selected edge once. AOTU019 shape is close
to the published aggregate; AOTU025 peaks at 45° versus 72° in the reference.
The map's retinal-angle scale is assumed, so this is not a validated
cell-level substitution. Keep both the verified aggregate reference and the
playable LIF controller separate. Next, resolve the AOTU025 visual-field
mismatch before behavioral evaluation; do not tune the motor gain to hide it.

## 2026-09-26: pursuit reference Step 2

The offline Python population reference is in
`fly-creature/src/fly_creature/pursuit_reference.py`. The pinned authors' core
running in portable GNU Octave and the Python version match to floating-point
precision across static responses and all three direction-selectivity step
conditions, including a shared nonzero perturbation check. See
[pursuit_reference_result.md](../fly-creature/docs/pursuit_reference_result.md)
and compact evidence JSON. The MATLAB low-pass noise filter and full 20,000-run
published aggregate were not reproduced. In a 120° sample, the authors'
settling helper reports success where a true consecutive one-second stay
does not occur; both metrics are retained. Our tracked comparison harness is
under `fly-creature/tools/pursuit_reference_octave/`. The authors' code/data
and raw traces stay ignored under `fly-creature/outputs/research/`. Playable
Godot and MaleCNS v1.0 LIF steering remain unchanged. Next: map source v0.9
fields/weights to our v1.0 circuit without double-counting synapses.

## 2026-09-26: published pursuit reference Step 1

The pinned source, file hashes, MaleCNS table audit, exact author-code step
protocol, and comparison rules are in
[pursuit_reference_contract.md](../fly-creature/docs/pursuit_reference_contract.md).
The clean authors' clone is ignored under `fly-creature/outputs/research/`;
their source/data were not copied into tracked runtime files. Source revision
`65d72773121ffe148b56b8ba4f594a7a51c51789` uses MaleCNS v0.9-derived
response tables, while our creature's graph uses v1.0. No MATLAB/Octave
runtime or original numerical trace was available. The code's settling-time
helper counts separate visits to the target band cumulatively despite its
continuous-stay description; keep source parity and corrected metrics
separate. Playable behavior is unchanged.

## 2026-09-26: pursuit strategy reassessment

Read [pursuit_reassessment.md](../fly-creature/docs/pursuit_reassessment.md)
before another visual-input experiment. The next recommendation is to
reproduce the authors' released activity-based pursuit reference and reconcile
it with our MaleCNS circuit, rather than invent another LC10a motion filter.
Their repository contains MaleCNS v0.9 analysis as well as the older female
work; exact response-table provenance and v1.0 correspondence remain open.
Our generic LIF parameters are uncalibrated, and beating an exact-bearing
software controller is not a necessary biological acceptance criterion.
This was research only; no replacement model or new performance result exists.

## 2026-09-26: fixed-charge local LC10a motion candidate

The [offline local-motion experiment](../fly-creature/docs/local_motion_experiment.md)
redistributes half the existing visual current toward LC10a cells whose
modeled receptive fields the target is entering. Total side current is
unchanged. Fixed-fly pulses confirmed exact current matching, but AOTU019
showed no desired outward-motion preference; inward response was larger in
seven of eight paired settings. On five new target paths, mean bearing error
was 10.775° versus 10.297° for position only, 9.195° for playable whole-side
input, and 8.113° for a direct controller. It beat the median of 12 wiring
shuffles on all five paths, but failed the predeclared promotion gate. The
candidate stays offline; the new optional per-cell input override does not
change Godot or service defaults. Code and compact JSON are under
`fly-creature/`. Preserve the intentionally dirty worktree.

## 2026-09-26: fixed-fly DNa02 firing sensitivity result

The [fixed-fly firing experiment](../fly-creature/docs/fixed_fly_dn_firing.md)
uses published 22.5° object-pulse spans and 25/75°/s speeds with the selected
MaleCNS route and upstream-derived LC10a map. At original LIF settings,
full-strength moving input produced zero DNa02 spikes in all 16 moving trials
per input type. Multiplying only the four AOTU-to-DNa02 edge currents by 2 or
4 still produced none without tonic drive. An *unmeasured* symmetric tonic
DNa02 drive of 16 or 20 current-equivalent mV yielded a bridge-dependent
toward-side firing bias on all moving trials, but the position input drove
static objects too, and the motion gate showed no consistent inward/outward
preference. This is a sensitivity result, not a calibrated spiking model.
Code, compact JSON, and report are under `fly-creature/`; playable Godot and
neural service defaults remain unchanged.

## 2026-09-26: separate visual-input and steering-readout audit

The [paired offline audit](../fly-creature/docs/input_readout_audit.md) replays
the upstream position input and speed-sensitive input on identical direct-rule
trajectories. The motion rule cuts the mean dimensionless LC10a input-strength
factor from 0.1963 to 0.0955, and AOTU019 spikes from 855 to 286 across five
paths. The available
DNa02 voltage bias never points the wrong way on the 696 eligible sampled
frames, but becomes zero much more often (337 to 576 frames). In separate
closed-loop trials, position versus motion under the unchanged voltage decoder
gives 11.428° versus 17.102° mean bearing error. A spike-only DNa02 readout
cannot turn because this selected LIF model produces zero DNa02 spikes; both
input versions then score 26.849°. Keep the playable Godot behavior unchanged.
The audit code and compact JSON live entirely under `fly-creature/`.

## 2026-09-26: upstream LC10a map and motion-input decision

The [latest offline report](../fly-creature/docs/visual_motion_experiment.md)
uses MaleCNS medulla-column inputs to orient 275 LC10a positions independently
of the selected AOTU outputs. Direct upstream input covers 248 cells; 164 have
at least three mapped incoming column edges, and 111 use skeleton-based
fallback calibrated from those inputs. The 5°–60° rank scale is still a
model assumption. A fixed, magnitude-only motion feature suppresses static
responses but does not reproduce measured direction preference. On the five
repeated target paths, mean pursuit error was 17.102° with that motion input,
versus 9.903° for the current playable input and 9.088° for a direct rule.
It beat the median shuffled wiring but failed the predeclared promotion gate.
The packaged v2 map, derivation tool, experiment code, and compact JSON are
under `fly-creature/`; Godot and neural service defaults remain unchanged.
The deliberately dirty worktree and raw Feather release were preserved.

## 2026-09-26: fixed-fly visual pathway probe

The [pathway report](../fly-creature/docs/visual_pathway_probe.md) now answers
why the first anatomical input underperformed. With a fixed fly and matched
current, it creates a coarse AOTU019 frontal / AOTU025 lateral response split;
uniform whole-side input gives flat angle responses. The anatomical input
still produces less DNa02 voltage bias under the fixed decoder in all 48
probe settings. Static objects drive it, and inward/outward sweeps do not show
a consistent frontal AOTU019 direction preference. The report links two PNG
chart previews, their SVG originals, compact CSV/JSON summaries, and the
reproducible command. The Godot
default and other creature behaviors remain unchanged.

## 2026-09-26: LC10a anatomical input experiment

The long-term Fly Creature direction is now in `fly-creature/README.md`:
build sensory-to-action pathways whose particular MaleCNS wiring has a
demonstrable role, with simulator assumptions and controls explicit. The
[first per-cell input experiment](../fly-creature/docs/visual_input_experiment.md)
derives 275 provisional visual centers from official MaleCNS LC10a SWC
geometry. Raw skeletons are ignored under `fly-creature/outputs/`; a compact
reproducible map is packaged within the creature. Offline, the anatomy input
beat all 12 within-side wiring shuffles on ten paths, but lost to both the
existing uniform input and a direct-bearing controller on all five new paths.
The playable input was not changed. See the compact result JSON and the report
for exact methods, scores, and the cross-dataset visual-field caveat.

## 2026-09-26: pursuit trust audit

The current Fly Creature pursuit default remains intact. The read-only
[audit](../fly-creature/docs/pursuit_trust_audit.md) compares six active target
paths, six input strengths, and three world-step intervals with bridge removal,
a side-swapped bridge, and a direct-bearing controller. Its compact results are
at `fly-creature/docs/evidence/pursuit_trust_audit_v1.json`. The selected
281-cell/366-edge circuit was regenerated byte for byte from the working
MaleCNS release; all working Feather files still match the originals. None of
the 275 LC10a annotation rows has optic-lobe hex coordinates filled in, so the
per-cell visual assignment remains unresolved. The
[primary-source review](../fly-creature/docs/lc10a_visual_input_research.md)
records the supported and unsupported inferences. A short Godot 4.7 headless
run reached the Python service and produced a nonzero pursuit turn. The audit
supports modeled wiring dependence, not a unique advantage over a direct
tracker or a biological claim.

## 2026-09-26: working Fly Creature pursuit slice

The newest **uncommitted** milestone is in `fly-creature/`, separate from the
old arena described below. A moving green target now drives an engineered
left/right LC10a input into a compact 281-neuron, 366-edge MaleCNS
LC10a→AOTU019/AOTU025→DNa02 route. The Python LIF model returns the DNa02
voltage difference; an explicit software readout turns the walking fly in
Godot. Press `V` in the interactive scene. `C` restarts with the
AOTU→DNa02 steering bridge removed, yielding straight walking under the same
target script. The preexisting jump pathway retains its former diagnostic
result (first intact jump frame 24, none with its circuit disconnected).

Read `fly-creature/docs/pursuit_milestone.md` for exact input, model, motor
assumptions, three closed-loop trajectory comparisons, individual AOTU output
ablations, and the next loop.
Eight-second 1280×720/60 fps captures are local ignored artifacts at
`fly-creature/outputs/pursuit/pursuit_intact.mp4` and
`fly-creature/outputs/pursuit/pursuit_disconnected.mp4`. The packaged compact
circuit and all runtime imports live under `fly-creature/`; the parent Feather
release is read only during development. The Godot capture was made with the
workspace portable build in `tools/godot/4.7/` using the Windows compatibility
renderer. Sandbox-only launches failed while creating Godot user data; the
graphics-enabled workspace-copy launch succeeded. Keep the deliberately
mixed worktree intact; do not broadly
stage, clean, or reset it.

The following 2026-09-24 handoff remains as the historical lab snapshot.

Updated 2026-09-24 for the next Codex chat.

## Current snapshot — start here

The latest committed brain milestone is `4e96f78` (`Test competing cues with
paired arena decoders`) on `experiment/competitive-decoder-replay`. The
worktree is intentionally not clean. Before this handoff update, it already
contained uncommitted presentation work in `.gitignore`, `arena3d/main.gd`,
`docs/decisions.md`, `arena3d/assets/`, and `artwork/`. Do not reset, clean,
switch branches, or stage unrelated work without checking with the user. This
handoff and the new Blender decision entry are the only workspace edits made
for this chat-boundary preparation.

The latest visual work is a standalone procedural male fruit-fly study. Open
`artwork/blender/realistic_fly_hero/male_drosophila_hero.blend` in Blender;
the full-body and close-up renders are under
`outputs/blender/realistic-fly-hero/`. Its builder and Blender integration
test sit beside the scene. It is not wired into Godot and does not change the
connectome, simulator, or the existing Decision Chamber / earlier fly scenes.
This is a detailed procedural CG model, not a specimen scan or photoreal asset.

The visual checks passed: 4 hero-scene Blender tests, 3 tests for the earlier
realistic-fly scene, all 69 project tests, and `flytest.verify` (original and
working connectome copies still match). The hero scene was rendered at
2048×1536, 96 Cycles samples, using the local Blender 5.2.2 build and the GTX
1070 OptiX device. `git diff --check` reports only the checkout's existing
line-ending warnings.

For the next incremental project step, use the decoder-competition results
below as the brain-work starting point; a small set of matched timing/geometry
controls is more informative than adding neurons. Alternatively, continue
visual modeling only after choosing a specific target. Do not assume this
handoff authorizes either path by itself.

## What this project is

FlyTest is a local-first, inspectable experiment around the official FlyEM
Male CNS v1.0 release. The connectome wiring and annotations are real release
data. The retina, LIF parameters, memory, motor mapping, point-mass body, and
3D world are explicit simulator scaffolding. This is not a complete biological
fly or a validated behavior model.

Never edit `data/original-data/`. Keep the original and working copies
byte-identical. Do not commit Feather files, backups, `.venv/`, Godot caches,
or bulky movie/timestep artifacts.

## Current milestones

The browser baseline remains intact:

- `GET /api/run` is the regression control.
- `POST /api/arena/run` is schema version 2 and supports stages 54, 100, 250,
  and 1,024, moving lights/threats, the 9x5 retina, touch priority, descending
  population votes, memory, causal traces, and deterministic replay digests.

The standalone `arena3d/` project is now a live Godot client rather than a
replay viewer:

- `POST /api/arena/session` creates a persistent Python neural session.
- `POST /api/arena/session/{session_id}/step` accepts Godot's current body,
  light, and threat state and returns retina features, persistent LIF spikes,
  memory, descending votes, the chosen action, and the next deterministic
  state.
- Godot applies the returned action and sends the resulting world state back
  on the next tick.
- The scene defaults to stage 1,024. `SPACE` pauses; `R` creates a fresh neural
  session; right-drag orbits; the mouse wheel zooms.

The first embodied world slice is now present:

- scripted demo requests include two explicit static obstacles; sandbox
  requests remain obstacle-free unless they provide an `obstacles` array;
- Python resolves the circular toy body with swept circle/AABB contacts and
  returns requested versus actual motion, collision IDs, boundary contacts,
  and obstacle touch features in every frame;
- Godot renders matching `StaticBody3D` shapes, probes the next move with a
  `ShapeCast3D`, and shows a causal HUD from world contact through sensory
  features, input currents, spikes, descending votes, and action;
- set `FLYTEST_ARENA_ENDPOINT` to point the Godot bridge at a non-default local
  server during a smoke test.

This 3D lab is intentionally standalone. It is not part of the public website
yet, and no Cloudflare configuration is needed for it.

The first bounded arena diagnostic now exists as
`src/flytest/beacon_approach.py`. It runs a static-beacon, no-threat,
no-obstacle sandbox replay against the existing stage-54 visual context and
writes compact `report.md`, `summary.json`, and `trajectory.csv` artifacts.
Its deliberately modest pass criterion is a reduced minimum distance that
also crosses the configured threshold; it is not a sustained tracking or
biological-behavior claim.

The second bounded arena diagnostic now exists as
`src/flytest/wall_blocking.py`. It places a static beacon behind one explicit
toy wall, reuses the same stage-54 connectome-backed runtime, and writes the
same compact causal artifacts. The real 14-frame replay passed with two
blocked frames, wall collision and obstacle-touch evidence, and no crossing of
the wall's front-face limit. This is collision evidence for one fixed replay,
not biological obstacle avoidance.

The third bounded arena diagnostic now exists as
`src/flytest/threat_crossing.py`. It runs one moving collision-triggered threat
and a no-threat control at stages 54, 250, and 1,024, then checks two nearby
threat geometries at 1,024 nodes. It records first threat sensing, first touch
output spike, and first touch-sourced escape latency. The real result is in
`outputs/diagnostics/threat-crossing/`: the baseline response was present at
all three stages, with escape latency of 6 ms, 2 ms, and 2 ms respectively;
both nearby geometries also responded at 2 ms. This remains narrow simulator
evidence, not biological predator avoidance or broad generalization.

## Important files

- `src/flytest/arena_simulation.py`: arena configuration, retina/world model,
  batch replay, and stateful `ArenaSession`.
- `src/flytest/arena_circuit.py`: staged graph runtime and named sensory/output
  populations.
- `src/flytest/visual_simulation.py`: public server, `/api/run`, arena batch
  endpoint, and live session endpoints.
- `arena3d/main.gd`: 3D lab, world rendering, live tick loop, HUD, trail, and
  retina display.
- `arena3d/arena_bridge.gd`: Godot HTTP transport for the live loop.
- `src/flytest/beacon_approach.py`: bounded beacon diagnostic and compact
  artifact writer.
- `src/flytest/wall_blocking.py`: bounded wall-blocking diagnostic and compact
  artifact writer.
- `src/flytest/threat_crossing.py`: stage-comparison and geometry-matrix threat
  diagnostic with compact causal artifact writer.
- `tests/test_visual_simulation.py`: arena, staged graph, retina, memory, and
  live-session coverage.
- `docs/decisions.md`: provenance/model-boundary decisions.

## Run it again

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m flytest.visual_simulation --host 127.0.0.1 --port 8767
```

The first request for a larger graph stage can take a while while the official
working data is scanned and cached. The live Godot bridge has a 120-second
request timeout for that reason.

The browser and Godot live lab now use the exact 1,024-node unified stage by
default. The API remains stage 54 by default for compatibility; the smaller
250-node unified stage remains available as a control.

Use the installed Godot executable with the Windows compatibility renderer:

```powershell
& 'C:\Users\ringd\CodexProjects\Godot-GaulRTS\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe' --path 'arena3d' --display-driver windows --rendering-method gl_compatibility --audio-driver Dummy
```

The bundled portable editor is under `tools/godot/4.7/` and is ignored by
Git. In this environment the compatibility renderer is the reliable path;
headless/default rendering can fail for environment reasons unrelated to the
scene scripts.

## Last verification

The last completed checks were:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flytest.verify
git diff --check
```

Result: 69 tests passed; provenance verification passed; `git diff --check`
reported only line-ending warnings. The real stage-54 beacon-approach replay
also passed: the body went from 2.828 m to a minimum of 1.416 m, crossing the
1.5 m threshold in a 30-frame causal trace. Godot script parsing passed, and a
real compatibility-renderer live capture completed against a fresh Python
stage-54 server. The headless Godot runner still crashes in this environment
while trying to write its `user://` log/settings files; that is an environment
limitation, not a scene parse error.

The real stage-54 wall-blocking replay also passed: 14 frames produced two
blocked frames, a wall collision, obstacle-touch causes, and a maximum body
center x of 0.635 m against a 0.650 m front-face limit. Its compact artifacts
are under `outputs/diagnostics/wall-blocking/`.

The real 1,024-node acceptance run also passed. It selected exactly 1,024
unique nodes and 24,807 induced edges (512 touch nodes plus 512 vision nodes),
completed 24 causal frames, produced the same replay digest twice, and stepped
the live session twice. The initial graph build plus replay took about 88.15 s;
the cached replay took about 44 ms, and the two live steps took under 1.3 ms
each. Compact evidence is under `outputs/diagnostics/arena-1024/`.

The real threat-crossing comparison also passed structurally and detected a
touch-linked escape response at stages 54, 250, and 1,024. Each no-threat
control produced zero escape actions; both 1,024-node geometry variants also
met the response criterion with 2 ms escape latency. Compact evidence is under
`outputs/diagnostics/threat-crossing/`.

The stage-1,024 decoder-attribution follow-up is under
`outputs/diagnostics/decoder-attribution/`. Run it with
`.\.venv\Scripts\python.exe -m flytest.decoder_attribution`. It keeps the live
touch-priority decoder and compares a strongest-vote shadow decoder on the
same recorded neural vote vectors in one no-threat and one crossing replay.
The control had no touch/visual vote competition. The crossing had one
competitive frame: at 3 ms a touch escape had no visual opposition; at 4 ms
vision voted 6 against touch's 1 and the live action was a memory-sourced
visual turn. Thus the priority rule was *vote-level sensitive* at 4 ms but
did not cause the observed escape. The shadow readout is not a second
closed-loop flight path. The next causal question needs a scene that produces
simultaneous competing votes on an escape-eligible frame, not more neurons.

That follow-up is `outputs/diagnostics/decoder-competition/`; rerun with
`.\.venv\Scripts\python.exe -m flytest.decoder_competition`. A bounded
0-4 ms activation sweep found that starting the threat at 2 ms puts touch
vote 3 against visual vote 6 at 4 ms, before escape cooldown. Two genuine
closed-loop stage-1,024 replays use the same graph, initial state, and world;
only the batch decoder policy changes. Their first four frames and neural
inputs/votes at the fork match. Touch priority chooses `escape_right` at
4 ms; strongest-vote chooses `turn_left`. The no-threat control has no
escape, and the strongest-vote run matches its action/body trace for all
12 frames. Later trajectories diverge because the different actions change
the body's path; they are not matched-input comparisons. This is one
designed scene, not biological or robust avoidance. Live Godot decoding
retains the existing touch-priority default.

## What is deliberately unfinished

The live session store is in-memory and local-only. Restarting the Python
server destroys sessions. The 3D body is still a simple circular point-mass
controller; there is no full character-body physics, flight dynamics, learning,
webcam input, or biological muscle model. Beacon approach, wall blocking, and
threat crossing are bounded evidence for three fixed scenarios plus a small
geometry matrix, and the 1,024-node scale target is validated as a runnable
graph/runtime workload rather than a behavior claim. The geometry result is not
a broad generalization study; the next useful work is to expand controls or
move to a more demanding circuit question, not add neurons merely for the
number.
The Python/NumPy backend has not been replaced; its measured costs remain
available for that later decision.

## Worktree note

The bounded beacon slice is committed as `8688590`, and the wall-blocking slice
as `0ec49d4`; both are fast-forwarded onto `main`. The old
`experiment/beacon-approach` pointer remains at `0ec49d4`, while `main` now
also contains the 1,024-node work. Do not reset or clean the tree blindly.

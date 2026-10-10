# Frozen matched population-tuning comparison

2026-10-02. Freeze before new prediction results. Offline target/shape
diagnosis; no production promotion, field retuning or new motor input.

Use the four checksum-verified motion-pulse archives, unchanged extraction,
known duplicate exclusion and canonical ipsilateral coordinates from the
repeatability audit. Primary P1; separate NoP1 sensitivity. Analyze types
separately, preserving uncertainty about physical sides and condition labels.
Use quiescent baseline-subtracted pulse-mean firing. Match nominal speed,
direction and 11.25-degree center bins; aggregate within trial-cell. Retain
recording/cells with at least four trials. Score the exact previous common
coverage: held cells present in at least three other eligible recordings.

## Predictors and calibration

Freeze existing static anatomy and simple spatial predictors. Anatomy pools
model hemispheres in canonical coordinates; direction rules, registered eye
map, projection, ELU, widths and overlap remain unchanged. Simple spatial
is the existing direction-independent Gaussian (peaks 35/65 degrees for
019/025, width 20 degrees). Replay actual full native trials, not snapped
positions, with existing rounding and the 50 ms Gaussian observation filter
truncated at 250 ms. Subtract native predicted pre-stimulus mean in
[-250,-100] ms and average the complete visible pulse. No response memory,
lag or temporal search is added.

Leave each entire recording out. For anatomy and simple spatial, fit one
nonnegative gain, no intercept, on other recordings' eligible training
trial-cells. Training and scoring give cells equal weight within trial,
trials equal weight within recording and recordings equal weight. Use the
same training observations for all three gains. No held response enters a
gain, template or training mean.

The empirical template is the mean response in each matching stimulus cell,
equal-weighting available other recordings' cell means. For its gain fit,
cross-fit template predictions within the outer training set by excluding
each training recording in turn and requiring at least three remaining
recordings for a cell. Fit all three gains on that common inner-eligible
training subset. Rebuild the empirical template using all outer training
recordings for held predictions. This extra cross-fit prevents the empirical
gain being fitted against responses used in its own template. Report training
coverage and gains. Empirical fitting learns many cell-specific values;
matching one final gain does not equalize total model complexity. It is an
empirical reference, not evidence of a superior mechanistic circuit.

Include an outer-training-only stimulus-blind constant (weighted mean evoked
response, allowed negative) and zero evoked response. Report empirical
unscaled prediction as a separate sensitivity so gain fitting cannot hide
what the original other-recording template did. Same-recording templates and
concurrent movement are excluded from this held-recording comparison.

## Metrics and interpretation

Primary: mean held-recording pulse-mean RMSE, individual paired changes and
count improved. Do not call pulses independent animals or claim significance.
Secondary: equal-cell Pearson correlation between held-recording measured
cell means and its held predictions, reported per recording (undefined for
constant curves). Plot P1 measured and out-of-fold predicted cell means by
speed/direction, equal weighting recordings within each cell. Show only cells
with at least three scored recordings; SEM reflects between-recording means,
not independent pulses. Report the number of recordings contributing to each
point. Describe peak positions/residuals without fitting new field locations.

Compare models with an empirical reference on identical held observations.
If empirical prediction helps, inspect the repeatable shape our hypotheses
miss. If it does not help, record that limitation rather than invent a new
input. No threshold here authorizes promotion or establishes a noise ceiling.
These errors are not directly comparable to previous raw-rate/full-trace
metrics or the same-recording trial holdouts.

## Checks and artifacts

Enforce MD5/member CRC, finite arrays, count accounting and duplicate exclusion.
Check compact canonical lookups against the existing physiology lookup builder
and native filtering against direct convolution. Match extracted trial-cell
responses and scoring coverage exactly to saved repeatability evidence.
Independently reconstruct gain fitting, held template exclusion, weights,
recording losses and plotted means from saved tables. Repeat the complete
replay and require byte-identical output artifacts. Keep full observations,
folds and cell traces ignored; track compact provenance, recording/cell tables,
checks, plot and result. Production, raw data and old evidence remain unchanged.

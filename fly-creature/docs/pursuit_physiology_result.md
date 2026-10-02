# Measured AOTU response comparison v1

2026-10-02. Implemented and evaluated; no production change.
Frozen [protocol](pursuit_physiology_protocol.md),
[JSON and source hashes](evidence/pursuit_physiology_v1.json),
[compact error table](evidence/pursuit_physiology_summary_v1.csv),
[spatial overview](evidence/pursuit_physiology_overview_v1.png),
[time-course examples](evidence/pursuit_physiology_temporal_v1.png).

## What ran

The authors' [Zenodo NoP1 archives](https://zenodo.org/records/15474938) contain
24 recordings, 12 per type. Both full archives pass published MD5 checks;
every read member passes ZIP CRC. The independent loader restores MATLAB
dimensions and assigns recorded hemisphere using the corresponding sorted
file list and side metadata. Source preprocessing already makes measured
angles positive ipsilaterally; the model receives global angles with one
explicit side transform.

Extracted **13,038 motion pulses**, rejecting 25 malformed/fragmented/overlapping
intervals. All finite intervals are accounted for. Recorded motion is a
staircase: nominal 25/75 degrees/s conditions have median fitted speeds
24.526/71.691 degrees/s and visible durations 988.5/337.5 ms. An initially too
narrow duration rule was corrected from stimulus evidence before any fit;
the protocol records that correction. We replay actual positions, not ideal
nominal ramps. Full acquisition metadata remains unavailable, so this is not
an exact finite-object reproduction of the paper.

Frozen baseline and footprint AOTU responses, 32 within-side input-bundle
shuffles for each, and a fixed simple Gaussian spatial control were compared.
A secondary intercept-only diagnostic was added after the first fit and is
explicitly labelled post hoc. All observation gains/intercepts use training
recordings only, with equal weight per animal. Each recording is held out in
turn. States are stratified; the unit is a recording, not 13,038 independent
animals. The motor decoder, queue, gain and body do not participate.

## Primary held-out pulse errors

Mean animal RMSE, spikes/s. Lower is better. Footprint barely changes any
value; the additional precision makes that visible.

| Type/state | Animals/pulses | Baseline | Footprint | Simple spatial | Intercept only |
| --- | --- | ---: | ---: | ---: | ---: |
| AOTU019 quiescent |12/4560|7.0391|7.0389|7.0437|7.0395|
| AOTU019 running |10/652|11.7572|11.7533|11.5809|11.2256|
| AOTU025 quiescent |12/3856|9.2049|9.2047|9.2202|9.3756|
| AOTU025 running |10/733|10.9794|10.9768|10.9385|11.0060|

Baseline SEM across animals is 0.818, 1.804, 0.621, 1.485 respectively. These
describe substantial animal variability; they are not a significance test
of paired candidate differences. Mixed-state results, baseline-subtracted
errors, time-course errors and every shuffle are retained in the JSON.

Intact baseline/footprint beat 32/32 shuffle aggregates in both quiescent
types and running AOTU025. Running AOTU019 ranks 22/32 and 18/32. **Rank alone
is misleading:** quiescent AOTU019's best baseline shuffle is 7.0411 versus
intact 7.0391, while ignoring visual input gives 7.0395. For quiescent AOTU025,
baseline improves only about 1.82% over the constant predictor. The simple
spatial control is close throughout and slightly better in both running
strata. This is modest evidence for spatial structure under this assay,
not evidence for a useful circuit-specific pursuit advantage.

## What this teaches us

The footprint rewrite does not resolve measured-response disagreement.
More upstream geometry is therefore not an empirically supported fix here.
The broad frontal/lateral organization is compatible with coarse response
structure, but that organization is also captured by a simple spatial curve.

Predicting absolute rate across animals is difficult: spontaneous activity,
behavioral state and animal differences dominate much of the error. The
intercept-only comparison exposes that limitation rather than crediting tiny
shuffle wins to sophisticated computation. Raw and baseline-subtracted
metrics answer different questions; both are reported without separate gains.
Recorded AOTU activity also includes motor/state-related contributions omitted
by our visual-only adapter. These coarse locomotor strata do not remove
continuous walking or turning covariates. Poor absolute prediction therefore
does not isolate a defect in the recorded LC10a connections.

The temporal figure shows the static curves' measurement-filtered envelopes
alongside measured responses. Differences remain, but these examples and broad
animal uncertainty cannot uniquely attribute them to a spatial width, response
latency, adaptation or internal state. The 50 ms filter is an observation model,
not a neural mechanism; these adapters still have no intrinsic temporal dynamics.
Direction CSVs retain paired animal/position/speed differences and ratios;
nonpositive evoked rates leave ratios undefined rather than manufacture a
direction-selectivity statistic. Pooled curves are descriptive, not full
stimulus or source-analysis parity.

NoP1 means **no P1 optostimulation**, not proven absence of all arousal. This
condition cannot calibrate the aroused pursuit model's gain or justify importing
a stronger LC10a direction penalty. We have tested a meaningful but limited
physiological condition; the model is not now a validated neural fly.

## Reproduction and checks

From this project's directory, use its environment (or the root environment
with this package installed):

```powershell
python -m pip install -e '.[physiology-research]'
python tools/fetch_aotu_recordings.py --data-dir outputs/research/aotu-recordings
python -m fly_creature.pursuit_physiology --data-dir outputs/research/aotu-recordings --output-dir outputs/research/aotu-physiology
```

The fetcher downloads only the 499 MB pair, validates existing downloads, and
does not change PATH. h5py/scipy are optional research dependencies, not runtime
requirements. Raw archives and full pulse/fold/curve CSVs remain ignored.

Two complete evaluations give byte-identical five CSVs and two PNGs and identical
numerical/source-hash report fields. A cosmetic protocol formatting change
accounts for the protocol-hash difference between those runs. The tracked report
uses the current protocol hash. FFT filtering agrees with direct convolution
to 2.2e-16; an independent time-error calculation agrees to 3.6e-15. Frozen
controller/model/input hashes stay unchanged. No new unit tests or gameplay
tests were run in this task; the checks above cover the requested diagnostic.

## Next

Extend the same frozen benchmark to the **P1-stimulated recordings** before
fitting another spatial kernel. Keep the NoP1 result as a condition-specific
baseline, separate locomotor strata, and audit protocol/animal differences
instead of pretending the two archives are paired animals. Compare measured
state-related amplitude, direction and time-course changes; do not change
production from an aggregate improvement alone. Sol medium fits this extension's
state and measurement interpretation. It may motivate a bounded response model
after physiological agreement is established; fresh pursuit paths remain reserved.

**TL;DR:** The benchmark works. The footprint adds almost nothing, and these
NoP1 recordings support only modest spatial benefitâ€”not the pursuit claim.

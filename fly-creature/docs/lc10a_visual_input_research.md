# LC10a / AOTU visual input: measured constraints and next comparison

2026-10-02. Research complete; production input, wiring, activation, decoder
and timing are unchanged. This replaces the earlier whole-side-input proposal.
Read the [footprint result](pursuit_footprint_result.md) for the current failure
and [source/sample audit](evidence/pursuit_sensory_source_audit_v1.json) for
retrieval evidence. That source audit was research-only. The subsequent
[measured-response benchmark](pursuit_physiology_result.md) now evaluates
13,038 NoP1 pulses with training-only observation calibration; footprint effects
are negligible and simple controls are close. No production change follows.

## Conclusion

We have enough public evidence to **test AOTU responses against recordings**
before another sensory rewrite. We do not have measured receptive fields for
each selected MaleCNS LC10a body ID. More anatomical detail did not fix tracking;
matching another anatomical reference curve would not resolve that gap.

The current registered map and footprint retain 164 directly mapped LC10a
cells and 111 anatomical fallbacks. Their 18-degree kernels are hypotheses.
The [official MaleCNS release](https://male-cns.janelia.org/download/) supplies
connectivity and anatomy; neither type labels nor upstream column contacts
are measured visual responses. This coverage limit remains material, especially
for the left lateral pathway in the footprint experiment.

Object dimensions, retinal position, motion direction, behavioral state and
measurement units must be kept separate. A 20-degree object, a 20-degree
Gaussian width and a neuron responding while an object crosses 20 degrees are
three different statements.

## What is measured, and what it constrains

| Primary source | Useful measured constraint | What it does not provide |
| --- | --- | --- |
| [Ribeiro et al., Cell 2018](https://pubmed.ncbi.nlm.nih.gov/30033367/) | LC10 small-moving-object preference and antagonistic motion-based center/surround | Per-MaleCNS LC10a widths or currents; detailed numerical figures were inaccessible in this pass |
| [Aptekar et al., J Neurosci 2015, Figs. 4–5](https://pmc.ncbi.nlm.nih.gov/articles/PMC4429157/) | Female LC10a dendritic imaging shows local retinal ordering with a 30-degree sweeping bar; figure/background and direction matter | Response duration includes bar width; pooled dendritic ROIs are not calibrated single-cell axonal outputs |
| [Hindmarsh Sten et al., Nature 2021](https://www.nature.com/articles/s41586-021-03714-w) | Progressive responses exceed regressive responses; P1-associated arousal amplifies tested LC10a calcium responses | Neither complete regressive silence nor a per-body spatial map; calcium amplitude is not spikes/s |
| [Schretter et al., Nature 2025, Fig. 3a and Extended Data Fig. 2](https://www.nature.com/articles/s41586-024-08255-6) | Male LC10a object-size tuning: seven axons/five flies, rectangles at 100 degrees/s; displayed preference roughly 15–30 degrees in width/height. A 50 degrees/s assay is also shown | Object width/height is not spatial RF standard deviation. The plots labelled RF mapping are size matrices, not azimuth/elevation maps |

Hindmarsh Sten's Extended Data Fig. 10 compares 10/25-degree dots and a
10-degree-wide tall bar at 75 degrees/s. Its fluorescence baseline and
peak-normalized shape plots answer different questions. Its model's visual
tiles and complete direction selectivity are modelling choices, not measured
widths. Bouton imaging does not identify MaleCNS body IDs. [Methods and
Extended Data Figs. 10–11](https://pmc.ncbi.nlm.nih.gov/articles/PMC8973426/).

Schretter's [Figshare deposit](https://doi.org/10.25378/janelia.26847772)
was checked, including the workbook XML of
[SourceData_Fig3.xlsx](https://ndownloader.figshare.com/files/48823015).
It contains sheets **Fig3b, Fig3c, Fig3f**, not Fig3a calcium-size tuning.
There is no FigS2 workbook in the listed files. Its large ZIPs and
[code](https://github.com/ceschretter/SocialState2024_Code) concern behavior.
Therefore the existence of this public deposit does not make numerical LC10a
size tuning available for fitting. Published matrices could be digitized with
explicit graphical uncertainty; underlying physiology would be preferable.
No author was contacted.

## The pursuit pathway: physiology versus anatomical reference

[Collie et al., Neuron 2026](https://pubmed.ncbi.nlm.nih.gov/41713413/)
supports peripheral and frontal pursuit pathways, with the frontal pathway
recruited by outward motion, fast running and arousal. The available
[2025 preprint, Fig. 1](https://pubmed.ncbi.nlm.nih.gov/40599160/) describes
25/75 degrees/s motion pulses traversing 22.5 degrees, with firing rates
averaged during each pulse and plotted at its sweep center. This is a stimulus
response measurement, not a point-sampled intrinsic field.

**Version correction:** PMC12212441 is the 2025 preprint, not the final Neuron
article. The earlier note's female-only statement applies to that preprint's
connectomics; it is not an adequate description of the source we now use.
Our [pinned author-code audit](pursuit_reference_contract.md) identifies a
MaleCNS v0.9 analysis and male model table. Our graph is MaleCNS v1.0. These
are separate specimens/releases and must not be equated by matching type names.
The final PDF was read in the earlier [timing audit](pursuit_timing_contract.md);
its lab download was inaccessible during this pass. Exact new stimulus claims
above are explicitly attributed to the readable preprint, not silently promoted
to final-paper parity.

The pinned `Pursuit_RFs.csv` is **anatomy/image-derived and already weighted**,
not a recording of 275 LC10a fields. Feeding it into our LC10a edges would
reuse connection strength. This source distinction was established by the
[mapping audit](pursuit_mapping_result.md), not by an assumed biological fit.

## Actual AOTU recordings are accessible

The authors' [Zenodo version record 15474938](https://zenodo.org/records/15474938)
is accessible; 15474937 is its concept record. It lists separate AOTU019/025
motion-pulse archives with and without P1 stimulation, and walking signals.
The repository description reports 20 kHz acquisition and approximately
667 Hz stored data. The API declares **CC BY 4.0** for this dataset; the pinned
code README declares different terms. Do not infer data terms from code terms.

I inspected ZIP central directories with small HTTP range requests, then
retrieved one small recording per type. Each NoP1 archive contains **12
`*_int.mat` recordings and `trackLR.mat`**. The selected members were chosen
by compressed size, not response quality. Portable Octave loads them:

| Sample | Matrix dimensions | Time spacing | Position coverage |
| --- | --- | --- | --- |
| AOTU019, 2023-06-19 fly01 | 40,000 samples × 10 trials | 1.5 ms | 39.78% finite |
| AOTU025, 2024-06-27 fly01 | 58,000 samples × 4 trials | 1.5 ms | 39.63% finite |

Both expose `int_time`, `int_panelps`, `int_spikert`, `int_voltage`,
`int_forward`, `int_angular`, `int_sideway`. Position NaNs are intentional
hidden/excluded intervals, not zeros to fill. Downloaded members pass ZIP
CRC32 and have saved SHA-256 hashes; the published full-archive MD5 was **not**
verified because full archives were not downloaded. Recordings stay in ignored
`outputs/research/sensory-constraints/`; compact metadata is tracked. Two loaded
samples establish format/access, not representative physiology.

### Processing details verified directly in pinned source

Source paths and hashes are in the [audit](evidence/pursuit_sensory_source_audit_v1.json).

`preprocess_motionpulse.m` mirrors left-cell stimulus position, yaw and lateral
motion into **ipsilateral-positive** coordinates before saving. Do not mirror
the distributed `int_*` data again. It excludes hidden positions/acquisition
jumps and rounds stored position to two decimals. A naive derivative of those
quantized positions is not an exact instantaneous stimulus-speed measurement.

`pipeline_motion_pulse.m` computes pulse **means**, despite naming several
variables “peak”. Its normalized rightward and leftward curves each use their
own maxima; the bilateral difference has another denominator. Those curves
cannot establish relative type or direction gains in raw spikes/s. Preserve
raw responses and baseline-subtracted responses separately.

`spikert_seqfit.m` fixes the visual predictor's centers to 35/65 degrees and
spread to 20 degrees, fitting its amplitude. **These widths/centers are supplied
predictors, not fitted physiological estimates.** The stored firing rate is
already smoothed; the Gaussian acquisition function uses sigma=1,000 samples
at 20 kHz (50 ms). Do not smooth measured rates again or interpret their
pre-onset tail as causal neural anticipation. Source running/quiescent filters
also differ: a comparison must declare the exact state criterion.

## Measured-response benchmark: specification now implemented

The [result](pursuit_physiology_result.md) implements the data adapter and
fixed-body report specified below. Its [frozen protocol](pursuit_physiology_protocol.md)
records extraction corrections and comparison details. **Do not rewrite the
production input from these NoP1 results.** Subsequent P1 comparisons, population
tuning, reference-history audit and a rejected output correction are summarized
in the [completed improvement cycle](pursuit_goal_result.md). The current next
task is the [LC10a sensor contract](pursuit_replacement_plan.md); the specification
below records the implemented benchmark's original design and limitations.

Acquire the two NoP1 archives with checksum verification and preserve file/fly
identity. Reconstruct visible pulse intervals from recorded position/time,
audit spans/durations/direction, and verify against the author ordering logic.
Keep blanks, incomplete pulses and exclusions explicit. Confirm bar dimensions
and protocol version before claiming matched stimulus size; the sample files
do not embed full acquisition metadata. Use NoP1 initially to avoid mixing
arousal conditions, but do not equate absence of optostimulation with a measured
uniform internal state.

Replay the measured position histories through the frozen baseline and offline
footprint candidate. Compare predicted AOTU activity **before DNa02/decoder**
with measured AOTU rates, separating spatial shape, direction ratio and time
course. The current adapter has no internal neural response dynamics, so this
assay may expose missing temporal behavior rather than just a spatial error.
Apply a matched observation filter to predictions for time-course
comparisons; do not move the established 200 ms motor queue into this assay.
Arbitrary activity units require a declared observation calibration; they must
not be labelled spikes/s without one.

Declare animal-level training/held-out splits and a small calibration budget
before fitting. Start with unfitted shape diagnostics and training-only affine
observation calibration; report raw and baseline-subtracted rates. Use the
same allowance for intact anatomy, spatial shuffles and a simple fitted spatial
response control. Report pulse-mean error, direction ratios and matched-filter
time-course error with per-animal uncertainty; do not independently peak-normalize
every channel to hide gain errors. These tests address visual-response agreement,
not a motor advantage. AOTU-to-DNa02 bridge removal is irrelevant to an upstream
AOTU response test.

Only after locating a measured-response mismatch should a bounded sensory
candidate be designed. LC10a size tuning motivates a later finite-object,
center/surround contract, but does not identify our 18-degree per-cell kernel.
Validate any justified change on held-out physiology before opening fresh pursuit
paths. If wiring controls fit equally well, report that the physiology did not
identify a wiring-specific benefit. Aggregate AOTU recordings still cannot
uniquely recover 275 individual LC10a fields.

**TL;DR:** There is a practical empirical target now: recorded AOTU responses.
Test our visual response against those before tuning another pursuit input.

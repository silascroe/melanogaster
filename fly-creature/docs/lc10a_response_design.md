# LC10a retinal response v1: frozen design and comparison protocol

2026-10-04. **The design is frozen. The offline LC10a image-response
implementation and 68-probe numerical checkpoint pass; no recorded physiology
fit or new biological result exists.** This continues the [retinal renderer](lc10a_sensor_renderer.md)
and [input contract](lc10a_sensor_contract.md). The machine-readable
[manifest](evidence/lc10a_response_design_v1.json) pins the constants and sources.

## The question and the limits

Can a shared, causal image-response hypothesis improve our predictions of
recorded AOTU activity, and does the particular MaleCNS wiring contribute beyond
the same visual features with ordinary weights? These are separate questions.

Build one rule that reads luminance images and their history, samples them at
the existing 275 LC10a azimuth hypotheses, and projects the resulting activity
through the existing LC10a-to-AOTU contact counts. The image rule supplies the
unmodelled visual processing upstream of LC10a. It does not reconstruct that
upstream connectome, assign measured fields to these body IDs, or simulate
spikes. All numerical spatial and motion-detector constants below are synthetic.

The archived stimulus is predominantly a fixed bar on a uniform background.
It cannot identify size tuning, a contrast law, surround interactions, or 275
individual fields. It can test the consequences of a frozen rule on the available
recordings. Reused recording holdouts remain exploratory. Passing this protocol
allows a subsequent bounded experiment; it does not certify biology or authorize
Godot promotion.

An important structural limitation stays visible: this rule and the selected
LC10a-to-AOTU projection are nonnegative. An isolated target after a sufficiently
long uniform-background rest cannot produce a below-rest AOTU prediction.
Negative *evoked* predictions can arise when preceding-target activity decays
between the reference and stimulus windows. If the data ultimately require
history-independent inhibition, this model cannot supply it. Do not add a
negative fitted offset to conceal that limitation.

## Sources and what is actually new

[Ribeiro 2018](https://www.janelia.org/publication/visual-projection-neurons-mediating-directed-courtship-in-drosophila)
supports small-moving-object sensitivity and antagonistic motion center/surround
at the LC10 level. Its accessible abstract does not identify our kernel widths,
motion-detector delay, or suppression strength.

[Hindmarsh Sten 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8973426/)
reports aggregate LC10a progressive-motion preference and arousal-associated
gain. Its *model* assumes complete progressive selectivity and ignores object
size; those are not the measured physiological inequalities. This design permits
regressive and stationary responses and has no gain inferred from a P1 filename.

The [published model repository](https://github.com/rutalaboratory/LC10NetworkModel/tree/d15afdfd21b93774cef963f5c92d511a9ea0d15e)
provides a useful additional constraint: the exact fitted temporal-envelope
equation in
[temporalRF_LC10.m](https://github.com/rutalaboratory/LC10NetworkModel/blob/d15afdfd21b93774cef963f5c92d511a9ea0d15e/Tethered/temporalRF_LC10.m).
We borrow its *shape* as a declared transfer hypothesis, without its ampere scale,
uniform spatial partitions, neuron count, LIF constants, or turning decoder.
This is a published model fit to estimated receptive fields, not a measured
spiking impulse response for MaleCNS LC10a or AOTU. Its relation to calcium
measurement dynamics is unresolved; an instantaneous-envelope ablation is
therefore mandatory. Never add a calcium observation kernel to the AOTU spike
benchmark or describe this envelope as established electrical latency.

[Schretter 2025](https://www.nature.com/articles/s41586-024-08255-6)
supports qualitative object-size preference around 15–30 degrees in a small
male LC10a calcium cohort. Its approximately 90-by-90-degree imaging screen
differs from our 330-by-60-degree probe panel. Preferred object size is not a
receptive-field sigma. In particular, a 60-degree-high target fills our vertical
panel, so that probe cannot faithfully reproduce the paper's large-height assay.
Use the preference as a compatibility diagnostic, not a numerical fit target.

Paper bar dimensions, archive timing/metadata gaps, and the 164 mapped/111
fallback azimuths retain the [contract's limitations](lc10a_sensor_contract.md).
The source files are small CC0 author code, pinned and hashed in the manifest;
local copies remain under ignored `outputs/research/lc10a-response-design-v1/`.

## Exact image rule

Use float64 throughout. `step(image, time_s, state_gain=1)` receives only the
176-by-32 linear-luminance frame, its timestamp, and an explicit external gain.
Stimulus identity, target presence, bearing, velocity, size, contrast label,
surround label, and P1 filename must not enter the neural response function.
They are renderer inputs or diagnostic labels. This prevents an invisible target
or an oracle motion label from driving neurons. The rule supports frames in
[0,2], a reference luminance of 1, and strictly increasing finite timestamps.
Reject unsupported values; do not silently clip images or use 8-bit previews.

### Local motion from image history

Let `c = image - 1`, `p+ = max(c,0)`, and `p- = max(-c,0)`. Maintain separate
delayed ON/OFF contrast images `d+` and `d-`, initially zero. At timestamp `t_n`,
first advance each delayed image over the previous held frame:

```
dt = t_n - t_(n-1)
a = exp(-dt / 0.020)
d_n = a*d_(n-1) + (1-a)*p_(n-1)
```

Then compare adjacent horizontal pixels in both polarity channels:

```
h_(j+1/2) = sum_polarities(d_(j,n)*p_(j+1,n) - d_(j+1,n)*p_(j,n))
```

Positive `h` denotes rightward image motion. Assign it to pixel centers by
averaging adjacent valid pairs; an edge pixel uses its single valid pair.
There is no horizontal wrap or invented pixel beyond the panel. A reflected
movie negates/reflexes `h` exactly apart from floating-point error. The first
frame uses zero delayed images. Constant stationary images generate zero motion
after startup; their static-contrast response below remains available.

For eye sign `s=+1` right, `s=-1` left, define
`e_s = max(s*h,0) + 0.5*max(-s*h,0)`. This places the hypothesized direction
preference at LC10a, rather than multiplying only downstream AOTU019 by 0.66.
The old penalty is bypassed for every new-rule predictor, including controls.
The residual regressive weight 0.5 is a frozen assumption, not a measured ratio.
The 20 ms delay is an elementary correlation-detector setting, distinct from
the subsequent response envelope and the game's motor queue.

### Spatial center/surround and the missing elevation map

Keep the packaged azimuth centers and sorted body IDs unchanged. For a cell
with absolute center `mu`, use signed center `s*mu`. At each of the 32 existing
pixel-row elevations `y`, construct two separable circular Gaussian kernels
centered at `(s*mu,y)`: sigma 7.5 degrees (center) and 22.5 degrees (broad surround).
The latter overlaps the center; it is not an annulus. These are four- and
twelve-pixel engineering scales, chosen to construct a compact-object example
compatible with the qualitative size preference. They are not measurements of
receptive-field width and were not fitted to AOTU responses. The simple 1D
construction below already favors about 24-degree objects by design; recovering
that preference later would therefore be compatibility, not new evidence.

Weight **both** kernels by the frozen per-pixel aperture
`A_s(x)=clip(0.5+s*x/15,0,1)` and normalize each to sum to one over the observed
panel. No unseen off-panel image is assumed to be bright background. Apply the
aperture in pooling, after motion extraction, so an artificial eye boundary
cannot create image motion. Save kernel mass before normalization and report
aperture/border truncation. This replaces point-bearing aperture multiplication;
its boundary behavior is a declared part of the new sensor.

For a contrast or motion image `q`, define
`D(q,y) = max(sum(K_center(y)*q)-sum(K_surround(y)*q),0)`.
Combine the channels at the same elevation, then pool:

```
f_i(t) = max_y(0.25*D(abs(c),y) + 0.75*D(e_s,y))
```

Vertical maximum pooling is a shared translation-tolerant hypothesis. It avoids
inventing 275 measured elevations or silently putting every cell's field at
zero elevation. It nevertheless grants every cell the same range of vertical
sampling, and may overestimate off-center responses. Preserve the winning row
and pre-rectification center-minus-surround values in representative diagnostics.
An average-over-rows ablation reports dependence on this choice; it is not
eligible to replace the primary result after seeing scores.

The static channel permits a stationary finite object to respond. ON/OFF symmetry
implies equal bright/dark responses on a uniform background in this hypothesis;
that is an unsupported construction choice to report, not a biological finding.
The motion channel has quadratic contrast dependence whereas the static channel
is linear. There is no fitted contrast exponent or saturation curve. Surround
motion is inferred from the whole image, so the rule also sees background motion.
Do not classify pixels using the known target mask.

For supported input values, `0 <= f_i <= 1`. Do not normalize each cell, probe,
speed, direction, recording, or output channel to its own observed maximum.

### Fixed response envelope and time ownership

For lag `u>=0` seconds, use the author code's stable equivalent:

```
k(u) = sigmoid(5.5273*(0.84962-u)) * sigmoid(15.5884*(u-0.1859))
K(u) = k(u) / integral_0^3 k(v) dv, for 0 <= u < 3 s; otherwise zero
r_i(t) = state_gain(t) * integral_0^3 K(u)*f_i(t-u) du
```

The unit-area normalization and 3 s horizon are our choices. The original code
sums historical binary samples and multiplies by an ampere scale; copying that
sum onto 500/667 Hz images would introduce sample-rate-dependent gain. We use
an integral so constant drive retains its amplitude. The construction figure
and manifest record the peak, mean lag, and omitted tail. This kernel has
substantial response memory; it must not be described as a new pure delay.
Independent equation checks give a 411.38 ms peak and 587.78 ms mean lag, with
about 0.000187% of its area beyond 3 s. See the
[construction figure](evidence/lc10a_response_construction_v1.png). The separate
1D static spatial illustration peaks at 23.58 degrees; it does not predict the
full 2D, moving, vertically pooled response.

At native uniform `dt`, use weights
`w_m = integral_[m*dt,min((m+1)*dt,3)] K(u) du`. A value `f_n` begins its held
interval at `t_n`. Therefore output at `t_n` is
`r_n = gain_n * sum_m(w_m*f_(n-1-m))`, with unavailable history zero. This
one-sample integration convention is explicit and causal. Do not read the next
position/frame, snap to a different time grid, or renormalize the startup prefix.
For genuinely irregular timestamps, integrate over the actual past held
intervals with these same continuous limits; do not round intervals into bins.

Reset detector/envelope state only at independent trial boundaries, never at
an individual pulse, visibility gap, or direction reversal. A hidden target
renders the background; earlier drive decays naturally. No virtual paper gaps
are inserted. `state_gain=1` for all physiological replays and ordinary probes.
The caller may explicitly demonstrate gain 2 on synthetic probes as an algebraic
gain check; the P1 label alone changes nothing. Gain multiplies current recalled
drive, as in the source function, rather than being stored with old input.

Retain `f_i` and `r_i` in sorted body-ID order, with side and map-provenance
metadata. Units are dimensionless hypothesized drive/activity. There is no
voltage, spike train, inferred calcium, motor response, or new neuron count.

## Probe stage: checks before any physiology fit

Run all 68 existing 2 ms probes; keep the first three seconds identical to v1.
Extend the target-absent suffix to six seconds, continuing its declared surround,
so the response tail is inspectable. Append separate auxiliary controls without
altering the frozen 68 rows: target-absent counterparts for each surround probe,
static grating, spatially uniform flash, a target that pauses, and an isolated
target after a 6 s uniform rest. Use identical renderers/photometry for partners.
Synthetic explicit gain-2 counterparts are labelled software checks.

The manifest gives exact auxiliary movies: both-polarity whole-panel flashes
on [1,1.4) s; a 10-degree disc present on [1,2.3) s, moving from 30 to 60
degrees at 75 degrees/s, paused on [1.4,1.9), then moving to 90 degrees;
and an isolated 10-degree disc sweeping 30 to 90 degrees on [6,6.8) after
uniform rest. Include left mirrors. Static-grating nulls are already supplied
by the absent-target partners of zero-surround-speed probes. An explicit gain
check uses `dot25_dir1_unstimulated_R` and its left partner, with gains 1 and 2;
label-swapped copies must be identical at gain 1. Auxiliaries are software
checks with no claimed experimental stimulus parity.

Required numerical checks, with tolerances pinned in the manifest:

| Check | What must happen |
| --- | --- |
| Uniform absent / zero-contrast movies | Equal zero drive and response; modifying invisible target metadata cannot change output |
| Causality and chunking | Different future frames cannot alter a shared prefix; chunked and one-pass states agree |
| Image mirroring | Detector sign reverses and the shared virtual unit at +60/-60 mirrors; anatomical L/R curves need not equal because maps/weights differ |
| Stationary and uniform flashes | Motion detector stays zero for a static image/whole-field flash; static finite-object channel may respond |
| Pooling arithmetic | Independent direct weighted sums match optimized separable pooling; uniform contrast or uniform local motion gives equal center/surround means |
| Envelope | Nonnegative, unit mass, causal integration, bounded output; 1.5/2 ms converge to continuous quadrature for a known held-input pulse |
| Raster stability | Eight/16/32 subpixel coverage and an independent exact rectangle compositor give stable integrated virtual-unit responses; no direction-sign reversal |
| Gain | Gain labels alone do nothing; explicit gain 2 doubles response without changing the recalled history or spatial map |
| Reset and identity | Only trial reset clears history; all 275 IDs remain in the same order and source hashes match |

Report width/height peaks, progressive/regressive differences, polarity, contrasts,
stationary residuals, and temporal tails. Use a virtual center at +/-60 degrees
for a map-independent compatibility check and additionally report actual-cell
per-eye/per-provenance summaries. Source-inspired inequalities are descriptive
compatibility flags, not hard evidence of biological accuracy. If a flag fails,
retain it and the fixed constants; do not tune until the plot looks right.

For each surround condition, report both total response and the **signed**
difference from its target-absent background counterpart. The latter is an
analysis contrast, never a subtraction inside the sensory function. Otherwise
background responses could be mistaken for object suppression. Zero target
contrast on a textured background can still occlude texture and is not a null.

Declare these one-factor ablations before running: no surround (broad-kernel
weight zero in both channels), direction-neutral (`e_s=0.75*abs(h)`), no static
channel (static coefficient zero; leave motion coefficient 0.75), vertical mean
instead of maximum, and instantaneous envelope (`r=f`, gain unchanged). They
explain the primary rule; there is no best-of-ablations selection or parameter
grid. Numerical failures block physiology scoring until corrected and rechecked.

Raster checks use `width_15_R`, `dot10_dir1_unstimulated_R`,
`bar_25_1_15_R`, `bar_75_1_65_R` and their mirrors at horizontal phase offsets
0, 0.46875, 0.9375 and 1.40625 degrees (reflect offsets for left partners).
Compare the virtual unit at the shifted nominal center, using the same physical
coordinates for each rendering resolution. Relative differences in its
six-second integrated response must be <=5% for 8 versus 32 and 16 versus 32
samples per axis, and for 8 versus exact rectangle coverage where applicable;
denominator is `max(abs(reference_integral),1e-9)`. A direction-preference sign
reversal also fails. This guards against the motion detector learning the
8-by-8 renderer's temporal staircasing. Report phase dependence separately;
passing a raster convergence check does not recover the actual LED movie.

## Recorded AOTU stage: matched information and budgets

Use the same four checksum-verified archives, exclusion of
`AOTU019/2023_06_15_fly03`, original extraction, 69 recordings, 35,484 quiet
pulses and exact 34,554 scored trial-cells from the
[population comparison](pursuit_population_protocol.md). Reuse its complete
recording holdouts and inner-eligible calibration indices. Copy neither motor
covariates nor response-informed adjustments into the sensory input.

Render **actual unsnapped** position samples at their recorded timestamps,
not the synthetic probe's centered trajectory formula. Support staircase holds,
direction changes, offsets, and NaNs explicitly. Canonical ipsilateral-positive
positions drive a right-eye replay and its left mirror; average the two AOTU
outputs as before. Distributed recordings must not be mirrored a second time
as a data transformation. A NaN renders uniform background under the previous
benchmark's absence/exclusion convention; this does not recover the missing
physical movie. Report initial-trial history truncation without dropping cells.

Primary association assumption: dark rectangle 11.25 by 60 degrees at elevation
zero, Weber contrast -1, uniform background 1. The archive does not establish
those exact dimensions, luminance, or per-recording patterns. Predeclared
one-factor association sensitivities: width 5.625 and 22.5 degrees, height
30 degrees, and contrast -0.5. No cadence substitutions or inferred state gain.

For every new-rule predictor, compute `raw_AOTU = r @ W` and apply the unchanged
type-specific, fixed-peak ELU lookup from the existing adapter. Use its original
peaks, nearest-lookup convention and limits. Bypass only its old AOTU019
direction multiplier: LC10a already supplies direction. Record unclipped drives
and every saturation. If any recorded raw input exceeds a frozen peak beyond
1e-9, the representation gate fails; publish the failure and do not refit peaks,
silently clip, or discard affected recordings. Never multiply by AOTU-to-DNa02
edges in this upstream benchmark.

The same 50 ms symmetric Gaussian observation filter, truncated at 250 ms,
matches the already-filtered spike-rate observations. It is a separate
measurement operation after AOTU activation. Apply it over full native trials;
do not filter measured rates again. Subtract each prediction's original
[-250,-100] ms pre-reference and average the complete visible pulse exactly as
before. The symmetric observation filter may extend predictions before onset;
causality checks use raw drive/activity before this filter.

### Predictors

| Predictor | Purpose and allowance |
| --- | --- |
| Frozen legacy intact and legacy simple | Exact historical point-input references, including their existing direction rules and lack of response envelope |
| New intact | Primary rule and original LC10a-to-AOTU counts, one fitted gain |
| New 32 shuffles | Exactly the existing within-side input-bundle permutations, full new rule and original normalization, one gain each |
| New matched spatial | Same 275 responses, envelope, pooling, aperture, normalization, ELU and fitting allowance; anatomy-independent fixed spatial weights |
| New flat | Same responses/timing/nonlinearity with uniform within-side output weights; one gain |
| New ablations | New intact, spatial and all 32 shuffles for each declared ablation; identical fitting budget, diagnostic only |
| Constant and zero | Preserve original training-only constant/zero evoked references |

Construct matched-spatial weights separately for each existing AOTU side/type
using `q_i=exp(-0.5*((mu_i-p_type)/20)^2)` within that side, zero on the other
side; `p_019=35`, `p_025=65` degrees. Set
`W_simple[:,j]=q/sum(q)*sum(W_intact[:,j])`. Flat weights share that same
column total equally across same-side cells. Thus every control receives the
same sensory information and total contact budget; it fits no fields, centers,
direction-specific gains or extra offsets. The synthetic weights are not an
alternative anatomical claim. Keep the old bearing-only simple control too:
it does not have equal visual information and is not the circuit-specific gate.

Load/audit the already-used permutations from the old builder (physiology seed
20261006); do not generate a new favorable shuffle cohort. The complete sensory
vectors, including provenance, stay fixed when wiring is shuffled. Keep each
cell's entire AOTU output bundle together and never cross hemispheres.

For each outer held recording, type and archive condition, fit one nonnegative
gain with no intercept on the exact prior training subset. With normalized
hierarchical weights `w`, use
`g=max(0,sum(w*x*y)/sum(w*x*x))`; if denominator is zero, gain is zero and the
degeneracy is reported. Weight cells equally within trial, trials within
recording, recordings equally. No held recording supplies a gain, field,
normalizer, parameter selection, or response-template entry. Gains are
observation calibrations, not measured LC10a state gains or synaptic strengths.

Primary score remains mean held-recording pulse-mean RMSE, separately for
P1 AOTU019 and AOTU025. Report recording improvements, correlations, direction/
speed residuals, negative evoked coverage, clipping, and losses for all controls.
NoP1 is a separate sensitivity. Retain source/group/physical-side uncertainties.
Association sensitivities apply equally to new intact, spatial, flat and all
32 shuffles; they cannot be used to select a winning primary geometry.

### Gates and interpretations

Reuse the existing practical thresholds rather than inventing easier ones:
for **both** primary P1 types, new intact must reduce RMSE at least 5% versus
legacy intact and improve at least 60% of recordings. A circuit-specific gate
also requires at least 1% lower RMSE than the **new matched spatial** control
and lower error than at least 30/32 new wiring shuffles. Strictly lower scores
count as wins; ties do not. Numerical/provenance/coverage/normalization checks
must all pass. These are practical gates, not significance tests.

Report the image/timing contribution by comparing new versus old spatial
controls, and the wiring contribution by comparing new intact versus new
spatial/shuffles. The difference between those improvements is descriptive,
not a causal mediation estimate. The instantaneous-envelope ablation identifies
whether the source envelope helps; it is not a license to claim whichever
configuration scores best was the primary hypothesis.

For each association sensitivity report the same gates and paired losses; call
the conclusion association-sensitive if the anatomical advantage changes sign
against matched spatial, or the >=30/32 wiring requirement fails. A primary pass
with an association-sensitive conclusion warrants metadata recovery, not a
gameplay upgrade. A generic input benefit with no wiring advantage is a useful
sensor result and does not satisfy the project's connectome-specific goal.
If all benefits fail, retain the evidence and reassess missing inhibition/state
or the appropriateness of this recording target. Do not start another gain or
kernel sweep. Independent confirmation needs genuinely new data/stimuli.

## Probe implementation checkpoint: complete

`src/fly_creature/lc10a_response.py` implements the frozen image-only rule;
`tools/run_lc10a_response_probes.py` streams the existing renderer through all
68 probes at six seconds and 2 ms; `tools/check_lc10a_response.py` independently
checks pooling, timing, history, source hashes and raster convergence. Compact
results and the claim boundary are in the [implementation report](lc10a_response_result.md).
The exact-repeat hashes are in
[`lc10a_response_repeatability_v1.json`](evidence/lc10a_response_repeatability_v1.json).

The source renderer, selected 275 IDs, map, connections, probe matrix, and
playable production code remain unchanged. The new output is dimensionless
LC10a activity; no AOTU contact projection, recorded fit, spike model, or
Godot integration is part of this checkpoint. Full activity traces remain in
ignored outputs. Reproduce from the workspace root with:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/run_lc10a_response_probes.py
.\.venv\Scripts\python.exe fly-creature/tools/check_lc10a_response.py
```

## Next checkpoint: recorded AOTU comparison

Implement a separate offline `lc10a_response_benchmark.py` using the existing
recording readers, extraction, and scoring. First verify the frozen extraction
and calibration indices/targets, legacy predictions, and exact `LC10a→AOTU`
weights against prior evidence. Then compare the frozen response through those
unchanged contacts against legacy, matched-spatial, flat, and the existing 32
within-side wiring shuffles with identical visual information and fit allowance.
Pin source/protocol hashes before inspecting candidate scores; preserve the
declared 5%/60% predictive and 1%/30-of-32 wiring gates. Keep complete traces,
folds, and raw recordings ignored. A failure retains the frozen result; it does
not authorize a gain/kernel sweep or Godot promotion.

**Recommended settings:** Luna Max for the bounded benchmark implementation;
Sol medium for protocol review and interpretation of the recorded comparison.

## Reproduce the design arithmetic

The checker requires the existing `physiology-research` optional dependencies.
From the workspace root, restore the three pinned small source files if absent:

```powershell
$rutaRevision = 'd15afdfd21b93774cef963f5c92d511a9ea0d15e'
$rutaSources = 'fly-creature/outputs/research/lc10a-response-design-v1/sources'
New-Item -ItemType Directory -Force -Path $rutaSources | Out-Null
foreach ($rutaFile in @('Tethered/temporalRF_LC10.m', 'Tethered/sampleLC10Model_tethered.m', 'LICENSE')) {
    Invoke-WebRequest "https://raw.githubusercontent.com/rutalaboratory/LC10NetworkModel/$rutaRevision/$rutaFile" -OutFile (Join-Path $rutaSources ([IO.Path]::GetFileName($rutaFile)))
}
.\.venv\Scripts\python.exe fly-creature/tools/check_lc10a_response_design.py
```

Check downloaded SHA-256 values against the manifest. The checker reconstructs
the stable envelope equation, independent held-input integration at both native
sample intervals, and the explicitly simplified static spatial illustration.
Its figure is tracked; detailed design arithmetic is saved to ignored outputs.
It does not implement the image-response rule or read recorded responses.

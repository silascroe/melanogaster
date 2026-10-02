# LC10a visual-input contract and offline probe matrix

2026-10-02. **Contract complete; response model not implemented or validated.**
This is the first milestone in the [replacement plan](pursuit_replacement_plan.md).
The [fresh primary-source note](lc10a_sensor_source_refresh.md) distinguishes
measured constraints from hypotheses. Production, circuit, maps and old evidence
are preserved. The matrix specifies inputs and checks, not predicted fly biology.

## What changes conceptually

The current adapter receives a point bearing and motion direction. Its 18-degree
Gaussian is a hypothesized neuronal response width, not a visible object's width.
The opt-in overlap adapter mixes the hemispheres near the center; AOTU019's
direction penalty is imposed downstream. Neither implementation encodes target
height, contrast or surrounding motion. Adding those fields is a sensor change,
not a discovery of new connectome connections.

The selected 275 LC10a IDs and edges stay fixed. Their registered map contains
164 upstream-mapped azimuths and 111 fallbacks. It does **not** supply a per-cell
elevation map. A first sensor may use horizontal geometry and a shared height
response hypothesis, but must not pretend to assign measured two-dimensional
receptive fields. Keep fallback/direct labels in every report and show left/right
coverage separately before any pooled summary.

## New source fact and unresolved archive association

The final [Collie 2026 PDF, methods p. e4](https://wilson.hms.harvard.edu/sites/g/files/omnuum8421/files/2026-03/Collie%202026.pdf)
is now readable. Main pursuit targets were dark 11.25-by-60-degree bars on bright
backgrounds. The panel covered 330 degrees horizontally and 60 vertically, with
approximately 1.875-degree pixels and 500 Hz control. Methods describe 22.5-degree
sweeps at 25/75 degrees/s, appearing every three seconds. These are paper-level
specifications, not proof of each archived trial's pattern or luminance.

The prior history audit recovered predominantly one-second hidden gaps and
approximately 0.99/0.34-second visible intervals. Their sum is incompatible with
a uniform three-second onset period. Preserve actual timestamps; do not insert
paper timing into recorded trials. Potential protocol variation remains
unresolved. The [Zenodo dataset](https://zenodo.org/records/15474938) stores
position histories, not a calibrated retinal movie for each sample.

Pinned author code `runExptBattery.m` selects dark-bar pattern 2 and different
function families for motion pulses/extended range. Acquisition stores size,
object gray level and background gray level from external `patt_lookup_*` files.
Those lookup files are absent from the inspected pinned clone. The acquisition
assignment `sweepRate = funlookup.sweepRange` also prevents trusting that metadata
field as actual speed without checking the trajectory. See
[pinned source](https://github.com/wilson-lab/CollieWilson/tree/65d72773121ffe148b56b8ba4f594a7a51c51789/Data_Acquisition_Code).
The next recorded replay may use paper bar dimensions only as an explicitly
declared association assumption, with a size sensitivity; it cannot claim exact
stimulus parity until per-recording pattern metadata is recovered.

## Input and output interface

| Field | Meaning / units | Required limitation |
| --- | --- | --- |
| Time and visibility | seconds; target-present flag distinct from image contrast | Hidden samples remain hidden; never convert recorded NaN positions to 0 degrees |
| Target geometry | shape, center azimuth/elevation, angular width/height in degrees | Disc diameter is distinct from rectangle dimensions; no 3D body size inferred |
| Motion | signed retinal angular velocity in degrees/s, separate target and surround | Already mirrored recordings must not be mirrored again |
| Photometry | normalized background luminance and signed Weber contrast | Synthetic normalized values do not establish LED luminance or a measured contrast law |
| Surround | uniform or a declared grating, period/contrast/phase/velocity | Finite target occludes the background; background motion is not target motion |
| State | provenance label and observed locomotor metadata when available | P1 label, quiet threshold and actual internal state are different quantities |
| Output | activity vector in fixed sorted body-ID order; dimensionless hypothesis units | No calibrated spikes/s, calcium or per-neuron elevation field without supporting data |

Canonical body coordinates: positive azimuth right, negative left, zero ahead;
positive elevation up. For the right eye, progressive motion is positive
horizontal velocity; the left-eye mirror reverses that sign. This convention
describes front-to-back retinal motion, not a body's turn direction. Targets
crossing the midline need explicit eye apertures; do not apply a global sign
classifier there. Matched direction probes stay in one hemisphere.

Synthetic probes use panel bounds [-165,165] azimuth and [-30,30] elevation,
2 ms time steps and 1.875-degree pixels. Their centered vertical origin is our
convention, not a verified eye-specific calibration. Render a finite rectangle
or disc with fractional pixel coverage, clip to the declared aperture, and
preserve phase. Contrast C=(target-background)/background, background=1;
zero contrast with a uniform background makes an invisible target. A grating
uses 30-degree period and 0.5 Weber amplitude; these are diagnostic choices.

For a probe starting at t0 with duration T, center azimuth is
`center + velocity*(t-t0-T/2)` on the half-open interval `[t0,t0+T)`.
Outside it the target is absent; the background persists. Directional pairs
traverse the same positions in opposite order. Their mirrored partners have
negated center, target velocity and surround velocity. The future renderer
must use chronological history, not only an instantaneous coordinate.

## Probe matrix and acceptance meaning

The [CSV](evidence/lc10a_sensor_probes_v1.csv) contains exact stimulus parameters;
the [manifest](evidence/lc10a_sensor_contract_v1.json) pins protected sources,
documentation, builder and CSV hashes. Reproduction uses the stdlib builder below.
There are 68 probes, including explicit left/right mirrors. The 100-degree/s
size-probe speed comes from the previous figure inspection, not an independently
reverified numeric constraint in the fresh source note. Synthetic trials last
three seconds with target onset at one second; this is a convenience for probes,
not a reconstruction of archived pulse cadence.
Probe geometries inspired by experiments remain synthetic: positions, paths,
state scheduling and screen calibration are not asserted to reproduce them.

| Family | Comparison | Interpretation |
| --- | --- | --- |
| Nulls | Absent target; zero target contrast on uniform background | Rendering equivalence; any target-driven response difference is an implementation error, not biology |
| Width / height | Independently vary 5/15/30/60 degrees | Check ability to express size preference; 15–30-degree preference is qualitative cohort evidence, not a fitted RF width or every-cell guarantee |
| Direction / state | 10/25-degree discs, +/-75 degrees/s, unstimulated/P1 labels | Aggregate progressive > regressive and P1 amplification are source constraints; nonzero regressive activity is allowed; exact ratios unavailable |
| Surround | Static, co-moving, counter-moving textured background | Mechanism diagnostic only; no verified numerical or universal suppression ordering |
| Contrast / polarity | -1, -0.5, -0.25, +1 Weber values | Report sensitivity; no fitted biological law or imposed bright/dark ranking |
| Stationary | Same finite target with zero velocity | Diagnostic; do not force complete neural silence without supporting evidence |
| AOTU bar | 11.25-by-60-degree bar at 25/75 degrees/s, two centers/two directions | Paper geometry, synthetic timing; archive association explicitly unverified |

Rendering checks must establish identical null movies, mirror consistency,
independent width/height, target/surround motion and reproducible histories.
Candidate response checks must retain both raw and observation-filtered activity,
report per-eye/per-map-provenance results and leave unsupported probes descriptive.
Qualitative inequalities show compatibility with assumptions, not validation of
275 cells. A point/Gaussian adapter may pass simple spatial probes while ignoring
size/surround; expose that loss of information explicitly.

## Implementation boundary and next deliverable

The finite-object renderer and probe runner are implemented in
[`retina.py`](../src/fly_creature/retina.py) and
[`run_lc10a_probes.py`](../tools/run_lc10a_probes.py). Their outputs are retinal
frames and geometry measurements, with no new neural model. See the
[renderer report](lc10a_sensor_renderer.md). Do not add fitted LC10a dynamics or
select a center/surround parameter sweep yet. Exact numerical size/contrast/surround
constraints remain incomplete, so a later shared center/surround response rule
would be a synthetic hypothesis requiring its own frozen protocol.

Keep the original AOTU benchmark as a downstream exploratory assay; retain exact
recording coverage, native timing and training-only calibration. Apply equal
visual information and parameter allowances to ordinary predictions and the
same 32 wiring controls. If input representation improves prediction, measure
whether intact wiring contributes beyond that improvement. Freeze response
parameters and thresholds before inspecting new candidate scores. Do not infer
causal P1 effects from archive filenames or feed descriptive motor correlations
back as sensory inputs. Godot promotion still requires closed-loop gates.

**Recommendation:** Luna Max for the defined renderer/probe-runner implementation;
Sol medium for choosing the subsequent response hypothesis and interpreting
physiology. This contract authorizes no physiological success claim.

## Reproduce this deliverable

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/build_lc10a_probe_matrix.py --output-dir fly-creature/outputs/research/lc10a-contract-v1
.\.venv\Scripts\python.exe fly-creature/tools/run_lc10a_probes.py --output-dir fly-creature/outputs/research/lc10a-render-v1
```

The builder checks unique probe IDs, legal geometry/contrast, aperture bounds
and the packaged map's coverage. Renderer outputs are described in the
[renderer report](lc10a_sensor_renderer.md). No neural response experiment,
unit-test suite, AOTU fit or Godot validation ran here.

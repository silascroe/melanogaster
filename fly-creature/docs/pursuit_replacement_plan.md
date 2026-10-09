# Replacement direction: build the missing visual-input boundary

## Why this direction

The [completed correction cycle](pursuit_goal_result.md) rejects a bounded
direction-skew/negative-offset fix. It does not show that more connectome neurons
would help, or prove the input is the sole fault. Stop fitting downstream output
corrections; make the retinal stimulus input explicit and inspectable.

The [LC10a research audit](lc10a_visual_input_research.md) and
[fresh primary-source note](lc10a_sensor_source_refresh.md) distinguish measured
constraints from assumptions. Size preference, calcium and spatial receptive
field width are different measurements. The older point-input adapter's
18-degree Gaussian remains an engineering choice; MaleCNS annotations do not
provide measured fields for each selected LC10a.

## Completed: contract and probe matrix

The [sensor contract](lc10a_sensor_contract.md) defines target shape, azimuth,
elevation, dimensions, contrast, independent surround motion and state metadata.
The reproducible 68-probe matrix keeps selected IDs/edges fixed and labels 164
mapped centers versus 111 fallback estimates. The source audit does not specify
a biologically measured response function with enough numeric detail to fit.

## Completed: retinal renderer and probe runner

The [renderer report](lc10a_sensor_renderer.md) describes the first runnable
boundary. The renderer makes a 176x32 image on the contract's 1.875-degree grid,
uses eight-by-eight subpixel coverage for target geometry and yields normalized
linear-luminance frames. The runner samples the chronology at each probe's
declared 2 ms step, records a time-series geometry/luminance CSV and a summary,
and saves labeled early/middle/late preview images in an SVG contact sheet.
It produces no neural activity, firing rates or behavior. The existing point
adapter remains untouched and outside this renderer.

## Completed: frozen response rule and probe gate

The [frozen design](lc10a_response_design.md) is now implemented offline by
`src/fly_creature/lc10a_response.py`. The [result](lc10a_response_result.md)
records the 68 six-second probes, paired target-absent surround conditions,
independent arithmetic/history checks, 0.197% worst raster difference against
the 5% limit, and byte-identical repeat. Its output is dimensionless LC10a
activity. The later recorded benchmark projects it through LC10a-to-AOTU
contacts and scores it against physiology. Production and Godot are unchanged.

## Completed: recorded AOTU comparison and bounded diagnosis

The [reviewed implementation contract](lc10a_response_benchmark_protocol.md)
now specifies exact full-trial history, post-ELU hemisphere averaging, fixed
lookup/quantization handling, audited calibration indices and explicit shuffle
matrices. The raw target and legacy calibration audit passes. The frozen runner
and independent checker completed all 69 units; see the
[recorded result](lc10a_recorded_benchmark_result.md). Both practical P1
prediction gates failed. Intact wiring beats shuffled wiring but does not
establish useful superiority over matched spatial weights.

The [bounded diagnosis](lc10a_response_diagnosis.md), completed 9 October,
localizes most recoverable loss to the transferred temporal envelope. Removing
it recovers fit only to approximately legacy performance and still fails the
joint practical gates. Native/cache replay and source-equation checks pass.
Retire this primary candidate rather than tuning its constants on the archive.
Keep the frozen runner/results, renderer and anatomy as inspectable evidence.

## Next decision boundary

The [downstream contract](pursuit_downstream_contract.md) now defines a smaller
question: supply measured AOTU population responses to the signed MaleCNS
AOTU→DNa02 bridge and compare its predicted pulse responses with independently
recorded DNa02 responses and equally weighted signed routing. First implement
only Phase A: verify archive metadata, state, geometry, filtering and common
25°/s quiet-pulse coverage before opening DNa02 response values. Stop if
compatibility is unresolved. No new neural simulator or controller is needed.

**Recommended settings:** Luna Max for the bounded Phase A metadata audit;
Sol medium for compatibility gaps and final Phase B protocol review.
The passing probe checks validate implementation arithmetic, not biology or a
connectome-specific advantage.

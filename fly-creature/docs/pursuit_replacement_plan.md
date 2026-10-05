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
activity. It has not yet been projected through the LC10a-to-AOTU contacts or
scored against recorded physiology. Production and Godot are unchanged.

## Next experiment boundary: recorded AOTU comparison

The [reviewed implementation contract](lc10a_response_benchmark_protocol.md)
now specifies exact full-trial history, post-ELU hemisphere averaging, fixed
lookup/quantization handling, audited calibration indices and explicit shuffle
matrices. The raw target and legacy calibration audit passes. Use that contract
and its machine-readable freeze for the next runner; the new responses have
not been scored against recordings.

Implement the separate frozen `lc10a_response_benchmark.py` runner using the
existing recording readers, extraction, and scoring. Verify extraction,
calibration indices, legacy outputs, and contact weights against old evidence
before candidate scoring. Compare the fixed image response through the
unchanged LC10a-to-AOTU weights against legacy, matched-spatial, flat, and the
existing 32 within-side wiring shuffles under equal information and calibration
budgets. Keep the existing gates and holdouts; do not fit fields to the archived
responses. Reused recording holdouts remain exploratory. If intact wiring does
not beat matched controls, report that plainly. Godot still requires separate
closed-loop stability and fresh-path evidence.

If sources cannot constrain the proposed response rule, document the gap and
keep it labeled synthetic. If sensory fit improves but intact anatomy does not
beat matched controls, report that plainly. Godot still requires existing
closed-loop stability and fresh-path controls.

**Recommended settings:** Luna Max for the bounded benchmark implementation;
Sol medium for protocol review and interpretation of the recorded comparison.
The passing probe checks validate implementation arithmetic, not biology or a
connectome-specific advantage.

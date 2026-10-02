# Replacement direction: build the missing visual-input boundary

## Why this direction

The [completed correction cycle](pursuit_goal_result.md) rejects a bounded
direction-skew/negative-offset fix. It does not show that more connectome neurons
would help, or prove the input is the sole fault. Stop fitting downstream output
corrections; make the retinal stimulus input explicit and inspectable.

The [LC10a research audit](lc10a_visual_input_research.md) and
[fresh primary-source note](lc10a_sensor_source_refresh.md) distinguish measured
constraints from assumptions. Size preference, calcium and spatial receptive
field width are different measurements. Our 18-degree Gaussian remains an
engineering choice; MaleCNS annotations do not provide measured fields for each
selected LC10a.

## Completed: contract and probe matrix

The [sensor contract](lc10a_sensor_contract.md) defines target shape, azimuth,
elevation, dimensions, contrast, independent surround motion and state metadata.
The reproducible 68-probe matrix keeps selected IDs/edges fixed and labels 164
mapped centers versus 111 fallback estimates. No response function is specified
by the source audit with enough numeric detail to fit yet.

## Completed: retinal renderer and probe runner

The [renderer report](lc10a_sensor_renderer.md) describes the first runnable
boundary. The renderer makes a 176x32 image on the contract's 1.875-degree grid,
uses eight-by-eight subpixel coverage for target geometry and yields normalized
linear-luminance frames. The runner samples the chronology at each probe's
declared 2 ms step, records a time-series geometry/luminance CSV and a summary,
and saves labeled early/middle/late preview images in an SVG contact sheet.
It produces no neural activity, firing rates or behavior. The existing point
adapter remains untouched and outside this renderer.

## Next experiment boundary

First inspect whether the finite raster preserves the declared geometry and its
mirrors. Then specify one shared hypothetical center/surround response rule with
a small frozen parameter budget, citing the source constraint for each parameter.
Keep any LC10a rate/state dynamics separate from image geometry. Do not fit 275
individual fields to downstream AOTU responses, treat calcium amplitude as
spikes/s, or infer receptive field width from preferred object size.

Replay the existing AOTU benchmark only after that sensor contract check, using
the frozen recording coverage and exact recorded timestamps. Apply equal visual
information/calibration freedom to anatomy, the same wiring shuffles and a
non-neural controller. Separate improvement due to the pixels/features from
improvement due to wiring. Reused-data recording holdouts remain exploratory;
reserve genuinely new stimuli/data for confirmation. Freeze coverage and gates
before looking at candidate scores.

If sources cannot constrain the proposed response rule, document the gap and
keep it labeled synthetic. If sensory fit improves but intact anatomy does not
beat matched controls, report that plainly. Godot still requires existing
closed-loop stability and fresh-path controls.

**Recommended settings:** Sol medium for designing/interpreting the response
hypothesis; Luna Max for a frozen implementation and checks. A rendered retinal
image is the new concrete output. It is not a claim that the biological input
path or pursuit behavior has been fixed.

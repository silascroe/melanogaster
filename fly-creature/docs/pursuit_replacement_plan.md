# Replacement direction: define and test the LC10a visual input

## Why this direction

The [completed correction cycle](pursuit_goal_result.md) rejects a bounded
direction-skew/negative-offset fix. It does not show that more connectome neurons
would help, or prove the input is the sole fault. It gives a reason to stop
fitting output corrections and interrogate the sensory assumptions directly.

The [LC10a research audit](lc10a_visual_input_research.md) records the relevant
primary evidence: LC10 small-object responses and antagonistic motion surround
(Ribeiro 2018), spatial ordering (Aptekar 2015), state-dependent directional
responses (Hindmarsh Sten 2021), and LC10a object-size preferences (Schretter
2025). These constrain an input hypothesis, but calcium, object-size preference,
and a neuron's receptive-field width are different measurements. The existing
18-degree Gaussian width is our assumption. MaleCNS annotations do not provide
measured receptive fields for each selected neuron.

## First milestone: a source-grounded sensor contract

Completed in the [sensor contract](lc10a_sensor_contract.md), fresh source note
and 68-probe matrix. Neural responses have not been evaluated. The next bounded
implementation is the finite-object renderer/probe runner described there.

Create an offline retinal-stimulus/LC10a probe matrix before rewriting pursuit.
Its input must describe finite target azimuth/elevation, angular width/height,
contrast against a declared background, trajectory and surrounding motion over
time. Its output is an explicitly hypothetical activity per selected LC10a
neuron, before AOTU projection, decoder or body movement. Use the registered eye
map with its 164 mapped/111 fallback centers and uncertainty labels; keep the
selected graph and synapse weights frozen.

First resolve what each reference actually supports numerically. Document the
recording modality, stimulus dimensions, direction convention, state and missing
metadata for every intended check. The previous source audit could not locate
the numerical Fig. 3a size-tuning data in the inspected public deposit. A declared
figure digitization with uncertainty is an option if a usable figure exists;
do not manufacture exact tuning values. Verify the AOTU motion-pulse stimulus
dimensions from acquisition records before calling a retinal replay matched.

The initial probe cases are: isolated small versus large objects at a fixed
center; object motion with a static versus moving surround; progressive versus
regressive motion; and target absence/contrast changes. Define evidence-backed
qualitative constraints and any available numeric ranges before implementing.
Do not demand selectivity or suppression that the cited measurement cannot show.

## Candidate and comparison budget

If the evidence supports a finite-object center/surround hypothesis, implement
one shared sensor rule with declared units and a small frozen parameter budget.
Keep any LC10a rate/state dynamics separate from image geometry. Do not fit
275 independent receptive fields to downstream AOTU responses or treat calcium
amplitude as spikes/s. Do not infer receptive-field width from preferred object
size. Retain the point/Gaussian adapter as the explicit baseline.

Check the sensor contract first. Only then replay the existing AOTU benchmark
with intact wiring, the same fixed shuffles and a non-neural spatial controller
receiving equivalent visual information and calibration freedom. Separate
upstream sensory improvement from downstream wiring contribution. Recording
holdouts on reused data remain exploratory; reserve genuinely new stimuli or
data for confirmation. Freeze the evaluation coverage and acceptance thresholds
before inspecting candidate scores. Preserve unfavorable results.

## Stop and promotion conditions

If public evidence cannot constrain the proposed rule, finish with a documented
data gap and a clearly labeled synthetic hypothesis; do not claim physiological
validation. If its LC10a checks fail, revise or reject at that boundary before
running a parameter sweep on AOTU. If it improves sensory agreement but anatomy
does not beat matched ordinary/shuffled controls, report that limit plainly.
Godot promotion additionally requires the existing closed-loop stability and
fresh-path controls; a prettier response curve alone is insufficient.

**Recommended settings:** Sol medium for the source/contract decisions and
interpretation; Luna Max for a frozen implementation with concrete checks.
The next deliverable is the contract and probe matrix, not a promise that this
sensor change will fix the fly.

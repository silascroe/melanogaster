# Moving-target neural pursuit milestone

The fly now visibly changes heading toward a small green target that sweeps
across the room. Press `V` in the playable scene, or record an automatic run
with `--pursuit-demo`. Press `C` to restart with the selected steering bridge
removed. The [intact clip](../outputs/pursuit/pursuit_intact.mp4) and
[disconnected clip](../outputs/pursuit/pursuit_disconnected.mp4) were recorded
from Godot at 1280×720, 60 fps for eight seconds. `outputs/` is local and
ignored by Git; the scene can reproduce both clips.

## What each piece does

Godot moves the green target horizontally along
`x = 3.2 sin(0.62t − 1.2), z = −6.5` and reports its position plus the fly's
position and heading every 50 ms. Python computes the target's bearing
relative to the fly. An object within ±65° and 0.4–9 m drives all selected
LC10a cells on its side, with current increasing from 0 beyond a 3° dead zone
to 90 mV of model input at 35°. This is an engineered lateralized visual
feature, not reconstructed retinal processing or measured LC10a tuning.

The packaged [Male CNS candidate circuit](../src/fly_creature/data/visual_steering_v1.json)
contains 281 traced cells and 366 recorded direct edges through
LC10a → AOTU019/AOTU025 → DNa02. The creature's 1 ms LIF model runs these
edges with one-step delay. It treats acetylcholine as positive and GABA as
negative current, at 0.05 mV per recorded synapse. Those signs and coupling
are modeling assumptions. The model records mean left and right DNa02
voltages over each 50 ms world step.

An engineered motor decoder multiplies **right minus left DNa02 voltage** by
0.42 rad/s per mV and caps the requested turn at ±1.2 rad/s. Godot applies
that turn and moves the fly forward at 0.55 m/s using its existing walk
animation. The next neural step sees the changed fly heading, closing the
loop. The fixed square-pulse probe in [the candidate study](steering_candidate.md)
produced no DNa02 spikes; this milestone deliberately uses subthreshold
voltage. It does not claim the real fly uses this motor decoder.

## What the controls showed

The `disconnected` condition preserves the LC10a-to-AOTU connections and
removes only the AOTU-to-DNa02 bridge for steering. The same scripted target
and forward speed are used. In the recorded Godot demo, the intact fly turns
left and then right, while the disconnected fly keeps its original heading.
The `C` key also disconnects the independent jump circuit, but no looming
object is active during pursuit.

The [closed-loop diagnostic](../src/fly_creature/pursuit_diagnostic.py) uses the
same target path and two further paths. It also removes each AOTU output
branch separately, without changing the target or motor rule. Its
[frame-by-frame result](evidence/pursuit_closed_loop_v1.json) is reproducible
with `python -m fly_creature.pursuit_diagnostic`. Mean absolute target bearing
over eight seconds was:

| Target path | Intact | Both outputs removed | AOTU019 output removed | AOTU025 output removed |
| --- | ---: | ---: | ---: | ---: |
| Crossing | 10.389° | 23.103° | 18.616° | 10.938° |
| Mirrored crossing | 10.389° | 23.103° | 18.949° | 10.948° |
| Faster crossing | 10.500° | 26.674° | 23.095° | 11.211° |

These are three configured simulator scenes, not a biological validation or
a broad robustness result. Godot telemetry and inspected frames separately
confirmed that the playable scene receives the neural turn signal and shows
the corresponding change in heading. In this configured model, the AOTU019
branch carries most of the useful correction. That conclusion concerns this
input pattern, synapse-to-current scale, and voltage decoder; the branch
ablation is not evidence that AOTU025 is unimportant to a real fly.

## Next development loop

This is a usable visual milestone. The next useful question is sensory
specificity: our input excites every LC10a cell on one side together, whereas
the real population has visual-field structure and is associated with small
moving objects. The Male CNS annotation rows for these 275 LC10a cells have
no assigned optic-lobe hex coordinates, so the release does not give us a
ready-made per-cell receptive-field map. [Collie et al.](https://doi.org/10.1016/j.neuron.2026.01.001)
report that AOTU019 samples LC10a cells associated mainly with frontal vision,
while AOTU025 samples more lateral cells, in a different connectome analysis.
The next loop should check whether the Male CNS connection patterns can support
a *stated hypothesis* for frontal/lateral subsets and compare it with this
whole-side baseline under the same target paths and controls. Keep the current
demo playable while the alternative is evaluated. A more refined model should
replace this input only if it gives a clearer, supported signal; increasing
gain merely to force DNa02 spikes would not answer that question.

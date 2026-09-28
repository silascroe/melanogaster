# Local LC10a motion input: fixed-charge experiment

**Decision: keep this candidate offline.** It fixes the previous motion
rule's loss of total visual drive, but does not improve pursuit over the
position-only input. It also fails to produce the outward-motion preference
seen in the frontal AOTU019 pathway.

## The change

The upstream-derived LC10a map assigns each selected cell a provisional
visual center. On each 20 ms step, the new input compares that cell's
position weight with its weight on the previous step. A positive change means
the object's image is entering that *modeled* receptive field. While the
target moves, half the existing side current follows the original position
weights and half follows those positive local changes. When no field weight
rises, including a static target, the original position weights receive all
the current. The sum of current sent to the stimulated side is unchanged at
the same target bearing.

That **50/50 split**, the 18° field width, 0.1 field floor, visual-center
angles, and 20 ms sampling are engineered. They were fixed before scoring
the new paths and were not fitted to LC10a response measurements. The input
depends on *retinal* image movement, which can include the fly's own turn.
It does not assign a biological direction preference to individual LC10a
cells. [Experiments](https://pubmed.ncbi.nlm.nih.gov/25972183/) support local
LC10a receptive fields and direction-dependent responses, while
[AOTU recordings](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) show
stronger outward-motion preference near the visual midline. They do not
measure the particular per-cell filter implemented here.

The selected **281-cell, 366-edge MaleCNS route**, LIF dynamics, input-current
scale, DNa02 voltage-to-turn gain, walking speed, view gate, and turn cap
were held fixed. Only the sensory distribution changed. The optional
per-cell-weight input in `SteeringSession.step` is unused by the playable
runtime unless explicitly supplied; Godot and service defaults are unchanged.

## Fixed fly: does it actually change the circuit?

A fixed fly saw static, inward, and outward **22.5°** object sweeps at
**25°/s** and **75°/s**, centered at modeled 25° and 45° positions on both
sides. Position-only and local-motion trials received equal total side
current at every step; **0 of 24** matched pulse settings had a current-sum
mismatch. Static trials produced exactly the same neural counts and voltage
bias under both inputs. Moving trials redistributed the same current among
LC10a cells and changed AOTU and DNa02 responses.

The response went the wrong way for the desired frontal direction cue.
Across eight paired side/center/speed conditions, AOTU019 responded more to
**inward** movement in seven and equally in one; outward movement won none.
For a right-side 25° center at 25°/s, the local input gave **107 AOTU019
spikes** for either motion direction, versus **129 outward / 130 inward**
with position-only input. At a right-side 45° center, local input gave
**71 outward / 120 inward**. AOTU025 and DNa02 voltage also changed, but
the simple leading-edge redistribution did not recover the published
frontal outward preference. DNa02 still did not spike at unchanged LIF
settings.

## Closed-loop check on five new paths

Five deterministic target paths were defined before scoring this candidate:
weave, abrupt offset hops, approach arc, lateral drift, and a small
flutter. Each lasts eight seconds. Lower mean absolute bearing error means
better target centering; it is not a biological-behavior score.

| Input or control | Mean bearing error |
|---|---:|
| Direct-bearing software controller | 8.113° |
| Playable whole-side input | 9.195° |
| Upstream-map position input | 10.297° |
| **New local-motion input** | **10.775°** |
| Previous global speed gate | 14.681° |
| Median of 12 local-input wiring shuffles | 11.532° |
| New local input, AOTU→DNa02 bridge removed | 20.067° |

The local version beat position-only on **1/5** paths, playable whole-side
on **0/5**, and direct bearing on **0/5**. It beat the wiring-shuffle median
on **5/5**. That shows dependence on the selected modeled connections, but
not an advantage in pursuit. The predeclared promotion gate required lower
mean error than position-only, playable, and direct control, at least three
path wins over each, and at least three wins over shuffled wiring. It failed.

The two failed motion ideas are informative in different ways. The global
speed gate largely silenced the circuit. This local alternative preserved
side current but redistributed it in a way the selected outputs did not
usefully decode. Merely keeping charge constant is insufficient. Further
blind changes to the mixture fraction would fit this benchmark without
answering the biological question. Any next visual revision needs a more
specific, independently constrained account of LC10a direction responses;
the present playable input remains the honest demonstration default.

Full fixed-fly and per-path summaries:
[local_motion_experiment_v1.json](evidence/local_motion_experiment_v1.json).
Reproduce from `fly-creature/`:

```powershell
$env:PYTHONPATH="src"
..\.venv\Scripts\python.exe -m fly_creature.local_motion_experiment --output docs/evidence/local_motion_experiment_v1.json
```

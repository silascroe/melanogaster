# Independent visual-axis check and motion-input test

**Decision: keep the playable input unchanged.** An upstream-derived MaleCNS
map independently supports the *ordering* of the earlier LC10a skeleton map.
It does not supply measured retinal angles. A fixed, speed-sensitive input made
the modeled circuit distinguish static from moving targets, but made pursuit
substantially worse under the unchanged neural runtime and motor readout.

## Where the new map comes from

The [MaleCNS release](https://male-cns.janelia.org/download/) contains
`assignedOlHex1/2` for many optic-lobe columnar neurons, direct connection
weights, and LC10a skeletons. We traced **incoming** connections from those
columnar neurons to each of the 275 selected LC10a cells, using weighted
horizontal column position `hex2 - hex1`. The [Nern et al. optic-lobe
analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC12119369/) places the
frontal side at the low end of this horizontal eye-map coordinate. The
[Hoeller et al. MaleCNS visual-pathways work](https://pubmed.ncbi.nlm.nih.gov/42691997/)
also predicts anatomical visual fields, but its public [LC10a gallery](https://github.com/reiserlab/visualpathways)
is a type-level view, not a table of measured visual angles for our body IDs.

Incoming mapped column contacts reach **112/135 left** and **136/140 right**
LC10a cells. Their horizontal coordinate correlates with distal LC10a
skeleton y position at **0.958 left** and **0.961 right**. This provides an
orientation check that does not inspect LC10a outputs to AOTU019, AOTU025, or
DNa02. But left-side direct coverage is thin: only **41 left** cells have at
least three mapped incoming column edges, versus **123 right**. For cells
below that threshold, a side-specific linear fit from upstream coordinate to
skeleton y supplies the position. The resulting **164 direct / 111 geometric
fallback** assignments are packaged in
[`lc10a_upstream_hypothesis_v2.json`](../src/fly_creature/data/lc10a_upstream_hypothesis_v2.json).
The final conversion of within-side position rank into **5°–60°** visual
centers is still an engineering approximation. It is not a measured
receptive-field map. The new centers correlate **0.980** with the earlier
skeleton map and differ by **2.05° on average**.

Rebuild the compact map from `fly-creature/` with the local official release
and downloaded official SWCs:

```powershell
..\.venv\Scripts\python.exe tools\derive_lc10a_upstream_map.py --annotations ..\data\working\male-cns-v1.0\body-annotations-male-cns-v1.0-minconf-0.5.feather --weights ..\data\working\male-cns-v1.0\connectome-weights-male-cns-v1.0-minconf-0.5.feather --skeleton-dir outputs\lc10a_skeletons --output src\fly_creature\data\lc10a_upstream_hypothesis_v2.json
```

## Motion input, fixed before comparing pursuit scores

[Ribeiro et al.](https://pubmed.ncbi.nlm.nih.gov/30033367/) showed that LC10
neurons preferentially respond to small moving objects. This licenses asking
whether a motion-sensitive input helps our model; it does **not** calibrate a
current waveform. The experimental rule measures absolute change in target
bearing across 20 ms world steps and multiplies the existing current by
`0.2 + 0.8 × min(retinal speed / 25° per second, 1)`. Static targets retain
20% of the former input. All LC10a cells receive the same motion factor; their
spatial weighting comes from the new map. The rule contains no direction
preference, contrast model, or arousal state. During pursuit, turning the fly
itself changes retinal bearing and therefore contributes to this speed signal.

A fixed-fly probe reused the earlier 100 ms baseline and 400 ms pulse protocol
at 12°, 25°, 40°, and 55° on both sides. At right 25° with matched base
current, a static target changed the modeled AOTU019/AOTU025 spike counts
from **66/22** under position input to **8/0** under motion input. An outward
25°/s sweep gave **55/20**, an inward sweep **59/20**. The modeled DNa02
toward-side voltage bias was **0.257 mV static**, **2.393 mV outward**, and
**2.540 mV inward** with the motion rule. Thus the **engineered input**
suppresses static responses, but the circuit still does not reproduce the
robust frontal AOTU019 direction preference measured by
[Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/).
No modeled DNa02 cell spiked in the fixed or pursuit trials.

## Closed-loop comparison

Five eight-second paths from the earlier experiment were replayed without
changing the 281-neuron circuit, 366 selected edges, LIF dynamics, walking
speed, visual-field gate, voltage decoder, or turn cap. Lower mean absolute
target bearing means better centering. The simple direct-bearing rule has no
neural graph. The shuffled control permutes whole LC10a output bundles within
each side, preserving the selected cells and edge weights.

| Input / controller | Mean error on five paths |
|---|---:|
| Direct-bearing software rule | 9.088° |
| Playable whole-side input | 9.903° |
| Earlier skeleton-position input | 11.522° |
| New upstream-oriented position input | 11.428° |
| New upstream-oriented **motion** input | **17.102°** |
| Median of 12 motion-input wiring shuffles | 19.695° |

The motion version lost to the playable uniform input and the direct rule on
**all five** paths, although it beat the median shuffled wiring on all five.
That is evidence the selected modeled connections affect the response under
this input, not evidence of useful pursuit or biological fidelity. The motion
factor weakened drive over much of each path, and the present decoder turns
from DNa02 *voltage* even when DNa02 never spikes. This experiment does not
isolate which of those two assumptions causes most of the tracking loss.
These five paths were previously used for v1, so this is a repeated comparison,
not untouched validation. The map, motion rule, and promotion criterion were
fixed before inspecting the v2 scores; no post-result gain tuning was done.

The predeclared promotion gate required the motion version to beat both the
playable input and direct rule in mean error and on at least three of five
paths, and the shuffle median on at least three. It failed the first two
requirements (**0/5** each). **Do not enable this input in Godot.** The
independent upstream-axis result is worth retaining; the simple motion gate
is a failed behavioral candidate. Further work on this route would need a
better grounded input waveform and a separately justified DNa02 readout,
not another arbitrary gain adjustment.

Full compact fixed-fly and path summaries:
[`visual_motion_experiment_v2.json`](evidence/visual_motion_experiment_v2.json).
Reproduce from `fly-creature/` using the workspace virtual environment:

```powershell
$env:PYTHONPATH="src"
..\.venv\Scripts\python.exe -m fly_creature.visual_motion_experiment --output docs/evidence/visual_motion_experiment_v2.json
```

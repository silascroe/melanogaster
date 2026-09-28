# First per-cell visual-input experiment

**Result:** A skeleton-derived input assignment made the identity of the selected MaleCNS connections matter, but did **not** improve pursuit. The playable scene still uses the original whole-side input. This is an offline anatomical hypothesis, not a measured map of what each LC10a neuron sees.

## Why this assignment exists

The local MaleCNS annotation rows have no filled optic-lobe hex fields for the 275 selected LC10a cells. The [official release](https://male-cns.janelia.org/download/) does provide an SWC skeleton for each body ID. We downloaded those 275 skeletons from the official release (12.8 MB total) into ignored `outputs/lc10a_skeletons/`, then used a fixed distal optic-lobe point window (`y < 20000`, `z < 26000`, MaleCNS 8 nm voxel coordinates). Every selected skeleton had at least 156 points in that window. This is a reproducible **geometric proxy**, not an official segmented lobula ROI or an eye-to-brain registration.

For each hemisphere separately, [the derivation tool](../tools/derive_lc10a_map.py) ranks the median `y` position of those points. It maps that rank linearly to a provisional 5°–60° absolute target-bearing center. Low `y` is provisionally frontal. A cross-check against this MaleCNS circuit found that low-`y` cells tend to devote more of their selected AOTU output to AOTU019: Pearson correlations were −0.802 left and −0.788 right. Thirty-five LC10a cells have no edge to either selected AOTU type and count as 0.5 in that cross-check. The orientation is partly inferred from that wiring association and [Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/), who found a frontal AOTU019 preference and a more lateral AOTU025 preference. Their anatomical map was from **female FAFB/FlyWire**, while their recordings included males. Thus the correlation is a useful consistency check, but neither it nor the paper measures retinal degrees for these individual MaleCNS body IDs.

The complete 275-body-ID assignment, source URLs, input-window rule, and ordered source-skeleton digest are in [lc10a_anatomy_hypothesis_v1.json](../src/fly_creature/data/lc10a_anatomy_hypothesis_v1.json). The JSON travels with `fly-creature/`; raw skeletons do not. Reproduce the local derivation from the official source with:

```powershell
python tools/fetch_lc10a_skeletons.py --output-dir outputs/lc10a_skeletons
python tools/derive_lc10a_map.py --skeleton-dir outputs/lc10a_skeletons --output src/fly_creature/data/lc10a_anatomy_hypothesis_v1.json
```

## Fair comparison and its limits

The experiment changes **only which LC10a cells receive how much of the existing bearing-based current**. Each cell receives a broad 18° Gaussian around its provisional center plus a 0.1 floor. The currents are normalized so that the total current delivered to the stimulated hemisphere is identical to the old whole-side input at every target bearing. Those width, floor, and angle-range choices are engineering assumptions fixed before the behavioral comparison. Python still gets the exact scripted target position; this does not simulate camera pixels, retinal transduction, or object-motion selectivity.

The controls are the old uniform input; the anatomical input with AOTU-to-DNa02 bridges removed; a simple direct-bearing turner with the same view gate and turn cap; and 12 seeded shuffles of LC10a output **bundles** within each hemisphere. Each shuffle preserves the cells, synapse counts, AOTU/DNa02 targets, signs, and total connection inventory while changing which anatomical input assignment meets which LC10a output bundle. A uniform-input shuffle produced the same trajectory to three decimal places, as it should when every cell on a side is driven alike. The bridge and motor decoder were not tuned. The five new target paths were defined without using their scores to choose the anatomy map or its input parameters.

Mean absolute target bearing over eight seconds is the centering score; **lower is better**. These are the five new paths; all ten paths and all shuffle scores are in [visual_input_experiment_v1.json](evidence/visual_input_experiment_v1.json).

| New target path | Anatomy | Old uniform | Median shuffle | Direct rule | Bridge removed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Two reversals | 12.61° | 11.18° | 13.32° | 11.35° | 18.64° |
| Offset sweep | 7.97° | 6.99° | 8.49° | 5.17° | 30.31° |
| Near target | 16.28° | 13.00° | 18.94° | 13.09° | 38.93° |
| Far target | 10.01° | 8.87° | 10.76° | 8.02° | 17.49° |
| Stop and go | 10.75° | 9.48° | 11.79° | 7.81° | 28.88° |

The anatomy input beat **every one of the 12 wiring shuffles on all ten paths**, and it beat bridge removal. That is evidence of a useful *input-to-wiring alignment in this configured simulator*. It is not independent validation of per-cell visual fields: we chose the axis direction partly from the same connection preferences later disrupted by shuffling. More decisively, it lost to both the old uniform input and the direct rule on **all five new paths**. Their five-path mean errors were 11.52° (anatomy), 9.90° (uniform), and 9.09° (direct). No modeled DNa02 cell spiked; the motor output still comes from the engineered voltage decoder. Better than shuffled does not mean good enough to promote.

## Decision

Keep the current playable default. This experiment succeeded in making a clear, repeatable test of *which LC10a body ID receives which input*. It failed to show better tracking or a fly-specific advantage. A stronger next input would need a visual-field assignment derived independently of the selected output wiring—ideally registered lobula anatomy plus functional measurements—and should represent object motion as well as position. Then rerun these same controls and new paths, without using demo score to invent the receptive fields after the fact.

The [fixed-fly pathway follow-up](visual_pathway_probe.md) shows what the two AOTU branches and DNa02 did under this input, separating spatial response from the existing current-amplitude rule and testing matched inward/outward motion pulses.

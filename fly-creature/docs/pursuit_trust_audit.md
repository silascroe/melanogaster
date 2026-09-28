# How much of the pursuit result can we trust?

**Short answer:** The current playable fly visibly steers because a chosen visual feature drives a selected MaleCNS circuit, whose modeled voltage is converted to a turn command. The selected wiring matters *inside this model*. These comparisons do not show that the fly connectome is necessary or better than a simple controller, and they do not establish real fly pursuit.

The reproducible results are in [pursuit_trust_audit_v1.json](evidence/pursuit_trust_audit_v1.json). Run them from `fly-creature/` with `python -m fly_creature.pursuit_trust_audit --output docs/evidence/pursuit_trust_audit_v1.json`. The playable default, its circuit, input current, decoder, and Godot scene were not changed for this audit.

## What was checked

The fixed baseline uses an eight-second world, 0.55 m/s forward walk, 50 ms world updates, 1 ms neural updates, 90 mV maximum modeled LC10a input, and the same ±65° engineered target view. All four controllers receive the target position directly from the scripted world. Each comparison changes one path, input strength, or update interval from that baseline. A 3° bearing dead zone and ±1.2 rad/s turn cap are unchanged. Input-strength changes affect the neural controller only; the direct controller's rule is fixed.

`intact` uses the selected circuit. `disconnected` removes its AOTU-to-DNa02 bridge. `bridge_side_swapped` retains the same bridge synapse counts and transmitter signs but sends each bridge to the other DNa02 cell. This is a synthetic wiring control, not a second measured connectome. `direct_bearing` bypasses the network and uses the same engineered bearing strength, field-of-view gate, dead zone, and turn-rate cap. It is a deliberately simple comparison, not a tuned competitor. Mean absolute target bearing includes frames when the active target leaves the field of view; lower means better centering in this particular scripted world.

| Target path | Intact | Bridge removed | Side swapped | Direct bearing |
| --- | ---: | ---: | ---: | ---: |
| Crossing, baseline | 10.35° | 23.07° | 78.57° | 10.15° |
| Mirrored crossing | 10.39° | 23.07° | 78.52° | 10.15° |
| Faster crossing | 10.50° | 26.51° | 92.85° | 10.72° |
| Slower crossing | 8.77° | 25.33° | 64.84° | 7.39° |
| Narrow crossing | 6.83° | 9.45° | 69.64° | 5.43° |
| Stationary target | 8.63° | 31.98° | 81.16° | 4.26° |

The intact model centers better than either wiring intervention on all six active paths. Its lead over the direct controller is small and occurs only on the faster crossing here (0.22°). The direct controller matches or beats it on the other five paths. The absent-target run produced zero turn in every condition. Across active paths, the intact and direct controllers kept the target within the encoded view for all sampled frames; the side-swapped controller often lost it. No modeled DNa02 cell spiked in any neural trial. Steering reads a *subthreshold voltage difference* and multiplies it by an engineered motor gain.

## Sensitivity and failures

With the crossing path and 50 ms world update held fixed, intact mean bearing was 18.64°, 15.47°, 13.25°, 11.59°, 10.35°, and 8.72° at maximum LC10a input currents of 30, 45, 60, 75, 90, and 120 mV. The disconnected run stayed at 23.07°; the direct controller stayed at 10.15° because its rule does not use that model current. The result is meaningfully sensitive to an arbitrary input amplitude. The 120 mV result is not evidence that 120 mV is biologically right.

At 25, 50, and 100 ms world updates, holding the baseline path and current, intact mean bearing was 10.32°, 10.35°, and 10.43°. The direct controller scored 10.10°, 10.15°, and 10.24°. This limited interval range showed little change; it does not establish stability at slower updates, with noise, or over longer pursuit. The scripted stationary target also causes this position-based encoder to keep steering, even though LC10a experimental responses include motion and visual-context dependence. That exposes what this encoder lacks; it does not prove the real fly would ignore a stationary target.

The old [pursuit milestone](pursuit_milestone.md) used its earlier offline target sampling convention. This audit samples the target after each world step, approximating the current Godot update order; live HTTP request timing is not reproduced. Its baseline number need not exactly equal the older JSON. The playable default's original offline replay result was separately checked for exact equality after the feature-encoder refactor. A three-second headless Godot 4.7 smoke run also reached the local Python service and produced a nonzero pursuit turn. That checks integration, not visual quality or long-run behavior.

## What is measured and what is invented

The [official MaleCNS v1.0 release](https://male-cns.janelia.org/download/) supplies the body IDs, type labels, predicted transmitter annotations, and the 366 selected direct synapse-count edges. A fresh read-only extraction from the current working release reproduced the packaged 281-neuron circuit **byte for byte** (SHA-256 `12da5553adbfe4d8164e861786879dc71e7468a787420a66e7b3def5a5658c4c`). `python -m flytest.verify` also confirmed all three working Feather files match their untouched original copies. None of the 275 MaleCNS LC10a annotation rows has `assignedOlHex1` or `assignedOlHex2` filled in. Their individual visual fields are not supplied by those fields.

Primary experiments support LC10a responses to small visual objects, spatially structured responses, and a route through AOTU cells associated with pursuit. [Ribeiro et al.](https://pubmed.ncbi.nlm.nih.gov/30033367/), [Aptekar et al.](https://pubmed.ncbi.nlm.nih.gov/25972183/), [Hindmarsh Sten et al.](https://www.nature.com/articles/s41586-021-03714-w), and [Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) support these narrower statements. Collie's mapping of frontal AOTU019 and more lateral AOTU025 input used a **different, female FAFB/FlyWire connectome**, though the paper also reports male physiology and behavior. It is not a MaleCNS per-cell receptive-field map. See the [source review](lc10a_visual_input_research.md) for the evidence and limits.

Every LC10a cell on one side currently gets the **same** current from a hand-coded target bearing. The one-step-delayed LIF dynamics, ACh/GABA sign convention, current-per-synapse coupling, voltage subtraction, turn gain, view bounds, walking speed, and target motion are model or game choices. A model comparison can show that those choices route a signal through these edges. It cannot distinguish the value of the fly's precise LC10a connections from the value of a generic left/right steering arrangement when all selected cells on each side are driven together. The direct-bearing result makes that limit concrete.

The next scientific improvement is a sourced visual input hypothesis that distinguishes individual or grouped LC10a cells, with an explicit body-ID assignment and the same controls. Lobula anatomy and functional mapping may help construct one, but any inferred retinal angles and currents must remain labeled as hypotheses until supported by matching measurements. A better demo score alone is insufficient.

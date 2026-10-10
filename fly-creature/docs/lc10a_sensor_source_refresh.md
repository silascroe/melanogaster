# LC10a sensor contract: primary-source refresh

2026-10-02. Research for an offline contract/probe matrix only. No simulator,
connectivity, motor decoder or production settings changed. This supplements
[the earlier source audit](lc10a_visual_input_research.md).

## Verified source constraints

### Ribeiro et al., Cell 2018

The primary abstract states that LC10 preferentially responds to small moving
objects through an antagonistic motion-based center/surround mechanism.
This supports including surrounding motion in the proposed input contract;
it does not supply numerical center/surround widths, weights, contrast curves,
or individual LC10a fields here. The broad LC10 statement must not silently
become a quantitatively measured property of each MaleCNS LC10a body ID.
[Author institution publication page](https://www.janelia.org/publication/visual-projection-neurons-mediating-directed-courtship-in-drosophila),
[PubMed abstract](https://pubmed.ncbi.nlm.nih.gov/30033367/).

Access limit: PubMed direct opening returned an effectively empty page; its
indexed abstract and the Janelia publication page were readable. The publisher
[full article](https://www.sciencedirect.com/science/article/pii/S0092867418307888)
returned an internal fetch error. Exact stimulus dimensions, measurement
compartment and state-specific quantitative effects were not refreshed.
Do not present a universal background-suppression ordering as verified from
the abstract alone.

### Hindmarsh Sten et al., Nature 2021

Male LC10a AOTu-terminal calcium responses were greater for progressive than
regressive motion in aggregate, before and during P1 activation. Tested targets
were dark 10-degree and 25-degree spheres, a tall 10-degree-wide bar, all
sweeping at 75 degrees/s; a separate sphere expanded 10 to 100 degrees at
20 degrees/s. Each direction was presented ten times, with five-second gaps,
before repeating the panel with P1 activation. Responses were amplified across
the panel, supporting gain modulation rather than a newly fitted spatial map.
[Methods and Extended Data Fig. 10](https://pmc.ncbi.nlm.nih.gov/articles/PMC8973426/).

Readouts are fluorescence, not spikes/s. Pooled AOTu ROIs and correlated
bouton-like pixels do not identify MaleCNS body IDs. Crucially, the authors
clamped negative mean calcium responses to zero when calculating their
direction-selectivity index. That is an analysis convention, not evidence that
regressive responses vanish. Complete progressive selectivity was a model
choice, distinct from the measured directional inequality. A matched check
should permit regressive activity and leave raw signed measurements intact.
[Direction-selectivity methods and network-model section](https://pmc.ncbi.nlm.nih.gov/articles/PMC8973426/).

### Schretter et al., Nature 2025

Fig. 3a measures responses to dark rectangles with varied dimensions: male
LC10a, seven axons from five flies. The stated preferred width/height range is
roughly 15–30 degrees. Imaging stimulated the right eye and sampled the right
brain with a roughly 90-by-90-degree green projection screen. Extended Data
Fig. 2d repeats size tuning at 50 degrees/s. These are calcium size matrices,
not azimuth/elevation receptive-field maps or calibrated spiking curves.
[Article, Fig. 3a, imaging methods and Extended Data Fig. 2](https://www.nature.com/articles/s41586-024-08255-6).

The size assay must not inherit the paper's female-aggression state by title:
the LC10a physiology cohort was male. No P1-defined arousal condition is
reported for that size assay in the retrieved methods. Its baseline speed of
100 degrees/s is retained from the earlier project figure inspection, not
independently reverified in this text refresh. The full figure page failed
through an identity redirect. Numerical tuning remains unavailable in the
previously inspected public workbook; no fresh workbook audit was done here.

## Proposed checks and their evidence level

These are contract-design recommendations, not additional measurements:

| Probe | Useful check now | Numerical limit still missing |
| --- | --- | --- |
| Finite object with separately varied angular width/height | Ensure the API preserves both dimensions and can express nonmonotonic size tuning; compare the published qualitative preferred range | Per-cell peak, bandwidth, gain and uncertainty; no RF sigma may be inferred from preferred object size |
| Matched progressive/regressive trajectory | State a retinal direction convention; permit unequal nonzero responses | Exact ratio by cell, speed and state |
| Same panel with explicit state metadata | Permit shared gain to vary while holding geometry fixed | Universal P1 multiplier or equivalence to the existing AOTU recording groups |
| Object plus independently moving surround | Represent object motion and surround motion separately; test the proposed mechanism diagnostically | Suppression strengths and ordering across backgrounds; no hard biological acceptance gate from the inaccessible Ribeiro details |
| Contrast and polarity variations | Record them in the stimulus definition and report sensitivity | A validated LC10a contrast-response law; these probes are engineering diagnostics until evidence is supplied |

A contrast-zero null response is a mathematical consistency check for the
chosen image/contrast adapter, not proof of LC10a biology. Likewise, reproducing
the supplied qualitative inequalities would show that an adapter expresses its
assumptions. It would not validate 275 individual fields or establish a
connectome-specific behavioral advantage. Keep those later claims behind
held-out physiology and matched wiring/simple-controller comparisons.

**TL;DR:** Finite size, motion direction, surround and state belong in the
contract. Current sources justify qualitative probes, not a fitted LC10a
front end or a promise that it will repair pursuit.

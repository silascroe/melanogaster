# Step 3: mapping the pursuit reference to MaleCNS v1.0

Date: 2026-09-26. Compact reproducible result:
[pursuit_mapping_v1.json](evidence/pursuit_mapping_v1.json).
Preceding numerical reference: [Step 2](pursuit_reference_result.md).

## What maps, and what does not

The authors' `lc10_to_dn_male.R` queries `male-cns:v0.9`. Its
`dn_type_avg_DNa02.csv` saves **16 downstream partner body IDs**, not the
individual LC10a IDs used to make the heatmaps. I looked up all 16 saved IDs
in the official v1.0 body annotations: **16/16 retain the same type and are
traced**. The two branches needed for this creature also appear by the same
IDs in our compact circuit: AOTU019_L `10070` and AOTU025_L `516361`.
An unchanged ID and type is strong evidence for these particular cells, but
it does not prove the older and newer synapse tables or visual fields are
identical. We cannot pair the source's individual LC10a cells to the 275
v1.0 LC10a cells because the released response and heatmap tables do not
retain those LC10a IDs.

The source's field construction already uses connection strength. In
`lc10_heatmap_male.R`, v0.9 LC10a-to-target contact counts color each rendered
LC10a mesh. In `heatmap_analysis.m`, the grayscale image is processed into a
spatial response, then multiplied by the *mean target-to-DNa02 count divided
by the largest such mean*. The AOTU019 output multiplier is 1; AOTU025's is
**200.5 / 293 ≈ 0.6843**. `Pursuit_RFs.csv` closely follows the resulting
weighted table at checked shared angles. The exact intermediate CSV-building
script is absent, and image processing makes the earlier LC10a weighting
nonlinear. Still, treating this field as raw visual input and then multiplying
it by our LC10a→AOTU and AOTU→DNa02 counts would reuse those strength
components. The [Step 2 reference](pursuit_reference_result.md) remains an
aggregate model; its licensed curves are not packaged as creature inputs.
Across all 14 modeled columns and the weighted table's shared -15°–165°
range, simple linear interpolation differs by at most **0.000447** activity
units. That supports the table lineage but does not establish the authors'
missing CSV-construction procedure exactly.

Our v1.0 counts are close but not identical to the old type means:

| Branch | v0.9 mean LC10a input | v1.0 input L / R | v0.9 mean DNa02 output | v1.0 output L / R |
| --- | ---: | ---: | ---: | ---: |
| AOTU019 | 7,076 | 6,615 / 7,595 | 293 | 289 / 297 |
| AOTU025 | 3,494 | 3,303 / 3,728 | 200.5 | 205 / 196 |

These are anatomical contact counts. The source means and our selected
v1.0 sides are different summaries; similar totals do not calibrate
activity, neural gain, or turning.

## Implemented v1.0 adapter

[`pursuit_activity.py`](../src/fly_creature/pursuit_activity.py) now offers an
**offline fixed-fly projection** that reads only the creature's packaged
v1.0 circuit and its existing upstream-derived LC10a position hypothesis.
For a target bearing it gives each LC10a a unit-peak Gaussian response at
its putative center, then applies the recorded LC10a→AOTU counts once and
the signed AOTU→DNa02 counts once. AOTU019 is negative and crosses the body;
AOTU025 is positive and stays on the same side under our transmitter-sign
convention. It exposes cell responses, four AOTU contact drives, bilateral
DNa02 signed contact products, and right-minus-left difference. Removing or
side-swapping the output bridge gives explicit structural controls. This
module has no external source-data dependency and can travel with the
standalone creature folder. It is **not** enabled in Godot.

The visual centers have independently supported ordering from medulla-column
inputs, but their 5°–60° scale and the Gaussian width of 18° are assumed.
The output is in contact counts or contact-count products, **not** modeled
voltage, spikes, measured neural activity, or degrees per second. It does
not apply the authors' ELU, directional penalty, 450 ms delays, or motor gain
to these uncalibrated values. Doing so now would create numerical behavior
without validating the substituted visual input.

## Fixed-fly diagnostic and decision

On the positive-bearing (right) side, the v1.0 hypothesis's AOTU019
contact-drive curve peaks at **28°**, near the authors' weighted AOTU019
field peak at **26°**. Their normalized shapes across 0°–165° correlate
**0.904**. AOTU025 is the problem: the v1.0 hypothesis peaks at **45°**,
while the authors' field peaks at **72°**, with shape correlation **0.263**.
These are *shape* comparisons after each curve is separately scaled to its
own maximum; the amplitudes have incompatible units. The current 5°–60°
assumed LC10a center scale cannot be called a verified reproduction of the
more lateral AOTU025 field.

At right 25°, the adapter yields a positive DNa02 right-minus-left
contact-product score. Bridge removal makes it zero; swapping the same
signed output edges reverses it. That verifies the implementation's stated
structural sign convention, not real firing or useful pursuit.

**Decision:** the identity/weight audit and inspectable v1.0 projection are
complete. A validated cell-level substitution is **not** complete because
the individual source LC10a correspondence is unavailable and the AOTU025
shape disagrees strongly. Keep Step 2's verified aggregate reference and
the existing playable LIF controller separate. Before Step 4 behavior tests,
find a defensible retinal-angle calibration or cell-level visual-field source
that resolves AOTU025, then compare fixed-fly shapes without adjusting
motor gains. If that evidence cannot be found, use the aggregate reference
as its own labeled model instead of calling the v1.0 adaptation equivalent.
The [follow-up diagnosis](pursuit_field_gap_diagnosis.md) isolates the
assumed 5°–60° visual-angle compression as the main cause *within this
adapter*. This was the status when the v2 audit was written. The subsequent
[registered eye-map candidate](pursuit_registered_eye_map_result.md) resolves
the specific field gap enough to begin a bounded Step 4 offline evaluation,
while retaining substantial registration and fallback uncertainty.
The public [MaleCNS visual-pathways gallery](https://github.com/reiserlab/visualpathways)
offers predicted anatomical receptive fields at cell-type level, a useful
next calibration lead, but its described gallery is not a per-body-ID LC10a
field table. No direct replacement was established in this audit.

## Reproduce

From `fly-creature/`, with the pinned authors' clone under ignored
`outputs/research/CollieWilson/` and the official working release at the
default development path:

```powershell
$env:PYTHONPATH = 'src'
..\.venv\Scripts\python.exe tools\audit_pursuit_mapping.py
```

The tool checks the pinned source-file hashes, reads v1.0 annotations, loads
the packaged circuit and map, exercises the three bridge conditions, and
writes only compact metadata and metrics. It never writes the source tables
or raw connectome files into the creature package.

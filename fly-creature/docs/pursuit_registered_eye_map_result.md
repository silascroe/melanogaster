# Step 3 resolution: a registered anatomical eye-map candidate

Date: 2026-09-26. This resolves the **specific 45° versus 72° mapping gap
enough to begin Step 4's controlled experiments**. It does not establish
measured LC10a receptive fields, neural firing, or successful pursuit.
The derivation is
[`derive_lc10a_registered_eyemap.py`](../tools/derive_lc10a_registered_eyemap.py),
the portable candidate is
[`lc10a_registered_eyemap_hypothesis_v3.json`](../src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json),
and the compact audit is
[`registered_eyemap_v3.json`](evidence/registered_eyemap_v3.json).

## The independent input change

The v2 map took an anatomically ordered set of LC10a cells and arbitrarily
squeezed their preferred positions into 5°–60°. The v3 derivation uses
[Zhao et al.'s published eye map](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/)
instead. Its [public data](https://github.com/reiserlab/eyemap_T4) pair FAFB
female Mi1 medulla-grid positions with micro-CT ommatidial viewing vectors.
The [MaleCNS column-coordinate diagram](https://github.com/reiserlab/visualpathways/blob/main/docs/column_coord.pdf)
specifies `hex2 → p`, `hex1 → q`, and centered origin `[hex1,hex2]=[18,19]`.
We transfer the eye-map angle using `p=hex2−19`, `q=hex1−18`, with no output
curve involved. The axes agree in direction: the source eye-map azimuth rises
with `p−q`, and elevation rises with `p+q`. MaleCNS Mi1 occupies **776/778**
of the mapped FAFB grid coordinates on the left and **777/778** on the right
at the centered, zero-shift registration. This is a strong lattice and
orientation check, though it cannot prove the two flies' eyes align perfectly.

For each LC10a with at least three incoming annotated-column edges, the map
averages source-column azimuth by MaleCNS input contact count. These are
**164 cells** (41 left, 123 right). The other **111** retain the prior
skeleton-estimated horizontal coordinate and convert it through the eye-map's
median azimuth for that coordinate. MaleCNS columns just outside the published
FAFB eye grid use a 12-neighbor local affine estimate. Its *within-source*
leave-one-out azimuth error is 0.21° median, 1.12° at the 95th percentile,
and 13.26° worst case. That check says little about cross-specimen error.
The source may also differ by eye position: the [eye-map study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/)
reports that flies can shift their eyes by about 15°.

The right AOTU019 and AOTU025 branches get respectively **98.0%** and
**94.7%** of their LC10a contact weight from directly mapped cells. Among
those direct cells, only **4.4%** and **0.17%** of source-contact weight
requires boundary interpolation. The left branches get just **42.6%** and
**35.4%** from directly mapped cells, so left-side results rely much more on
the skeleton fallback. All individual assignments remain anatomical
estimates. The source eye-map raw files are kept in ignored research output;
the creature package contains only the compact derived centers.

## Fixed-fly result

The authors' aggregate field is a **comparison**, not an input to the v3
derivation. Each curve below is separately scaled to its own maximum, since
our contact drive and the source response have different units. Correlation
is calculated across 0°–165°; peaks are in degrees from the midline.

| Branch | Old v2 peak / shape correlation | Registered v3 peak / shape correlation | Reference peak |
| --- | ---: | ---: | ---: |
| AOTU019 left | 27° / 0.897 | **18° / 0.934** | 26° |
| AOTU025 left | 44° / 0.229 | **62° / 0.853** | 72° |
| AOTU019 right | 28° / 0.904 | **21° / 0.948** | 26° |
| AOTU025 right | 45° / 0.263 | **62° / 0.846** | 72° |

The diagnostic gate checks each branch for a peak within 15° of the
reference, shape correlation at least 0.8, and AOTU025 at least 30° more
lateral than AOTU019 on each side. The v2 map fails; v3 passes. These are
**practical troubleshooting bounds chosen during this investigation**, not
preregistered or held-out validation. The reference itself is an older,
connectome-derived aggregate with different response assumptions.

Wiring contributes to this result. In 500 fixed-fly controls, whole
LC10a-to-AOTU output bundles were shuffled *within each side*, preserving
the selected cells and their edge weights but breaking the match between
visual position and downstream targets. Intact v3 mean correlation across
four branch curves is **0.895**; shuffled median is **0.540** and shuffled
95th percentile **0.627**. None of the 500 matched the intact score. Mean
left/right AOTU025–AOTU019 peak separation is **42.5°** intact and **0.5°**
at the shuffle median; again none matched. This supports a specific role for
the recorded v1.0 input wiring in the *modeled spatial split*. It does not
show locomotor benefit or biological neural dynamics.

## Registration sensitivity and the Step 4 boundary

The centered grid origin defines the nominal zero-shift map. One-column
perturbations were generated **afterward for sensitivity**, not selected by
pursuit score. Shifts of +1 in p or −1 in q preserve nearly all Mi1 grid
overlap and pass the same field gate; shifts of −1 in p or +1 in q reduce
grid overlap and fail the AOTU025 shape criterion. The nominal map therefore
has a plausible local registration, but the exact angle scale is still
sensitive to a one-column displacement. Step 4 must carry that uncertainty
as declared input variants. It must not silently pick the shift that makes
behavior look best.

**Decision:** Step 3 now has a portable, upstream-derived, independently
registered *candidate* with the frontal/lateral spatial split, bilateral
fixed-fly response, and a strong shuffled-wiring distinction. That is enough
to enter Step 4's bounded evaluation. Keep Step 2's verified aggregate model,
the old LIF controller, and this v1.0 candidate separately labeled. The
candidate remains offline until Step 4 checks motion responses, held-out
paths, intervention effects, and parameter sensitivity. No Godot behavior
has been promoted by this result.

## Reproduce

The public source RData files belong under ignored
`outputs/research/eyemap_T4/`; the derivation pins their Git blob hashes.
Download the two files from the [eye-map repository](https://github.com/reiserlab/eyemap_T4/tree/main/data)
as `eyemap.RData` and `med_ixy.RData` into that directory. The derivation
rejects files whose Git blob hashes differ from the values in the script.
From `fly-creature/`, prepare the development environment and files with:

```powershell
..\.venv\Scripts\python.exe -m pip install -e ".[eye-map-research]"
New-Item -ItemType Directory -Force outputs\research\eyemap_T4
Invoke-WebRequest https://raw.githubusercontent.com/reiserlab/eyemap_T4/main/data/eyemap.RData -OutFile outputs\research\eyemap_T4\eyemap.RData
Invoke-WebRequest https://raw.githubusercontent.com/reiserlab/eyemap_T4/main/data/med_ixy.RData -OutFile outputs\research\eyemap_T4\med_ixy.RData
```

Then run:

```powershell
..\.venv\Scripts\python.exe tools\derive_lc10a_registered_eyemap.py --annotations ..\data\working\male-cns-v1.0\body-annotations-male-cns-v1.0-minconf-0.5.feather --weights ..\data\working\male-cns-v1.0\connectome-weights-male-cns-v1.0-minconf-0.5.feather
$env:PYTHONPATH = 'src'
..\.venv\Scripts\python.exe tools\check_pursuit_field_gate.py --map src\fly_creature\data\lc10a_upstream_hypothesis_v2.json
..\.venv\Scripts\python.exe tools\check_pursuit_field_gate.py --map src\fly_creature\data\lc10a_registered_eyemap_hypothesis_v3.json
..\.venv\Scripts\python.exe tools\audit_registered_eyemap.py
```

The first gate command intentionally exits 1: it reproduces the old gap.
The second exits 0. The audit writes only compact derived metrics.

# Why the v1.0 AOTU025 field missed the reference

Date: 2026-09-26. This is the Step 3 troubleshooting result, not a new
controller. Reproducible numbers are in
[pursuit_field_gap_v1.json](evidence/pursuit_field_gap_v1.json); the calculation
is [diagnose_pursuit_field_gap.py](../tools/diagnose_pursuit_field_gap.py).

## Diagnosis

The packaged LC10a map ranks cells within each side by an upstream medulla
column coordinate, then squeezes **all** of those ranks into an assumed
**5°–60°** preferred-bearing range. The 5°–60° conversion is an engineering
choice, not a measured visual-field calibration. AOTU025 receives more
laterally placed LC10a input than AOTU019 in this map. Compressing that
anatomical separation into 55° explains why the right AOTU025 contact-drive
curve peaks at **45°** while the authors' aggregate field peaks at **72°**.
This is a diagnosis of the adapter's sensitivity, not proof that the v1.0
cells have the same fields as the authors' v0.9 cells.

The following controls hold the packaged v1.0 connections fixed unless the
row explicitly changes their inclusion or cap. Curve correlations compare
separately normalized shapes over positive bearings 0°–165°. Their amplitudes
and units are different.

| Input hypothesis or control | AOTU019 peak | AOTU025 peak | AOTU025 shape correlation |
| --- | ---: | ---: | ---: |
| Packaged 5°–60° rank, 18° Gaussian | 28° | 45° | 0.263 |
| Same map, 5°–30° Gaussian width sweep | 27°–28° | 45°–46° | 0.159–0.370 |
| Same map, other hemisphere | 27° | 44° | 0.229 |
| Same map, minimum input-contact count 5 | 28° | 45° | 0.264 |
| Same map, input-contact cap 170 | 28° | 45° | 0.263 |
| Raw horizontal coordinate, linearly mapped to 0°–90° | 26° | 51° | 0.486 |
| Raw horizontal coordinate, linearly mapped to -15°–165° then clipped at 0° | 33° | 86° | 0.933 |
| Authors' aggregate reference | 26° | 72° | 1.000 |

The raw-coordinate alternatives preserve the spacing of the upstream medulla
coordinate instead of throwing it away with within-side ranks. The second
uses the authors' stated angular table range as *hypothetical endpoints*;
those endpoints are **not** a measured registration of MaleCNS columns to
retinal degrees. It greatly improves both full curve shapes (AOTU019
correlation 0.967; AOTU025 0.933), but its peaks still miss by 7° and 14°.
The different result for 0°–90° shows why picking endpoints from a pleasant
curve would be unjustified.

The right AOTU025 branch gets **94.7%** of its LC10a input contacts from
cells whose medulla-column positions were assigned directly; right AOTU019
gets **98.0%**. Thus the skeleton fallback is unlikely to explain this
right-side discrepancy. The left branch has much more fallback and is a
weaker calibration check. Changing the Gaussian width, side, contact-count
threshold, or cap does not move the packaged right AOTU025 peak materially.
Those checks isolate the assumed angle assignment as the main cause within
this adapter. They do not independently verify the v1.0 contact topology or
unit-Gaussian cell response assumption.

As a warning, a coarse two-endpoint search **using the authors' two output
peaks as targets** can put the v1.0 peaks at 25° and 72°. This is circular
fitting, included only to show that peak agreement can be manufactured.
It is not a proposed map and is never loaded by the creature.

## Decision and next evidence

Keep the current map labeled as a hypothesis and the projection offline. Do
not tune motor gains or move it into Godot. The needed fix is an independently
justified conversion from MaleCNS medulla columns to visual bearings, with
uncertainty, ideally registered at the column or per-cell level. The public
[MaleCNS visual-pathways gallery](https://github.com/reiserlab/visualpathways)
is a useful starting point for type-level anatomy, but does not itself give
each selected LC10a body ID a measured bearing. Its
[coordinate notes](https://github.com/reiserlab/visualpathways/blob/main/docs/coordinate-systems.md)
define anatomical hex and H/V axes, not a retinal-degree origin. Its
[pipeline guide](https://github.com/reiserlab/visualpathways/blob/main/docs/run_order.md)
describes per-neuron anatomical receptive-field calculations, but the
derived tables require substantial NeuPrint-generated caches and do not
arrive as a ready per-body retinal-angle table. An
[eye-map study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/) links
ommatidial directions to medulla columns; using its map here would still
require checking dataset compatibility and registration. After obtaining an
independent map, rerun the fixed-fly comparison against both AOTU branches
and report uncertainty before any behavior step.

From `fly-creature/`, with the pinned authors' source clone already under
ignored `outputs/research/CollieWilson/`, regenerate the evidence using:

```powershell
$env:PYTHONPATH = 'src'
..\.venv\Scripts\python.exe tools\diagnose_pursuit_field_gap.py
```

The script verifies the pinned source table hash and reads the packaged
compact map and circuit. It never changes runtime behavior or raw connectome
files.

## Subsequent resolution

The [registered eye-map candidate](pursuit_registered_eye_map_result.md)
uses a public FAFB eye map and the MaleCNS p/q coordinate transform without
fitting to AOTU outputs. It passes the bilateral fixed-fly field check.
The original diagnosis above remains the record of why v2 failed; Step 4
may now begin as a bounded offline evaluation, with registration and
fallback uncertainty explicit.

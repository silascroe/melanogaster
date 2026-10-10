# Retinal-angle source audit for the MaleCNS LC10a map

Date: 2026-09-26. Scope: an independently derived **medulla column to visual bearing** map for the 275 selected MaleCNS v1.0 LC10a cells. This is a source audit, not a new input map.

**Follow-up:** The crosswalk requested below was subsequently implemented as
the explicit MaleCNS `p=hex2−19`, `q=hex1−18` transform to the FAFB p/q eye
grid. Its source-only occupancy and axis checks, v3 candidate, uncertainty,
and AOTU comparison are in the
[registered eye-map result](pursuit_registered_eye_map_result.md). The text
below records the state of the audit *before* that registration; its claims
that the crosswalk is still missing are superseded. The registration remains
a cross-specimen hypothesis, not a per-cell measured field.

## Finding

The missing angular scale has a credible **source**, but no verified **registration** to this project's MaleCNS v1.0 columns yet. [Zhao et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/) measured individual ommatidial viewing directions as lens-to-photoreceptor-tip vectors in whole-head micro-CT. They aligned that eye grid to **female FAFB** Mi1 medulla columns by the equator and central meridian, then used kernel regression to project positions into visual space. Their [public code and data](https://github.com/reiserlab/eyemap_T4) include [`data/eyemap.RData`](https://github.com/reiserlab/eyemap_T4/blob/main/data/eyemap.RData): `ucl_rot_sm` holds unit viewing vectors, `eyemap` pairs matched FAFB Mi1 and lens indices, and `lens_ixy` holds lens grid positions. [`data/med_ixy.RData`](https://github.com/reiserlab/eyemap_T4/blob/main/data/med_ixy.RData) is the FAFB Mi1 grid. The actual one-to-one matching is in [`proc_eyemap.R`](https://github.com/reiserlab/eyemap_T4/blob/main/proc_eyemap.R), near its `# manual matching` and `# SAVE eyemap` sections. These are anatomical **estimates of viewing direction**, not measured LC10a receptive fields.

The paper explicitly says the EM and micro-CT grids came from different flies, uses central landmarks to align them, and warns that boundary matches are less certain ([methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/#Sec17)). Ommatidial direction spans roughly -10° to 155° azimuth and varies with elevation; the retina can also move by about 15° ([results](https://pmc.ncbi.nlm.nih.gov/articles/PMC12488493/)). Consequently a single linear rescale of `assignedOlHex2 - assignedOlHex1`, or of within-side LC10a ranks, cannot be asserted as retinal degrees.

## What can be joined, and what cannot

[MaleCNS v1.0](https://male-cns.janelia.org/download/) supplies `assignedOlHex1/2` for upstream columnar neurons, body IDs and connection weights. Our [upstream derivation](../tools/derive_lc10a_upstream_map.py) traces those inputs to LC10a without examining AOTU outputs; its compact result has **164 direct** and **111 skeleton-fallback** LC10a positions ([experiment](visual_motion_experiment.md)). The current 5°–60° conversion is expressly a model assumption. The [MaleCNS coordinate notes](https://github.com/reiserlab/visualpathways/blob/main/docs/coordinate-systems.md) place the `hex1/hex2` origin arbitrarily outside the eye and define `[18, 19]` as the centered `p/q` origin. Those integers are **MaleCNS grid addresses**, not the FAFB Mi1 indices or lens indices in `eyemap.RData`. Matching equal numbers across the two files would silently invent a registration.

The [MaleCNS visual-pathways repository](https://github.com/reiserlab/visualpathways) offers predicted anatomical receptive-field plots for VPN *types* and a retinotopy-colored Neuroglancer layer. Its public description does not provide a checked, per-body-ID LC10a retinal-bearing table or a FAFB-to-MaleCNS angular crosswalk. The [official LC10a type page](https://reiserlab.github.io/male-drosophila-visual-system-connectome/LC10a_R.html) likewise reports population anatomy, not individual visual angles. [Collie et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/) offer a useful independent AOTU comparison, but their output peaks cannot set the column map's endpoints: that would fit the answer to the result being tested.

## Reproducible route to a usable map

1. Read `ucl_rot_sm`, `eyemap`, and lens grid coordinates from the authors' R data. Their [`cart2Mercator`](https://github.com/reiserlab/eyemap_T4/blob/main/eyemap_func.R) flips the vector's `y` coordinate before extracting signed azimuth: for their rotated unit vector `(x,y,z)`, `bearing = atan2(-y, x) * 180/pi`, wrapped to [-180°,180°]. Confirm its orientation against the paper's convention that positive azimuth is the fly's right visual field before applying it to either MaleCNS side.
2. Build a **two-dimensional** `(hex1,hex2)` MaleCNS column table from the v1.0 annotations; locate its equator and central meridian in the MaleCNS grid. Register that grid to the authors' lens/FAFB grid using those anatomical landmarks, the chiasm reflection, and grid adjacency. Record the transform, anchor columns, unmatched columns, and boundary error. The authors' `proc_eyemap.R` demonstrates how the FAFB eye and medulla grids were matched; it does not supply this additional MaleCNS registration.
3. Transfer viewing vectors or azimuth/elevation to matched MaleCNS columns. Aggregate *incoming* mapped-column contacts for each LC10a cell, recording spread, input count, and whether skeleton fallback was needed. Validate coverage and both eye orientations using source anatomy, without using AOTU019/025 peaks, DNa02 output, or pursuit score as calibration targets. Compare those outputs only after the angle map is frozen.

At the time of this source audit, Step 4 could proceed only with an explicitly
**provisional** angle-sensitivity analysis. The subsequent cross-specimen
registration and its bounded Step 4 decision are documented above. Neither
the original 5°–60° map nor the new transfer is a calibrated per-cell field.

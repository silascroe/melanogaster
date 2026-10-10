# Column-footprint candidate v1

2026-10-02, frozen before evaluation. Offline only; no production promotion.

Derive from the same official MaleCNS working tables and pinned eye-map blobs.
For the same 164 directly mapped LC10a cells, retain all same-side annotated
upstream column angles and contact counts, grouped by column. Normalize each
cell's upstream counts to sum to one. Do not infer unknown columns or claim
measured receptive fields. The other 111 cells retain exactly their old
single-center fallback; expose their contribution separately.

Response is the contact-weighted mixture of 18-degree Gaussian column kernels,
multiplied by the existing 15-degree eye aperture. The kernel width is a new
column-level assumption borrowed from the previous cell-level model. Do not
renormalize each cell's response peak, refit type peaks, or tune motor gain.
Keep baseline type peaks, output-edge normalization, ELU, direction penalty,
gain 0.65, 200 ms queue, body convention and cap unchanged.

Primary candidate uses signed registered column angles. Separate controls:
signed upstream mean only (isolates unclipping negative means); footprint
recentered to old clipped means (isolates spatial spread); and original center
baseline. Fallback inputs stay identical in all variants. Audit coverage,
weighted means/spreads, finite/bounded responses, clipping, fixed-fly peaks and
wide-angle signal, with direct/fallback contact contributions separated.

Only after those checks pass, replay the existing 22 consumed retinal cases.
Report regressions and baseline equality; no fresh promotion set is consumed.
32 within-side input-bundle shuffles compare candidate and baseline spatial
fields and behavioral family ranks, with the same seed and fixed normalization.
This is exploratory evidence, not a new success gate or biological validation.

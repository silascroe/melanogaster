# Declared post-audit timing-resolution sensitivity

2026-10-02. The frozen literal >=1 s selection is preserved. The initial
audit shows nominal one-second hidden gaps digitized mainly as 0.999 or
1.0005 s on the 1.5 ms grid. A strict 1 s cut therefore selects timing jitter,
not a distinct isolation condition. Add a clearly post-hoc `nominal_1s`
sensitivity at >=0.995 s, with all three baseline windows valid, before
examining its response results. Do not replace the original primary results.
Two-second and first-stimulus-only coverage remain reported even when empty.
Add previously omitted previous-segment direction metadata; no extraction,
rates, primary windows or original strata change. Repeat the revised audit.

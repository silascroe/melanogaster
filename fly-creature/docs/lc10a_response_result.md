# LC10a image-response implementation and probe result

2026-10-04. The frozen image-to-LC10a rule is implemented as an offline
research component. The primary probe run and independent checker pass. This
closes the input-response checkpoint; it does not show that the MaleCNS wiring
improves an AOTU prediction or produces a useful behavior.

## What the code now does

`src/fly_creature/lc10a_response.py` accepts a 176×32 linear-luminance image,
its timestamp, and an explicit gain. It derives causal horizontal motion from
the previous held image, pools static contrast and motion through the frozen
synthetic center/surround kernels at the existing sorted 275 LC10a IDs, then
applies the unit-area temporal envelope. Its outputs are dimensionless
hypothesized activity, not voltage, spikes, or measured firing rates.

The cell identities and centers are unchanged: 164 use upstream-column map
positions and 111 use skeleton-derived fallback positions. There is no
per-cell elevation map. The new function does not use target labels, bearing,
velocity labels, stimulus state, or a P1 filename. It also does not yet apply
the LC10a-to-AOTU contacts; that comparison is the next, separate experiment.

## Checks and observed probe behavior

All 68 frozen probes ran for six seconds at 2 ms steps: 204,000 rendered frames
in total, with 3,000 samples and 275 cell outputs per probe. Six moving-surround
conditions also have target-absent partners. Flash, pause, isolated-disc,
explicit-gain, and label-swap checks remain separate software controls.

- All four absent/zero-contrast traces are exactly zero. Bright and dark copies
  have identical responses. Hiding a target while changing its metadata does
  not change its rendered frames.
- A stationary object produces static drive but no motion signal. Whole-panel
  flashes and uniform local motion also produce no motion signal or
  center-surround residual.
- An explicit gain of two doubles activity exactly; a P1 label swap changes
  nothing. The first response sample is zero, and an independent-trial reset
  clears history.
- An independent direct 2D spatial calculation agrees with optimized pooling
  to at most `6.94e-17`. Independent quadrature agrees with the held-pulse
  temporal response to `2.78e-17`; the 1.5 ms and 2 ms temporal bins each sum
  to one within floating-point precision.
- The public stateful path with irregular timestamps and changing current gain
  matches separate interval-by-interval quadrature to `5.1e-15`; each output
  uses only previously held image features.
- Mirrored motion reverses exactly. Mirrored virtual-unit responses differ by
  less than `7e-18`. Frame chunk sizes 8 and 32 produce identical probe output.
- The worst integrated-response difference across 8×8, 16×16, 32×32 raster
  sampling and exact rectangle coverage is `0.197%`, below the frozen 5%
  ceiling. The progressive-minus-regressive virtual response keeps the same
  sign across all three raster resolutions.
- Two full runs produced byte-identical reports, 68-row summaries, surround
  contrasts, and compressed activity traces. Nineteen frozen input hashes
  still match.

The largest instantaneous feature across the primary probes is `0.17495`; the
largest temporally filtered output is `0.07989`. These are consequences of the
chosen scaling and probe set, not calibrated neural units. Population-summed
activity rises with target width because wider targets cover more hypothesized
fields; that is not evidence that one LC10a cell prefers a larger target.
Moving background gratings can drive activity even with the target absent, so
their effect is reported as a signed target-versus-background comparison after
the sensory calculation.

## What remains unproven

The selected cells receive a useful, inspectable image-derived signal under
this construction. No recorded AOTU activity has been scored against it, no
intact-versus-matched-spatial or wiring-shuffle comparison has run, and no
connectome-specific advantage has been demonstrated. The spatial fields,
direction ratio, contrast law, and shared vertical pooling remain hypotheses.
The temporal envelope comes from a published fitted model shape; it is not a
measured MaleCNS LC10a spiking response. Production Python, Godot, and the
playable controller were not changed.

## Reproduce and inspect

From the FlyTest workspace root:

```powershell
.\.venv\Scripts\python.exe fly-creature/tools/run_lc10a_response_probes.py
.\.venv\Scripts\python.exe fly-creature/tools/check_lc10a_response.py
```

The default outputs are under ignored
`fly-creature/outputs/research/lc10a-response-v1/`. The full compressed
68-probe activity archive stays local. Compact tracked tables and check reports
are in `docs/evidence/lc10a_response_*_v1.*`.

**Next checkpoint:** implement the separately specified recorded-AOTU
comparison, first verifying its frozen extraction, holdouts, lookup, and wiring
controls. Pass the exact 275-cell responses through the existing recorded
LC10a-to-AOTU counts, then compare new intact, legacy, matched-spatial, flat,
and the existing 32 within-side wiring shuffles under the same calibration
budget. Keep it offline; do not promote it to Godot based on probe checks.

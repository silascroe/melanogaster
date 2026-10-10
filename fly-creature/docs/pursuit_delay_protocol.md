# Pursuit timing and center-field diagnosis

Frozen before running the matrix, 2026-09-30. This is an offline causal
diagnosis of Step 4, not a new biological model or permission to integrate it.

Keep the packaged v3 map, recorded edges, 18 degree Gaussian width, Step 4
normalization, 0.65 gain, motion penalty, 10 ms update, turn cap and walking
speed fixed. Reproduce the original step-hold failure first. Use both mirrored
walking step-holds and a stationary translating-body control (rotation only,
target jumps from -20 to +20 degrees at 2 s). Run the full matrix of visual
history delays 0/50/200/450 ms, additional motor-command delays 0/200 ms, and
center overlap 0/15 degrees. The 50 ms value is exploratory, not a measured
latency. Delays are distinct queues, not two labels for the same delay.

Zero overlap reproduces the old hard hemisphere gate. The alternative uses
signed Gaussian cell centers and linear eye aperture crossfades over -7.5 to
+7.5 degrees. It is an engineered 15-degree total binocular overlap hypothesis;
it does not measure LC10a receptive fields. Preserve the old normalization
when comparing it, including shuffles. All response changes and clipping are
reported. Degree-bin sampling remains unchanged.

Diagnostic signals: continuous one-second residence within +/-10 degrees
after the 2 s target jump, center crossings, mean/final bearing, motor caps,
and AOTU/DNa02 clipping. Baseline-equivalence checks must reproduce Step 4.
Compare factors within the matrix, not just the best outcome.

For a fresh evaluation, try the prespecified interpretation with zero visual
history delay, 200 ms motor delay and 15-degree overlap. This tests placing
the source's separately named visuomotor delay at the motor effect; it is
not author-code parity or a proven biological correction. Evaluate it even
if diagnosis fails, without choosing a different variant from path scores.

New eight-second paths are harmonic (two frequencies), dwell reversal (three
held positions), and ramp-stop (move, hold, reverse), each mirrored. Their
equations are fixed in the runner before execution. Compare original Step 4,
the declared candidate, bridge removal, 32 within-side bundle shuffles (seed
20260930), direct bearing and playable LIF. Evaluate gain multipliers 0.8/1.2
and overlap widths 10/20 degrees as sensitivity only, without adopting them.

An encouraging candidate must settle in both walking step-holds, improve
median fresh-path error by >=20% over bridge removal, beat the median shuffle
on >=5/6 paths, keep >=80% in view, <25% capped commands, and have no lookup
clipping. Its gain sensitivities must also settle and change median error
by <=25%. A pass authorizes a subsequent review, not automatic Godot rollout.

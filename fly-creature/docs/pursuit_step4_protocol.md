# Step 4 frozen offline protocol

Declared 2026-09-27 before running Step 4 trajectories. This is a bounded
engineering evaluation of the MaleCNS v1.0 pursuit adaptation. Passing would
permit consideration of Step 5 as a selectable demo; it would not validate
biological LC10a receptive fields, DNa02 firing, or fly pursuit.

## Model held fixed

The default v3 eye-map hypothesis assigns 275 LC10a Gaussian centers with
18° width. Its projected LC10a→AOTU contact curves replace the authors'
aggregate receptive-field table. AOTU activity is transformed by the same
ELU lookup used in the verified Step 2 dynamic reference: each AOTU type is
normalized across both sides, with one shared type-specific peak taken from
the nominal intact map and held fixed for every intervention. Both
pathways have the published 450 ms visual delay at 100 Hz. The primary
candidate applies the author's AOTU019 nonpreferred-motion factor 0.66 before
the lookup; AOTU025 uses 1.0. A position-only, delayed condition omits that
motion factor. The direction preference is **imposed by this source rule**;
any advantage cannot be credited to the connectome alone.

The selected v1.0 AOTU→DNa02 edges contribute their recorded signs and
relative side-specific strengths, normalized separately by the maximum
absolute edge of each AOTU type. The source's linear DNa02 transform and
0.65 degrees per 10 ms step per unit right-minus-left activity turn the
fly. This normalization sets model units; it is not measured synaptic
efficacy. A 1.2 rad/s turn cap matches the playable demo. No gain, width,
delay, source penalty, or normalization is chosen from held-out trajectories.

World steps are 10 ms for 8 seconds. The walking fly starts at (x,z)=(0,0),
heading 0°, walks forward at 0.55 m/s, and steers with the previous step's
neural command. The target remains at z=-7 m. A target is seen within
0.4–9 m and ±120°; outside this engineered view the neural input is zero.
The direct-bearing control sees the same target and has the same turn cap,
using a fixed signed linear command that reaches the cap at 45°.
The existing playable LIF controller is a contextual comparison on the same
paths but retains its documented ±65° encoder and voltage decoder.

## Cases and interventions

The calibration/sanity cases are static ±30° and ±70° plus the *previously
used* crossing x=3.2 sin(0.62t−1.2). They can expose implementation mistakes;
they will not determine parameters. The held-out target functions are frozen
here before evaluation (mirrors negate x):

| Pair | Base x(t), metres | Question |
| --- | --- | --- |
| Chirp / mirrored chirp | 2.6 sin(0.25t + 0.055t² − 0.9) | Changing speed |
| Triangle / mirrored triangle | −2.4 + 1.2t for t<4; 2.4 − 1.2(t−4) afterward | Reversal |
| Offset / mirrored offset | 1.4 + 0.9 sin(1.1t−0.4) | Persistent one-sided target |
| Step hold / mirrored step hold | −1.8 for t<2; +1.8 afterward | Final settling |

Conditions: intact; AOTU019→DNa02 edges removed; AOTU025→DNa02 edges
removed; both bridges removed; 32 deterministic within-side shuffles of
whole LC10a→AOTU output bundles (seed 20260927); direct bearing; existing
playable LIF. The shuffle preserves hemisphere, edge signs, the multiset of
source output bundles, and all AOTU→DN edges, but breaks the association
between retinal position and the particular source cell's output bundle.
Bridge removal tests output dependence; single-path removals test branch
contribution, not whether either type is dispensable in a real fly.

Registration sensitivity uses centered v3 plus all four one-column p/q
perturbations already derived from the source eye map, without selecting one
by pursuit performance. Widths 15°, 18°, 21° and steering-gain multipliers
0.8, 1.0, 1.2 are separate one-factor sweeps, each applied to every held-out
path. No combined grid search.

## Measures and decision before results

Report each active frame's absolute bearing in the mean, including out-of-
view frames. Also report median and final error, in-view fraction, turn-cap
fraction, continuous 1 s settling within ±10° after the last step change
(step-hold only), and sign crossings after the target enters ±10° as a
simple oscillation proxy. Keep full per-step traces ignored locally and a
compact JSON with metrics and hashes under `docs/evidence/`.

The fixed-fly v3 spatial gate from Step 3 must still pass. The motion check
must show the imposed AOTU019 preferred/nonpreferred ratio above 1.2 at
30° and 60° on both sides for 25°/s and 75°/s sweeps; AOTU025 should differ
by under 5%. Position-only must show no direction selectivity. This is a
software-rule check, not a claim of recorded motion tuning.

For a Step 5 recommendation, the primary intact model must have a median
held-out mean bearing error at least 20% below bridge removal, never exceed
bridge removal by over 10% on an individual path, retain ≥80% in-view frames
on every path, spend <25% of frames at the turn cap, and continuously settle
on both step-hold cases before the 8 s end. It must beat the median shuffled
model on at least six of the eight held-out paths. Bridge removal must produce
zero neural command, and each single-path removal must change fixed-fly DN
output somewhere. The median held-out error under each one-factor width,
gain, and registration perturbation must stay within 25% of nominal.

These are practical demo bounds, not biological thresholds. If any gate
fails, report the component and stop before Step 5 rather than retuning the
same held-out paths. The direct rule may outperform the candidate without
invalidating a distinct wiring effect; report that comparison honestly.

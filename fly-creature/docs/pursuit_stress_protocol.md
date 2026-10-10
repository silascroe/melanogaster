# Frozen pursuit stress protocol

Declared 2026-10-02 before evaluation. This tests the existing `activity_v1`
controller without changing its graph, map, normalization, dynamics, gain,
sensor bounds, or motor queue. World timestep is 10 ms, walking speed 0.55
m/s, duration 10 seconds. There is no collision, distance-dependent retinal
size, obstacle avoidance, search behavior, or target stopping rule. The world
is unbounded; this is an offline controller test, not a room simulation.

## Cases

All equations and case construction live in `pursuit_stress.py`, frozen and
hashed before running. Each case is reflected across X, including initial
heading, giving 48 runs per controller. Reflection checks asymmetry without
assuming that the selected anatomy is symmetric.

| Family | Levels | Definition |
| --- | --- | --- |
| Following distance | 3, 5, 8 m | Forward-moving target; novel two-frequency lateral motion scales with depth |
| Target speed | 0.35, 1.7, 3 rad/s | Lateral sinusoid at fixed amplitude, forward-moving target |
| Reversals | periods 2, 4, 6 s | Continuous triangular lateral motion, forward-moving target |
| Starting heading | 25, 65, 105 degrees | Offset body heading, forward-moving target |
| Disappearance | 0.2, 0.8, 2 s | Target inactive from t=4 while continuing its trajectory |
| Reappearance elsewhere | 0.2, 0.8, 2 s | Same disappearance, target changes lateral position while hidden |
| Stationary depth | 2.5, 5, 8 m | Target does not retreat; fly may approach/pass it |
| Unsupported initial inputs | behind, beyond 9 m, closer than 0.4 m | Boundary cases, not expected tracking successes |

The first six families are the supported-task evaluation (36 reflected
cases). Stationary depth and unsupported input are challenges, reported
separately rather than silently excluded. No new-case results select gains.

## Controls

Run intact and bridge-disconnected actual `ActivitySteeringSession` objects.
Run 32 independently permuted LC10a outgoing bundles within each side, seed
20261002; preserve recorded weight bundles and the intact normalization.
Inject only the shuffled adapter into the actual session for this diagnostic.

Also run an ordinary proportional bearing controller with the same sensor
range, field of view, turn cap, body and 200 ms command delay. Select its gain
from 0.5/1/2/3/4/6/8 rad/s per radian, using only the six **previously
evaluated** delay-diagnosis paths; minimize their mean error, tie to lower
gain. Repeat that same selected gain without delay to disclose the cost of
the imposed delay. This is a more serious comparator than the prior fixed
gentle gain, but it is still one controller family, not the best possible
ordinary controller. No calibration or retuning uses the new 48 cases.

## Measurements and interpretation

Primary error averages absolute bearing on **all active-target ticks**,
including out-of-view ticks. Hidden ticks are excluded because no target is
available then. Report active-target visibility, distance, turn saturation,
lookup clipping, final active bearing, turn effort and inactive-turn count.
Track reacquisition after disappearance: first 0.5-second continuous interval
within 10 degrees and visible; report completion latency from reappearance,
or null. Boundary cases never receive a fictitious recovery score.

A case meets the declared tracking envelope if active mean error <=10 degrees,
active visibility >=80%, capped ticks <25%, no lookup clipping, no turning
while inactive, and (when applicable) reacquisition completes within 1.5 s.
Report each component; do not treat a whole-matrix pass as a biological claim.
Aggregate with equal case weights and report family and mirror differences.
Compare intact with median shuffle and disconnected per case; use aggregate
shuffle ranks descriptively, not as independent biological replicates.

Save compact JSON/CSV and full local traces for intact/matched direct runs.
Reproduce the already measured harmonic result as a seam check. Preserve the
working controller even if it fails; diagnose failures before proposing fixes.

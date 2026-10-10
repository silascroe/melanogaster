# Pursuit timing audit and next experiment contract

2026-10-02. Research/design complete; no production timing changed.
[Reproducible audit](evidence/pursuit_timing_audit_v1.json),
runner `tools/audit_pursuit_timing.py`.

The specified benchmark is now implemented: see the
[matched retinal result](pursuit_retinal_result.md) and
[frozen implementation protocol](pursuit_retinal_protocol.md). Production
timing and the verified 450 ms source default remain unchanged.

## Primary evidence resolved

The [authors' final article](https://wilson.hms.harvard.edu/sites/g/files/omnuum8421/files/2026-03/Collie%202026.pdf)
is now accessible through their lab, resolving our earlier abstract-only gap.

| Evidence | Location in final PDF | Meaning |
| --- | --- | --- |
| Male AOTU019 40 ±9 ms; AOTU025 36 ±10 ms | PDF p5, Figure 3D | Visual-response derivative-peak latency |
| Activity precedes turning by about 200 ms | PDF p10, Figure 8 discussion | Neural/behavioral lead-lag |
| Steering updates retinal position after 200 ms | PDF p24, e8, Equation 6 | Published model feedback delay |

The latency measure uses a firing-rate derivative peak. Neural/behavior lag
uses cross-correlation; post hoc smoothing is described on e5–e7. These are
not hard onset delays or individual synaptic constants. The paper uses a
fixed-distance, rotation-only model; our translating body is a different task.
The final model's direction penalty is 0.66, and its random-motion source is
filtered at 0.05 Hz (e8–e9).

## Released code is a separate reference

The pinned author revision remains
`65d72773121ffe148b56b8ba4f594a7a51c51789`. The audit hashes files and records
exact source-line locations. `modelSettings.m` sets `AOTU019_delay=450` and
`Others_delay=AOTU019_delay`; the dynamic function reads 45-sample-old visual
positions and their adjacent history. It then updates retinal position with
the current computed steering value. It does not add a separate 200 ms queue.

`visuomotor_delay=200` is used by `analyzeErrorVsTurn.m` to align data for
analysis. That analysis shift is not an additional dynamical delay. The
function's `dt=2/fs` affects reported velocity, not its 100 Hz position update.
The variable values and operation sites, rather than comments such as
"Apply delay for DNa02 output", establish what the code actually does.
Why its 450 ms default differs from the article's 200 ms remains unresolved.
Do not change the pinned reference or its verified numerical fixtures.

## What our simulator currently means

The activity adapter is a static function of bearing and the sign of the
previous bearing increment. It has no separate synaptic, membrane or muscle
time course. Its recorded edges, hypothetical fields, imposed direction rule,
normalization and output cap jointly generate a current turn request.
The runtime delays that request by 20 ticks, then the world uses the delivered
command for the next body interval. This is a coarse source-supported
feedback approximation, not a measured AOTU→DNa02→muscle conduction time.

A clamped constant-input probe finds the first sensor sample at 10 ms,
first nonzero delivered command at 210 ms, and first changed heading sample
at 220 ms. The command queue is exactly 200 ms; the last difference reflects
the next integration interval's endpoint. Preserve this convention. Do not
silently shorten the queue to 19 ticks to match a plotted first movement.
Rendering/HTTP wall-clock latency is separate from this logical timing.

## Rejected timing shortcuts

Subtracting the visual-response value from 200 ms does not establish a motor
delay: the two observations refer to different signals and measurements.
Adding a literal 40 ms input hold would be a new hypothesis, not a recovered
cellular time course. A population derivative peak does not specify a pure
input FIFO, a filter time constant, or a cell-by-cell latency distribution.
Post hoc Gaussian smoothing must not become an acausal online neural filter.

More fundamentally, merely redistributing a fixed delay cannot improve our
static adapter. If `F` maps a timestamped bearing/direction feature to a
command and `D` delays the whole feature, `F(D(input)) = D(F(input))`.
Pointwise normalization, lookup and clipping do not break this equality.

The audit checks 600 continuously visible active samples against the actual
session. All four total-200-ms splits (sensory/motor 0/200, 40/160, 100/100,
200/0) produce identical commands: maximum difference **0.0 rad/s**.
Both the bearing and direction feature carry the same source timestamp, and
missing warm-up samples produce zero output. This result does not cover
different reset/hiding rules, unequal pathway delays, state-dependent gain,
or added temporal dynamics. None should be introduced just to beat a path.

## Task difficulty is also different

The audit measures independent target bearing with a straight-walking body,
before the controller's steering feedback. The old speed-3 case averages
40.105°/s and peaks at 84.771°/s; speed-1.7 averages 22.791°/s and peaks at
48.049°/s. The fresh shallow chirp peaks at 88.476°/s. Our imposed turn cap
is 68.755°/s. A target peak exceeding this cap is a challenge, not proof of
an impossible whole trajectory or the sole cause of the observed error.
Mean speed alone also does not describe reversal frequency or predictability.
Do not equate these paths with the article's filtered random motion.

## Concrete next implementation: matched retinal reference benchmark

Purpose: determine whether our adaptation loses something the reference can
do under **identical** inputs, body/update conventions, timing and saturation.
This is the next build, not an already executed result.

First preserve the verified 450 ms author-code reproduction. Create a
separately labelled article-method variant of that core with both pathway
delays explicitly set to 200 ms. Cross-check its delayed update against an
independent Equation-6 implementation using a shared timestamped input stream.
Use exact 10 ms intervals and report per-step turning separately from the
source's velocity-reporting quirk. Do not call a parameter override an exact
Figure 6 reproduction: tables, noise/filter details and aggregate outputs
still need corresponding source evidence.

Then compare the author aggregate fields and our packaged MaleCNS projection
in a rotation-only retinal world at fixed distance. Use matched 200 ms
feedback, initial hold/warm-up, visibility, gain and cap. Record an uncapped
source-reference case separately; our 1.2 rad/s cap is engineering. Keep the
200 ms delay even if zero delay scores better. Do not rederive fields from
successful outputs or silently renormalize the recorded projection.

Freeze the protocol and input streams before running. Include mirrored
held steps, constant-speed sweeps at 25/75°/s, and independently generated
smooth target paths. These speeds define diagnostic inputs, not a claim that
our chosen sweeps reproduce the article's stimulus duration or geometry.
Include slow and fast/reversing paths already consumed for diagnosis; reserve
fresh trajectories for any subsequent promotion decision. Use the same exact
stream for every controller, rather than matching only average target speed.

Compare direction on/off, bridge removal, within-side bundle shuffles, and
ordinary proportional steering under the same 200 ms timing. Author table
responses already contain output-strength information; do not multiply them
by our individual edges. Trace visual feature, AOTU contribution, DNa02
difference, command creation/delivery and body application timestamps.

Report error, continuous settling, saturation, visibility, and aggregate
wiring-control ranks. A useful circuit result needs both anatomical
dependence and a clear account of engineering contributions. Do not make
beating an ideal exact-bearing controller a biological prerequisite.

Interpretation: if the reference and adaptation share the fast-motion
weakness, it supports an operating-range limitation under this contract.
If the reference handles the same stream substantially better, isolate the
remaining spatial/normalization/readout differences one at a time. Neither
outcome automatically promotes a playable change. Freeze any proposed fix
before fresh validation, including gentle-path regression gates.

Use **Sol medium** for this implementation: the difficulty is keeping the
reference, recorded projection and timing conventions comparable, not adding
features. No temporal filter, new circuit, gained speed control or Godot
change is part of this benchmark.

## Verification and retrieval limits

The audit ran through actual packaged data, source files and runtime. Its
source hashes and numerical checks are saved. The final PDF was read via
web extraction; a direct local download was denied by the host, so no local
PDF checksum is claimed. The official URL and PDF-page anchors are recorded.
The paper's methods and the pinned code remain distinct sources of truth.

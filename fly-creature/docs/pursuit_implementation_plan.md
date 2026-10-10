# Published pursuit reference and MaleCNS adaptation

Status: implementation plan, 2026-09-26. No runtime changes made by this plan.
Background: [research reassessment](pursuit_reassessment.md).
Step 1 source and protocol audit: [pursuit_reference_contract.md](pursuit_reference_contract.md).

## Intended result

A selectable pursuit implementation whose response rules are traceable to a
published reference and whose MaleCNS wiring contribution can be inspected.
The first visible milestone is a fly centering a moving target in Godot, with
intact and pathway-disabled comparisons and correctly labeled activity.
This milestone does not include a complete retina, neural walking-speed
control, or whole-brain simulation.

Keep three identities explicit: existing LIF baseline, published reference,
and MaleCNS adaptation. A successful reference reproduction does not validate
the adaptation. A population-level reference does not run our 281 neurons.

## 1. Establish the reference contract

Pin the authors' repository revision, file hashes, license, dataset version,
and one specific published protocol. Trace its calling script, effective
parameters, visual tables, sign conventions, delays, timestep, interpolation,
and conversion to turning velocity. Resolve overrides rather than treating
`modelSettings.m` defaults as a figure specification.

Select one fixed-fly response protocol and one closed-loop target-centering
protocol. Establish expected curves, units, and comparison tolerances before
evaluating the Python implementation. Use identical deterministic inputs.
Prefer numerical traces from the original MATLAB implementation; assess
Octave compatibility if no suitable existing MATLAB runtime is available.
Do not install a large runtime before checking necessity and compatibility.
If only published plots can be compared, record the weaker reproduction
claim and digitization uncertainty. Do not silently claim numerical parity.

Deliverable: `docs/pursuit_reference_contract.md`, compact source manifest,
and permitted reference fixtures. Keep third-party source in ignored research
outputs until reuse terms are resolved; do not publish an unauthorized port.

## 2. Implement and verify the Python reference

Proposed module: `src/fly_creature/pursuit_reference.py`; parameters and
permitted compact data under `src/fly_creature/data/`.

Keep the numerical update independent of Godot. Input is a time-stamped
retinal target position plus only the additional variables required by the
chosen protocol. State contains pathway activity and delay histories. Output
contains bilateral AOTU and DNa02 activity and the reference turning command.
Use the reference's internal timestep, explicit units, and deterministic reset.
Do not reuse the existing 65-degree gate, bearing-dependent current ramp,
voltage decoder, or turn cap without identifying each as an adaptation.

Verify the fixed-fly and closed-loop traces against phase 1. Inspect response
shape, magnitude, latency, signs, and pathway interventions. A correct-looking
trajectory alone is insufficient. Test delay boundaries, angle wrapping,
reset, and elapsed-time handling where they can alter the scientific result.

Gate: documented reproduction at the available evidence level. If it fails,
resolve the discrepancy before adapting the circuit; do not tune it away.

## 3. Make the MaleCNS adaptation explicit

Proposed module: `src/fly_creature/pursuit_activity.py`; build tooling under
`tools/`. Runtime assets must remain portable within `fly-creature/`.

Trace the authors' receptive-field construction and v0.9 cell identities to
our v1.0 release. Produce a coverage/mismatch report before substituting data.
The intended cell-level path is visual input to LC10a, real selected edges to
AOTU019/AOTU025, then signed edges to DNa02 and an explicit motor readout.
Determine which response tables already incorporate LC10a and downstream
weights so those weights are not counted twice.

Only implement per-cell visual fields where the derivation supports them.
If the reference supplies only aggregate AOTU fields, retain that reference
as an aggregate model and identify the missing information for the cell-level
adaptation. Do not fabricate 275 measured fields or pretend that the lookup
table itself exercises all their individual connections.

Record every response curve, normalization, direction preference, baseline
activity, and delay as measured, anatomy-derived, or assumed. Hold the
reference dynamics fixed while substituting mapped connectivity; separate
any later calibration from that comparison.

## 4. Evaluate on a bounded protocol

Choose calibration cases and held-out cases before fitting anything. Compare
fixed-fly spatial and motion responses first, then held-out pursuit paths.
Use intact wiring, each main pathway disabled separately, bridge removal,
and an appropriate wiring shuffle preserving side/sign and relevant weight
statistics. Explain precisely what each intervention tests.

Report tracking error, settling time, overshoot/oscillation, target loss,
activity saturation, and sensitivity to a small declared parameter range.
Distinguish imposed direction selectivity from effects caused by connectivity.
Keep the LIF and direct-bearing controllers as contextual comparisons.
Do not require beating direct bearing as evidence of biological relevance.

Gate: the reproduction remains valid; the adaptation shows supported response
patterns and interpretable intervention effects on held-out cases; tracking
is stable enough for the demo. Define quantitative bounds from the selected
reference protocol before evaluating the candidate. If the adaptation fails,
report the failed component and retain the verified reference without
launching an open-ended parameter search.

## 5. Integrate through the existing creature interface

Add explicit model selection to `CreatureSession` and `/session` in
`controller.py` and `server.py`. Preserve the existing `lif.py` implementation
and jump pathway. Return model/version, condition, activity units, pathway
activity, and `turn_rate_rad_s`. Do not put activity values in mV/spike fields.

Update `godot/neural_bridge.gd` to request the selected model, and `main.gd`
to display its actual units and assumptions. Use fixed simulation steps and
an elapsed-time accumulator so HTTP latency/render rate cannot silently alter
neural delays. Handle missing replies explicitly rather than accumulating
an unlimited stale turning command. Match this timing in the offline replay.

First integrate as a selectable candidate. Keep walking speed explicitly
scripted for this milestone. Make a repeatable intact/disabled demonstration
with the existing portable Godot and a 1080p/60 fps capture; inspect sampled
frames and telemetry and provide the video for user inspection.

Verify session reset, backend selection, response units, actual service/Godot
integration, preserved escape behavior, and standalone packaged data access.
Update README, decisions, and handoff with measured outcomes and remaining
limitations. Promote the candidate only after the gates above are satisfied.

## Work order and stopping point

Phases 1–2 now have a pinned contract and a Python reference that matches
the unchanged author core running in Octave for static and deterministic
step cases, plus shared unfiltered perturbations. See
[the Step 2 result](pursuit_reference_result.md). MATLAB's low-pass noise
pipeline, the 20,000-run aggregate, and final-paper figure correspondence
remain unverified. Phase 3's [mapping audit](pursuit_mapping_result.md)
found 16/16 preserved downstream partner IDs and confirmed that reusing the
already weighted source curves with v1.0 edges would count strength twice.
The original offline v1.0 projection's assumed AOTU025 field peaked 27° away
from the reference. The [registered eye-map candidate](pursuit_registered_eye_map_result.md)
supplied a source-derived, cross-specimen angular hypothesis and passed the
fixed-fly check. Phase 4 was then run under a [frozen protocol](pursuit_step4_protocol.md);
see the [result](pursuit_step4_result.md). Intact wiring improved centering
against bridge removal and 32 within-side shuffles on eight held-out paths,
but the controller oscillated rather than continuously settling on the two
step-hold cases and failed the declared gain-sensitivity bound. Its direct
and earlier LIF controls also tracked better. **Phase 5 is not authorized by
these results.** Preserve the failed run and use fresh held-out cases for any
future revised controller. Speed regulation and search are later work with
their own sensory inputs, neural outputs, and evidence.

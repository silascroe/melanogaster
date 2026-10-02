# Matched retinal benchmark v1

Frozen before results, 2026-10-02. Offline only; no promotion or gain search.

Question: does the source-inspired reference share our adaptation's fast-motion
weakness under identical world motion and engineering constraints?

100 Hz, 12 seconds, fixed distance 6 m, rotation only. First second freezes
body rotation but samples inputs and fills queues. All models use their own
closed-loop retinal bearing, the same exogenous world-angle array, a 200 ms
queue, prior delivered command applied during the next body interval, a
120-degree visibility window and a 1.2 rad/s cap. Gain stays 0.65; ordinary P
stays 4/s. Invisible inputs produce zero commands but do not reset queues.
Direction uses successive visible-or-zero retinal samples, matching the current
activity controller. No hide/reset scenarios in this protocol.

Mirrored steps 20/60/105 degrees; triangle sweeps at exactly 25/75 degrees/s
between -60 and +60 degrees; three new smooth multisine paths (two independent
seeded frequency/phase draws plus one chirp); previously examined slow/fast
sinusoidal and reversing paths converted to world angles. Exact arrays and
their hashes are saved before evaluation. New paths become diagnostic evidence,
not reserved validation for a later fix.

Compare author aggregate RF with direction on/off; our recorded-edge projection
with direction on/off; bridge removal; ordinary P. Also 32 within-side LC10a
input-bundle shuffles for each direction setting, keeping original normalization.
Author responses already encode output strength: never apply our edges to them.
An additional uncapped author run isolates our engineering cap, not biology.

Score mean absolute retinal error after the hold, fraction visible, cap fraction,
and earliest full consecutive second within 10 degrees for step cases. Report
family aggregates and intact rank among shuffles. No biological success gate.
Save timestamped traces locally, compact CSV/JSON in docs/evidence.

Separately validate a 200 ms parameter override of the previously verified
source core against an independent Eq6 recurrence, on mirrored stationary and
smooth moving inputs. Preserve source 450 ms defaults and fixtures. This is an
article-method variant of the pinned core, not exact final-figure reproduction:
the source includes ELU lookups and DNa02 nearest quantization. The parity
section uses full visibility, no cap, and immediate delayed-history updates;
the matched world deliberately adds the production body endpoint convention.
Report true degrees/s from 10 ms increments; the legacy source's reported
velocity divides by 20 ms and remains untouched.

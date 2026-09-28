# Step 4 result: wiring matters; this controller does not settle

Date: 2026-09-27. The [frozen protocol](pursuit_step4_protocol.md) was written
before the held-out run. The reproducible [compact result](evidence/pursuit_step4_v1.json)
and `src/fly_creature/pursuit_step4.py` contain the parameters, source hashes,
interventions, all path metrics, and decision gates. Detailed step-hold traces
are ignored local files under `outputs/research/pursuit_step4_traces/`.

**Decision: Step 4 was implemented and run, but its Step 5 promotion gate
failed.** Keep the new candidate offline. The older playable Godot/LIF
steering demo and verified aggregate pursuit reference remain separate.

## What was actually adapted

The v3 eye-map hypothesis drives the selected 275 LC10a cells through their
recorded v1.0 LC10a→AOTU edges. The authors' delayed dynamic AOTU ELU
transformation and AOTU019 nonpreferred-motion factor are applied to those
derived AOTU curves. The four recorded signed AOTU→DNa02 edges determine
which side receives excitation or inhibition. Branch maxima and edge maxima
set dimensionless activity units, and the authors' 0.65 gain turns right-minus-
left DNa02 model activity into a 10 ms turning command. A 1.2 rad/s cap and
the walking body are engineered. This is a **source-inspired cell-level
adaptation**, not a numerical reproduction of the published population model
after its response table is replaced. It does not simulate measured spikes.

The original v3 fixed-fly spatial gate still passes. With the published
motion penalty, AOTU019's preferred/nonpreferred response ratio is 1.73–1.79
at the declared angles on both sides; AOTU025's is 1.00. Position-only has
ratio 1.00 everywhere. The direction preference is therefore imposed by the
published motion rule, not discovered from the v1.0 graph. The unchanged
Step 2 Python reference was rechecked against its pinned Octave traces; all
three source direction conditions still passed the 1e-6 tolerance.

## Held-out paths

Mean absolute target bearing over all eight seconds, including startup, in
degrees. Lower means better centering in these synthetic paths; the direct
rule and existing LIF controller are contextual comparisons with different
input and model assumptions. Each mirrored path uses the same rule with x
negated.

| Held-out path | Intact candidate | Output bridge removed | Median of 32 wiring shuffles | Direct bearing | Playable LIF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Chirp | 13.660 | 18.256 | 17.144 | 8.958 | 9.325 |
| Mirrored chirp | 12.916 | 18.256 | 15.192 | 8.958 | 9.241 |
| Triangle | 11.329 | 14.765 | 15.131 | 7.734 | 8.890 |
| Mirrored triangle | 11.260 | 14.765 | 14.626 | 7.734 | 8.804 |
| Offset | 10.914 | 18.795 | 13.962 | 4.658 | 6.925 |
| Mirrored offset | 10.907 | 18.795 | 13.927 | 4.658 | 6.938 |
| Step hold | 14.397 | 21.829 | 18.004 | 4.046 | 8.911 |
| Mirrored step hold | 14.788 | 21.829 | 20.144 | 4.046 | 8.932 |

Median path error is **12.123° intact** versus **18.526° bridge removed**,
**6.196° direct bearing**, and **8.901° playable LIF**. The intact candidate
beats bridge removal and the median shuffle on all eight held-out paths;
none of the 32 shuffled models beats its mean score across the eight.
This is evidence that the modeled retinal positions paired with the specific
LC10a→AOTU output bundles affect behavior. It does not show that the candidate
tracks better than simpler software or the older playable model.

Both individual AOTU pathway removals change fixed-fly DNa02 output. On
held-out paths the median error is 13.285° with AOTU019 output removed and
11.044° with AOTU025 output removed. The latter can improve centering in
this adapter; this is a warning against calling all selected edges uniformly
useful. Bridge removal produces exactly zero neural turn command. The target
stays within the common ±120° view on every path, and no AOTU or DNa02
lookup clips in the nominal candidate.

## Why the gate failed

The frozen protocol required a continuous one-second stay within ±10° on
both step-hold cases. Neither happened. The intact trace crosses the target
near center **nine times** on each side; the direct rule and playable LIF
each have one such crossing and settle. The 450 ms delayed feedback keeps
steering after the object has passed the center. The predeclared turn-cap
fraction stayed below 25%, so clipping is not the main explanation. This is
consistent with the Step 2 observation that the published source's own
zero-noise 120° example lacks a continuous one-second stay within ±2° even
where its cumulative helper reports settling.

The one-factor sensitivity gate also failed. One registration-column shift
changes median error to 10.538°–13.477°; widths 15° and 21° yield 9.912°
and 13.847°. A 20% lower gain improves the median to **8.374°**, more than
25% from nominal 12.123°, while 20% higher gain worsens it to 14.083°.
The lower-gain step cases still do not settle and still cross center nine
times each. The gain improvement is an *exploratory diagnostic on this
already-seen held-out set*, not permission to choose 0.8 and declare success.

The other frozen gates pass: spatial and imposed-motion checks, bridge and
single-path effects, ≥80% in-view time, <25% nominal turn-cap time, no path
more than 10% worse than bridge removal, median error ≥20% better than bridge
removal, and eight of eight paths better than median shuffle. Failure of the
settling and sensitivity gates is enough to stop before Step 5.

## Scope and next decision

The external eye map is a cross-specimen anatomical hypothesis; most left
AOTU input contact weight still depends on skeleton fallback. The dynamic
adaptation uses source-inspired transformations and recorded edge signs but
introduces explicit activity normalizations, an engineered ±120° view, a
turn cap, and a walking world. Only the source reference, not this new
adaptation, has numerical Octave parity. The scripted target paths are
synthetic and are not fly experiments.

Do not retune the failed candidate on these eight paths or integrate it into
Godot. A future revision should first explain the delayed oscillation and
gain sensitivity with fixed-fly or simple step diagnostics, then declare
*new* held-out cases before evaluating a revised controller. Preserve this
run as the comparison baseline.

## Reproduce and verify

From `fly-creature/`, with the root workspace virtual environment installed:

```powershell
..\.venv\Scripts\python.exe -m fly_creature.pursuit_step4
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe tools\check_pursuit_reference.py
..\.venv\Scripts\python.exe tools\check_pursuit_field_gate.py
```

The source reference check needs the previously pinned ignored author source
and Octave traces; the field gate needs the pinned response CSV. The Step 4
runner itself uses only compact creature data. Root project tests, data-copy
verification, and `git diff --check` also passed on this run.

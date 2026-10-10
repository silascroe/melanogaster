# Step 2: Python pursuit reference reproduction

Date: 2026-09-26. Source and selected protocol:
[pursuit_reference_contract.md](pursuit_reference_contract.md). Compact numerical
comparison: [pursuit_reference_comparison_v1.json](evidence/pursuit_reference_comparison_v1.json).

## What ran

`src/fly_creature/pursuit_reference.py` is an offline, independently written
population-activity implementation. It loads a response CSV supplied at run
time, mirrors the two contralateral minor pathways, and provides the source's
static steering calculation and dynamic closed-loop step response. It has no
MaleCNS v1.0 neuron graph, no LIF spikes, no Godot interface, and no licensed
response table packaged with it. The existing playable creature is unchanged.

I ran the pinned authors' *unchanged core functions* with portable GNU Octave
11.3.0. An external harness supplies source settings and parses the CSV;
separate shims supply `wrapTo180` and the missing `lowpass`. The Octave build
is under `C:\Users\ringd\.codex\tools\octave\11.3.0\`. Its official
459 MB archive was downloaded from GNU and had SHA-256
`fd3cf0e885467a15211b8ceded42800432a5462481324d49a896ef257e05d1a0`,
matching the official GitHub release checksum. The authors' repository
remains a clean clone under ignored `outputs/research/CollieWilson/`.

The low-pass shim is **identity**, so zero-noise runs preserve the author
function's meaningful inputs exactly. The nonzero-noise check is a shared
perturbation test of the feedback equations; it is *not* a reproduction of
MATLAB's random low-pass process. Neither check establishes numerical parity
with MATLAB itself. The tracked Octave harness and ignored complete traces can
be rerun locally; only the compact comparison summary is retained as evidence.

## Numerical comparison

The static 361-angle steering curve differs by at most **3.9e-16** activity
units. For the closed-loop 120° step, I compared three direction-selectivity
conditions, both start sides, and all 1,600 samples: azimuth, reported turn
rate, six pathway channels, and time. Maximum azimuth discrepancy was
**5.7e-14°**, below the predeclared 1e-6 tolerance. Every other channel
also matched to floating-point precision. With eight runs per condition and
shared nonzero unfiltered noise, maximum azimuth discrepancy was again
**5.7e-14°**. The compact JSON records the maximum for every signal.

These comparisons verify that Python follows the pinned author core's
lookup, pathway signs, delays, direction penalties, feedback update, angle
handling, and peculiar reported-velocity conversion for these protocols.
They do not validate the model as fly physiology.

In the zero-noise two-run example, average absolute retinal error after
release was 23.70° with no direction selectivity, 13.70° with AOTU019
selectivity, and 25.51° with AOTU025 selectivity. Final absolute error was
23.72°, 0.07°, and 7.13° respectively. The eight-run unfiltered-noise case
showed similar ordering, but its sample and noise process are inadequate for
claims about the authors' 20,000-run experiment.

## Settling-time correction

For the zero-noise AOTU019 case, the source helper reports 6.064 s after
release. I called the authors' actual `calculateAverageSettlingTime.m` in
Octave and confirmed that number. Its implementation accumulates in-band
samples across separate visits. A separate corrected measure requiring
**100 consecutive samples** within ±2° found no qualifying one-second stay
in either run. The eight-run shared-noise case likewise had zero qualifying
stays for AOTU019 despite its source-style 6.079 s result. This is a
measurement correction for these specific traces; the effect on the full
publication analysis has not been evaluated.

## How to reproduce

From `fly-creature/`, after obtaining the pinned authors' repository at the
path recorded in the source contract:

```powershell
$octave = 'C:\Users\ringd\.codex\tools\octave\11.3.0\octave-11.3.0-w64\mingw64\bin\octave-cli.exe'
& $octave --quiet --no-gui --eval "source('tools/pursuit_reference_octave/run_zero_noise.m')"
& $octave --quiet --no-gui --eval "source('tools/pursuit_reference_octave/run_shared_noise.m')"
$env:PYTHONPATH = 'src'
..\.venv\Scripts\python.exe tools\check_pursuit_reference.py
```

Our harness and compatibility shims are tracked under
`tools/pursuit_reference_octave/`. The authors' source and complete traces
stay ignored.

## Boundary for the next stage

We now have a verified mathematical reference for the selected static and
step cases. It is a model of *pathway activity*, not a run of our 281 MaleCNS
neurons. Step 3 must determine which source fields already include
connectome output weights, resolve v0.9-to-v1.0 correspondence, and define
how cell-level visual input can be supported before substituting our graph.

The exact MATLAB low-pass noise pipeline, the authors' full 20,000-run
aggregate, and correspondence to a numbered final-paper figure remain
unverified. They should not be silently inferred from the parity results.

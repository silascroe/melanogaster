# Pursuit delay diagnosis: revised offline candidate settles

2026-09-30. [Frozen protocol](pursuit_delay_protocol.md),
[compact evidence](evidence/pursuit_delay_v1.json),
[trace plot](evidence/pursuit_delay_v1.png) ([SVG](evidence/pursuit_delay_v1.svg)).

**Decision:** The declared 200 ms motor-effect / smooth center-input candidate
passes this diagnostic and fresh-path review gate. It remains offline pending
a separate integration decision. Frozen Step 4, reference reproduction,
packaged graph, and playable Godot controller have not changed.

## Cause supported by the interventions

The runner reproduces frozen Step 4 metrics exactly on both step-holds;
regression tests cover all eight original paths. A 16-configuration matrix
changes visual-history delay, additional motor delay, and eye aperture while
holding graph, map, gains, normalization, motion rule, and body constants fixed.
Rotation-only controls remove forward translation as a possible cause.

| History / motor delay / overlap | Walking step error | Continuous settling | Final-second peak |
| --- | ---: | --- | ---: |
| 450 ms / 0 / 0 degrees (original) | 14.397 degrees | none | 18.017 degrees |
| 450 ms / 0 / 15 degrees | 13.960 degrees | none | see evidence |
| 200 ms / 0 / 0 degrees | 5.481 degrees | 2.52 s | see evidence |
| 0 / 200 ms / 0 degrees | 6.402 degrees | 2.66 s | 7.680 degrees |
| 0 / 200 ms / 15 degrees (declared) | 3.231 degrees | 2.60 s | 0.949 degrees |

Large delayed-feedback oscillation persists with no forward motion. Overlap
alone does not cure it; reducing feedback delay to 200 ms makes both mirrored
steps settle. Adding both 200 ms history and 200 ms motor delays fails again.
Total feedback latency matters; this does not establish that motor-queue
placement is biologically correct. History queues repeat the first observation
during startup, whereas motor queues initially emit zero, so their placement
comparisons also differ during startup. Actual body effects include the
unchanged next-tick application of every command (one additional 10 ms tick).

The old gate supplies zero input at exactly zero bearing but large signed turn
signals immediately either side. At -1/+1 degrees those signals are
-0.634/+0.683; the overlap gives -0.091/+0.124. This reduces effective feedback
gain near center despite keeping the explicit motor gain fixed. The intervention
tests engineered smooth center encoding, not binocular anatomy independently
of signal strength.

The mirrored revised step settles at 2.67 s; its final-second peak is 0.884
degrees. Both stay inside the 10-degree band after settling. There are about
30 tiny sign crossings versus nine large baseline crossings: count alone is
misleading. Degree bins and the motion-penalty switch remain possible sources
of small jitter; neither was changed.

## Independent-source interpretation

The pinned source settings name a 200 ms `visuomotor_delay` and 450 ms AOTU
delays, but the reproduced active source loop reads 450 ms-old positions and
does not apply an additional 200 ms motor queue. Step 4 followed that loop,
rather than accidentally stacking both delays.
[Collie et al.'s earlier figure description](https://pmc.ncbi.nlm.nih.gov/articles/PMC12212441/)
describes a 200 ms delay. This supports testing an alternative; it does not
make this revision a numerical reproduction or resolve the version/code
discrepancy. The 50 ms matrix level is exploratory, not a measured latency.

[Zhao et al.'s eye map](https://www.nature.com/articles/s41586-025-09276-5)
reports binocular overlap below 20 degrees; [earlier courtship work](https://pmc.ncbi.nlm.nih.gov/articles/PMC5047376/)
uses a central 30-degree region. Our 15-degree **total** linear crossfade
(-7.5 to +7.5) is an engineering hypothesis, not a measured LC10a field or
uniquely supported width. We report 10/20-degree sensitivities without
selecting either alternative from these results.

## Six new paths

The candidate and paths were declared before the matrix or evaluation ran.
Each path has a mirrored partner. Values are mean absolute target bearing over
eight seconds including startup, in degrees.

| Path | Original | Candidate | Bridge removed | Median shuffle | Direct bearing | Playable LIF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Harmonic | 10.810 | 2.350 | 12.296 | 3.233 | 6.957 | 8.593 |
| Mirrored harmonic | 11.060 | 2.395 | 12.296 | 3.301 | 6.957 | 8.541 |
| Dwell reversal | 12.949 | 4.376 | 13.606 | 8.075 | 5.698 | 9.023 |
| Mirrored dwell reversal | 13.308 | 4.429 | 13.606 | 7.928 | 5.698 | 9.017 |
| Ramp-stop | 10.792 | 2.288 | 9.344 | 5.257 | 4.815 | 7.225 |
| Mirrored ramp-stop | 11.006 | 2.260 | 9.344 | 5.316 | 4.815 | 7.207 |

Median path error: original 11.033 degrees, candidate **2.373 degrees**, bridge
removed 12.296 degrees, direct 5.698 degrees, playable LIF 8.567 degrees.
None of 32 shuffles beats the candidate's aggregate mean across six paths.
Shuffles preserve each side's output-bundle multiset and fixed normalization;
no candidate or shuffle lookup clips on these paths. Bridge removal emits
zero turn. Every candidate fresh-path frame is in view. Step-hold cap fractions
are 2.62% and 4.37%. All declared gates pass.

Gain multipliers 0.8/1.2 yield median errors 2.821/2.188 degrees (+18.9%/-7.8%),
and both mirrored steps still settle. The sensitivity bound passes; these are
not new defaults. The direct rule has different gain and input assumptions:
its ranking is not proof this graph is superior to conventional control or
reproduces a real fly. These six synthetic paths are now used evaluation data.

## Reproduce and verification

From `fly-creature/`, with this package installed in the root environment:

```powershell
..\.venv\Scripts\python.exe -m fly_creature.pursuit_delay_diagnostic
..\.venv\Scripts\python.exe -m pytest -q tests
# Optional plotting, after installing .[research-plots]:
..\.venv\Scripts\python.exe tools/plot_pursuit_delay.py
```

The runner uses packaged creature data only. Protocol, map, graph, runner and
Step 4 hashes are in the evidence. Detailed traces remain ignored under
`outputs/research/pursuit_delay_traces/`. 15 creature tests and 69 lab tests
pass; original/working release verification passes. An added peak-after-settling
metric initially included the sample before its interval: its index was
corrected and the regression checks the full remaining interval. Existing
settling metrics were not altered. Matplotlib 3.11.2 was installed only in the
root virtual environment; `research-plots` records the optional dependency.

Next: review residual jitter and a portable controller interface, then consider
an explicit experimental Godot mode with intact/disconnected comparison.

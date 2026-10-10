# Recorded AOTU benchmark result

**Outcome:** independent artifact validation passed; the predeclared practical
prediction gates failed for both AOTU types.

## What ran

The frozen image-to-LC10a hypothesis was replayed through the packaged
LC10a-to-AOTU contacts against the recorded AOTU stimulus archive. The run
covered 69 condition/type/recording units, 35,484 quiet pulses, 1,561 native
trials, 76,786,718 native frames, and 34,554 scored trial cells. It compared
345 new predictor configurations plus four fixed reference predictors.

The primary score is recording-weighted mean RMSE on held-out P1 recordings.
For each cell type, the frozen gate required intact predictions to reduce mean
RMSE by at least 5% versus the legacy contact-input predictor and to win on at
least 60% of recordings. An anatomical wiring claim also required at least 1%
lower RMSE than the matched-spatial control and strictly lower aggregate RMSE
than at least 30 of 32 shuffled circuits.

## Result

| P1 output | Recordings | Intact RMSE (spikes/s) | Legacy contact RMSE | Matched-spatial RMSE | Change vs legacy | Wins vs legacy | Change vs spatial | Shuffles beaten |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| AOTU019 | 24 | 7.556 | 6.451 | 7.539 | 17.13% worse | 8/24 | 0.22% worse | 32/32 |
| AOTU025 | 22 | 10.127 | 9.216 | 10.198 | 9.89% worse | 7/22 | 0.70% better | 32/32 |

Neither primary gate passed. Both intact models beat all 32 shuffled circuits
on aggregate error, which indicates that the specific wiring changes these
predictions relative to shuffled topology. That result did not translate into a
practical advantage over the legacy predictor. AOTU019 was also slightly worse
than matched spatial; AOTU025's 0.70% improvement fell short of the frozen 1%
threshold. The [held-recording curves](evidence/lc10a_recorded_benchmark_p1_curves_v1.png)
show a visible mismatch at faster motion, but that pattern is a diagnostic clue,
not proof of a particular biological cause.

This is an exploratory reuse of the same public recording archive for
development and holdout evaluation. The image-to-LC10a mapping includes
engineered spatial/directional assumptions and a published-model-shaped
response envelope; it is not a measured LC10a spike model. The benchmark
supports no claim of a useful connectome advantage, fly behavior, or promotion
of a Godot controller.

## Independent checks and reproducibility

The independent checker passed with 24,081 recording-score rows and 349
predictors. Reconstructed held predictions matched exactly; independently
refitted gains and recording RMSEs differed by zero. All 190,440 representation
rows were finite and below the frozen overflow limit. Eight canonical and
mirrored full-movie sensor replays matched within 1.50e-15 activity units, and
the public two-dimensional replay parity checks passed.

The frozen runner hash is
5c6498f18ec20e39f119c600f39cc1fcef21fc8d0bd782cb6338eaaeec27fad7.
Protocol and contract hashes, full counts, and machine-readable gate values are
in [the compact evidence JSON](evidence/lc10a_recorded_benchmark_summary_v1.json).
The full arrays and 121 MB report remain in ignored local outputs; they are not
part of the repository.

From the workspace root, reproduce with the six worker checkpoint sets and
recording archives already present under fly-creature/outputs/research:

    .\.venv\Scripts\python.exe fly-creature\tools\assemble_lc10a_benchmark.py --run
    .\.venv\Scripts\python.exe fly-creature\tools\check_lc10a_response_benchmark.py

The assembler temporarily adapts JSON serialization so the unchanged frozen
runner can write NumPy Boolean gate values to its report. It restores the
standard serializer in a finally block. The runner source hash and every
condition-specific checkpoint are rechecked during assembly.

# Creature architecture

This folder is a standalone project; runtime source and packaged circuit
data never import or read the surrounding FlyTest lab. External Python,
NumPy and Godot runtimes are still required.

| Component | Responsibility |
| --- | --- |
| `circuit.py`, `data/*.json` | Selected cells/recorded edges and modelling metadata |
| `lif.py`, `controller.py`, `steering.py` | Existing looming/jump and LIF steering sessions |
| `brain_model.py`, `brain_session.py`, `data/brain_subset_v1.npz`, `data/brain_subset_v3.npz` | Default whole-brain-subset mode: published LIF reimplementation (NumPy, one-core Numba and all-core Numba engines, bit-identical), one brain copy per sense (taste, loom, target, touch), each on the subset that passed for that sense; engineered input and action rules ([result](whole_brain_result.md)) |
| `tools/build_whole_brain.py`, `tools/build_brain_subset.py`, `tools/run_*_brain_test.py`, `tools/run_grooming_bitter_tests.py`, `tools/run_courtship_tests.py`, `tools/run_target_song_test.py` | Whole-brain tests against shuffled controls and subset selection; caches stay in ignored `outputs/whole_brain/` |
| `pursuit_controller.py` | Frozen opt-in activity steering, 10 ms ticks and 200 ms queue |
| `pursuit_activity.py`, `pursuit_step4.py`, `pursuit_delay_diagnostic.py` | Projection, source-inspired activity adapter and declared timing/input choices; also research runners |
| `playground.py` | Four-controller comparison world, stimuli, statistics and ordered batching |
| `server.py` | Local JSON transport for creature and comparison sessions |
| `godot/main.tscn`, `main.gd`, `neural_bridge.gd` | Original creature scene; Godot owns its body/world, including the presentation-only female fly (`M`) |
| `godot/playground.tscn`, `playground.gd` | Interactive comparison rendering/UI; Python owns its body/world |
| `godot/fly_actor.tscn`, `fly_actor.gd`, `assets/` | Reusable textured visual fly and authored animation |
| Diagnostic modules, `docs/evidence/` | Reproducible research comparisons; full traces stay in ignored outputs |
| `pursuit_footprints.py`, `data/lc10a_column_footprints_v1.json` | Portable offline upstream-column input hypothesis; production does not import it |
| `pursuit_physiology.py`, `pursuit_p1_comparison.py`, `tools/fetch_aotu_recordings.py` | Offline NoP1/P1 recorded-stimulus extraction, held-out AOTU response comparison, condition audit and verified public-data acquisition; optional research dependencies |
| `pursuit_temporal.py` | Offline native-trial causal response-memory hypothesis, pooled hemisphere and side sensitivities, nested recording holdouts and speed-transfer diagnostic |
| `pursuit_repeatability.py`, `tools/check_repeatability.py` | Offline repeated-stimulus pulse-mean templates, held-trial descriptive motor association and independent saved-artifact arithmetic; no production changes |
| `pursuit_population.py`, `tools/check_population.py` | Offline matched held-recording anatomy/simple/empirical response fields, training-only gain fits and independent reconstruction; prior repeatability outputs define unchanged coverage |
| `pursuit_history.py` | Offline paired reference-window and preceding-target audit; preserves literal-gap results and labels nominal-gap sensitivity posthoc |
| `pursuit_revision.py`, `tools/check_pursuit_cycle.py`, `tools/plot_pursuit_cycle.py` | Offline bounded direction-skew/visible-offset hypothesis, matched control fits, independent reconstruction and figures; rejected, never imported by production |
| `docs/lc10a_sensor_contract.md`, `tools/build_lc10a_probe_matrix.py` | Source-grounded finite-object interface and reproducible stimulus specifications only; no neural response implementation |
| `retina.py`, `tools/run_lc10a_probes.py` | Finite angular luminance frames and temporal geometry summaries; no modeled neuron response or behavioral readout |
| `lc10a_response.py` | Offline causal image-to-LC10a activity hypothesis over the existing 275 IDs; not imported by production, and not a spike model |
| `tools/run_lc10a_response_probes.py`, `tools/check_lc10a_response.py` | Frozen 68-probe replay and independent spatial, temporal, causal, identity, repeatability, and raster checks; full traces stay ignored |
| `docs/lc10a_response_design.md`, `docs/lc10a_response_result.md`, `docs/evidence/lc10a_response_*_v1.*` | Frozen assumptions, checked probe result, compact artifacts, and boundaries for the recorded-AOTU benchmark |
| `docs/lc10a_response_benchmark_protocol.md`, `tools/review_lc10a_benchmark.py`, `docs/evidence/lc10a_benchmark_*_v1.json` | Frozen assay contract, target/fold/legacy reconstruction, matched controls, and predeclared numerical and performance gates |
| `lc10a_response_benchmark.py`, `tools/check_lc10a_response_benchmark.py` | Offline 69-unit native-trial replay and independent score/refit/sensory-witness checks; compact outcome is in docs/lc10a_recorded_benchmark_result.md |
| `tools/assemble_lc10a_benchmark.py` | Audits parallel worker checkpoints and routes condition-specific caches through the frozen runner because 23 recording filenames recur across NoP1/P1 |
| `tools/diagnose_lc10a_response.py` | Bounded posthoc ablation/native-trace diagnosis; preserves the frozen benchmark and explains retirement of the transferred-envelope primary candidate |
| `tools/audit_downstream_recordings.py`, `tools/check_downstream_metadata_audit.py` | Offline metadata-only DNa02/AOTU integrity, schema and repeat-coverage audit; neural response values forbidden, no bridge fit or production integration |

Comparison endpoints are `POST /playground` and
`POST /playground/{world_id}/step`. They have a separate single-world store
from the original `/session` endpoints. The comparison does not change the
original creature session's dynamics. Reset/inspection and timing semantics
are documented in [playground.md](playground.md).

Recorded anatomy, hypothesized receptive fields/transmitter signs, simulated
dynamics, geometric sensors, motor decoding and authored body/animation are
different sources of behavior. Keep their contributions labelled. The
comparison playground displays prior test situations; it is not a new
biological validation result.

# Creature architecture

This folder is a standalone project; runtime source and packaged circuit
data never import or read the surrounding FlyTest lab. External Python,
NumPy and Godot runtimes are still required.

| Component | Responsibility |
| --- | --- |
| `circuit.py`, `data/*.json` | Selected cells/recorded edges and modelling metadata |
| `lif.py`, `controller.py`, `steering.py` | Existing looming/jump and LIF steering sessions |
| `pursuit_controller.py` | Frozen opt-in activity steering, 10 ms ticks and 200 ms queue |
| `pursuit_activity.py`, `pursuit_step4.py`, `pursuit_delay_diagnostic.py` | Projection, source-inspired activity adapter and declared timing/input choices; also research runners |
| `playground.py` | Four-controller comparison world, stimuli, statistics and ordered batching |
| `server.py` | Local JSON transport for creature and comparison sessions |
| `godot/main.tscn`, `main.gd`, `neural_bridge.gd` | Original creature scene; Godot owns its body/world |
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

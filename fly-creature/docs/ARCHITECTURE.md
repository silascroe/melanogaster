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

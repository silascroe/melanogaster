# Threat crossing

A deterministic moving-threat replay compared with a no-threat control at stages 54, 250, and 1,024.
The experiment asks whether a threat crossing the toy fly's route produces a threat-linked escape action through the existing causal chain.

## Result

- Structural run: `True`
- Behavioral readout: **response detected** in `3` of `3` stages

| Stage | Control escape actions | Threat frames sensed | Threat touch spikes | Threat-linked escapes | Response detected |
| --- | ---: | ---: | ---: | ---: | --- |
| `54` | `0` | `13` | `1` | `1` | `True` |
| `250` | `0` | `18` | `7` | `2` | `True` |
| `1024` | `0` | `5` | `2` | `1` | `True` |

## What the columns mean

- Threat frames sensed: the moving threat became the world's active touch source.
- Threat touch spikes: the touch population produced an output spike while the threat was sensed.
- Threat-linked escapes: the selected action was an escape action with `action_source=touch` while the threat was sensed.
- Response detected: threat sensed, touch output spike present, and at least one threat-linked escape action; the no-threat control is reported separately.

## Boundaries

- Real: node/edge wiring and the native-sign runtime come from the local FlyEM Male CNS v1.0 release.
- Assumed: the synthetic retina, static beacon, moving threat, collision-radius sensing, point-mass body, and action decoder.
- Demonstrated: this fixed replay's stage-by-stage causal response, if any. It does not demonstrate biological predator avoidance, learning, or generalization.

Scenario parameters: `{"beacon_intensity": 1.0, "beacon_x": 2.0, "beacon_y": 2.0, "duration_ms": 60.0, "forward_step_per_target_spike": 0.25, "initial_heading_degrees": 0.0, "initial_x": 0.0, "initial_y": 0.0, "stages": [54, 250, 1024], "threat_active_end_ms": 60.0, "threat_active_start_ms": 0.0, "threat_radius": 0.65, "threat_start_x": 0.6, "threat_start_y": -0.3, "threat_vx": 0.0, "threat_vy": 0.1, "turn_degrees_per_target_spike": 15.0}`

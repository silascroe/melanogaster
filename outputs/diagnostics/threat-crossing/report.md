# Threat crossing

A deterministic moving-threat replay compared with a no-threat control at stages 54, 250, and 1,024.
The experiment asks whether a threat crossing the toy fly's route produces a threat-linked escape action through the existing causal chain, then checks two nearby paths at 1,024 nodes.

## Result

- Structural run: `True`
- Behavioral readout: **response detected** in `3` of `3` stages

| Stage | Control escape actions | Threat frames sensed | Threat touch spikes | Threat-linked escapes | Escape latency | Response detected |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `54` | `0` | `13` | `1` | `1` | `6.00 ms` | `True` |
| `250` | `0` | `18` | `7` | `2` | `2.00 ms` | `True` |
| `1024` | `0` | `5` | `2` | `1` | `2.00 ms` | `True` |

## Geometry generalization

At stage `1024`, `2` of `2` nearby threat geometries produced the same causal response criterion. Escape latency is measured from first threat sensing to the first touch-sourced escape action.

| Geometry | Threat frames sensed | Threat touch spikes | Threat-linked escapes | Escape latency | Response detected |
| --- | ---: | ---: | ---: | ---: | --- |
| `right-lane` | `4` | `2` | `1` | `2.00 ms` | `True` |
| `late-crossing` | `3` | `1` | `1` | `2.00 ms` | `True` |

## What the columns mean

- Threat frames sensed: the moving threat became the world's active touch source.
- Threat touch spikes: the touch population produced an output spike while the threat was sensed.
- Threat-linked escapes: the selected action was an escape action with `action_source=touch` while the threat was sensed.
- Escape latency: elapsed replay time between first threat sensing and the first threat-linked escape action.
- Response detected: threat sensed, touch output spike present, and at least one threat-linked escape action; the no-threat control is reported separately.

## Boundaries

- Real: node/edge wiring and the native-sign runtime come from the local FlyEM Male CNS v1.0 release.
- Assumed: the synthetic retina, static beacon, moving threat, collision-radius sensing, point-mass body, and action decoder.
- Demonstrated: this narrow stage and geometry matrix's causal response, if any. It does not demonstrate biological predator avoidance, learning, or broad generalization.

Scenario parameters: `{"baseline_geometry_id": "centerline", "beacon_intensity": 1.0, "beacon_x": 2.0, "beacon_y": 2.0, "duration_ms": 60.0, "forward_step_per_target_spike": 0.25, "geometry_generalization_stage": 1024, "geometry_matrix": [{"geometry_id": "centerline", "start_x": 0.6, "start_y": -0.3, "vx": 0.0, "vy": 0.1}, {"geometry_id": "right-lane", "start_x": 1.2999999999999998, "start_y": -0.5, "vx": 0.0, "vy": 0.1}, {"geometry_id": "late-crossing", "start_x": 1.0, "start_y": -1.0, "vx": 0.0, "vy": 0.1}], "initial_heading_degrees": 0.0, "initial_x": 0.0, "initial_y": 0.0, "stages": [54, 250, 1024], "threat_active_end_ms": 60.0, "threat_active_start_ms": 0.0, "threat_radius": 0.65, "threat_start_x": 0.6, "threat_start_y": -0.3, "threat_vx": 0.0, "threat_vy": 0.1, "turn_degrees_per_target_spike": 15.0}`

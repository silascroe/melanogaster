# Beacon approach

A deterministic, obstacle-free replay of the existing FlyTest arena.
It asks one narrow question: does the current visual pathway drive the
toy body inside the configured distance threshold at any point in the
replay?

## Result

- Status: **PASS**
- Initial distance: `2.828` m
- Closest distance: `1.416` m
- Final distance: `3.292` m
- Distance threshold: `1.500` m
- Threshold reached: `True`
- Distance decreased: `True`
- Closest frame: `10`

## Causal trace

The run contains `30` frames; `30` include the required retina, input-current, spike, action, and body-position fields.
Visual stimulus frames: `11`. Frames with a vision-sourced action: `7`. Frames with a visual output spike: `18`.

## What is real, assumed, and demonstrated

- Real: the staged node and edge selection comes from the local FlyEM Male CNS v1.0 release.
- Assumed: the 9×5 retina, static beacon, point-mass body, movement step, turn decoder, and approach threshold.
- Demonstrated: this one fixed replay's observed trajectory and causal trace. It does not demonstrate a biological light-seeking behavior or a learned controller.

Scenario parameters: `{"approach_threshold": 1.5, "beacon_intensity": 1.0, "beacon_x": 2.0, "beacon_y": 2.0, "duration_ms": 30.0, "forward_step_per_target_spike": 0.25, "initial_heading_degrees": 0.0, "initial_x": 0.0, "initial_y": 0.0, "network_stage": 54, "turn_degrees_per_target_spike": 15.0}`

The closest-distance criterion is intentional: the current toy action decoder is a reflex mapping, so the body may pass near the beacon and then turn away. Sustained tracking is a separate experiment.

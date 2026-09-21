# Wall blocking

A deterministic stage-54 replay with a static beacon behind a solid
wall. It asks whether the toy body is physically blocked and whether
the causal trace exposes the obstacle as the world cause.

## Result

- Status: **PASS**
- Wall: `wall` at `(1.5, 0.0)`
- Blocked frames: `2`
- Collision observed: `True`
- Obstacle touch observed: `True`
- Maximum body center x: `0.635` m
- Wall front-face limit: `0.650` m
- Wall front face crossed: `False`
- Minimum point-to-wall distance: `0.365` m

## Causal trace

The run contains `14` frames; `14` include retina, input-current, spike, action, body-motion, and world-cause fields.
Visual action frames: `4`. Touch action frames: `1`. Wall-touch frames: `12`.

## What is real, assumed, and demonstrated

- Real: the staged node and edge selection comes from the local FlyEM Male CNS v1.0 release.
- Assumed: the 9×5 retina, beacon, point-mass body, wall rectangle, collision resolver, and action decoder.
- Demonstrated: this fixed replay's collision and causal trace. It does not demonstrate biological obstacle avoidance or learned navigation.

Scenario parameters: `{"beacon_intensity": 1.0, "beacon_x": 3.0, "beacon_y": 0.0, "body_radius": 0.35, "duration_ms": 14.0, "forward_step_per_target_spike": 0.25, "initial_heading_degrees": 0.0, "initial_x": 0.0, "initial_y": 0.0, "network_stage": 54, "touch_range": 0.45, "turn_degrees_per_target_spike": 15.0, "wall_height": 3.0, "wall_id": "wall", "wall_width": 1.0, "wall_x": 1.5, "wall_y": 0.0}`

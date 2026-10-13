# Fly model v1 (original)

The fly as it was before the 2026-10-13 rework, kept so it can always be
restored or compared. These files are byte-identical to the originals:

- `male_drosophila_v1.blend` is the original Blender source (was `art/male_drosophila_textured.blend`).
- `male_drosophila_v1.glb` is the original Godot asset (was `godot/assets/male_drosophila.glb`).
- `fly_actor_v1.gd` is the actor script that animated it.

To put v1 back in the game, copy `male_drosophila_v1.glb` over
`godot/assets/male_drosophila.glb`. The current actor still accepts it: with
no ankle pivot it falls back to the original two-joint legs.
`tools/refine_fly_model.py` reads `male_drosophila_v1.blend` to build v2.

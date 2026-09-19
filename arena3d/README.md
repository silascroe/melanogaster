# FlyTest Arena 3D

This is a standalone Godot scene for giving the FlyTest controller a world to
inhabit. It is deliberately separate from the public FlyTest website.

The current milestone is a live closed-loop world client:

- a stylized low-poly fly body with a heading, trail, segmented abdomen,
  wings, eyes, antennae, and six legs;
- a beacon and a timed threat in a bounded 3D lab;
- orbit/zoom camera controls;
- a compact 9×5 retina preview;
- a bridge to `POST /api/arena/session` plus persistent
  `POST /api/arena/session/{id}/step` ticks;
- Godot-owned body and moving-stimulus state sent to Python on every tick;
- Python-owned retina projection, LIF state, memory, descending votes, action,
  and causal trace returned to Godot;
- a visible trail, retina panel, threat marker, and live action readout.
- matching static obstacle geometry with Godot collision shapes;
- a causal HUD tracing world contact through sensory features, input currents,
  spikes, descending votes, and the selected action.

The Python Arena remains the source of truth for connectome selection, LIF
state, spikes, memory, and action decoding. Godot is deliberately the source
of truth for the current visible world state. Press `SPACE` to pause the tick
loop, `R` to create a fresh neural session, right-drag to orbit, and use the
mouse wheel to zoom.

The scripted session includes two static obstacles. Python resolves the toy
body against their two-dimensional rectangles so the live response exposes
requested versus actual motion and collision IDs; Godot renders the same
rectangles as `StaticBody3D` shapes and probes the next move with a
`ShapeCast3D`. The result is collision-aware experiment scaffolding, not
flight physics.

The visible fly is a procedural presentation shell separate from the spherical
collision shape. Its insect silhouette is intentionally stylized and cheap to
render; the wings flap at a low idle rate and more actively while the controller
is moving. This keeps visual polish from changing the experiment's body radius
or collision semantics.

## Run locally

From the repository root:

```powershell
.\tools\godot\4.7\Godot_v4.7-stable_win64.exe --editor --path arena3d
```

Or run the scene headlessly to validate the project file:

```powershell
.\tools\godot\4.7\Godot_v4.7-stable_win64.exe --headless --path arena3d --editor --quit
```

The downloaded Godot binary is local-only and ignored by Git.

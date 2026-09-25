# Fly Creature decisions

## First reaction: looming object to jump

The first visible behavior is deliberately narrow: an object approaches a fly standing or walking on the floor, and a DNp01 giant-fiber spike requests a jump animation. Published work identifies LC4 and LPLC2 as direct visual inputs to the giant fiber during looming. The local MaleCNS v1.0 files contain 126 traced LC4, 185 traced LPLC2, and two traced DNp01 neurons; the selected direct path has 311 weighted body-to-body edges. These counts are from the local release, not a claim that this is a complete escape circuit.

## Selection boundary

The exporter includes only traced neurons of those three exact types and only direct LC4/LPLC2 → DNp01 edges. It intentionally omits other partners, upstream retina and optic-lobe circuits, downstream motor circuitry, and connections among or outside the selected nodes. Synapse counts are recorded data. Predicted acetylcholine is an annotation; assigning positive fast current to those edges is a model convention.

## Sensor and motor contract

Godot sends fly position and heading plus the object's position, radius, and active state every 50 ms. Python computes the object's apparent angular size and positive expansion rate when it is inside a 130-degree forward field. LC4 current scales with expansion above 5 degrees/s; LPLC2 current scales with apparent size above 8 degrees while expansion exceeds 3 degrees/s. Those thresholds and the 90 mV maximum external current are engineered, not measured visual physiology. The scene never injects current directly into DNp01.

The neural model is an adapted version of FlyTest's general one-step-delayed LIF runtime: 1 ms steps, 20 ms membrane time constant, -65 mV rest/reset, -50 mV threshold, 2 ms refractory period, and 0.05 mV current scale per recorded synapse. These are simplifying settings. A DNp01 spike requests a jump, gated by a 1.2 s animation cooldown. Walking, object motion, and the ballistic animation are Godot behaviors; they are not neural outputs.

## What the first diagnostic establishes

A fixed 36-frame approach at 50 ms per frame compares identical world inputs and neuron parameters with the recorded direct edges present versus removed. The first local run produced a first intact jump at frame 24 and no disconnected giant-fiber spikes or jump. This establishes signal propagation and action dependence on the included edges in this configured simulation. It does not show biological timing, natural vision, anatomical superiority to a matched alternative, or robust behavior across scenes.

## Portability

The packaged circuit is a compact, attributed derivative of the official release. Runtime source, Godot scene, dependency manifest, and data all live under `fly-creature/`; normal use needs no file from the parent FlyTest lab. The release exporter is development-only and accepts an explicit source directory.

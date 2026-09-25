# Fly Creature

A standalone, local 3D creature with one inspectable connectome-backed reaction. A fly can be moved around a small room; an approaching object supplies visual features to a recorded MaleCNS pathway; giant-fiber activity triggers a jump. This is the first playable slice of a larger creature project, not an autonomous fly or a biological flight simulator.

Everything required from this workspace is inside this folder. Copy `fly-creature/` elsewhere and use its own setup instructions. Python 3.12+, Godot 4, and the Python dependencies still need to be installed on the destination computer.

## Run

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m fly_creature.server
```

Open `godot/` as a project in Godot 4 and run its main scene. The Python service listens only on `127.0.0.1:8768` by default. Set `FLY_CREATURE_ENDPOINT` to another local base URL before starting Godot if you change the port.

`WASD` moves the fly on the floor. `SPACE` sends an object toward its current heading. `C` restarts the scene's neural session with the recorded connections removed or restored. `R` resets the neural session and world. Walking, the object trajectory, and the jump animation are Godot code. The neural circuit controls only the **jump trigger**.

The small circuit-level diagnostic can be run without Godot:

```powershell
.\.venv\Scripts\python.exe -m fly_creature.diagnostic
```

It prints a fixed approach for intact and disconnected conditions. In the recorded local run, the intact circuit first requested a jump at frame 24; the disconnected condition had no giant-fiber spikes or jump. That is one configured comparison, not a claim about general behavior.

## What is running

The packaged `src/fly_creature/data/loom_escape_v1.json` contains 313 traced neurons: 126 LC4, 185 LPLC2, and two DNp01 giant fibers, plus 311 recorded direct weighted connections from LC4/LPLC2 to DNp01. It is a **selected direct path**, not the whole fly brain. The release's predicted neurotransmitter for the selected presynaptic neurons is acetylcholine; the simulator treats it as excitatory by convention.

Python converts object distance and motion into apparent angular size and expansion speed. LC4 receives an engineered expansion-speed current; LPLC2 receives an engineered size-during-expansion current. A simplified, one-step-delayed leaky integrate-and-fire model updates the selected cells. A DNp01 spike outside the animation cooldown requests a jump. The 3D scene and the labels show this chain.

The input encoder, model parameters, jump rule, and body physics were made for this project. This implementation does not process camera pixels, simulate the retina, drive fly muscles, or establish that the selected wiring outperforms another controller. Disconnecting the edges shows that the current demo uses them; it does not establish a unique advantage of fly anatomy. See [decisions](docs/decisions.md).

## Data and provenance

The compact JSON was exported from the official [FlyEM Male CNS v1.0 release](https://male-cns.janelia.org/download/) using `tools/export_circuit.py`. MaleCNS is a collaboration between FlyEM at HHMI Janelia, the University of Cambridge Department of Zoology, the MRC Laboratory of Molecular Biology, and Google Research, and is licensed under CC-BY. This JSON is a filtered derivative: it keeps selected body annotations, predicted transmitters, and direct weighted edges. The source manifest and files in the FlyTest lab were read during development; no full release file is needed at runtime. The direct LC4/LPLC2-to-giant-fiber choice is motivated by [Ache et al., *Current Biology* (2019)](https://doi.org/10.1016/j.cub.2019.01.079), which studied looming size and velocity inputs to escape. The paper's measured physiology is separate from this project's toy neuron dynamics.

To regenerate the compact file from a MaleCNS v1.0 download, install the optional `build-circuit` dependency and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[build-circuit]'
.\.venv\Scripts\python.exe tools\export_circuit.py --release-dir PATH_TO_RELEASE --output src\fly_creature\data\loom_escape_v1.json
```

The exporter only reads the three official Feather tables. It does not edit them. Any regenerated circuit should be reviewed before replacing the shipped artifact.

## Project boundary

This folder owns its Python package, Godot project, compact data, and instructions. It has no runtime imports from `../src/flytest/` and no runtime reads from `../data/`. The older FlyTest arena remains an independent experimental record outside this folder.

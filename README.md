# FlyTest: Drosophila connectome baseline

This repository is a small, local-first exploration of the official FlyEM Male CNS connectome release. It began with a readable data loader, a bounded subgraph extractor, and a simple leaky integrate-and-fire simulator; it now also includes an inspectable local browser lab and standalone Godot arena. There is still no opaque graph database or claim of a validated biological behavior model.

The current baseline uses MaleCNS v1.0 from HHMI Janelia's public Google Storage bucket. The downloaded release files live in `data/original-data/male-cns-v1.0/` and are never edited. Byte-identical copies live in `data/working/male-cns-v1.0/`; derived tables and simulation output go under `outputs/`.

## Setup

The tested interpreter is Python 3.12. Create or activate the project environment, then install the package and development dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The checked-in code expects the release files to already exist locally. The provenance and hashes are recorded in [data/metadata/source_manifest.json](data/metadata/source_manifest.json).

Verify both the immutable download and the working copy at any time:

```powershell
.\.venv\Scripts\python.exe -m flytest.verify
```

## Inspect the release

```powershell
.\.venv\Scripts\python.exe -m flytest.analysis `
  --data-dir data/working/male-cns-v1.0 `
  --output outputs/inspection
```

This writes a JSON report containing file schemas, row counts, label counts, and graph statistics. The weights scan is streamed with PyArrow; it does not load the 1 GB table into a pandas DataFrame.

## Build and simulate the baseline

The default example selects the two curated `DNge104` neurons, chooses their strongest traced neighbors, joins consensus neurotransmitter predictions, and extracts the induced directed weighted subgraph:

```powershell
.\.venv\Scripts\python.exe -m flytest.baseline `
  --data-dir data/working/male-cns-v1.0 `
  --output outputs/baseline `
  --type DNge104 `
  --neighbors 64 `
  --min-weight 3 `
  --duration-ms 100
```

Outputs are ordinary CSV/JSON files: selected neuron metadata, selected directed edges, spike events, and a run summary. The simulation is a discrete-time LIF model. Edge weights are synapse counts, scaled by a configurable `--mv-per-synapse`; transmitter signs use a conservative default mapping: acetylcholine excitatory, GABA/glutamate/histamine inhibitory, and monoamines/unclear predictions neutral. This is a modelling convention, not a claim that every Drosophila synapse has a globally fixed sign.

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Version control

This project is now managed as a Git repository. Code, tests, documentation,
the source manifest, and compact experiment reports are tracked. The official
Feather files, their working copy, the separate local backup, the virtual
environment, and bulky timestep traces are deliberately ignored. See
[docs/git-workflow.md](docs/git-workflow.md) for the exact policy and the
checkout/commit commands.

Run the separate controlled propagation diagnostic without changing production defaults:

```powershell
.\.venv\Scripts\python.exe -m flytest.propagation_diagnostic
```

It reads `outputs/baseline/selected_neurons.csv` and `selected_edges.csv`, tests native versus forced-excitatory sign handling at `0.05` and `1.5 mV/synapse`, and writes `outputs/diagnostics/propagation_matrix.json` plus `propagation_matrix.csv`.

## Run the native-sign pathway slice

The next small experiment selects a reproducible three-role path from the
working release: `vnc_sensory -> vnc_intrinsic -> descending_neuron`. It keeps
the native transmitter signs, pulses the selected source neuron once, and
runs a small coupling sweep without changing the baseline defaults:

```powershell
.\.venv\Scripts\python.exe -m flytest.pathway_slice
```

The default sweep is `0.05`, `0.5`, `1.5`, `3.0`, and `4.0 mV/synapse`. The
selector streams the large weights table and keeps all induced edges among the
three selected neurons, including reverse or inhibitory edges. Outputs under
`outputs/pathway-slice` include node and edge tables, spike and voltage traces,
per-edge current contributions, per-coupling summaries, and `summary.json`.
These coupling values are calibration probes for this simplified LIF model,
not biological parameter estimates. This command does not run behavioral or
FlyDoom simulation.

## Tell the circuit story

The separate circuit-story diagnostic turns the same three-neuron pathway into
a plain-language input-to-output experiment:

```powershell
.\.venv\Scripts\python.exe -m flytest.circuit_story
```

It uses the native transmitter signs and production-compatible synaptic
settings, stimulates only the selected sensory neuron, and compares the same
five coupling probes. It writes `story.md`, compact node/edge/run tables, and
detailed traces for the lowest-coupling condition plus the first condition
that produces a complete source-to-target path. A complete path means the
source, intrinsic, and descending neurons spike one timestep apart. The report
is an interpretable diagnostic, not a claim that the selected path is a
complete biological behavior circuit.

## Put a toy body behind the pathway

The next diagnostic gives the same real sensory-to-intrinsic-to-descending
pathway an explicit action interface. The selected sensory neuron receives a
longer pulse, each descending-neuron spike becomes a fixed turn impulse, and a
point-mass body records its heading and position:

~~~powershell
.\.venv\Scripts\python.exe -m flytest.sensorimotor
~~~

This is deliberately a reflex demo, not a named biological behavior. The
connectome-backed neural path, native signs, and one-step delay are inherited
from the existing model. The body, movement rule, and spike-to-turn decoder
are explicit toy assumptions. outputs/sensorimotor/story.md separates those
assumptions from the data and records the resulting trajectory.

## Watch the local circuit

The browser-facing visual simulation now runs two 27-node local contexts side
by side: the existing traced touch path and a separate annotated visual
projection -> optic-lobe intrinsic -> descending path. It shows the toy body,
the visual beacon, trajectory, active spikes, signed edges, and a replayable
control panel. Start it with:

~~~powershell
.\.venv\Scripts\python.exe -m flytest.visual_simulation
~~~

Then open http://127.0.0.1:8765. The page runs entirely against the local
server and local release. The default view uses 54 nodes and 435 induced
edges: 27 nodes and 288 edges for touch, plus 27 nodes and 147 edges for
vision. Coupling, stimulus duration, visual contrast, playback speed, and turn
decoding can be changed from the page. The visual source is an annotated
visual-projection neuron, not a claim that this demo models the retina or a
complete visual behavior.

The page also has an Arena mode. Its API-compatible control stage is the same
54-node local graph, and the browser can request unified 100-, 250-, and
1,024-node multi-hop expansions. The browser defaults to the 1,024-node stage;
54 remains the API compatibility default and 250 remains a smaller unified
control. A deterministic 9x5 synthetic retina exposes brightness,
motion, and looming to named sensory populations; descending spikes vote for
turning, forward motion, or touch-priority escape. The scripted demo uses
moving light and timed threat objects. Sandbox mode supports still, drifting,
and crossing user-placed objects, replayed from neural rest with a frame
scrubber and causal trace. The arena is intentionally a sensorimotor
experiment, not a biological retina or a learned fly. The API defaults to
stage 54 to preserve compatibility; the browser and Godot lab explicitly
request stage 1,024.

The scripted arena demo now includes two explicit static obstacles. The body
is a circular toy agent: Python resolves proposed movement with swept
circle-versus-rectangle contacts and returns requested versus actual motion,
collision IDs, boundary contacts, and obstacle touch features in each frame.
Godot renders matching `StaticBody3D` shapes and its HUD exposes the current
world event, sensory features, input currents, spikes, descending votes, and
action. Sandbox requests remain obstacle-free unless an `obstacles` array is
provided. This is an inspectable collision experiment, not flight physics.

Measure the first real arena scale target against the local release:

~~~powershell
.\.venv\Scripts\python.exe -m flytest.arena_scale
~~~

This builds the exact 1,024-node unified stage, runs a deterministic batch
replay twice, steps a live session twice, and writes compact evidence under
`outputs/diagnostics/arena-1024`. The first run includes graph expansion and
runtime compilation; the second measures the cached replay.

Run the next bounded arena diagnostic against the same local release:

~~~powershell
.\.venv\Scripts\python.exe -m flytest.beacon_approach
~~~

This freezes one beacon in an otherwise empty sandbox and writes a compact
`report.md`, `summary.json`, and `trajectory.csv` under
`outputs/diagnostics/beacon-approach`. The pass criterion is deliberately
small: the body must get closer than its start and enter the configured
distance threshold at least once. The report separates connectome facts from
the retina, body, movement, and threshold assumptions. It is a diagnostic of
one fixed replay, not evidence of biological light seeking or sustained
tracking.

## Report runs to Discord

The report-only Discord bridge uses the bot REST API and a local JSONL event
spool. It needs no privileged Gateway intents or Discord dependency:

```powershell
$env:FLYTEST_DISCORD_BOT_TOKEN = "token-set-only-in-the-running-shell"
$env:FLYTEST_DISCORD_CHANNEL_ID = "target-channel-id"
.\.venv\Scripts\python.exe -m flytest.discord_bridge watch
```

Jobs can append completion or failure events with `flytest-discord emit`; see
[docs/discord-bridge.md](docs/discord-bridge.md) for the event format, dry-run
path, and the always-on droplet deployment. The token is never part of the
repository or event spool.

The deployed watcher runs as `flybot.service` on `first-droplet`. From the
repository root, update it with the secret-blind deployment script and inspect
its logs with:

```powershell
powershell -NoProfile -File deploy/flybot/deploy.ps1 -HostAlias first-droplet
ssh first-droplet "systemctl status flybot.service --no-pager"
ssh first-droplet "journalctl -u flybot.service -n 50 --no-pager"
```

Only the bridge code and unit are copied to the droplet. The bot token remains
only in `/etc/flytest/flybot.env`; event emission is explicit, and DomainPatrol
is a separate untouched service.

To report a local job without putting the Discord token on Windows, use the
existing SSH alias:

```powershell
\.venv\Scripts\python.exe -m flytest.discord_bridge run --job "FlyTest verification" -- .\.venv\Scripts\python.exe -m flytest.verify
```

The wrapper reports start and completion through the droplet, streams the local
command's output, and preserves its exit code. See
[docs/discord-bridge.md](docs/discord-bridge.md) for one-off notifications and
failure behavior.

## Compare synaptic dynamics

The simulator defaults to the original one-step synaptic current. The separate
synaptic-dynamics diagnostic adds no new data and compares that legacy mode with
an optional exponentially decaying current:

```powershell
.\.venv\Scripts\python.exe -m flytest.synaptic_dynamics_diagnostic
```

It tests gains `1`, `3`, `6`, and `12` at the fixed conservative coupling
`0.05 mV/synapse`, using both legacy current and a `5 ms` synaptic time
constant. It runs on the existing `10732 -> 10968` baseline graph and the
three-neuron pathway. Results are written to
`outputs/diagnostics/synaptic_dynamics_matrix.json`, the matching CSV, and a
per-node voltage/current trace CSV. A gain is a multiplier on the existing raw
synapse-count current; no new weight normalization is introduced.

## Data scope and caveats

The official full weights table is segment-to-segment and contains many uncurated IDs. The baseline filters both endpoints to annotation rows whose release status is `Traced`, making the neuron-level assumption visible and reproducible. A future analysis can deliberately compare this with the full segment graph or use the official traced-only derivative, but it should not silently mix the two.

See [docs/data-dictionary.md](docs/data-dictionary.md) for the measured schemas and statistics, and [docs/decisions.md](docs/decisions.md) for the modelling choices.

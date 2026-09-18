# FlyTest: Drosophila connectome baseline

This repository is a small, local-first exploration of the official FlyEM Male CNS connectome release. It deliberately stops at a readable data loader, a bounded subgraph extractor, and a simple leaky integrate-and-fire simulator. There is no web app, game layer, or opaque graph database.

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

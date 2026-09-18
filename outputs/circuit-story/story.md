# Circuit story

This is a small, connectome-backed input-to-output experiment. It is a diagnostic, not a behavioral or FlyDoom simulation.

## Data and model

- Dataset: FlyEM Male CNS v1.0 (`data\working\male-cns-v1.0`)
- Provenance manifest: `data/metadata/source_manifest.json`
- External input: a brief pulse applied only to the selected source neuron.
- Fixed timestep: 1 ms; membrane time constant: 20 ms.
- Threshold/reset: -50 / -65 mV.
- Native transmitter signs are used; gain and synaptic decay remain at their production-compatible defaults.
- An edge's sign comes from its presynaptic neuron: the target's own GABA label describes what it sends onward, not the incoming edge.

## Selected circuit

- body 22012 (DNxl114_R), target; gaba, modelled as inhibitory
- body 800225 (IN23B009_R), intermediate; acetylcholine, modelled as excitatory
- body 806745 (SNta30), source; acetylcholine, modelled as excitatory

Path edges:
- 800225 → 22012: 73 synapses, acetylcholine (excitatory)
- 806745 → 800225: 137 synapses, acetylcholine (excitatory)

## What happened

At the lowest tested coupling (0.05 mV/synapse), the source fires at 9 ms. The intermediate and target are no spike and no spike; the path is silent after the source.

The first complete condition is the `first_complete_path` condition at 4 mV/synapse. The source fires at 9 ms, the intermediate at 10 ms, and the target at 11 ms. Each hop is one simulator timestep.

The coupling sweep changes only the current contribution per synapse. These values are calibration probes for this simplified model, not measurements of biological synaptic strength.

## Sweep results

| Coupling | Source | Intermediate | Target | Complete path |
| ---: | ---: | ---: | ---: | :--- |
| 0.05 | 9 ms | no spike | no spike | no |
| 0.5 | 9 ms | no spike | no spike | no |
| 1.5 | 9 ms | no spike | no spike | no |
| 3 | 9 ms | 10 ms | no spike | no |
| 4 | 9 ms | 10 ms | 11 ms | yes |

The selected neuron and edge tables, full sweep summary, and two key time traces are stored beside this report.

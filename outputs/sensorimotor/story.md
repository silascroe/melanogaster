# Connectome-backed sensorimotor reflex

This is the first body-facing layer above the circuit story: a real Male CNS pathway receives a sensory pulse, and its descending spikes move a deliberately tiny point-mass body.

## What is data and what is ours

- Dataset: FlyEM Male CNS v1.0 (`data\working\male-cns-v1.0`)
- Provenance manifest: `data/metadata/source_manifest.json`
- Source: body 806745 (SNta30), annotated as `mechanosensory_tactile`.
- Target: body 22012 (DNxl114_R), a descending neuron.
- The selected edges, transmitter labels, signs, and pathway roles come from the local release and existing model conventions.
- Our toy action decoder maps each target spike to a fixed turn impulse of 15 degrees and a forward step of 1 body units.

## Neural path

- 800225 → 22012: 73 synapses, acetylcholine (excitatory)
- 806745 → 800225: 137 synapses, acetylcholine (excitatory)

## Result

A 30 ms sensory pulse starts at 5 ms. The pathway produces 4 descending target spike(s), which produce 4 toy turn command(s).
The body ends at (3.039, 2.332) with heading 60.000 degrees.

This is not a claim that this exact pathway controls a named fly behavior. It demonstrates the important interface: sensory input enters the connectome-backed network, a descending neuron spikes, and only then does the body state change through an explicit decoder.

The full neural/body trajectory is in `trajectory.csv`; the selected node and edge tables are beside this report.

# Whole-brain LIF: sugar → MN9 protocol (written before any run)

## Question

With the published Shiu et al. (2024) whole-brain LIF settings applied to every
neuron and connection in MaleCNS v1.0, do sugar/water taste neurons drive the
proboscis-extension motor neuron MN9, and does that depend on the actual wiring?

Our earlier small hand-picked circuits (LC16→MDN, LB3→MN9) failed: signals died
after one or two relays at the creature's 0.05 mV/synapse setting, and when the
gain was raised far enough, shuffled wiring worked as well as real wiring.

## Model (fixed, from the authors' `model.py`, philshiu/Drosophila_brain_model)

- v_0 = v_rst = −52 mV, v_th = −45 mV, membrane time constant 20 ms.
- Conductance g decays with 5 ms time constant; dv/dt = (v_0 − v + g)/20 ms;
  v and g are not integrated while refractory (2.2 ms); reset sets v = v_rst, g = 0.
- Each presynaptic spike adds signed synapse count × 0.275 mV to g after 1.8 ms.
- Stimulated neurons receive one Poisson input at 150 Hz that adds
  0.275 mV × 250 to v, and have no refractory period.
- Time step 0.1 ms, 1 s trials, no background activity.
- Signs (paper convention): acetylcholine, dopamine, serotonin, octopamine
  excitatory; GABA, glutamate inhibitory. Our additions, decided in advance:
  histamine inhibitory; `unclear` or missing transmitter → the neuron's
  outgoing synapses have no effect (conservative: it can only weaken the result).
- Transmitter label: `consensus_nt` (fewest `unclear` among annotated neurons:
  22,645 unclear plus 24,561 annotated neurons with no transmitter row).
- Neurons: the 211,577 bodies in the annotation table. Connectivity: every row
  of the MaleCNS v1.0 minconf-0.5 weight table whose two ends are both neurons.

This is a reimplementation in NumPy, not the authors' Brian2 code; it is
checked against hand-computed single-neuron and two-neuron cases in tests.

## Stimulus and readout

- Input: all traced labellar-bristle neurons with FlyWire type LB3
  (FlyWire subclass "sugar/water"; sugar and water cells are not separated).
- Output: mean firing rate of the two traced MN9 neurons.

## Pass criteria (all required)

1. MN9 mean rate ≥ 10 Hz with LB3 input (mean of 3 trials), and 0 Hz without input.
2. Wiring specificity: intact MN9 rate (seed 0) exceeds the rate in at least
   19 of 20 shuffled brains. A shuffle permutes the postsynaptic targets of all
   connections, keeping each neuron's outgoing synapse counts and signs and each
   neuron's number of incoming connections.

If either fails, we report it and stop; no parameter is tuned against these results.

# Addendum: active-subset check (written 2026-10-11, before any subset run)

Question: can a smaller circuit, chosen by the whole brain rather than by hand,
reproduce the whole-brain sugar → MN9 result fast enough to consider live use?

- Subset: every neuron that spikes at least once in any of three whole-brain
  sugar trials (seeds 0, 1, 2), plus MN9. Connections: all whole-brain
  connections whose two ends are both in the subset. Same model settings.
- Test on fresh seeds 10, 11, 12 (not used to choose the subset), comparing
  subset and whole brain on identical Poisson input.

Pass criteria (all required):

1. Subset MN9 mean rate within ±20% of the whole-brain MN9 mean rate over seeds 10–12.
2. Subset MN9 rate is 0 Hz with no input.
3. Subset MN9 rate is 0 Hz when the other 76 labellar taste neurons are driven
   instead (only those present in the subset can receive input).

Reported, not gated: subset size, connections, and seconds per simulated second.

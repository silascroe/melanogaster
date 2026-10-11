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

# Addendum: jump and turn in the whole brain (written 2026-10-11, before any run)

Same model, signs, 150 Hz Poisson input, 1 s trials, and shuffle method as the
sugar test. Side labels are MaleCNS `somaSide`; the creature's existing steering
convention is that a target on the right drives right-side LC10a and should raise
right DNa02 relative to left, turning the fly right.

Jump. Input: all traced LC4 and LPLC2 (both sides). Readout: the two DNp01.
1. DNp01 mean rate ≥ 10 Hz over seeds 0–2, and 0 Hz without input.
2. Intact DNp01 rate (seed 0) exceeds ≥ 19 of 20 shuffled brains.

Turn. Inputs: right-side traced LC10a only; separately, left-side only.
Readout: DNa02 asymmetry, R minus L rate.
1. Right input: mean asymmetry ≥ +10 Hz over seeds 0–2. Left input: ≤ −10 Hz.
   No input: 0 Hz for both DNa02.
2. Intact asymmetry with right input (seed 0) exceeds the same measure in
   ≥ 19 of 20 shuffled brains.

Each behavior passes or fails on its own; a failing behavior is reported and
not used in the game.

# Addendum: combined game subset (written 2026-10-11, after jump and turn passed, before any subset run)

Subset: every neuron that spikes in any whole-brain trial (seeds 0, 1, 2) of the
four stimuli sugar (LB3), loom (LC4+LPLC2), right LC10a, left LC10a, plus all
input and readout neurons (LB3, LC4, LPLC2, LC10a, MN9, DNp01, DNa02).
Connections: all whole-brain connections among them.

Pass criteria on fresh seeds 10–12, subset versus whole brain, same inputs:
1. MN9 rate (sugar), DNp01 rate (loom), and DNa02 asymmetry (right LC10a; left
   LC10a) each within ±20% of the whole-brain mean.
2. No input: all readouts 0 Hz.
Reported, not gated: size, connections, packaged file size, and compute seconds
per simulated second with all four input groups active at 150 Hz together.

# Addendum: spike-frequency adaptation (written 2026-10-11, before any adaptation run)

Problem found in game use: with the published settings, activity never settles.
After a 300 ms loom burst, ~13,700 of 211,577 neurons still fire 1–2 s later and
MN9 fires without taste input; right-LC10a input also drives MN9 (~20 Hz).
The published model has no adaptation, and its trials always started at rest.

Change (ours, not the paper's): add a standard adaptation term, fixed in advance
from the AdEx "tonic" parameters of Brette & Gerstner (2005), b = 0.0805 nA and
tau_w = 144 ms, converted with this model's 10 MΩ membrane resistance:

    dv/dt = (v_0 − v + g − w) / t_mbr      (v, g frozen while refractory)
    dw/dt = −w / 144 ms                     (always)
    on spike: w += 0.805 mV

b = 0 reproduces the published model exactly. No other parameter changes, and
b and tau_w are not tuned against any result below.

Pass criteria, whole brain with adaptation (all required):
1. Settling: after 300 ms of loom input then silence, at most 1% of neurons
   (2,116) spike in the window 500–1000 ms after the input ends.
2. Sugar, jump, and turn each pass their original criteria (rate thresholds,
   no-input silence, and ≥ 19/20 shuffled brains), same seeds and shuffles.
3. Game-use gate: MN9 mean rate with right-LC10a input below the game's 20 Hz
   feeding threshold.
If any fails, we report it; we do not adjust b or tau_w.

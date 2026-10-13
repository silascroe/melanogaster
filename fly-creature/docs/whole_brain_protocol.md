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

# Addendum: mushroom-body (Kenyon cell) silencing (written 2026-10-11, before any run)

Adaptation failed (see whole_brain_result.md). Diagnosis: the self-sustained
activity is a runaway loop with ~1.6 M spikes/s indefinitely, some neurons pinned
at the maximum rate, and ~4,000 of ~14,000 persistently active neurons are
Kenyon cells (4,064 KCs, all cholinergic, held in check in the fly by the two
GABAergic APL neurons). This simple model cannot represent that inhibition.

Change (ours): silence all 4,064 neurons whose type starts with "KC", by removing
every connection to and from them (the paper's silencing method). Published
settings otherwise; no adaptation (one change at a time). None of the three
game behaviors is expected to need the mushroom body; if one does, that is a
result to report.

Pass criteria, whole brain with KCs silenced: identical to the adaptation
addendum (settling ≤ 1% of neurons 500–1000 ms after a 300 ms loom burst;
sugar, jump and turn original criteria with 20 shuffles of the silenced brain;
MN9 from right-LC10a input below 20 Hz). If any fails, we report it.

# Addendum: one brain copy per sense (written 2026-10-11, before implementation)

KC silencing also failed (settling 8,273 active; MN9 from target ~32 Hz), while
sugar, jump and turn still passed. Conclusion: the published model is validated
for single stimuli from rest; continuous multi-sense operation is an open
problem we will not chase further here.

Game architecture (engineering, labeled as such): three copies of the combined
subset, each starting at rest and receiving only one sense (taste, loom, target).
Each copy's action output is read only for its own sense (taste copy -> MN9 ->
feeding; loom copy -> DNp01 -> jump; target copy -> DNa02 -> turn). A copy is
reset to rest after its input has been zero for 500 ms; a resting copy with no
input is not simulated (it would stay exactly at rest). Published settings, no
adaptation, no silencing.

Pass criteria (BrainSession tests, written before running):
G1 Loom: 300 ms loom then 2 s without: at least one jump; no DNp01 spikes in the
   last 1 s; feeding never true.
G2 Target: 3 s on the right then 3 s on the left: mean turn rate in each phase's
   last second has the target's sign (right positive); feeding never true.
G3 Taste: 2 s sugar contact then 2 s without: feeding true at the end of contact,
   false at the end.
G4 Cut wiring (connections onto action neurons removed): no jump, no feeding,
   and |turn| < 0.05 rad/s throughout the same scenarios.
Reported: compute milliseconds per 50 ms frame.

# Addendum: antennal grooming and bitter taste (written 2026-10-13, before any run)

Same model, signs, 150 Hz Poisson input, 1 s trials, seeds and shuffle method as
the sugar, jump and turn tests. Neuron groups come from MaleCNS v1.0 `type` and
`status == Traced`.

## Antennal grooming

Basis: Hampel et al. (2015, eLife 4:e08758): Johnston's organ neurons projecting
to zones C and E (JO-CE) excite brain interneurons aBN1/aBN2 and descending
neurons aDN1–3, and activating any of these layers makes the fly groom its
antennae. The MaleCNS synonyms identify DNg62 as aDN1 and DNge078 as aDN2
(Hampel 2015); aDN3 is not named in this release.

- Input: every traced neuron whose type starts with `JO-C` or `JO-E` (68 + 267 =
  335; both antennae, as somaSide is blank for these afferents).
- Readout: mean rate of the four aDN neurons (DNg62 × 2, DNge078 × 2).

Pass criteria (all required):
1. aDN mean rate ≥ 10 Hz over seeds 0–2, and 0 Hz without input.
2. Intact aDN rate (seed 0) exceeds the rate in ≥ 19 of 20 shuffled brains
   (shuffle seeds 1000–1019).

Reported, not gated (seed 0): aDN1 and aDN2 separately; aDN rate when JO-A and
JO-B (hearing; Hampel found grooming only from C/E) or JO-F (MaleCNS subclass
"grooming") are driven instead; active-neuron counts.

## Bitter taste stops feeding

Basis: FlyWire classifies labellar taste type LB1 as bitter (LB2 low salt, LB3
sugar/water; Virtual Fly Brain records of FlyWire annotations). Bitter taste
suppresses proboscis extension in flies.

- Bitter input: every traced neuron whose type starts with `LB1` (57; the 6
  with `unclear` transmitter are inert under the existing rule).
- Sugar input: the LB3 group of the sugar test. Readout: MN9 mean rate.
- Suppression S = 1 − MN9(sugar + bitter) / MN9(sugar alone), same seed.

Pass criteria (all required):
1. Mean MN9 with sugar + bitter ≤ 50% of mean MN9 with sugar alone (seeds 0–2),
   and bitter alone gives MN9 0 Hz (seeds 0–2).
2. Wiring specificity. A whole-brain shuffle already abolishes sugar → MN9, so
   it cannot test suppression. Control brains instead rewire only the bitter
   neurons' outgoing connections: each gets a postsynaptic partner drawn at
   random from the postsynaptic partners of all connections in the brain,
   keeping its synapse count and sign; the rest of the brain is untouched
   (20 controls, seeds 2000–2019). Intact S (seed 0) exceeds control S
   (seed 0) in ≥ 19 of 20.

Reported, not gated: descending neurons (type starting `DN`) that fire ≥ 10 Hz
with bitter alone (seed 0). This is a screen, not a result: any movement
reaction it suggests needs its own pre-declared test before it is used.

## Use

Each behavior passes or fails on its own; a failure is reported and not tuned.
A passing behavior enters the game only after a new combined subset, selected
from all stimuli together, reproduces it (to be pre-declared separately).

# Addendum: game subset v3 with grooming and bitter (written 2026-10-13, after both passed, before any subset run)

Subset: every neuron that spikes in any whole-brain trial (seeds 0, 1, 2) of the
seven stimuli sugar (LB3), loom (LC4+LPLC2), right LC10a, left LC10a, antenna
(JO-C + JO-E), bitter (LB1) alone, and sugar + bitter together, plus all input
and readout neurons (adding JO-CE, LB1, DNg62, DNge078). Connections: all
whole-brain connections among them. Packaged as `brain_subset_v3.npz` (v1 stays
the record of the earlier subset; v2 was the failed adaptation variant).

Pass criteria on fresh seeds 10–12, subset versus whole brain, same inputs:
1. MN9 (sugar), DNp01 (loom), DNa02 asymmetry (right LC10a; left LC10a) and aDN
   rate (antenna) each within ±20% of the whole-brain mean.
2. Bitter in the subset: mean MN9 with sugar + bitter ≤ 50% of the subset's
   mean MN9 with sugar alone, and MN9 is 0 Hz with bitter alone.
3. No input: all readouts 0 Hz.
Reported, not gated: size, connections, package size, compute speed.

Game rules (engineering, labeled as such): an antenna-dust event drives JO-CE
at 150 Hz in a fourth brain copy ("touch") while dust remains; grooming is the
smoothed aDN rate above 30 Hz; grooming removes dust over 2.5 s. A bitter drop
drives LB1 together with LB3 in the taste copy on contact; feeding stays the
existing MN9 rule. Game check, before claiming the reaction in-game: with dust,
the intact brain grooms and the cut-wiring brain does not; at a bitter drop the
intact brain does not feed while at a plain drop it does.

## Subset v3 result and decision (written 2026-10-13, after the v3 run, before game checks)

Subset v3 (27,956 neurons) passed every check except one: right-LC10a DNa02
asymmetry was 97 Hz against the whole brain's 123 Hz (−21%, gate ±20%). Left
turns, sugar, loom, antenna grooming and both bitter checks passed. Per the rule
above, the selection is not adjusted. Decision (engineering): each brain copy
uses a package that passed for its own sense. The target copy keeps subset v1
(which passed both turn checks); the taste, loom and touch copies use v3. No
copy receives an input its package was not checked for.

# Addendum: courtship song from foreleg pheromone taste (written 2026-10-13, before any run)

Same model, signs, 150 Hz Poisson input, 1 s trials and shuffle method as the
earlier tests. Neuron sets come from MaleCNS v1.0 annotations (`receptorType`,
`entryNerve`, `type`, `status == Traced`).

Basis: male flies tap a female with their forelegs; foreleg taste neurons
expressing the ppk23 channel detect contact pheromones (Thistle et al. 2012;
Toda et al. 2012), and the descending neuron pIP10 drives courtship song
(von Philipsborn et al. 2011). In the fly, ppk23 is expressed both in "F cells"
(female pheromone, also ppk25+) that promote courtship and "M cells" (male
pheromone) that suppress it, so this input is a mixture; that is a known risk.

Facts checked before the run (annotations only, no simulation): the 65 foreleg
`putative_ppk25` neurons have predicted transmitter unclear (52) or glutamate
(13), so under the existing sign rule they cannot excite anything. The 71 foreleg
`putative_ppk23` neurons (entry nerve ProLN) are all predicted acetylcholine.
The ppk23 and ppk25 labels do not overlap in the annotations. pIP10 (2), vPR6 (8) and TN1 types are traced.

- Input: the 71 traced `putative_ppk23` neurons entering through the prothoracic
  leg nerve (ProLN), both forelegs.
- Readout: mean rate of the two pIP10 neurons.

Pass criteria (all required):
1. pIP10 mean rate ≥ 10 Hz over seeds 0–2, and 0 Hz without input.
2. Intact pIP10 rate (seed 0) exceeds the rate in ≥ 19 of 20 shuffled brains
   (shuffle seeds 1000–1019).

Reported, not gated (seed 0): pIP10 with ppk23 plus both LC10a groups (a seen
target; real courtship combines sight and taste); song-circuit neurons in the
nerve cord (vPR6, all TN1 types, dPR1) and DNp13, pMP2, MDN; pIP10 from other
inputs instead: ppk23 neurons of the mid and hind legs, foreleg IR52b, and the
foreleg ppk25 group with its sign set to excitatory (an explicit assumption
change, labelled as such and never used to pass); descending neurons ≥ 10 Hz;
active-neuron count.

Use: a failure is reported and not tuned. A pass enters the game only after a
new combined subset reproduces it (to be pre-declared separately).

## Courtship result (written 2026-10-13, after the run)

FAIL on criterion 1: foreleg ppk23 gave pIP10 1.0, 0 and 6.5 Hz (mean 2.5 Hz,
needed ≥ 10). Not tuned. Reported values included one large, unexpected
response: the 275 LC10a neurons alone drove pIP10 at 97.5 Hz (92 Hz with ppk23
added). Because this was noticed after the run, it is only a lead until the next
addendum tests it.

# Addendum: visual target to song command (written 2026-10-13, after the lead above, before any run)

Question: does one-sided LC10a input (the creature's existing target channel)
drive pIP10, and is that specific to this channel rather than any strong visual
input? Basis: LC10a neurons are needed for males to track a female during
courtship (Ribeiro et al. 2018), and males sing while tracking.

Fresh seeds; same model and 150 Hz Poisson input. Groups as in the jump/turn test:
right LC10a (traced, somaSide R, 140), left LC10a (135), loom = LC4 + LPLC2.
Readout: mean rate of the two pIP10 neurons.

Pass criteria (all required):
1. pIP10 mean ≥ 10 Hz over seeds 3–5 with right LC10a, and separately with
   left LC10a; 0 Hz without input.
2. Right-LC10a pIP10 (seed 3) exceeds the rate in ≥ 19 of 20 shuffled brains
   (shuffle seeds 1020–1039).
3. Specificity: pIP10 with loom input (seed 3) is below half the right-LC10a
   rate (seed 3).

Reported, not gated: each pIP10 cell per input side; vPR6, TN1, dPR1 rates;
pIP10 in game subset v1 (the target copy's package) on seeds 10–12 for right and
left LC10a, against the whole brain on the same seeds.

Game rule if it passes (engineering): while the target copy runs, a smoothed
pIP10 rate above 30 Hz is "singing": the fly extends one wing and vibrates it.
Game check: the intact brain sings while approaching a target, and the cut-wiring
brain does not (pIP10 joins the cut action neurons).

## Visual target song result (written 2026-10-13, after the run, before game work)

PASS, all three criteria ([evidence](evidence/whole_brain_target_song_v1.json)):
pIP10 38.5, 44.5, 46.5 Hz (right LC10a) and 37, 47, 39 Hz (left); 0 Hz without
input; 0 Hz with loom input; intact beat 20/20 shuffles (highest shuffle 25 Hz,
a narrower margin than earlier tests). Reported: subset v1 reproduces pIP10
(right 39.3 vs 40.5 Hz, left 36.7 vs 40.5 Hz whole-brain means on seeds 10–12),
so the target copy needs no new package; nerve-cord song interneuron dPR1 fires
at 71 Hz and TN1 at 14 Hz; vPR6 stays silent. The game rule above applies.

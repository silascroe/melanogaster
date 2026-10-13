# Whole-brain LIF: sugar → MN9 result (2026-10-11)

Protocol: [whole_brain_protocol.md](whole_brain_protocol.md), written before any run.
Evidence: [evidence/whole_brain_sugar_v1.json](evidence/whole_brain_sugar_v1.json).

## Result: PASS (both pre-declared checks)

The full MaleCNS v1.0 connectome (211,577 neurons, 25.2 million signed
connections, 125 million synapses) was run with the published Shiu et al. (2024)
LIF settings. Driving the 86 traced LB3 labellar taste neurons (FlyWire
"sugar/water") at 150 Hz:

| Condition | MN9 mean rate |
|---|---|
| Sugar/water input, 3 trials | 78, 76, 66 Hz (cells differ: e.g. 142 and 14 Hz in trial 0) |
| No input | 0 Hz |
| 20 shuffled brains, same input | 0 Hz in all 20 |

Intact wiring beat 20/20 shuffles (19 required).

## Checks that the shuffle result is not an artifact

- A shuffled brain still runs: the 86 inputs fire and 827 other neurons respond
  (913 active versus 16,552 in the intact brain). MN9 keeps exactly its number of
  incoming connections (253 and 128). The signal just does not reach MN9.
- Exploratory, not pre-declared: driving the other 76 labellar taste neurons
  (LB1, LB2, LB4 types, which include bitter-sensing cells) activates 15,361
  neurons but leaves MN9 at 0 Hz. MN9 responds to this taste group specifically,
  not to any widespread activity.

## Why the earlier small circuits failed

Hand-picked circuits with the creature's original LIF (0.05 mV/synapse, 15 mV to
threshold, 1 ms current pulses) could not carry signals through one or two
relays, and at high gain shuffled wiring worked equally well. The published
model has a 7 mV threshold gap, 0.275 mV/synapse conductances that decay over
5 ms, and every neuron and connection, so convergent and recurrent routes add up.

## Also tried (exploratory, single trial)

LC16 → MDN (backing up): MDN fired at 3–5 Hz. A weak response; not tested
against controls and not used.

## What this does and does not show

- Shows: in this model, the recorded MaleCNS wiring routes a sugar/water taste
  signal to the proboscis motor neuron, and random rewiring with the same
  neurons and connection counts does not.
- Does not show: realistic firing rates, the right sugar-versus-water split
  (LB3 mixes both), or that this model reproduces fly physiology generally.
  The model parameters, transmitter signs, and the "unclear → no effect" rule are
  assumptions; this is a NumPy reimplementation of the authors' Brian2 model,
  checked by unit tests, not their code.
- Cost: one simulated second takes about 70 s on this PC (i5-8400), so the
  whole-brain model cannot yet run live inside the game.

## Reproduce

```powershell
.\.venv\Scripts\python.exe fly-creature\tools\build_whole_brain.py
.\.venv\Scripts\python.exe fly-creature\tools\run_sugar_brain_test.py
```

The cache and run log stay in ignored `fly-creature/outputs/whole_brain/`.

# Active subset (2026-10-11): PASS, with caveats

Protocol: addendum in [whole_brain_protocol.md](whole_brain_protocol.md).
Evidence: [evidence/whole_brain_subset_v1.json](evidence/whole_brain_subset_v1.json).

The 17,561 neurons that fired in any of three whole-brain sugar trials (plus MN9),
with the 2.49 million connections among them, reproduce the result on fresh seeds:

| Seed | Whole brain MN9 | Subset MN9 |
|---|---|---|
| 10 | 57.0 Hz | 67.0 Hz |
| 11 | 67.0 Hz | 78.5 Hz |
| 12 | 66.5 Hz | 79.0 Hz |

Means 63.5 versus 74.8 Hz (+18%, inside the ±20% gate). No input: 0 Hz.
Speed: 7.3 s per simulated second versus 71.8 s for the whole brain (~10× faster),
still about 7× slower than real time.

Caveats:

- MN9 runs consistently higher in the subset, close to the gate. Overall activity
  is not inflated: on seed 10 the whole brain and subset produce 1,476,992 and
  1,477,433 spikes. (An earlier note comparing different seeds wrongly called the
  subset broadly overactive.) A likely reason is that neurons silent during
  selection, including inhibitory ones near MN9, are missing from the subset;
  larger or more varied selection would probably tighten this.
- The "other taste" check passed vacuously: none of the 76 other labellar taste
  neurons are in the subset, so nothing received input. It shows the subset
  cannot respond to those cells at all, not that it discriminates them. A subset
  for several behaviors must be selected from all of their stimuli together.

# Speed (2026-10-11)

`simulate()` now has a compiled Numba engine (optional dependency `fast-brain`),
used automatically when installed, with the NumPy loop as fallback. The Numba
step mirrors the NumPy operations and summation order, and produces bit-identical
spike counts (checked on the sugar subset and in `tests/test_brain_model.py`).

| | Original NumPy | Faster NumPy | Numba |
|---|---|---|---|
| Sugar subset (17,561 neurons) | 10.5 s | 5.3–6.0 s | **1.03 s** |
| Whole brain (211,577 neurons) | ~72 s | — | **6.1 s** |

Seconds of computing per simulated second on an i5-8400. The subset now runs at
about real time; a game integration still needs headroom for rendering.

# Game integration (2026-10-11)

Jump and turn also pass whole-brain tests ([evidence](evidence/whole_brain_behaviors_v1.json)):
DNp01 ~404 Hz with looming input versus at most 34.5 Hz in 20 shuffles; DNa02
right-minus-left +104 to +168 Hz (target right) and −139 to −154 Hz (left), beating
all 20 shuffles. A combined 25,151-neuron subset reproduces all three behaviors
within 20% of the whole brain ([evidence](evidence/brain_subset_v1.json)) and is
packaged as `src/fly_creature/data/brain_subset_v1.npz` (10.3 MB).

## Problem found in live use, and two failed fixes

Running continuously exposed what single 1 s trials from rest could not: after a
300 ms loom burst, ~13,500 neurons keep firing indefinitely (~1.6 M spikes/s,
some neurons pinned at the 435 Hz ceiling), MN9 then fires with no taste, and
target input alone drives MN9 at ~20–25 Hz. The whole brain does the same, so
this is a property of the published model, not of the subset. Two pre-declared
fixes failed and were not tuned:

- AdEx-derived adaptation (0.805 mV, 144 ms): still 13,472 active; MN9 from
  target ~25 Hz ([evidence](evidence/whole_brain_adaptation_v1.json)).
- Silencing the 4,064 Kenyon cells (about 4,000 of the persistent neurons): still
  8,273 active; MN9 from target ~32 Hz ([evidence](evidence/whole_brain_kc_silenced_v1.json)).

Sugar, jump and turn passed in both variants.

## Architecture used: one brain copy per sense

Each sense (taste, loom, target) drives its own copy of the subset that starts at
rest; each copy's action output is read only for its own sense; a copy resets
after 500 ms without input. This keeps every reaction inside the validated
regime (one stimulus from rest) but is not one integrated brain. All pre-declared
game checks pass (`tests/test_brain_session.py`): the loom copy jumps then
settles, steering follows the target side without feeding, taste starts and then
stops feeding, and cutting connections onto the action neurons removes all three
actions. The Godot scene check confirms roaming, jump, target approach and
feeding from a right-clicked sugar drop.

Speed: a running copy costs ~72–76 ms per 50 ms frame for taste or target and
~31 ms median for loom, so an active brain runs at roughly 0.7× real time; the
game keeps moving and simply gets brain updates a little less often.

# Antennal grooming and bitter taste (2026-10-13): both PASS

Protocol: addendum in [whole_brain_protocol.md](whole_brain_protocol.md), written
before the run. Evidence: [evidence/whole_brain_grooming_bitter_v1.json](evidence/whole_brain_grooming_bitter_v1.json).

**Grooming.** Driving the 335 traced Johnston's organ neurons of zones C and E
(JO-C, JO-E; antennal touch/deflection) at 150 Hz, the four aDN descending
neurons (DNg62 = aDN1, DNge078 = aDN2, per Hampel et al. 2015) fire at 203, 199
and 204 Hz on seeds 0–2, and 0 Hz without input. 20 shuffled brains gave at most
3.25 Hz. Reported only: aDN1 226 Hz and aDN2 181 Hz; driving the hearing zones
JO-A/B (138 neurons) or the MaleCNS "grooming" JO-F group (78) instead gives 0 Hz,
which matches Hampel's finding that grooming comes from zones C/E.

**Bitter.** Sugar (LB3) alone drives MN9 at 78, 76 and 66 Hz; sugar plus the 57
LB1 bitter neurons gives 0.5, 0 and 1 Hz; bitter alone gives 0 Hz. Suppression is
0.99. In 20 control brains where only the bitter neurons' outgoing connections
were sent to random targets, suppression was at most 0.33 (median 0.11),
so the suppression depends on where the bitter neurons actually connect.

Reported, not gated: bitter alone drives 153 descending-neuron types above 10 Hz
(DNb05 ~350 Hz, DNg33 ~300 Hz, ...). That is broad activation, not a clean
avoidance signal, so no movement reaction to bitter was built. In the game,
bitter only means "does not feed".

What this does not show: that the model's rates are realistic, which grooming
movement the aDNs would produce (the leg sweep is animation), or that LB1 is the
only bitter channel (pharyngeal and leg taste neurons were not used).

## Game subset v3

A 27,956-neuron subset selected from all seven stimuli
([evidence](evidence/brain_subset_v3.json)) passed six of seven gates: sugar,
loom, left turn, antenna grooming, and both bitter checks. It **failed** right
turn: DNa02 asymmetry 97 Hz versus 123 Hz in the whole brain (−21%, gate ±20%).
It was not tuned. Each brain copy in the game now uses a package that passed for
its own sense: the target copy keeps subset v1, and the taste, loom and touch
copies use v3 (`SENSE_PACKAGE` in `brain_session.py`).

## In the game

`E` dusts the antennae: a fourth brain copy (touch) gets JO-CE input while dust
remains, and the fly stops and sweeps its forelegs over its antennae while the
smoothed aDN rate is above 30 Hz; grooming clears the dust over 2.5 s, and then
aDN goes quiet. Shift + right-click drops a bitter-laced drop: at contact the
taste copy gets LB3 and LB1 together, MN9 stays near 0 Hz, and the fly does not
feed. The dust, its clearing time, the 30 Hz threshold and the foreleg animation
are engineered; the aDN response to JO-CE input and the bitter suppression of
MN9 come from the wiring. Game checks (`tests/test_brain_session.py`, g4–g6):
dust grooms then stops; cut wiring gives no grooming; a bitter drop is not fed
on while a plain drop is. The Godot capture (`godot/capture_autonomy.gd`)
confirms the same in the scene: grooming at ~45 Hz smoothed aDN, stopping once
the dust is gone, and bitter contact with no feeding.

Speed: a running v3 copy costs ~82–90 ms per 50 ms frame (v1: ~72–76 ms), so an
active brain now runs at about 0.55–0.6× real time.

# Competing-cue decoder replay

The stage-1,024 beacon/threat scene starts the collision-triggered threat
at 2 ms. The graph, neural settings, world, and initial body state are
identical for the touch-priority and strongest-vote batch replays.
Only the decoder policy changes. A no-threat control uses touch priority.

Status: `decoder_changed_action`. No-threat control escapes: 0.
Strongest-vote crossing matches the control's action and body on 12 of 12 frames.

First different action: **4 ms**,
after 4 matched frames. Both policies
saw touch vote 3 and visual vote 6;
cooldown before the decision was 0 ms.
Touch priority chose `escape_right`; strongest vote chose
`turn_left`.

## Final body positions (toy world units)

| Decoder | x | y | heading |
| --- | ---: | ---: | ---: |
| Touch priority | 1.54 | -1.63 | -60° |
| Strongest vote | 2.39 | -0.31 | -30° |

The trajectory CSV shows votes, actual actions, and body positions in
all three runs. Through the first different action the recorded neural
inputs, votes, and pre-action body states match. After that, different
body actions can alter future sensations and spikes; later differences
are closed-loop consequences, not matched-input decoder comparisons.

Connectome facts: the local FlyEM Male CNS release supplies node/edge
wiring and native signs. Synthetic sensory input, LIF parameters,
descending action labels, vote aggregation, memory, body, and both
decoders are model assumptions. This tests one designed scene, not
biological predator avoidance or robust behavior across scenes.

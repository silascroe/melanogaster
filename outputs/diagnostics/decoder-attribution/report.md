# Decoder attribution at 1,024 nodes

The existing touch-priority decoder controlled both replays. A shadow
strongest-population-wins decoder scored the **same recorded descending votes**
frame by frame; it did not control the body or change future neural inputs.

| Condition | Frames | Both populations voted | Vote-policy differences | Realized priority overrides | Actual escapes | Shadow escape votes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| control | 60 | 0 | 0 | 0 | 0 | 0 |
| crossing | 60 | 1 | 1 | 0 | 1 | 1 |

Crossing attribution: `latent_priority_sensitivity`.

## Crossing frames that matter

| Time | Touch vote | Visual vote | Live action/source | Priority vote | Shadow vote |
| ---: | ---: | ---: | --- | --- | --- |
| 3.0 ms | 3 | 0 | escape_right / touch | escape_right | escape_right |
| 4.0 ms | 1 | 6 | turn_left / memory | escape_left | turn_left |

A realized override means both touch and vision voted, the priority
policy selected a touch escape despite the shadow winner being visual,
and the live action was that touch escape. This isolates the decoder's
contribution on that frame; it does not show an alternate flight path.
If both populations never voted together, arbitration was not tested.
Vote differences without a realized override are only latent sensitivity
because cooldown and recovery may gate the live decoder.
Shadow action totals are vote-only tallies, not simulated alternate body
actions; ordinary differences may reflect live cooldown or recovery.
They are not alternate closed-loop outcomes.

Connectome facts: node/edge wiring and native signs come from the local
FlyEM Male CNS release. Assumptions: sensory currents, touch/visual
action labels, vote aggregation, priority and shadow decoders, and body.
The CSV records every frame's raw action votes and both readouts.

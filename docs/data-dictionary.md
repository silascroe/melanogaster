# MaleCNS v1.0 data dictionary and baseline inspection

These figures were measured from the local working copies on 2026-09-18 with PyArrow. Feather files are Apache Arrow IPC tables; all IDs below are 64-bit integers.

## Files

| file | rows | columns | measured schema |
| --- | ---: | ---: | --- |
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | 211,577 | 36 | annotation fields including `bodyId`, `type`, `instance`, `status`, `superclass`, `class`, `somaSide`, `somaLocation`, `tosomaLocation` |
| `body-neurotransmitters-male-cns-v1.0.feather` | 1,835,518 | 10 | `body:int64`, `cell_type:string`, `total_nt_predictions:int32`, confidence doubles, predicted/consensus label strings |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 151,856,684 | 3 | `body_pre:int64`, `body_post:int64`, `weight:int64` |

The official page describes the weights as segment-to-segment connection strengths and the weight as the connection strength/synapse count. The graph is therefore not safe to treat as a curated neuron-only table without a node policy.

## Annotation labels

The annotation table has 165,122 `Traced` rows. Other status counts are: `Orphan` 15,925; `Glia` 11,864; `Unimportant` 10,751; missing 5,472; `Assign` 1,832; and `Anchor` 611. The baseline keeps only `Traced` endpoints.

The most frequent non-null `type` labels include `R1-R6` (3,377), `Tm3` (2,054), `T3` (1,940), `T2a` (1,872), and `L5` (1,787). The default baseline seed type `DNge104` resolves to body IDs 12,781 (`DNge104_R`) and 556,329 (`DNge104_L`).

## Neurotransmitter labels

The table has one distinct row per `body` ID in this release. Consensus labels measured locally are: `unclear` 1,671,117; `acetylcholine` 104,193; `glutamate` 29,443; `gaba` 22,196; `histamine` 8,024; `dopamine` 396; `octopamine` 101; and `serotonin` 48.

These are predictions, not direct receptor-level sign measurements. The simulator preserves the label and confidence and applies only the explicit configurable sign convention documented in [decisions.md](decisions.md).

## Weight graph statistics

The complete raw table has 151,856,684 rows, weights from 1 to 2,591, mean weight 2.053470646, and summed weight 311,833,243. Endpoint IDs are intentionally not interpreted as the curated neuron set.

When both endpoints are restricted to the 165,122 `Traced` annotation IDs, the local scan finds:

| statistic | value |
| --- | ---: |
| directed edges | 25,563,197 |
| unique presynaptic bodies | 163,539 |
| unique postsynaptic bodies | 164,463 |
| minimum weight | 1 |
| maximum weight | 2,591 |
| mean weight | 4.851703251 |
| summed synapse-count weights | 124,025,046 |

The exact raw total-weight figure is recorded in `outputs/inspection/dataset_report.json`; the important reproducible baseline is the traced-only graph above.

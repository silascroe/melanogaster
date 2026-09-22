# 1,024-node arena acceptance

This is a scale and interface check for the existing Python/NumPy arena runtime, not a biological behavior claim.

- Requested stage: `1024`
- Actual unique nodes: `1024`
- Induced edges: `24807`
- Unified graph: `True`
- Initial build and replay: `88.150` s
- Cached replay: `0.044` s
- Live steps: `2`
- Live step timings: `[0.0005850999987160321, 0.0005855999988853]` s
- Batch replay digest match: `True`
- Causal trace complete: `True`
- Acceptance result: `True`

The first timing includes graph expansion, induced-edge construction, runtime compilation, and one replay. The second timing measures the cached stage. No full trajectory is stored in this compact artifact.

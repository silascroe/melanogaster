"""Build the whole-brain connectome cache for fly_creature.brain_model.

Development-only: reads the official MaleCNS v1.0 release (read-only) and writes
fly-creature/outputs/whole_brain/brain_v1.npz, which is ignored by Git. Signs and
neuron set follow docs/whole_brain_protocol.md.

    .venv\\Scripts\\python.exe fly-creature\\tools\\build_whole_brain.py
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

import numpy as np
import pyarrow.dataset as ds
import pyarrow.feather as feather

CREATURE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CREATURE_DIR / "src"))
from fly_creature.brain_model import TRANSMITTER_SIGN  # noqa: E402

ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
TRANSMITTERS = "body-neurotransmitters-male-cns-v1.0.feather"
WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"


def build(release: Path, output: Path) -> dict:
    started = time.time()
    annotations = feather.read_table(release / ANNOTATIONS,
        columns=["bodyId", "type", "flywireType", "subclass", "somaSide", "status"])
    body_ids = annotations.column("bodyId").to_numpy().astype(np.int64)
    order = np.argsort(body_ids)
    body_ids = body_ids[order]
    if len(np.unique(body_ids)) != len(body_ids):
        raise ValueError("Duplicate body IDs in annotations")
    def column(name: str) -> np.ndarray:
        values = annotations.column(name).to_pylist()
        return np.asarray(["" if values[i] is None else str(values[i]) for i in order])
    nt_table = feather.read_table(release / TRANSMITTERS, columns=["body", "consensus_nt"]).to_pylist()
    nt_by_body = {int(r["body"]): r["consensus_nt"] for r in nt_table}
    transmitter = np.asarray([nt_by_body.get(int(b)) or "missing" for b in body_ids])
    sign = np.asarray([TRANSMITTER_SIGN.get(t, 0.0) for t in transmitter], dtype=np.float64)

    weights = ds.dataset(release / WEIGHTS, format="feather").to_table(
        columns=["body_pre", "body_post", "weight"])
    pre_ids = weights.column("body_pre").to_numpy()
    post_ids = weights.column("body_post").to_numpy()
    synapses = weights.column("weight").to_numpy()
    total_rows = len(pre_ids)
    del weights
    pre = np.searchsorted(body_ids, pre_ids)
    post = np.searchsorted(body_ids, post_ids)
    pre_ok = (pre < len(body_ids)) & (body_ids[np.minimum(pre, len(body_ids) - 1)] == pre_ids)
    post_ok = (post < len(body_ids)) & (body_ids[np.minimum(post, len(body_ids) - 1)] == post_ids)
    keep = pre_ok & post_ok
    del pre_ids, post_ids
    pre, post, synapses = pre[keep], post[keep], synapses[keep]
    signed = synapses * sign[pre]
    effective = signed != 0
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output,
             body_ids=body_ids, cell_type=column("type"), flywire_type=column("flywireType"),
             subclass=column("subclass"), side=column("somaSide"), status=column("status"),
             transmitter=transmitter,
             pre=pre[effective].astype(np.int32), post=post[effective].astype(np.int32),
             signed_synapses=signed[effective].astype(np.int32))
    summary = {
        "neurons": int(len(body_ids)),
        "weight_rows": int(total_rows),
        "rows_between_neurons": int(keep.sum()),
        "rows_with_signed_effect": int(effective.sum()),
        "synapses_between_neurons": int(synapses.sum()),
        "transmitters": dict(Counter(transmitter.tolist()).most_common()),
        "seconds": round(time.time() - started, 1),
        "output": str(output),
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    parser.add_argument("--output", type=Path,
                        default=CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    args = parser.parse_args()
    print(json.dumps(build(args.release, args.output), indent=2))


if __name__ == "__main__":
    main()

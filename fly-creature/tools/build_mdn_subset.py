"""Build and check the obstacle brain copy, subset v4 (whole_brain_protocol.md addendum, 2026-10-13).

Selects neurons active under foreleg-bristle input, checks MDN against the whole
brain on fresh seeds, and packages src/fly_creature/data/brain_subset_v4.npz.
Writes docs/evidence/brain_subset_v4.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pyarrow.feather as feather

CREATURE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREATURE_DIR / "src"))
sys.path.insert(0, str(CREATURE_DIR / "tools"))
from fly_creature.brain_model import BrainParams, BrainRunner, simulate  # noqa: E402
from run_sugar_brain_test import load  # noqa: E402
from run_subset_test import restrict  # noqa: E402

PACKAGE = CREATURE_DIR / "src" / "fly_creature" / "data" / "brain_subset_v4.npz"
EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "brain_subset_v4.json"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    args = parser.parse_args()
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    ann = feather.read_table(args.release / ANNOTATIONS,
                             columns=["bodyId", "subclass", "entryNerve", "status"]).to_pandas()
    keep_rows = ((ann.status == "Traced") & (ann.subclass == "mechanosensory bristle")
                 & (ann.entryNerve == "ProLN"))
    g = {"foreleg": np.flatnonzero(np.isin(data["body_ids"], ann.loc[keep_rows, "bodyId"].to_numpy())),
         "mdn": np.flatnonzero((data["cell_type"] == "MDN") & (data["status"] == "Traced"))}
    active = np.zeros(brain.n_neurons, dtype=bool)
    for seed in (0, 1, 2):
        active |= simulate(brain, duration_ms=1000, poisson_targets=g["foreleg"], seed=seed).spike_counts > 0
        print(f"selection seed {seed}: {int(active.sum())} neurons", flush=True)
    for idx in g.values():
        active[idx] = True
    keep = np.flatnonzero(active)
    sub, new_index = restrict(brain, keep)
    sg = {k: new_index[v] for k, v in g.items()}
    print(f"subset: {sub.n_neurons} neurons, {len(sub.post)} connections", flush=True)
    whole = [float(simulate(brain, duration_ms=1000, poisson_targets=g["foreleg"], seed=s)
                   .rate_hz(g["mdn"]).mean()) for s in (10, 11, 12)]
    part = [float(simulate(sub, duration_ms=1000, poisson_targets=sg["foreleg"], seed=s)
                  .rate_hz(sg["mdn"]).mean()) for s in (10, 11, 12)]
    silent = float(simulate(sub, duration_ms=1000, seed=10).rate_hz(sg["mdn"]).mean())
    wm, pm = float(np.mean(whole)), float(np.mean(part))
    runner = BrainRunner(sub, input_neurons=sg["foreleg"], seed=10)
    runner.advance(5, [(sg["foreleg"], 150.0)])  # compile
    t = time.time()
    runner.advance(1000, [(sg["foreleg"], 150.0)])
    busy_s = time.time() - t
    pre = np.repeat(np.arange(sub.n_neurons), np.diff(sub.indptr)).astype(np.int32)
    signed = np.rint(sub.weight_mv / BrainParams().w_syn_mv).astype(np.int16)
    np.savez_compressed(PACKAGE, body_ids=data["body_ids"][keep], cell_type=data["cell_type"][keep],
                        side=data["side"][keep], pre=pre, post=sub.post.astype(np.int32),
                        signed_synapses=signed, adapt_mv=np.float64(BrainParams().adapt_mv),
                        adapt_tau_ms=np.float64(BrainParams().adapt_tau_ms),
                        **{f"group_{k}": v.astype(np.int32) for k, v in sg.items()})
    checks = {"mdn_within_20pct": abs(pm - wm) <= 0.2 * abs(wm), "silent_without_input": silent == 0}
    summary = {"neurons": int(sub.n_neurons), "connections": int(len(sub.post)),
               "package_mb": round(PACKAGE.stat().st_size / 1e6, 1),
               "mdn_whole_hz": whole, "mdn_subset_hz": part, "no_input_mdn_hz": silent,
               "busy_seconds_per_simulated_second": round(busy_s, 2),
               "checks": checks, "pass": all(checks.values())}
    EVIDENCE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

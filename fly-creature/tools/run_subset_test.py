"""Active-subset check for the sugar -> MN9 result (whole_brain_protocol.md addendum).

Chooses the subset from whole-brain activity on seeds 0-2, then compares subset
and whole brain on fresh seeds 10-12. Writes docs/evidence/whole_brain_subset_v1.json
and the subset's body IDs to the ignored outputs/whole_brain/ folder.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import numpy as np

CREATURE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREATURE_DIR / "src"))
sys.path.insert(0, str(CREATURE_DIR / "tools"))
from fly_creature.brain_model import BrainParams, Connectome, simulate  # noqa: E402
from run_sugar_brain_test import load  # noqa: E402

CACHE = CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz"
EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_subset_v1.json"
SUBSET_IDS = CREATURE_DIR / "outputs" / "whole_brain" / "sugar_subset_v1_body_ids.npy"


def restrict(brain: Connectome, keep: np.ndarray) -> tuple[Connectome, np.ndarray]:
    """Return the induced sub-connectome on sorted indices `keep` and the index map."""
    new_index = np.full(brain.n_neurons, -1, dtype=np.int64)
    new_index[keep] = np.arange(len(keep))
    pre = np.repeat(np.arange(brain.n_neurons), np.diff(brain.indptr))
    mask = (new_index[pre] >= 0) & (new_index[brain.post] >= 0)
    signed = np.rint(brain.weight_mv[mask] / BrainParams().w_syn_mv)
    sub = Connectome.from_edges(len(keep), new_index[pre[mask]], new_index[brain.post[mask]],
                                signed, BrainParams().w_syn_mv)
    return sub, new_index


def main() -> None:
    data, brain = load(CACHE)
    lab = (data["subclass"] == "labellar bristle") & (data["status"] == "Traced")
    sugar = np.flatnonzero(lab & (data["flywire_type"] == "LB3"))
    other = np.flatnonzero(lab & (data["flywire_type"] != "LB3") & (data["flywire_type"] != ""))
    mn9 = np.flatnonzero(data["cell_type"] == "MN9")
    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    active = np.zeros(brain.n_neurons, dtype=bool)
    for seed in (0, 1, 2):
        active |= run(brain, sugar, seed).spike_counts > 0
        print(f"selection seed {seed}: {int(active.sum())} neurons active so far", flush=True)
    active[mn9] = True
    keep = np.flatnonzero(active)
    sub, new_index = restrict(brain, keep)
    np.save(SUBSET_IDS, data["body_ids"][keep])
    print(f"subset: {sub.n_neurons} neurons, {len(sub.post)} connections", flush=True)
    sub_sugar, sub_mn9 = new_index[sugar], new_index[mn9]
    sub_other = new_index[other][new_index[other] >= 0]
    whole_rates, sub_rates, whole_s, sub_s = [], [], [], []
    for seed in (10, 11, 12):
        t = time.time(); whole_rates.append(float(run(brain, sugar, seed).rate_hz(mn9).mean())); whole_s.append(time.time() - t)
        t = time.time(); sub_rates.append(float(run(sub, sub_sugar, seed).rate_hz(sub_mn9).mean())); sub_s.append(time.time() - t)
        print(f"seed {seed}: whole {whole_rates[-1]:.1f} Hz ({whole_s[-1]:.0f} s), "
              f"subset {sub_rates[-1]:.1f} Hz ({sub_s[-1]:.1f} s)", flush=True)
    silent = float(run(sub, [], 10).rate_hz(sub_mn9).mean())
    other_rate = float(run(sub, sub_other, 10).rate_hz(sub_mn9).mean())
    whole_mean, sub_mean = float(np.mean(whole_rates)), float(np.mean(sub_rates))
    checks = {
        "rate_within_20pct": abs(sub_mean - whole_mean) <= 0.2 * whole_mean,
        "silent_without_input": silent == 0.0,
        "silent_with_other_taste": other_rate == 0.0,
    }
    summary = {
        "subset_neurons": int(sub.n_neurons), "subset_connections": int(len(sub.post)),
        "whole_neurons": int(brain.n_neurons), "whole_connections": int(len(brain.post)),
        "test_seeds": [10, 11, 12],
        "whole_mn9_rate_hz": whole_rates, "subset_mn9_rate_hz": sub_rates,
        "subset_no_input_hz": silent, "subset_other_taste_hz": other_rate,
        "other_taste_inputs_in_subset": int(len(sub_other)),
        "seconds_per_simulated_second": {"whole": round(float(np.mean(whole_s)), 1),
                                         "subset": round(float(np.mean(sub_s)), 1)},
        "checks": checks, "pass": all(checks.values()),
    }
    EVIDENCE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

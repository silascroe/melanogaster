"""Build and check the combined game brain (whole_brain_protocol.md, last addendum).

Selects the subset from whole-brain activity, checks it against the whole brain
on fresh seeds, and packages it as src/fly_creature/data/brain_subset_v1.npz so
the creature runtime needs neither the release nor the whole-brain cache.
Writes docs/evidence/brain_subset_v1.json.
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
from fly_creature.brain_model import ADAPTIVE, BrainParams, BrainRunner, simulate  # noqa: E402
from run_sugar_brain_test import load  # noqa: E402
from run_subset_test import restrict  # noqa: E402

# v1: published settings. v2 (--adaptive): with the fixed adaptation term.
ADAPT = "--adaptive" in sys.argv
PARAMS = ADAPTIVE if ADAPT else BrainParams()
VERSION = "v2" if ADAPT else "v1"
PACKAGE = CREATURE_DIR / "src" / "fly_creature" / "data" / f"brain_subset_{VERSION}.npz"
EVIDENCE = CREATURE_DIR / "docs" / "evidence" / f"brain_subset_{VERSION}.json"


def groups(data: dict) -> dict[str, np.ndarray]:
    traced = data["status"] == "Traced"
    t = lambda name, side=None: np.flatnonzero((data["cell_type"] == name) & traced
                                               & ((data["side"] == side) if side else True))
    lab = (data["subclass"] == "labellar bristle") & traced
    return {
        "sugar": np.flatnonzero(lab & (data["flywire_type"] == "LB3")),
        "loom": np.concatenate([t("LC4"), t("LPLC2")]),
        "lc10a_R": t("LC10a", "R"), "lc10a_L": t("LC10a", "L"),
        "mn9": t("MN9"), "gf": t("DNp01"), "dna02_R": t("DNa02", "R"), "dna02_L": t("DNa02", "L"),
    }


def readouts(counts_or_result, g: dict) -> dict[str, float]:
    c = counts_or_result
    rate = lambda idx: float(c[idx].mean())  # 1 s trials: counts are Hz
    return {"mn9": rate(g["mn9"]), "gf": rate(g["gf"]),
            "dna02_asym": rate(g["dna02_R"]) - rate(g["dna02_L"])}


def main() -> None:
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    g = groups(data)
    stimuli = {"sugar": "sugar", "loom": "loom", "right": "lc10a_R", "left": "lc10a_L"}
    readout_for = {"sugar": "mn9", "loom": "gf", "right": "dna02_asym", "left": "dna02_asym"}
    active = np.zeros(brain.n_neurons, dtype=bool)
    for name, key in stimuli.items():
        for seed in (0, 1, 2):
            active |= simulate(brain, duration_ms=1000, poisson_targets=g[key], seed=seed, params=PARAMS).spike_counts > 0
        print(f"after {name}: {int(active.sum())} neurons", flush=True)
    for idx in g.values():
        active[idx] = True
    keep = np.flatnonzero(active)
    sub, new_index = restrict(brain, keep)
    sg = {k: new_index[v] for k, v in g.items()}
    print(f"subset: {sub.n_neurons} neurons, {len(sub.post)} connections", flush=True)
    comparison = {}
    for name, key in stimuli.items():
        whole, part = [], []
        for seed in (10, 11, 12):
            whole.append(readouts(simulate(brain, duration_ms=1000, poisson_targets=g[key], seed=seed, params=PARAMS).spike_counts, g)[readout_for[name]])
            part.append(readouts(simulate(sub, duration_ms=1000, poisson_targets=sg[key], seed=seed, params=PARAMS).spike_counts, sg)[readout_for[name]])
        wm, pm = float(np.mean(whole)), float(np.mean(part))
        comparison[name] = {"readout": readout_for[name], "whole": whole, "subset": part,
                            "within_20pct": abs(pm - wm) <= 0.2 * abs(wm)}
        print(name, comparison[name], flush=True)
    silent = readouts(simulate(sub, duration_ms=1000, seed=10, params=PARAMS).spike_counts, sg)
    all_inputs = np.concatenate([sg["sugar"], sg["loom"], sg["lc10a_R"], sg["lc10a_L"]])
    runner = BrainRunner(sub, input_neurons=all_inputs, seed=10, params=PARAMS)
    runner.advance(5, [(all_inputs, 150.0)])  # compile
    t = time.time()
    runner.advance(1000, [(all_inputs, 150.0)])
    busy_s = time.time() - t
    # Package: signed synapse counts, so the runtime rebuilds weights from BrainParams.
    pre = np.repeat(np.arange(sub.n_neurons), np.diff(sub.indptr)).astype(np.int32)
    signed = np.rint(sub.weight_mv / BrainParams().w_syn_mv).astype(np.int16)
    PACKAGE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PACKAGE, body_ids=data["body_ids"][keep], cell_type=data["cell_type"][keep],
                        side=data["side"][keep], pre=pre, post=sub.post.astype(np.int32),
                        signed_synapses=signed, adapt_mv=np.float64(PARAMS.adapt_mv),
                        adapt_tau_ms=np.float64(PARAMS.adapt_tau_ms),
                        **{f"group_{k}": v.astype(np.int32) for k, v in sg.items()})
    checks = {**{f"{k}_within_20pct": v["within_20pct"] for k, v in comparison.items()},
              "silent_without_input": all(v == 0 for v in silent.values())}
    summary = {"neurons": int(sub.n_neurons), "connections": int(len(sub.post)),
               "package_mb": round(PACKAGE.stat().st_size / 1e6, 1),
               "comparison": comparison, "no_input": silent,
               "busy_seconds_per_simulated_second": round(busy_s, 2),
               "checks": checks, "pass": all(checks.values())}
    EVIDENCE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("neurons", "connections", "package_mb",
                                              "busy_seconds_per_simulated_second", "checks", "pass")}, indent=2))


if __name__ == "__main__":
    main()

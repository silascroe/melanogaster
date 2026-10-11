"""Run the pre-declared sugar -> MN9 whole-brain test (docs/whole_brain_protocol.md).

Needs the cache from tools/build_whole_brain.py. Writes a compact JSON summary to
docs/evidence/whole_brain_sugar_v1.json; nothing is tuned against the results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

CREATURE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CREATURE_DIR / "src"))
from fly_creature.brain_model import BrainParams, Connectome, simulate  # noqa: E402

PROTOCOL = {"input": "traced labellar bristle, FlyWire type LB3 (sugar/water)",
            "output": "MN9", "rate_hz": 150.0, "duration_ms": 1000.0,
            "trials": 3, "shuffles": 20, "min_rate_hz": 10.0, "min_shuffles_beaten": 19}


def load(cache: Path) -> tuple[dict, Connectome]:
    data = dict(np.load(cache))
    connectome = Connectome.from_edges(len(data["body_ids"]), data["pre"], data["post"],
                                       data["signed_synapses"], BrainParams().w_syn_mv)
    return data, connectome


def shuffled(connectome: Connectome, data: dict, seed: int) -> Connectome:
    # Permute postsynaptic targets across all connections: each neuron keeps its
    # outgoing signed synapse counts and its number of incoming connections.
    rng = np.random.default_rng(seed)
    pre = np.repeat(np.arange(connectome.n_neurons), np.diff(connectome.indptr))
    post = rng.permutation(connectome.post)
    signed = connectome.weight_mv / BrainParams().w_syn_mv
    return Connectome.from_edges(connectome.n_neurons, pre, post, np.rint(signed), BrainParams().w_syn_mv)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path,
                        default=CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    parser.add_argument("--output", type=Path,
                        default=CREATURE_DIR / "docs" / "evidence" / "whole_brain_sugar_v1.json")
    parser.add_argument("--timing-only", action="store_true")
    args = parser.parse_args()
    data, brain = load(args.cache)
    sugar = np.flatnonzero((data["subclass"] == "labellar bristle") & (data["flywire_type"] == "LB3")
                           & (data["status"] == "Traced"))
    mn9 = np.flatnonzero(data["cell_type"] == "MN9")
    print(f"LB3 inputs: {len(sugar)}  MN9: {len(mn9)}", flush=True)
    run = lambda conn, targets, seed: simulate(conn, duration_ms=PROTOCOL["duration_ms"],
        poisson_targets=targets, poisson_rate_hz=PROTOCOL["rate_hz"], seed=seed)
    started = time.time()
    first = run(brain, sugar, 0)
    print(f"trial 0: MN9 {first.rate_hz(mn9).tolist()} Hz, {time.time() - started:.0f} s, "
          f"{int(first.spike_counts.sum())} spikes total, "
          f"{int((first.spike_counts > 0).sum())} neurons active", flush=True)
    if args.timing_only:
        return
    trials = [first] + [run(brain, sugar, seed) for seed in range(1, PROTOCOL["trials"])]
    sugar_rates = [float(t.rate_hz(mn9).mean()) for t in trials]
    silent = run(brain, [], 0)
    silent_rate = float(silent.rate_hz(mn9).mean())
    print(f"sugar MN9 mean rates: {sugar_rates}; no input: {silent_rate}", flush=True)
    intact = sugar_rates[0]
    shuffle_rates = []
    for seed in range(PROTOCOL["shuffles"]):
        rate = float(run(shuffled(brain, data, 1000 + seed), sugar, 0).rate_hz(mn9).mean())
        shuffle_rates.append(rate)
        print(f"shuffle {seed}: MN9 {rate:.1f} Hz", flush=True)
    beaten = sum(intact > r for r in shuffle_rates)
    mean_sugar = float(np.mean(sugar_rates))
    checks = {
        "mn9_responds": mean_sugar >= PROTOCOL["min_rate_hz"] and silent_rate == 0.0,
        "wiring_specific": beaten >= PROTOCOL["min_shuffles_beaten"],
    }
    summary = {
        "protocol": PROTOCOL,
        "params": BrainParams().__dict__,
        "neurons": int(brain.n_neurons), "connections": int(len(brain.post)),
        "inputs": int(len(sugar)), "mn9_body_ids": data["body_ids"][mn9].tolist(),
        "sugar_mn9_rate_hz_per_trial": sugar_rates, "no_input_mn9_rate_hz": silent_rate,
        "neurons_active_trial0": int((first.spike_counts > 0).sum()),
        "shuffle_mn9_rate_hz": shuffle_rates, "shuffles_beaten": int(beaten),
        "checks": checks, "pass": all(checks.values()),
        "runtime_s": round(time.time() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("checks", "pass", "shuffles_beaten", "runtime_s")}))


if __name__ == "__main__":
    main()

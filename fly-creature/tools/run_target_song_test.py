"""Pre-declared whole-brain test: one-sided LC10a -> pIP10 (whole_brain_protocol.md addendum, 2026-10-13).

Writes docs/evidence/whole_brain_target_song_v1.json. Uses the cache from
build_whole_brain.py and the packaged game subset v1 for the reported subset check.
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
from run_sugar_brain_test import load, shuffled  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_target_song_v1.json"
SUBSET = CREATURE_DIR / "src" / "fly_creature" / "data" / "brain_subset_v1.npz"


def main() -> None:
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    traced = data["status"] == "Traced"
    cell_type = data["cell_type"]
    cells = lambda t, side=None: np.flatnonzero((cell_type == t) & traced
                                                & ((data["side"] == side) if side else True))
    right, left = cells("LC10a", "R"), cells("LC10a", "L")
    loom = np.concatenate([cells("LC4"), cells("LPLC2")])
    pip10 = cells("pIP10")
    song = {"vPR6": cells("vPR6"), "TN1": np.flatnonzero(traced & np.char.startswith(cell_type, "TN1")),
            "dPR1": cells("dPR1")}
    print(f"LC10a R {len(right)} L {len(left)}  loom {len(loom)}  pIP10 {len(pip10)} "
          f"sides {data['side'][pip10].tolist()}", flush=True)
    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    mean_rate = lambda result, idx: float(result.rate_hz(idx).mean())
    started = time.time()

    right_runs = [run(brain, right, s) for s in (3, 4, 5)]
    left_runs = [run(brain, left, s) for s in (3, 4, 5)]
    right_hz = [mean_rate(r, pip10) for r in right_runs]
    left_hz = [mean_rate(r, pip10) for r in left_runs]
    silent_hz = mean_rate(run(brain, [], 3), pip10)
    loom_hz = mean_rate(run(brain, loom, 3), pip10)
    print("pIP10 right:", right_hz, "left:", left_hz, "silent:", silent_hz, "loom:", loom_hz, flush=True)
    shuffles = []
    for k in range(20):
        shuffles.append(mean_rate(run(shuffled(brain, data, 1020 + k), right, 3), pip10))
        print(f"shuffle {k}: pIP10 {shuffles[-1]:.1f} Hz", flush=True)
    beaten = sum(right_hz[0] > x for x in shuffles)
    checks = {
        "right_mean_ge_10hz": float(np.mean(right_hz)) >= 10,
        "left_mean_ge_10hz": float(np.mean(left_hz)) >= 10,
        "silent_without_input": silent_hz == 0,
        "beats_19_of_20_shuffles": beaten >= 19,
        "loom_below_half_right": loom_hz < 0.5 * right_hz[0],
    }

    # Reported: the packaged target-copy subset on the subset seeds.
    with np.load(SUBSET) as s:
        sub = Connectome.from_edges(len(s["body_ids"]), s["pre"], s["post"],
                                    s["signed_synapses"].astype(np.float64), BrainParams().w_syn_mv)
        sub_pip10 = np.flatnonzero(s["cell_type"] == "pIP10")
        sub_groups = {"right": s["group_lc10a_R"], "left": s["group_lc10a_L"]}
    subset_check = {}
    for name, whole_idx in (("right", right), ("left", left)):
        subset_check[name] = {
            "whole": [mean_rate(run(brain, whole_idx, seed), pip10) for seed in (10, 11, 12)],
            "subset": [mean_rate(run(sub, sub_groups[name], seed), sub_pip10) for seed in (10, 11, 12)],
        }
    result = {
        "pip10_body_ids": data["body_ids"][pip10].tolist(),
        "pip10_sides": data["side"][pip10].tolist(),
        "pip10_right_lc10a_hz": right_hz, "pip10_left_lc10a_hz": left_hz,
        "no_input_hz": silent_hz, "loom_hz": loom_hz,
        "shuffle_pip10_hz": shuffles, "shuffles_beaten": int(beaten),
        "checks": checks, "pass": all(checks.values()),
        "reported": {
            "pip10_each_hz_right_seed3": right_runs[0].rate_hz(pip10).tolist(),
            "pip10_each_hz_left_seed3": left_runs[0].rate_hz(pip10).tolist(),
            "song_circuit_hz_right_seed3": {k: mean_rate(right_runs[0], v) for k, v in song.items()},
            "subset_v1_pip10": subset_check,
        },
        "runtime_s": round(time.time() - started),
    }
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "shuffle_pip10_hz"}))


if __name__ == "__main__":
    main()

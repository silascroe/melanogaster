"""Pre-declared whole-brain jump and turn tests (whole_brain_protocol.md addendum).

Writes docs/evidence/whole_brain_behaviors_v1.json. Uses the shuffle method of
run_sugar_brain_test.py and the cache from build_whole_brain.py.
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
from fly_creature.brain_model import simulate  # noqa: E402
from run_sugar_brain_test import load, shuffled  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_behaviors_v1.json"


def main() -> None:
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    traced = data["status"] == "Traced"
    cells = lambda t, side=None: np.flatnonzero((data["cell_type"] == t) & traced
                                                & ((data["side"] == side) if side else True))
    loom = np.concatenate([cells("LC4"), cells("LPLC2")])
    gf = cells("DNp01")
    lc10a_r, lc10a_l = cells("LC10a", "R"), cells("LC10a", "L")
    dna_r, dna_l = cells("DNa02", "R"), cells("DNa02", "L")
    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    asym = lambda r: float(r.rate_hz(dna_r).mean() - r.rate_hz(dna_l).mean())
    started = time.time()
    jump_rates = [float(run(brain, loom, s).rate_hz(gf).mean()) for s in (0, 1, 2)]
    print("jump DNp01 rates:", jump_rates, flush=True)
    right = [asym(run(brain, lc10a_r, s)) for s in (0, 1, 2)]
    left = [asym(run(brain, lc10a_l, s)) for s in (0, 1, 2)]
    print("turn asymmetry right input:", right, "left input:", left, flush=True)
    silent = run(brain, [], 0)
    silent_gf = float(silent.rate_hz(gf).mean())
    silent_dna = silent.rate_hz(np.concatenate([dna_l, dna_r])).tolist()
    shuffle_jump, shuffle_turn = [], []
    for k in range(20):
        sh = shuffled(brain, data, 1000 + k)
        shuffle_jump.append(float(run(sh, loom, 0).rate_hz(gf).mean()))
        shuffle_turn.append(asym(run(sh, lc10a_r, 0)))
        print(f"shuffle {k}: DNp01 {shuffle_jump[-1]:.1f} Hz, DNa02 R-L {shuffle_turn[-1]:+.1f} Hz", flush=True)
    jump_beaten = sum(jump_rates[0] > x for x in shuffle_jump)
    turn_beaten = sum(right[0] > x for x in shuffle_turn)
    results = {
        "jump": {"dnp01_rate_hz": jump_rates, "no_input_hz": silent_gf,
                 "shuffle_dnp01_hz": shuffle_jump, "shuffles_beaten": int(jump_beaten),
                 "pass": float(np.mean(jump_rates)) >= 10 and silent_gf == 0 and jump_beaten >= 19},
        "turn": {"asymmetry_right_input_hz": right, "asymmetry_left_input_hz": left,
                 "no_input_dna02_hz": silent_dna, "shuffle_asymmetry_hz": shuffle_turn,
                 "shuffles_beaten": int(turn_beaten),
                 "pass": (float(np.mean(right)) >= 10 and float(np.mean(left)) <= -10
                          and max(silent_dna) == 0 and turn_beaten >= 19)},
        "runtime_s": round(time.time() - started),
    }
    EVIDENCE.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: results[k]["pass"] for k in ("jump", "turn")}))


if __name__ == "__main__":
    main()

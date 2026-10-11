"""Pre-declared adaptation tests (whole_brain_protocol.md, adaptation addendum).

Whole brain with fixed AdEx-derived adaptation: settling after a loom burst,
the original sugar/jump/turn criteria with 20 shuffles, and the MN9 game gate.
Writes docs/evidence/whole_brain_adaptation_v1.json.
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
from fly_creature.brain_model import ADAPTIVE, BrainRunner, simulate  # noqa: E402
from run_sugar_brain_test import load, shuffled  # noqa: E402
from build_brain_subset import groups  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_adaptation_v1.json"


def main() -> None:
    started = time.time()
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    g = groups(data)
    inputs = np.concatenate([g["sugar"], g["loom"], g["lc10a_R"], g["lc10a_L"]])
    run = lambda conn, key, seed: simulate(conn, duration_ms=1000.0, poisson_targets=g[key] if key else [],
                                           poisson_rate_hz=150.0, seed=seed, params=ADAPTIVE).spike_counts
    mean = lambda c, key: float(c[g[key]].mean())
    asym = lambda c: mean(c, "dna02_R") - mean(c, "dna02_L")
    # 1. Settling
    runner = BrainRunner(brain, input_neurons=inputs, seed=1, params=ADAPTIVE)
    runner.advance(300, [(g["loom"], 150.0)])
    runner.advance(500)
    late = runner.advance(500)
    settled_active = int(np.count_nonzero(late))
    print("settling: active in 500-1000 ms after input:", settled_active, flush=True)
    # 2. Behaviors, intact
    sugar = [mean(run(brain, "sugar", s), "mn9") for s in (0, 1, 2)]
    jump = [mean(run(brain, "loom", s), "gf") for s in (0, 1, 2)]
    right_runs = [run(brain, "lc10a_R", s) for s in (0, 1, 2)]
    right = [asym(c) for c in right_runs]
    left = [asym(run(brain, "lc10a_L", s)) for s in (0, 1, 2)]
    silent = run(brain, None, 0)
    silent_max = float(max(silent[g[k]].max() for k in ("mn9", "gf", "dna02_R", "dna02_L")))
    mn9_from_target = [mean(c, "mn9") for c in right_runs]
    print("sugar", sugar, "jump", jump, "right", right, "left", left,
          "silent max", silent_max, "MN9 from target", mn9_from_target, flush=True)
    sh_sugar, sh_jump, sh_turn = [], [], []
    for k in range(20):
        sh = shuffled(brain, data, 1000 + k)
        sh_sugar.append(mean(run(sh, "sugar", 0), "mn9"))
        sh_jump.append(mean(run(sh, "loom", 0), "gf"))
        sh_turn.append(asym(run(sh, "lc10a_R", 0)))
        print(f"shuffle {k}: MN9 {sh_sugar[-1]:.1f}  DNp01 {sh_jump[-1]:.1f}  DNa02 R-L {sh_turn[-1]:+.1f}", flush=True)
    beats = lambda intact, shuf: int(sum(intact > x for x in shuf))
    checks = {
        "settles": settled_active <= 0.01 * brain.n_neurons,
        "sugar": float(np.mean(sugar)) >= 10 and silent_max == 0 and beats(sugar[0], sh_sugar) >= 19,
        "jump": float(np.mean(jump)) >= 10 and silent_max == 0 and beats(jump[0], sh_jump) >= 19,
        "turn": (float(np.mean(right)) >= 10 and float(np.mean(left)) <= -10 and silent_max == 0
                 and beats(right[0], sh_turn) >= 19),
        "game_gate_mn9_from_target_below_20hz": float(np.mean(mn9_from_target)) < 20.0,
    }
    summary = {"params": ADAPTIVE.__dict__, "settling_active_neurons": settled_active,
               "sugar_mn9_hz": sugar, "jump_dnp01_hz": jump, "turn_asym_right_hz": right,
               "turn_asym_left_hz": left, "no_input_max_hz": silent_max,
               "mn9_from_right_lc10a_hz": mn9_from_target,
               "shuffles": {"sugar_mn9_hz": sh_sugar, "jump_dnp01_hz": sh_jump, "turn_asym_hz": sh_turn},
               "shuffles_beaten": {"sugar": beats(sugar[0], sh_sugar), "jump": beats(jump[0], sh_jump),
                                   "turn": beats(right[0], sh_turn)},
               "checks": checks, "pass": all(checks.values()), "runtime_s": round(time.time() - started)}
    EVIDENCE.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "pass": summary["pass"]}, indent=2))


if __name__ == "__main__":
    main()

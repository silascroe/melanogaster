"""Pre-declared whole-brain grooming and bitter tests (whole_brain_protocol.md addendum, 2026-10-13).

Writes docs/evidence/whole_brain_grooming_bitter_v1.json. Uses the shuffle method of
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
from fly_creature.brain_model import BrainParams, Connectome, simulate  # noqa: E402
from run_sugar_brain_test import load, shuffled  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_grooming_bitter_v1.json"


def rewired_outputs(connectome: Connectome, sources: np.ndarray, seed: int) -> Connectome:
    """Give every connection from `sources` a random postsynaptic partner drawn from
    all connections' partners, keeping its signed synapse count; nothing else changes."""
    rng = np.random.default_rng(seed)
    pre = np.repeat(np.arange(connectome.n_neurons), np.diff(connectome.indptr))
    post = connectome.post.copy()
    moved = np.isin(pre, sources)
    post[moved] = rng.choice(connectome.post, size=int(moved.sum()), replace=False)
    signed = connectome.weight_mv / BrainParams().w_syn_mv
    return Connectome.from_edges(connectome.n_neurons, pre, post, np.rint(signed), BrainParams().w_syn_mv)


def main() -> None:
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    traced = data["status"] == "Traced"
    cell_type = data["cell_type"]
    prefixed = lambda *p: np.flatnonzero(traced & np.any([np.char.startswith(cell_type, x) for x in p], axis=0))
    named = lambda t: np.flatnonzero(traced & (cell_type == t))
    jo_ce, jo_ab, jo_f = prefixed("JO-C", "JO-E"), prefixed("JO-A", "JO-B"), prefixed("JO-F")
    adn1, adn2 = named("DNg62"), named("DNge078")
    adn = np.concatenate([adn1, adn2])
    bitter = prefixed("LB1")
    sugar = np.flatnonzero((data["subclass"] == "labellar bristle") & (data["flywire_type"] == "LB3") & traced)
    mn9 = np.flatnonzero(cell_type == "MN9")
    dns = prefixed("DN")
    print(f"JO-CE {len(jo_ce)}  aDN {len(adn)}  LB1 {len(bitter)}  LB3 {len(sugar)}  MN9 {len(mn9)}", flush=True)
    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    mean_rate = lambda result, cells: float(result.rate_hz(cells).mean())
    started = time.time()

    # Antennal grooming.
    groom_trials = [run(brain, jo_ce, s) for s in (0, 1, 2)]
    groom_rates = [mean_rate(r, adn) for r in groom_trials]
    silent = run(brain, [], 0)
    print("grooming aDN rates:", groom_rates, "no input:", mean_rate(silent, adn), flush=True)
    groom_shuffles = []
    for k in range(20):
        groom_shuffles.append(mean_rate(run(shuffled(brain, data, 1000 + k), jo_ce, 0), adn))
        print(f"shuffle {k}: aDN {groom_shuffles[-1]:.1f} Hz", flush=True)
    jo_ab_run, jo_f_run = run(brain, jo_ab, 0), run(brain, jo_f, 0)
    groom_beaten = sum(groom_rates[0] > x for x in groom_shuffles)
    grooming = {
        "inputs": int(len(jo_ce)), "adn_body_ids": data["body_ids"][adn].tolist(),
        "adn_rate_hz": groom_rates, "no_input_hz": mean_rate(silent, adn),
        "shuffle_adn_hz": groom_shuffles, "shuffles_beaten": int(groom_beaten),
        "pass": (float(np.mean(groom_rates)) >= 10 and mean_rate(silent, adn) == 0 and groom_beaten >= 19),
        "reported": {
            "adn1_dng62_hz": mean_rate(groom_trials[0], adn1), "adn2_dnge078_hz": mean_rate(groom_trials[0], adn2),
            "jo_ab_inputs": int(len(jo_ab)), "adn_hz_from_jo_ab": mean_rate(jo_ab_run, adn),
            "jo_f_inputs": int(len(jo_f)), "adn_hz_from_jo_f": mean_rate(jo_f_run, adn),
            "active_neurons_seed0": int((groom_trials[0].spike_counts > 0).sum()),
        },
    }
    print("grooming:", json.dumps(grooming["reported"]), flush=True)

    # Bitter taste stops feeding.
    both = np.concatenate([sugar, bitter])
    sugar_mn9 = [mean_rate(run(brain, sugar, s), mn9) for s in (0, 1, 2)]
    both_mn9 = [mean_rate(run(brain, both, s), mn9) for s in (0, 1, 2)]
    bitter_runs = [run(brain, bitter, s) for s in (0, 1, 2)]
    bitter_mn9 = [mean_rate(r, mn9) for r in bitter_runs]
    suppression = lambda alone, mixed: 1.0 - mixed / alone if alone > 0 else 0.0
    intact_s = suppression(sugar_mn9[0], both_mn9[0])
    print("MN9 sugar:", sugar_mn9, "sugar+bitter:", both_mn9, "bitter:", bitter_mn9, flush=True)
    control_s, control_rates = [], []
    for k in range(20):
        control = rewired_outputs(brain, bitter, 2000 + k)
        alone, mixed = mean_rate(run(control, sugar, 0), mn9), mean_rate(run(control, both, 0), mn9)
        control_rates.append([alone, mixed])
        control_s.append(suppression(alone, mixed))
        print(f"control {k}: MN9 sugar {alone:.1f}, sugar+bitter {mixed:.1f}, S {control_s[-1]:+.2f}", flush=True)
    bitter_beaten = sum(intact_s > x for x in control_s)
    dn_rates = bitter_runs[0].rate_hz(dns)
    silent_dn = silent.rate_hz(dns)
    screen = [{"type": str(cell_type[i]), "side": str(data["side"][i]), "body_id": int(data["body_ids"][i]),
               "rate_hz": float(r)} for i, r, z in zip(dns, dn_rates, silent_dn) if r >= 10 and z == 0]
    screen.sort(key=lambda x: -x["rate_hz"])
    bitter_result = {
        "inputs": int(len(bitter)), "sugar_inputs": int(len(sugar)),
        "mn9_sugar_hz": sugar_mn9, "mn9_sugar_bitter_hz": both_mn9, "mn9_bitter_hz": bitter_mn9,
        "suppression_seed0": intact_s, "control_mn9_hz_sugar_and_mixed": control_rates,
        "control_suppression": control_s, "controls_beaten": int(bitter_beaten),
        "pass": (float(np.mean(both_mn9)) <= 0.5 * float(np.mean(sugar_mn9)) and max(bitter_mn9) == 0
                 and bitter_beaten >= 19),
        "reported_dn_screen_bitter_alone": screen,
        "active_neurons_bitter_seed0": int((bitter_runs[0].spike_counts > 0).sum()),
    }
    results = {"grooming": grooming, "bitter": bitter_result, "runtime_s": round(time.time() - started)}
    EVIDENCE.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"grooming": grooming["pass"], "bitter": bitter_result["pass"],
                      "dn_screen": [(x["type"], x["side"], round(x["rate_hz"])) for x in screen[:20]]}))


if __name__ == "__main__":
    main()

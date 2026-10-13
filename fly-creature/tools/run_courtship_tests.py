"""Pre-declared whole-brain courtship-song test (whole_brain_protocol.md addendum, 2026-10-13).

Foreleg ppk23 taste neurons -> pIP10 song command neurons, against 20 shuffled
brains. Writes docs/evidence/whole_brain_courtship_v1.json. Uses the cache from
build_whole_brain.py and reads receptor/nerve annotations from the release.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pyarrow.dataset as ds
import pyarrow.feather as feather

CREATURE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREATURE_DIR / "src"))
sys.path.insert(0, str(CREATURE_DIR / "tools"))
from fly_creature.brain_model import BrainParams, Connectome, simulate  # noqa: E402
from run_sugar_brain_test import load, shuffled  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_courtship_v1.json"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
WEIGHTS = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"


def receptor_cells(annotations, body_ids: np.ndarray, receptor: str, nerves: tuple[str, ...]) -> np.ndarray:
    keep = ((annotations["receptorType"] == receptor) & annotations["entryNerve"].isin(nerves)
            & (annotations["status"] == "Traced"))
    return np.flatnonzero(np.isin(body_ids, annotations.loc[keep, "bodyId"].to_numpy()))


def with_excitatory_outputs(data: dict, release: Path, sources: np.ndarray) -> Connectome:
    """Assumption change for a reported-only run: `sources` act as excitatory with
    their recorded synapse counts. Other connections are the cache's as-is."""
    body_ids = data["body_ids"]
    table = ds.dataset(release / WEIGHTS, format="feather").to_table(
        columns=["body_pre", "body_post", "weight"],
        filter=ds.field("body_pre").isin(body_ids[sources].tolist()))
    pre = np.searchsorted(body_ids, table.column("body_pre").to_numpy())
    post_ids = table.column("body_post").to_numpy()
    post = np.searchsorted(body_ids, post_ids)
    ok = (post < len(body_ids)) & (body_ids[np.minimum(post, len(body_ids) - 1)] == post_ids)
    others = ~np.isin(data["pre"], sources)
    return Connectome.from_edges(
        len(body_ids),
        np.concatenate([data["pre"][others], pre[ok]]),
        np.concatenate([data["post"][others], post[ok]]),
        np.concatenate([data["signed_synapses"][others], table.column("weight").to_numpy()[ok]]),
        BrainParams().w_syn_mv)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    args = parser.parse_args()
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    annotations = feather.read_table(
        args.release / ANNOTATIONS,
        columns=["bodyId", "receptorType", "entryNerve", "status"]).to_pandas()
    body_ids = data["body_ids"]
    traced = data["status"] == "Traced"
    cell_type = data["cell_type"]
    named = lambda *t: np.flatnonzero(traced & np.isin(cell_type, t))
    prefixed = lambda *p: np.flatnonzero(traced & np.any([np.char.startswith(cell_type, x) for x in p], axis=0))

    ppk23 = receptor_cells(annotations, body_ids, "putative_ppk23", ("ProLN",))
    ppk23_other_legs = receptor_cells(annotations, body_ids, "putative_ppk23", ("MesoLN", "MetaLN"))
    ir52b = receptor_cells(annotations, body_ids, "putative_IR52b", ("ProLN",))
    ppk25 = receptor_cells(annotations, body_ids, "putative_ppk25", ("ProLN",))
    pip10 = named("pIP10")
    lc10a = np.flatnonzero(traced & (cell_type == "LC10a"))
    song = {"vPR6": named("vPR6"), "TN1": prefixed("TN1"), "dPR1": named("dPR1"),
            "DNp13": named("DNp13"), "pMP2": named("pMP2"), "MDN": named("MDN")}
    dns = prefixed("DN")
    print(f"ppk23 foreleg {len(ppk23)}  pIP10 {len(pip10)}  LC10a {len(lc10a)}  "
          f"ppk23 mid/hind {len(ppk23_other_legs)}  IR52b {len(ir52b)}  ppk25 {len(ppk25)}", flush=True)

    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    mean_rate = lambda result, cells: float(result.rate_hz(cells).mean())
    started = time.time()

    trials = [run(brain, ppk23, s) for s in (0, 1, 2)]
    rates = [mean_rate(r, pip10) for r in trials]
    silent = run(brain, [], 0)
    print("pIP10 rates:", rates, "no input:", mean_rate(silent, pip10), flush=True)
    shuffles = []
    for k in range(20):
        shuffles.append(mean_rate(run(shuffled(brain, data, 1000 + k), ppk23, 0), pip10))
        print(f"shuffle {k}: pIP10 {shuffles[-1]:.1f} Hz", flush=True)
    beaten = sum(rates[0] > x for x in shuffles)

    with_sight = run(brain, np.concatenate([ppk23, lc10a]), 0)
    sight_only = run(brain, lc10a, 0)
    ppk25_excitatory = run(with_excitatory_outputs(data, args.release, ppk25), ppk25, 0)
    dn_rates, silent_dn = trials[0].rate_hz(dns), silent.rate_hz(dns)
    screen = [{"type": str(cell_type[i]), "side": str(data["side"][i]), "body_id": int(body_ids[i]),
               "rate_hz": float(r)} for i, r, z in zip(dns, dn_rates, silent_dn) if r >= 10 and z == 0]
    screen.sort(key=lambda x: -x["rate_hz"])
    result = {
        "inputs": int(len(ppk23)), "pip10_body_ids": body_ids[pip10].tolist(),
        "pip10_rate_hz": rates, "no_input_hz": mean_rate(silent, pip10),
        "shuffle_pip10_hz": shuffles, "shuffles_beaten": int(beaten),
        "pass": float(np.mean(rates)) >= 10 and mean_rate(silent, pip10) == 0 and beaten >= 19,
        "reported": {
            "pip10_each_hz": trials[0].rate_hz(pip10).tolist(),
            "song_circuit_hz": {k: mean_rate(trials[0], v) for k, v in song.items()},
            "pip10_with_lc10a_hz": mean_rate(with_sight, pip10),
            "pip10_lc10a_only_hz": mean_rate(sight_only, pip10),
            "pip10_from_ppk23_mid_hind_legs_hz": mean_rate(run(brain, ppk23_other_legs, 0), pip10),
            "pip10_from_foreleg_ir52b_hz": mean_rate(run(brain, ir52b, 0), pip10),
            "pip10_from_foreleg_ppk25_assumed_excitatory_hz": mean_rate(ppk25_excitatory, pip10),
            "input_counts": {"ppk23_mid_hind": int(len(ppk23_other_legs)), "ir52b": int(len(ir52b)),
                             "ppk25": int(len(ppk25)), "lc10a": int(len(lc10a))},
            "active_neurons_seed0": int((trials[0].spike_counts > 0).sum()),
            "dn_screen": screen,
        },
        "runtime_s": round(time.time() - started),
    }
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    shown = {k: v for k, v in result["reported"].items() if k != "dn_screen"}
    print(json.dumps({"pass": result["pass"], **shown,
                      "dn_screen": [(x["type"], x["side"], round(x["rate_hz"])) for x in screen[:20]]}))


if __name__ == "__main__":
    main()

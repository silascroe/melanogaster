"""Pre-declared whole-brain test: foreleg touch -> MDN (whole_brain_protocol.md addendum, 2026-10-13).

Writes docs/evidence/whole_brain_mdn_backup_v1.json. Uses the cache from
build_whole_brain.py and reads entry-nerve annotations from the release.
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
from fly_creature.brain_model import simulate  # noqa: E402
from run_sugar_brain_test import load, shuffled  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "whole_brain_mdn_backup_v1.json"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    args = parser.parse_args()
    data, brain = load(CREATURE_DIR / "outputs" / "whole_brain" / "brain_v1.npz")
    body_ids = data["body_ids"]
    traced = data["status"] == "Traced"
    cell_type = data["cell_type"]
    ann = feather.read_table(args.release / ANNOTATIONS,
                             columns=["bodyId", "superclass", "subclass", "entryNerve", "rootSide",
                                      "status"]).to_pandas().fillna("")
    ann = ann[ann.status == "Traced"]

    def cells(mask) -> np.ndarray:
        return np.flatnonzero(np.isin(body_ids, ann.loc[mask, "bodyId"].to_numpy()))

    bristle = ann.subclass == "mechanosensory bristle"
    foreleg = cells(bristle & (ann.entryNerve == "ProLN"))
    foreleg_left = cells(bristle & (ann.entryNerve == "ProLN") & (ann.rootSide == "L"))
    foreleg_right = cells(bristle & (ann.entryNerve == "ProLN") & (ann.rootSide == "R"))
    hindleg = cells(bristle & (ann.entryNerve == "MetaLN"))
    crown = cells(ann.superclass.isin(["cb_sensory", "sensory_descending"]) & (ann.entryNerve == "ON"))
    mdn = np.flatnonzero(traced & (cell_type == "MDN"))
    dns = np.flatnonzero(traced & np.char.startswith(cell_type, "DN"))
    print(f"foreleg {len(foreleg)} (L {len(foreleg_left)} R {len(foreleg_right)})  hindleg {len(hindleg)}  "
          f"crown {len(crown)}  MDN {len(mdn)}", flush=True)
    run = lambda conn, targets, seed: simulate(conn, duration_ms=1000.0, poisson_targets=targets,
                                               poisson_rate_hz=150.0, seed=seed)
    mean_rate = lambda result, idx: float(result.rate_hz(idx).mean())
    started = time.time()

    foreleg_runs = [run(brain, foreleg, s) for s in (6, 7, 8)]
    foreleg_hz = [mean_rate(r, mdn) for r in foreleg_runs]
    silent_hz = mean_rate(run(brain, [], 6), mdn)
    hindleg_hz = mean_rate(run(brain, hindleg, 6), mdn)
    print("MDN foreleg:", foreleg_hz, "silent:", silent_hz, "hindleg:", hindleg_hz, flush=True)
    shuffles = []
    for k in range(20):
        shuffles.append(mean_rate(run(shuffled(brain, data, 1040 + k), foreleg, 6), mdn))
        print(f"shuffle {k}: MDN {shuffles[-1]:.1f} Hz", flush=True)
    beaten = sum(foreleg_hz[0] > x for x in shuffles)
    checks = {
        "foreleg_mean_ge_10hz": float(np.mean(foreleg_hz)) >= 10,
        "silent_without_input": silent_hz == 0,
        "beats_19_of_20_shuffles": beaten >= 19,
        "hindleg_below_half_foreleg": hindleg_hz < 0.5 * foreleg_hz[0],
    }
    first = foreleg_runs[0]
    dn_rates = first.rate_hz(dns)
    busy = np.argsort(-dn_rates)
    result = {
        "mdn_body_ids": body_ids[mdn].tolist(), "mdn_sides": data["side"][mdn].tolist(),
        "foreleg_cells": int(len(foreleg)), "hindleg_cells": int(len(hindleg)),
        "mdn_foreleg_hz": foreleg_hz, "no_input_hz": silent_hz, "hindleg_hz": hindleg_hz,
        "shuffle_mdn_hz": shuffles, "shuffles_beaten": int(beaten),
        "checks": checks, "pass": all(checks.values()),
        "reported": {
            "mdn_each_hz_seed6": first.rate_hz(mdn).tolist(),
            "left_foreleg_mdn_each_hz": run(brain, foreleg_left, 6).rate_hz(mdn).tolist(),
            "right_foreleg_mdn_each_hz": run(brain, foreleg_right, 6).rate_hz(mdn).tolist(),
            "head_crown_mdn_hz": mean_rate(run(brain, crown, 6), mdn),
            "descending_ge_10hz": [{"type": str(cell_type[dns[i]]), "side": str(data["side"][dns[i]]),
                                    "hz": float(dn_rates[i])} for i in busy if dn_rates[i] >= 10],
            "active_neurons": int((first.spike_counts > 0).sum()),
        },
        "runtime_s": round(time.time() - started),
    }
    EVIDENCE.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("shuffle_mdn_hz", "reported")}))
    print("reported:", json.dumps({k: v for k, v in result["reported"].items() if k != "descending_ge_10hz"}))
    print("DNs >= 10 Hz:", [(d["type"], d["side"], d["hz"]) for d in result["reported"]["descending_ge_10hz"]])


if __name__ == "__main__":
    main()

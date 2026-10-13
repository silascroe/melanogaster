"""Exploratory screen: which single input group drives MDN? (whole_brain_protocol.md addendum, 2026-10-13).

No pass/fail; nominates at most one candidate for a separate pre-declared test.
Writes docs/evidence/mdn_input_screen_v1.json. Uses the cache from build_whole_brain.py
and reads superclass/subclass/entry-nerve annotations from the release.
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
from run_sugar_brain_test import load  # noqa: E402

EVIDENCE = CREATURE_DIR / "docs" / "evidence" / "mdn_input_screen_v1.json"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
SENSORY = ("vnc_sensory", "cb_sensory", "sensory_ascending", "sensory_descending")


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
                             columns=["bodyId", "superclass", "subclass", "entryNerve", "status"]).to_pandas()
    ann = ann[(ann.status == "Traced") & ann.superclass.isin(SENSORY)].fillna("")

    groups: dict[str, np.ndarray] = {}
    for (subclass, nerve), rows in ann.groupby(["subclass", "entryNerve"]):
        idx = np.flatnonzero(np.isin(body_ids, rows.bodyId.to_numpy()))
        if len(idx) >= 20:
            groups[f"sensory: {subclass or '(none)'} via {nerve or '(none)'}"] = idx
    for t in np.unique(cell_type[traced]):
        if str(t).startswith(("LC", "LPLC", "LLPC")):
            idx = np.flatnonzero(traced & (cell_type == t))
            if len(idx) >= 10:
                groups[f"visual: {t}"] = idx
    mdn = np.flatnonzero(traced & (cell_type == "MDN"))
    print(f"{len(groups)} groups; MDN {len(mdn)}", flush=True)

    started = time.time()
    rows = []
    for name, idx in groups.items():
        result = simulate(brain, duration_ms=1000.0, poisson_targets=idx, poisson_rate_hz=150.0, seed=0)
        rate = result.rate_hz(mdn)
        rows.append({"group": name, "cells": int(len(idx)), "mdn_mean_hz": float(rate.mean()),
                     "mdn_each_hz": rate.tolist(),
                     "active_neurons": int((result.spike_counts > 0).sum())})
        print(f"{rows[-1]['mdn_mean_hz']:6.1f} Hz  {name} ({len(idx)})", flush=True)
    silent = simulate(brain, duration_ms=1000.0, poisson_targets=[], seed=0).rate_hz(mdn)
    rows.sort(key=lambda r: -r["mdn_mean_hz"])
    result = {"mdn_body_ids": body_ids[mdn].tolist(), "mdn_sides": data["side"][mdn].tolist(),
              "no_input_mdn_hz": float(silent.mean()), "groups": rows,
              "runtime_s": round(time.time() - started)}
    EVIDENCE.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print("top 12:")
    for r in rows[:12]:
        print(f"  {r['mdn_mean_hz']:6.1f} Hz  {r['group']} ({r['cells']})  each {r['mdn_each_hz']}")


if __name__ == "__main__":
    main()

"""Export the obstacle brain copy (subset v4) for the browser, plus an exactness check.

Writes site/data/obstacle_brain_v4.json and .bin (connections, display positions)
and tests/web/obstacle_v4_vector.json: a recorded Poisson input schedule with the
spike counts the Python engine produced, so the JavaScript engine can be checked
spike for spike (tests/web/check_web_brain.mjs).

Display positions are soma locations from the release, projected onto the
left-right and brain-to-nerve-cord axes. Foreleg sensory neurons have their cell
bodies in the legs, outside the scanned volume; they are drawn near the
prothoracic leg nerve, and that position is approximate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pyarrow.feather as feather

CREATURE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREATURE_DIR / "src"))
from fly_creature.brain_model import BrainParams, BrainRunner  # noqa: E402
from fly_creature.brain_session import READOUT_GROUPS, load_package  # noqa: E402

SITE_DATA = CREATURE_DIR / "site" / "data"
VECTOR = CREATURE_DIR / "tests" / "web" / "obstacle_v4_vector.json"
ANNOTATIONS = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
INPUT_HZ = 150.0


def positions(body_ids: np.ndarray, release: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    ann = feather.read_table(release / ANNOTATIONS, columns=[
        "bodyId", "somaLocation", "exitNerve", "superclass", "rootSide"]).to_pandas()
    ann = ann.set_index("bodyId").reindex(body_ids)
    xyz = np.full((len(body_ids), 3), np.nan)
    has = ann.somaLocation.notna().to_numpy()
    xyz[has] = np.stack(ann.somaLocation[has].to_numpy())
    approx = ~has
    # Approximate: around the mean soma of motor neurons leaving through ProLN, by
    # side (motor somaSide; sensory rootSide).
    motor = feather.read_table(release / ANNOTATIONS, columns=[
        "somaLocation", "exitNerve", "somaSide"]).to_pandas()
    motor = motor[(motor.exitNerve == "ProLN") & motor.somaLocation.notna()]
    rng = np.random.default_rng(0)
    for side in ("L", "R", None):
        rows = motor if side is None else motor[motor.somaSide == side]
        centre = np.stack(rows.somaLocation.to_numpy()).mean(0)
        pick = approx & ((ann.rootSide == side).to_numpy() if side else np.isnan(xyz[:, 0]))
        xyz[pick] = centre + rng.normal(0, 2500, (int(pick.sum()), 3))
    classes = sorted(set(ann.superclass.fillna("unknown")))
    superclass = np.array([classes.index(c) for c in ann.superclass.fillna("unknown")], dtype=np.uint8)
    # Screen space: x = left-right, y = brain (top) to nerve cord (bottom), 0..1.
    x, y = xyz[:, 0], xyz[:, 2]
    span = max(np.ptp(x), np.ptp(y))
    screen = np.stack([(x - x.min()) / span, (y - y.min()) / span], axis=1).astype(np.float32)
    return screen, np.column_stack([approx.astype(np.uint8), superclass]), classes


def record_vector(package, condition: str, seed: int, press_ms: float, quiet_ms: float) -> dict:
    """Drive the one-core engine step by step with our own recorded Poisson hits."""
    p = BrainParams()
    runner = BrainRunner(package.connectome(condition), input_neurons=package.inputs, seed=0,
                         engine="numba")
    foreleg = package.groups["foreleg"]
    mdn = package.groups["mdn"]
    rng = np.random.default_rng(seed)
    prob = INPUT_HZ * p.dt_ms / 1000.0
    hit_steps, hit_cells, mdn_per_frame, fired_per_frame = [], [], [], []
    frame_steps = int(round(50.0 / p.dt_ms))
    total = int(round((press_ms + quiet_ms) / p.dt_ms))
    frame_start = runner.counts.copy()
    for step in range(total):
        hits = foreleg[rng.random(len(foreleg)) < prob] if step * p.dt_ms < press_ms \
            else np.empty(0, dtype=np.int64)
        hit_steps.extend([step] * len(hits))
        hit_cells.extend(hits.tolist())
        runner._step_numba(hits)
        runner.step_index += 1
        if (step + 1) % frame_steps == 0:
            delta = runner.counts - frame_start
            mdn_per_frame.append(int(delta[mdn].sum()))
            fired_per_frame.append(int(delta.sum()))
            frame_start = runner.counts.copy()
    return {"condition": condition, "seed": seed, "steps": total, "press_ms": press_ms,
            "hit_steps": hit_steps, "hit_cells": hit_cells,
            "mdn_spikes_per_50ms": mdn_per_frame, "spikes_per_50ms": fired_per_frame,
            "final_counts": runner.counts.tolist(),
            "final_v": runner.v.tolist()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", type=Path,
                        default=CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0")
    args = parser.parse_args()
    package = load_package("v4")
    p = BrainParams()
    conn = package.connectome("intact")
    signed = np.rint(conn.weight_mv.astype(np.float64) / p.w_syn_mv).astype(np.int16)
    assert np.array_equal((signed.astype(np.float64) * p.w_syn_mv).astype(np.float32), conn.weight_mv)
    assert package.n < 65536
    cut = np.concatenate([package.groups[k] for k in READOUT_GROUPS if k in package.groups])
    screen, flags, classes = positions(package.body_ids, args.release)

    parts = {"indptr": conn.indptr.astype(np.uint32), "post": conn.post.astype(np.uint16),
             "signed": signed, "xy": screen.ravel(), "flags": flags.astype(np.uint8).ravel()}
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    offsets, blob = {}, bytearray()
    for name, array in parts.items():
        while len(blob) % 8:
            blob.append(0)
        offsets[name] = {"offset": len(blob), "length": int(array.size), "dtype": str(array.dtype)}
        blob.extend(array.tobytes())
    (SITE_DATA / "obstacle_brain_v4.bin").write_bytes(bytes(blob))
    meta = {
        "source": "fly-creature subset v4 (obstacle copy), MaleCNS v1.0 wiring; see docs/whole_brain_result.md",
        "n": int(package.n), "connections": int(conn.post.size),
        "params": {"dt_ms": p.dt_ms, "v_0_mv": p.v_0_mv, "v_rst_mv": p.v_rst_mv, "v_th_mv": p.v_th_mv,
                   "t_mbr_ms": p.t_mbr_ms, "tau_ms": p.tau_ms, "t_rfc_ms": p.t_rfc_ms,
                   "t_dly_ms": p.t_dly_ms, "w_syn_mv": p.w_syn_mv, "f_poi": p.f_poi},
        "groups": {"foreleg": package.groups["foreleg"].tolist(), "mdn": package.groups["mdn"].tolist()},
        "inputs": package.inputs.tolist(),
        "cut_targets": cut.tolist(),
        "cell_type": [str(t) for t in package.cell_type],
        "superclasses": classes,
        "arrays": offsets,
    }
    (SITE_DATA / "obstacle_brain_v4.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")

    VECTOR.parent.mkdir(parents=True, exist_ok=True)
    vectors = [record_vector(package, "intact", 7, 600.0, 400.0),
               record_vector(package, "disconnected", 8, 600.0, 0.0)]
    VECTOR.write_text(json.dumps(vectors) + "\n", encoding="utf-8")
    for v in vectors:
        print(v["condition"], "MDN spikes per 50 ms:", v["mdn_spikes_per_50ms"])
    print(f"bin {len(blob) / 1e6:.2f} MB, vector {VECTOR.stat().st_size / 1e6:.2f} MB, "
          f"approximate positions {int(flags[:, 0].sum())}")


if __name__ == "__main__":
    main()

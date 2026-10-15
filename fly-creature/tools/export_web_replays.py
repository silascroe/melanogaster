"""Export recorded brain-copy replays and the 3D neuron map for the website.

The game's sense copies (subsets v1 and v3, 25,000-28,000 neurons each) are too
heavy to simulate live in a browser, so the site replays them instead. Each
replay is one run of one copy, from rest, under the same input the game sends
(150 Hz Poisson onto the sense's input neurons), recorded with the Python
engine. The intact copy and the copy with every connection onto the action
neurons cut ("disconnected", the game's C key) get the same seed, so they
receive identical input. Nothing here is new science; the multi-seed tests
behind each reaction are in docs/whole_brain_result.md.

Writes, under site/data/:
- map.json / map.bin: positions of all 28,584 packaged neurons
  (src/fly_creature/data/brain_map_v1.npz), their cell types, body IDs and
  whether the position is approximate, plus the named input/readout cells;
- replay_<name>.json / .bin: per 25 ms frame, a bit per map neuron (fired or
  not) for intact and cut, and the readout rates and action of each frame.

Run from fly-creature/: ../.venv/Scripts/python.exe tools/export_web_replays.py
"""

from __future__ import annotations

import base64
import gzip
import json
import math
from pathlib import Path
import sys

import numpy as np

CREATURE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CREATURE_DIR / "src"))
from fly_creature.brain_model import BrainRunner  # noqa: E402
from fly_creature.brain_session import (  # noqa: E402
    BACKUP_THRESHOLD_HZ, FEED_THRESHOLD_HZ, GROOM_THRESHOLD_HZ, MAX_INPUT_HZ, RESET_AFTER_MS,
    SENSE_PACKAGE, SING_THRESHOLD_HZ, SMOOTHING_S, TURN_GAIN_RAD_S_PER_HZ, BrainMap, load_map,
    load_package)
from fly_creature.steering import MAX_TURN_RATE_RAD_S  # noqa: E402

SITE_DATA = CREATURE_DIR / "site" / "data"
FRAME_MS = 25.0
REST_MS = 200.0
TAIL_MS = 300.0  # after the copy resets: dark, as in the game
SEED = 3

# name: (sense copy, input groups, stimulus ms, readout groups, plain-language title)
SCENARIOS = {
    "jump": ("loom", ("loom",), 300.0, ("gf",), "Something looms"),
    "feed": ("taste", ("sugar",), 1000.0, ("mn9",), "Sugar on the mouthparts"),
    "bitter": ("taste", ("sugar", "bitter"), 1000.0, ("mn9",), "Sugar laced with bitter"),
    "turn": ("target", ("lc10a_R",), 1000.0, ("dna02_R", "dna02_L", "pip10"),
             "A target to the right"),
    "groom": ("touch", ("jo_ce",), 1000.0, ("adn",), "Dust on the antennae"),
    "backup": ("obstacle", ("foreleg",), 1000.0, ("mdn",), "Forelegs against a wall"),
}


def record(package, condition: str, inputs: tuple[str, ...], stim_ms: float, readouts, index):
    runner = BrainRunner(package.connectome(condition), input_neurons=package.inputs, seed=SEED)
    total_ms = REST_MS + stim_ms + RESET_AFTER_MS + TAIL_MS
    frames = int(round(total_ms / FRAME_MS))
    n_map = load_map().n
    bits, rates, fired, spikes = [], {k: [] for k in readouts}, [], []
    running = True
    for f in range(frames):
        t = f * FRAME_MS
        on = REST_MS <= t < REST_MS + stim_ms
        if t >= REST_MS + stim_ms + RESET_AFTER_MS:
            running = False  # the game resets a copy after 500 ms without input
        if not running or t < REST_MS:
            counts = np.zeros(package.n, dtype=np.int64)
        else:
            drive = [(package.groups[g], MAX_INPUT_HZ) for g in inputs] if on else []
            counts = runner.advance(FRAME_MS, drive)
        mask = np.zeros(n_map, dtype=bool)
        mask[index[np.flatnonzero(counts)]] = True
        bits.append(np.packbits(mask, bitorder="little"))
        for k in readouts:
            rates[k].append(round(float(counts[package.groups[k]].mean()) / (FRAME_MS / 1000.0), 1))
        fired.append(int(np.count_nonzero(counts)))
        spikes.append(int(counts.sum()))
    return np.stack(bits), rates, fired, spikes


def actions(name: str, rates: dict[str, list[float]]) -> tuple[list[str], dict[str, list[float]]]:
    """The game's action rule for this reaction, frame by frame (engineered)."""
    alpha = 1.0 - math.exp(-(FRAME_MS / 1000.0) / SMOOTHING_S)
    smooth: dict[str, list[float]] = {}
    for k, series in rates.items():
        value, out = 0.0, []
        for r in series:
            value += alpha * (r - value)
            out.append(round(value, 2))
        smooth[k] = out
    frames = len(next(iter(rates.values())))
    act = []
    for f in range(frames):
        if name == "jump":
            act.append("jump" if rates["gf"][f] > 0 else "")
        elif name in ("feed", "bitter"):
            act.append("feed" if smooth["mn9"][f] >= FEED_THRESHOLD_HZ else "")
        elif name == "groom":
            act.append("groom" if smooth["adn"][f] >= GROOM_THRESHOLD_HZ else "")
        elif name == "backup":
            act.append("back up" if smooth["mdn"][f] >= BACKUP_THRESHOLD_HZ else "")
        elif name == "turn":
            asym = smooth["dna02_R"][f] - smooth["dna02_L"][f]
            turn = max(-MAX_TURN_RATE_RAD_S, min(MAX_TURN_RATE_RAD_S, asym * TURN_GAIN_RAD_S_PER_HZ))
            labels = []
            if abs(math.degrees(turn)) >= 10.0:
                labels.append("turn right" if turn > 0 else "turn left")
            if smooth["pip10"][f] >= SING_THRESHOLD_HZ:
                labels.append("sing")
            act.append(" + ".join(labels))
    if name == "turn":
        smooth["turn_deg_s"] = [round(math.degrees(max(-MAX_TURN_RATE_RAD_S, min(
            MAX_TURN_RATE_RAD_S, (r - l) * TURN_GAIN_RAD_S_PER_HZ))), 1)
            for r, l in zip(smooth["dna02_R"], smooth["dna02_L"])]
    return act, smooth


def export_map(brain_map: BrainMap) -> None:
    import pyarrow.feather as feather  # only needed to label cell types
    release = CREATURE_DIR.parent / "data" / "working" / "male-cns-v1.0"
    ann = feather.read_table(release / "body-annotations-male-cns-v1.0-minconf-0.5.feather",
                             columns=["bodyId", "type", "superclass"]).to_pandas()
    ann = ann.drop_duplicates("bodyId").set_index("bodyId").reindex(brain_map.body_ids)
    types = ann["type"].fillna("").astype(str).to_numpy()
    supers = ann["superclass"].fillna("").astype(str).to_numpy()
    type_names = sorted(set(types))
    super_names = sorted(set(supers))
    type_index = np.searchsorted(type_names, types).astype(np.uint16)
    super_index = np.searchsorted(super_names, supers).astype(np.uint8)
    xyz = np.clip(np.rint(brain_map.xyz * 32000), -32767, 32767).astype(np.int16)
    payload = brain_map.payload()
    parts = {"xyz": xyz.ravel(), "approximate": (brain_map.source == 2).astype(np.uint8),
             "type": type_index, "superclass": super_index,
             "body_id": brain_map.body_ids.astype(np.uint32)}
    assert np.array_equal(parts["body_id"].astype(np.int64), brain_map.body_ids)
    offsets, blob = {}, bytearray()
    for name, array in parts.items():
        while len(blob) % 8:
            blob.append(0)
        offsets[name] = {"offset": len(blob), "length": int(array.size), "dtype": str(array.dtype)}
        blob.extend(array.tobytes())
    (SITE_DATA / "map.bin").write_bytes(gzip.compress(bytes(blob), 9, mtime=0))
    meta = {"source": "fly-creature brain_map_v1.npz (tools/export_brain_map.py); "
                      "cell types and superclasses from MaleCNS v1.0 annotations",
            "n": brain_map.n, "xyz_scale": 1 / 32000, "left_x_sign": payload["left_x_sign"],
            "approximate_count": payload["approximate_count"],
            "types": type_names, "superclasses": super_names, "arrays": offsets,
            # Which map neurons belong to each packaged copy: little-endian bits, base64.
            "packages": {v: base64.b64encode(np.packbits(np.isin(
                np.arange(brain_map.n), brain_map.index_of(load_package(v))), bitorder="little")
            ).decode("ascii") for v in ("v1", "v3", "v4")},
            "compression": "gzip"}
    (SITE_DATA / "map.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    print(f"map: {brain_map.n} neurons, {(SITE_DATA / 'map.bin').stat().st_size / 1e3:.0f} kB gz")


def main() -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    brain_map = load_map()
    export_map(brain_map)
    for name, (sense, inputs, stim_ms, readouts, title) in SCENARIOS.items():
        package = load_package(SENSE_PACKAGE[sense])
        index = brain_map.index_of(package)
        out = {"name": name, "title": title, "sense": sense, "package": package.version,
               "package_neurons": int(package.n), "inputs": list(inputs),
               "input_hz": MAX_INPUT_HZ, "seed": SEED, "frame_ms": FRAME_MS,
               "rest_ms": REST_MS, "stimulus_ms": stim_ms, "reset_after_ms": RESET_AFTER_MS,
               "smoothing_s": SMOOTHING_S, "readouts": list(readouts),
               # Map positions of the driven and read cells, by package group.
               "cells": {"inputs": {g: index[package.groups[g]].tolist() for g in inputs},
                         "readouts": {g: index[package.groups[g]].tolist() for g in readouts}},
               "thresholds": {"feed_hz": FEED_THRESHOLD_HZ, "groom_hz": GROOM_THRESHOLD_HZ,
                              "sing_hz": SING_THRESHOLD_HZ, "backup_hz": BACKUP_THRESHOLD_HZ},
               "conditions": {}}
        blobs = []
        for condition in ("intact", "disconnected"):
            bits, rates, fired, spikes = record(package, condition, inputs, stim_ms, readouts, index)
            act, smooth = actions(name, rates)
            out["conditions"][condition] = {"rates_hz": rates, "smoothed_hz": smooth,
                                            "action": act, "neurons_fired": fired,
                                            "spikes": spikes}
            blobs.append(bits)
            print(f"{name:7s} {condition:12s} peak fired/frame {max(fired):6d}  "
                  f"actions {sorted(set(a for a in act if a))}", flush=True)
        stacked = np.stack(blobs)  # condition, frame, bytes
        out["frames"] = int(stacked.shape[1])
        out["bytes_per_frame"] = int(stacked.shape[2])
        out["compression"] = "gzip"
        (SITE_DATA / f"replay_{name}.bin").write_bytes(gzip.compress(stacked.tobytes(), 9, mtime=0))
        (SITE_DATA / f"replay_{name}.json").write_text(json.dumps(out) + "\n", encoding="utf-8")
        print(f"{name}: {(SITE_DATA / f'replay_{name}.bin').stat().st_size / 1e3:.0f} kB gz", flush=True)


if __name__ == "__main__":
    main()

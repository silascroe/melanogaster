"""Live whole-brain-subset session for the Godot creature.

Architecture (engineering, see docs/whole_brain_protocol.md): the published model
is validated for one stimulus starting from rest, and does not settle on its own
in continuous use. So each sense gets its own copy of the brain subset that
starts at rest and hears only that sense; each copy's action output is read only
for its own sense; a copy resets to rest after 500 ms without input, and a
resting copy without input is not simulated (it would stay exactly at rest).

Each copy loads a packaged subset that passed the whole-brain comparison for its
own sense (docs/whole_brain_result.md): the target copy uses subset v1, which
passed both turn checks; taste, loom and touch use subset v3, which adds the
bitter and antennal-grooming neurons but missed the right-turn check; the
obstacle copy uses subset v4, selected from foreleg-touch activity.
Everything that turns the world into Poisson input rates, and spikes into body
actions, is an engineered choice made here, not connectome data:

- loom: apparent size/expansion of an approaching object (same rule as the
  original jump circuit) -> LC4 and LPLC2 at up to 150 Hz;
- target: bearing within +/-65 degrees (same rule as pursuit) -> LC10a on the
  target's side at up to 150 Hz;
- taste: mouth within reach of a sugar drop -> LB3 (sugar/water) at 150 Hz,
  plus LB1 (bitter) at 150 Hz when the drop is laced with something bitter;
- touch: dust on the antennae -> JO-C and JO-E (Johnston's organ zones C/E) at
  150 Hz while any dust remains;
- obstacle: Godot reports the forelegs pressed against a solid obstacle ->
  foreleg mechanosensory bristles (both legs) at 150 Hz;
- jump: any giant-fiber (DNp01) spike outside a 1.2 s cooldown;
- turn: smoothed DNa02 right-minus-left firing rate x TURN_GAIN, capped;
- feed: smoothed MN9 firing rate above FEED_THRESHOLD_HZ;
- groom: smoothed aDN1/aDN2 (DNg62, DNge078) rate above GROOM_THRESHOLD_HZ;
- sing: smoothed pIP10 rate (target copy) above SING_THRESHOLD_HZ; the wing on
  the target's side is the one extended;
- back up: smoothed MDN rate (obstacle copy) at or above BACKUP_THRESHOLD_HZ.
"""

from __future__ import annotations

import base64
from importlib.resources import files
import math
from pathlib import Path
import time

import numpy as np

from .brain_model import BrainParams, BrainRunner, Connectome
from .steering import MAX_TURN_RATE_RAD_S, target_feature

MAX_INPUT_HZ = 150.0
# Whole-brain test: full one-sided LC10a input gave ~130 Hz DNa02 asymmetry,
# so that asymmetry maps to the creature's existing maximum turn rate.
TURN_GAIN_RAD_S_PER_HZ = MAX_TURN_RATE_RAD_S / 130.0
SMOOTHING_S = 0.15
FEED_THRESHOLD_HZ = 20.0
GROOM_THRESHOLD_HZ = 30.0
SING_THRESHOLD_HZ = 30.0
BACKUP_THRESHOLD_HZ = 8.0
MOUTH_REACH = 0.15
JUMP_COOLDOWN_MS = 1200.0
RESET_AFTER_MS = 500.0
SENSES = {"taste": ("sugar", "bitter"), "loom": ("loom",), "target": ("lc10a_R", "lc10a_L"),
          "touch": ("jo_ce",), "obstacle": ("foreleg",)}
# Which copy each display group is read from.
DISPLAY_SOURCE = {"LB3": "taste", "MN9": "taste", "LC4": "loom", "LPLC2": "loom", "DNp01": "loom",
                  "LC10a_L": "target", "LC10a_R": "target", "AOTU_L": "target", "AOTU_R": "target",
                  "DNa02_L": "target", "DNa02_R": "target", "LB1": "taste",
                  "JO-CE": "touch", "aDN": "touch", "pIP10": "target",
                  "Foreleg": "obstacle", "MDN": "obstacle"}
READOUT_GROUPS = ("gf", "dna02_R", "dna02_L", "mn9", "adn", "pip10", "mdn")
# Subset that passed the whole-brain comparison for each sense (engineering choice).
SENSE_PACKAGE = {"taste": "v3", "loom": "v3", "touch": "v3", "target": "v1", "obstacle": "v4"}
MAP_TEXTURE_WIDTH = 256  # neuron map image width (display only)


class BrainPackage:
    """One compact game brain, loaded once per server process."""

    def __init__(self, version: str = "v3", path: Path | None = None) -> None:
        if path is None:
            path = Path(str(files("fly_creature").joinpath(f"data/brain_subset_{version}.npz")))
        self.version = version
        with np.load(path) as data:
            self.body_ids = data["body_ids"]
            self.cell_type = data["cell_type"]
            self.side = data["side"]
            self.pre, self.post = data["pre"], data["post"]
            self.signed = data["signed_synapses"].astype(np.float64)
            self.groups = {k[len("group_"):]: data[k].astype(np.int64)
                           for k in data.files if k.startswith("group_")}
        self.n = len(self.body_ids)
        # The song command neurons were added as a readout after both subsets were
        # built; both contain them (docs/whole_brain_protocol.md, target song).
        self.groups.setdefault("pip10", np.flatnonzero(self.cell_type == "pIP10").astype(np.int64))
        # Older subsets lack the newer groups; only stimulate what is present.
        self.inputs = np.concatenate([self.groups[k] for k in
                                      ("sugar", "loom", "lc10a_R", "lc10a_L", "jo_ce", "bitter",
                                       "foreleg")
                                      if k in self.groups])
        # Display groups for the brain panel, by recorded cell type.
        by_type = lambda *types: np.flatnonzero(np.isin(self.cell_type, types))
        side = lambda idx, s: idx[self.side[idx] == s]
        aotu = by_type("AOTU019", "AOTU025")
        display_groups = {"DNp01": "gf", "LC10a_L": "lc10a_L", "LC10a_R": "lc10a_R",
                          "DNa02_L": "dna02_L", "DNa02_R": "dna02_R", "LB3": "sugar",
                          "MN9": "mn9", "LB1": "bitter", "JO-CE": "jo_ce", "aDN": "adn",
                          "pIP10": "pip10", "Foreleg": "foreleg", "MDN": "mdn"}
        self.display = {"LC4": by_type("LC4"), "LPLC2": by_type("LPLC2"),
                        "AOTU_L": side(aotu, "L"), "AOTU_R": side(aotu, "R")}
        self.display.update({k: self.groups[g] for k, g in display_groups.items() if g in self.groups})
        self._connectomes: dict[str, Connectome] = {}

    def connectome(self, condition: str) -> Connectome:
        if condition not in self._connectomes:
            keep = np.ones(len(self.post), dtype=bool)
            if condition == "disconnected":
                # Cut every connection onto the action neurons; sensing still runs.
                readouts = np.concatenate([self.groups[k] for k in READOUT_GROUPS if k in self.groups])
                keep = ~np.isin(self.post, readouts)
            self._connectomes[condition] = Connectome.from_edges(
                self.n, self.pre[keep], self.post[keep], self.signed[keep], BrainParams().w_syn_mv)
        return self._connectomes[condition]


_PACKAGES: dict[str, BrainPackage] = {}


def load_package(version: str = "v3") -> BrainPackage:
    if version not in _PACKAGES:
        _PACKAGES[version] = BrainPackage(version)
    return _PACKAGES[version]


class BrainMap:
    """Display positions for every packaged neuron (tools/export_brain_map.py).

    Positions are for drawing only: the cell body from the release where it was
    scanned, otherwise an approximate spot near the neuron's partners.
    """

    # Named cells on the map: (label, sense copy, kind, package groups).
    LABELS = (("sugar taste LB3", "taste", "input", ("sugar",)),
              ("bitter LB1", "taste", "input", ("bitter",)),
              ("MN9", "taste", "readout", ("mn9",)),
              ("LC4 + LPLC2", "loom", "input", ("loom",)),
              ("giant fibre", "loom", "readout", ("gf",)),
              ("LC10a", "target", "input", ("lc10a_L", "lc10a_R")),
              ("DNa02", "target", "readout", ("dna02_L", "dna02_R")),
              ("pIP10", "target", "readout", ("pip10",)),
              ("Johnston's organ", "touch", "input", ("jo_ce",)),
              ("aDN", "touch", "readout", ("adn",)),
              ("foreleg bristles", "obstacle", "input", ("foreleg",)),
              ("MDN", "obstacle", "readout", ("mdn",)))

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path(str(files("fly_creature").joinpath("data/brain_map_v1.npz")))
        with np.load(path) as data:
            self.body_ids = data["body_ids"]
            self.xyz = data["xyz"].astype(np.float32)
            self.source = data["source"]
        self.n = len(self.body_ids)
        if self.n >= 65536:
            raise ValueError("map indices are sent as 16-bit numbers")

    def index_of(self, package: BrainPackage) -> np.ndarray:
        """Map position of each neuron in a package."""
        index = np.searchsorted(self.body_ids, package.body_ids)
        if index.max() >= self.n or not np.array_equal(self.body_ids[index], package.body_ids):
            raise ValueError(f"brain map does not cover package {package.version}")
        return index

    def payload(self) -> dict:
        """Everything the game needs to draw the map, sent once per session."""
        labels = []
        for name, sense, kind, groups in self.LABELS:
            package = load_package(SENSE_PACKAGE[sense])
            local = np.concatenate([package.groups[g] for g in groups if g in package.groups])
            labels.append({"name": name, "sense": sense, "kind": kind,
                           "cells": _b64(self.index_of(package)[local], "<u2")})
        # Which way the fly's left points on the map's x axis (recorded side labels).
        v3 = load_package("v3")
        left = float(self.xyz[self.index_of(v3)[v3.side == "L"], 0].mean())
        return {"n": self.n, "senses": list(SENSES), "xyz": _b64(self.xyz, "<f4"),
                "left_x_sign": 1.0 if left > 0 else -1.0, "texture_width": MAP_TEXTURE_WIDTH,
                "approximate": _b64(self.source == 2, "u1"),
                "approximate_count": int((self.source == 2).sum()), "labels": labels}


_MAP: BrainMap | None = None


def load_map() -> BrainMap:
    global _MAP
    if _MAP is None:
        _MAP = BrainMap()
    return _MAP


def _b64(array: np.ndarray, dtype: str) -> str:
    return base64.b64encode(np.ascontiguousarray(array, dtype=dtype).tobytes()).decode("ascii")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class BrainSession:
    def __init__(self, condition: str = "intact", seed: int = 0) -> None:
        if condition not in ("intact", "disconnected"):
            raise ValueError("condition must be intact or disconnected")
        self.condition = condition
        self.packages = {sense: load_package(SENSE_PACKAGE[sense]) for sense in SENSES}
        self.connectomes = {sense: pkg.connectome(condition) for sense, pkg in self.packages.items()}
        self.next_seed = seed
        self.copies: dict[str, BrainRunner | None] = {sense: None for sense in SENSES}
        self.quiet_ms = {sense: 0.0 for sense in SENSES}
        self.last_angle_deg: float | None = None
        self.cooldown_ms = 0.0
        self.asym_hz = 0.0
        self.mn9_hz = 0.0
        self.adn_hz = 0.0
        self.pip10_hz = 0.0
        self.mdn_hz = 0.0
        self.map_index: dict[str, np.ndarray] | None = None

    def step(self, payload: dict) -> dict:
        fly, obj = payload["fly"], payload["object"]
        target = payload.get("target", {"active": False})
        sugar = payload.get("sugar", {"active": False})
        touch = payload.get("touch", {"active": False})
        obstacle = payload.get("obstacle", {"active": False})
        dt_ms = float(payload.get("dt_ms", 50.0))
        if not math.isfinite(dt_ms) or not 10.0 <= dt_ms <= 100.0:
            raise ValueError("dt_ms must be between 10 and 100")
        x, z, heading = float(fly["x"]), float(fly["z"]), float(fly["heading_rad"])

        # Loom encoder (engineered; same thresholds as the original jump circuit).
        dx, dz = float(obj["x"]) - x, float(obj["z"]) - z
        distance = max(0.001, math.hypot(dx, dz))
        forward_dot = (dx * math.sin(heading) - dz * math.cos(heading)) / distance
        in_view = bool(obj.get("active", True)) and forward_dot >= math.cos(math.radians(65.0))
        angle = math.degrees(2.0 * math.atan(float(obj["radius"]) / distance)) if in_view else 0.0
        expansion = (max(0.0, (angle - self.last_angle_deg) / (dt_ms / 1000.0))
                     if in_view and self.last_angle_deg is not None else 0.0)
        self.last_angle_deg = angle if in_view else None
        loom = max(_clamp01((expansion - 5.0) / 80.0),
                   _clamp01((angle - 8.0) / 25.0) if expansion > 3.0 else 0.0)

        # Target encoder (engineered; same bearing feature as pursuit).
        feature = target_feature(fly, target)
        right = feature["strength"] if feature["bearing_deg"] > 0 else 0.0
        left = feature["strength"] if feature["bearing_deg"] < 0 else 0.0

        # Taste encoder (engineered): the mouth is just ahead of the body centre.
        contact = False
        if sugar.get("active", False):
            mouth_x = x + math.sin(heading) * 0.35
            mouth_z = z - math.cos(heading) * 0.35
            reach = float(sugar.get("radius", 0.2)) + MOUTH_REACH
            contact = math.hypot(float(sugar["x"]) - mouth_x, float(sugar["z"]) - mouth_z) <= reach

        bitter = contact and bool(sugar.get("bitter", False))
        dusty = bool(touch.get("active", False))
        pressing = bool(obstacle.get("active", False))

        rates = {"loom": MAX_INPUT_HZ * loom, "lc10a_R": MAX_INPUT_HZ * right,
                 "lc10a_L": MAX_INPUT_HZ * left, "sugar": MAX_INPUT_HZ if contact else 0.0,
                 "bitter": MAX_INPUT_HZ if bitter else 0.0, "jo_ce": MAX_INPUT_HZ if dusty else 0.0,
                 "foreleg": MAX_INPUT_HZ if pressing else 0.0}
        started = time.perf_counter()
        counts = {sense: self._advance_copy(sense, dt_ms, rates) for sense in SENSES}
        compute_ms = (time.perf_counter() - started) * 1000.0
        window_s = dt_ms / 1000.0
        source = {"mn9": "taste", "gf": "loom", "dna02_R": "target", "dna02_L": "target",
                  "adn": "touch", "pip10": "target", "mdn": "obstacle"}

        def group_rate(key: str) -> float:
            sense = source[key]
            return float(counts[sense][self.packages[sense].groups[key]].mean()) / window_s

        alpha = 1.0 - math.exp(-window_s / SMOOTHING_S)
        self.asym_hz += alpha * (group_rate("dna02_R") - group_rate("dna02_L") - self.asym_hz)
        self.mn9_hz += alpha * (group_rate("mn9") - self.mn9_hz)
        self.adn_hz += alpha * (group_rate("adn") - self.adn_hz)
        self.pip10_hz += alpha * (group_rate("pip10") - self.pip10_hz)
        self.mdn_hz += alpha * (group_rate("mdn") - self.mdn_hz)
        turn = max(-MAX_TURN_RATE_RAD_S, min(MAX_TURN_RATE_RAD_S, self.asym_hz * TURN_GAIN_RAD_S_PER_HZ))
        gf_spikes = int(counts["loom"][self.packages["loom"].groups["gf"]].sum())
        self.cooldown_ms = max(0.0, self.cooldown_ms - dt_ms)
        jump = gf_spikes > 0 and self.cooldown_ms == 0.0
        if jump:
            self.cooldown_ms = JUMP_COOLDOWN_MS
        spikes = {k: int(counts[sense][self.packages[sense].display[k]].sum())
                  for k, sense in DISPLAY_SOURCE.items()}
        extra = {}
        if payload.get("neuron_map", False) or self.map_index is not None:
            sent = self._update_map(counts)
            if payload.get("neuron_map", False) and sent is not None:
                extra["neuron_map"] = sent
        return {
            "condition": self.condition, "model": "brain",
            "brain_neurons": self.packages["taste"].n,
            "brain_packages": {sense: pkg.version for sense, pkg in self.packages.items()},
            "active_neurons": int(sum(np.count_nonzero(c) for c in counts.values())),
            "brain_copies_running": [s for s, r in self.copies.items() if r is not None],
            "compute_ms": round(compute_ms, 1),
            "visual": {"in_view": in_view, "angle_deg": round(angle, 2),
                       "expansion_deg_s": round(expansion, 2)},
            "input_rate_hz": {k: round(v, 1) for k, v in rates.items()},
            "spikes": spikes,
            "jump": jump,
            "jump_rule": "DNp01 spike outside 1.2 s animation cooldown",
            "steering": {
                "bearing_deg": round(feature["bearing_deg"], 2),
                "in_view": feature["in_view"],
                "LC10a_spikes": {"L": spikes["LC10a_L"], "R": spikes["LC10a_R"]},
                "AOTU_spikes": {"AOTU": {"L": spikes["AOTU_L"], "R": spikes["AOTU_R"]}},
                "DNa02_spikes": {"L": spikes["DNa02_L"], "R": spikes["DNa02_R"]},
                "dna02_asymmetry_hz": round(self.asym_hz, 1),
                "turn_rate_rad_s": round(turn, 4),
                "readout": "engineered: smoothed DNa02 right-minus-left rate to turn rate",
            },
            "taste": {"contact": contact, "bitter": bitter},
            "feeding": self.mn9_hz >= FEED_THRESHOLD_HZ,
            "mn9_rate_hz": round(self.mn9_hz, 1),
            "touch": {"dust": dusty},
            "grooming": self.adn_hz >= GROOM_THRESHOLD_HZ,
            "adn_rate_hz": round(self.adn_hz, 1),
            "singing": self.pip10_hz >= SING_THRESHOLD_HZ,
            "song_side": "R" if feature["bearing_deg"] > 0 else "L",
            "pip10_rate_hz": round(self.pip10_hz, 1),
            "obstacle": {"forelegs_pressed": pressing},
            "backing": self.mdn_hz >= BACKUP_THRESHOLD_HZ,
            "mdn_rate_hz": round(self.mdn_hz, 1),
            **extra,
        }

    def _update_map(self, counts: dict[str, np.ndarray]) -> str | None:
        """Display only: steps since each map neuron last fired, and in which copy.

        Returned as a 256-wide two-byte-per-neuron image (age in steps, capped
        at 255 = not recently; sense index), base64, so the game can upload it
        as a texture without looping over neurons. None when nothing fired in
        the last 255 steps (the game's glow has long faded by then).
        """
        if self.map_index is None:
            brain_map = load_map()
            self.map_index = {s: brain_map.index_of(p) for s, p in self.packages.items()}
            padded = -(-brain_map.n // MAP_TEXTURE_WIDTH) * MAP_TEXTURE_WIDTH
            self.map_last = np.full(padded, -(1 << 20), dtype=np.int64)
            self.map_sense = np.zeros(padded, dtype=np.uint8)
            self.map_step = 0
        self.map_step += 1
        for sense, c in counts.items():
            if self.copies[sense] is None:
                continue
            fired = self.map_index[sense][np.flatnonzero(c)]
            self.map_last[fired] = self.map_step
            self.map_sense[fired] = list(SENSES).index(sense)
        age = np.minimum(self.map_step - self.map_last, 255).astype(np.uint8)
        if age.min() == 255:
            return None
        return _b64(np.stack([age, self.map_sense], axis=1), "u1")

    def _advance_copy(self, sense: str, dt_ms: float, rates: dict[str, float]) -> np.ndarray:
        """Advance one sense's brain copy; start it on input, reset it after quiet."""
        package = self.packages[sense]
        inputs = [(package.groups[key], rates[key]) for key in SENSES[sense] if rates[key] > 0]
        runner = self.copies[sense]
        if inputs:
            self.quiet_ms[sense] = 0.0
            if runner is None:
                runner = self.copies[sense] = BrainRunner(
                    self.connectomes[sense], input_neurons=package.inputs, seed=self.next_seed)
                self.next_seed += 1
        elif runner is not None:
            self.quiet_ms[sense] += dt_ms
            if self.quiet_ms[sense] >= RESET_AFTER_MS:
                self.copies[sense] = runner = None
        if runner is None:
            return np.zeros(package.n, dtype=np.int64)
        return runner.advance(dt_ms, inputs)

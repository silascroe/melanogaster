"""Live whole-brain-subset session for the Godot creature.

Architecture (engineering, see docs/whole_brain_protocol.md): the published model
is validated for one stimulus starting from rest, and does not settle on its own
in continuous use. So each sense gets its own copy of the brain subset that
starts at rest and hears only that sense; each copy's action output is read only
for its own sense; a copy resets to rest after 500 ms without input, and a
resting copy without input is not simulated (it would stay exactly at rest).

The packaged brain (data/brain_subset_v1.npz) was selected from whole-brain
activity and checked against the whole brain (docs/whole_brain_result.md).
Everything that turns the world into Poisson input rates, and spikes into body
actions, is an engineered choice made here, not connectome data:

- loom: apparent size/expansion of an approaching object (same rule as the
  original jump circuit) -> LC4 and LPLC2 at up to 150 Hz;
- target: bearing within +/-65 degrees (same rule as pursuit) -> LC10a on the
  target's side at up to 150 Hz;
- taste: mouth within reach of a sugar drop -> LB3 (sugar/water) at 150 Hz;
- jump: any giant-fiber (DNp01) spike outside a 1.2 s cooldown;
- turn: smoothed DNa02 right-minus-left firing rate x TURN_GAIN, capped;
- feed: smoothed MN9 firing rate above FEED_THRESHOLD_HZ.
"""

from __future__ import annotations

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
MOUTH_REACH = 0.15
JUMP_COOLDOWN_MS = 1200.0
RESET_AFTER_MS = 500.0
SENSES = {"taste": ("sugar",), "loom": ("loom",), "target": ("lc10a_R", "lc10a_L")}
# Which copy each display group is read from.
DISPLAY_SOURCE = {"LB3": "taste", "MN9": "taste", "LC4": "loom", "LPLC2": "loom", "DNp01": "loom",
                  "LC10a_L": "target", "LC10a_R": "target", "AOTU_L": "target", "AOTU_R": "target",
                  "DNa02_L": "target", "DNa02_R": "target"}
READOUT_GROUPS = ("gf", "dna02_R", "dna02_L", "mn9")


class BrainPackage:
    """The compact game brain, loaded once per server process."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = Path(str(files("fly_creature").joinpath("data/brain_subset_v1.npz")))
        with np.load(path) as data:
            self.body_ids = data["body_ids"]
            self.cell_type = data["cell_type"]
            self.side = data["side"]
            self.pre, self.post = data["pre"], data["post"]
            self.signed = data["signed_synapses"].astype(np.float64)
            self.groups = {k[len("group_"):]: data[k].astype(np.int64)
                           for k in data.files if k.startswith("group_")}
        self.n = len(self.body_ids)
        self.inputs = np.concatenate([self.groups[k] for k in ("sugar", "loom", "lc10a_R", "lc10a_L")])
        # Display groups for the brain panel, by recorded cell type.
        by_type = lambda *types: np.flatnonzero(np.isin(self.cell_type, types))
        side = lambda idx, s: idx[self.side[idx] == s]
        aotu = by_type("AOTU019", "AOTU025")
        self.display = {
            "LC4": by_type("LC4"), "LPLC2": by_type("LPLC2"), "DNp01": self.groups["gf"],
            "LC10a_L": self.groups["lc10a_L"], "LC10a_R": self.groups["lc10a_R"],
            "AOTU_L": side(aotu, "L"), "AOTU_R": side(aotu, "R"),
            "DNa02_L": self.groups["dna02_L"], "DNa02_R": self.groups["dna02_R"],
            "LB3": self.groups["sugar"], "MN9": self.groups["mn9"],
        }
        self._connectomes: dict[str, Connectome] = {}

    def connectome(self, condition: str) -> Connectome:
        if condition not in self._connectomes:
            keep = np.ones(len(self.post), dtype=bool)
            if condition == "disconnected":
                # Cut every connection onto the action neurons; sensing still runs.
                readouts = np.concatenate([self.groups[k] for k in READOUT_GROUPS])
                keep = ~np.isin(self.post, readouts)
            self._connectomes[condition] = Connectome.from_edges(
                self.n, self.pre[keep], self.post[keep], self.signed[keep], BrainParams().w_syn_mv)
        return self._connectomes[condition]


_PACKAGE: BrainPackage | None = None


def load_package() -> BrainPackage:
    global _PACKAGE
    if _PACKAGE is None:
        _PACKAGE = BrainPackage()
    return _PACKAGE


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class BrainSession:
    def __init__(self, condition: str = "intact", seed: int = 0) -> None:
        if condition not in ("intact", "disconnected"):
            raise ValueError("condition must be intact or disconnected")
        self.condition = condition
        self.package = load_package()
        self.connectome = self.package.connectome(condition)
        self.next_seed = seed
        self.copies: dict[str, BrainRunner | None] = {sense: None for sense in SENSES}
        self.quiet_ms = {sense: 0.0 for sense in SENSES}
        self.last_angle_deg: float | None = None
        self.cooldown_ms = 0.0
        self.asym_hz = 0.0
        self.mn9_hz = 0.0

    def step(self, payload: dict) -> dict:
        fly, obj = payload["fly"], payload["object"]
        target = payload.get("target", {"active": False})
        sugar = payload.get("sugar", {"active": False})
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

        g = self.package.groups
        rates = {"loom": MAX_INPUT_HZ * loom, "lc10a_R": MAX_INPUT_HZ * right,
                 "lc10a_L": MAX_INPUT_HZ * left, "sugar": MAX_INPUT_HZ if contact else 0.0}
        started = time.perf_counter()
        counts = {sense: self._advance_copy(sense, dt_ms, rates) for sense in SENSES}
        compute_ms = (time.perf_counter() - started) * 1000.0
        window_s = dt_ms / 1000.0
        source = {"mn9": "taste", "gf": "loom", "dna02_R": "target", "dna02_L": "target"}

        def group_rate(key: str) -> float:
            return float(counts[source[key]][g[key]].mean()) / window_s

        alpha = 1.0 - math.exp(-window_s / SMOOTHING_S)
        self.asym_hz += alpha * (group_rate("dna02_R") - group_rate("dna02_L") - self.asym_hz)
        self.mn9_hz += alpha * (group_rate("mn9") - self.mn9_hz)
        turn = max(-MAX_TURN_RATE_RAD_S, min(MAX_TURN_RATE_RAD_S, self.asym_hz * TURN_GAIN_RAD_S_PER_HZ))
        gf_spikes = int(counts["loom"][g["gf"]].sum())
        self.cooldown_ms = max(0.0, self.cooldown_ms - dt_ms)
        jump = gf_spikes > 0 and self.cooldown_ms == 0.0
        if jump:
            self.cooldown_ms = JUMP_COOLDOWN_MS
        spikes = {k: int(counts[DISPLAY_SOURCE[k]][idx].sum()) for k, idx in self.package.display.items()}
        return {
            "condition": self.condition, "model": "brain",
            "brain_neurons": self.package.n,
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
            "taste": {"contact": contact},
            "feeding": self.mn9_hz >= FEED_THRESHOLD_HZ,
            "mn9_rate_hz": round(self.mn9_hz, 1),
        }

    def _advance_copy(self, sense: str, dt_ms: float, rates: dict[str, float]) -> np.ndarray:
        """Advance one sense's brain copy; start it on input, reset it after quiet."""
        g = self.package.groups
        inputs = [(g[key], rates[key]) for key in SENSES[sense] if rates[key] > 0]
        runner = self.copies[sense]
        if inputs:
            self.quiet_ms[sense] = 0.0
            if runner is None:
                runner = self.copies[sense] = BrainRunner(
                    self.connectome, input_neurons=self.package.inputs, seed=self.next_seed)
                self.next_seed += 1
        elif runner is not None:
            self.quiet_ms[sense] += dt_ms
            if self.quiet_ms[sense] >= RESET_AFTER_MS:
                self.copies[sense] = runner = None
        if runner is None:
            return np.zeros(self.package.n, dtype=np.int64)
        return runner.advance(dt_ms, inputs)

"""Offline MaleCNS v1.0 pursuit-path projection, with explicit assumptions.

This is a fixed-fly diagnostic, not the published pursuit model or a motor
controller. The packaged LC10a centers are anatomical hypotheses; each
connection count enters exactly once at its own stage. No author response
table is used or distributed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ActivityProjection:
    body_ids: np.ndarray
    sides: np.ndarray
    centers_deg: np.ndarray
    aotu_ids: tuple[int, ...]
    aotu_types: tuple[str, ...]
    aotu_sides: tuple[str, ...]
    lc_to_aotu: np.ndarray
    aotu_to_dn: np.ndarray

    @classmethod
    def from_packaged_data(cls, circuit_path: Path | None = None,
                           map_path: Path | None = None) -> "ActivityProjection":
        data = files("fly_creature").joinpath("data")
        circuit = json.loads((circuit_path or Path(str(data.joinpath(
            "visual_steering_v1.json")))).read_text(encoding="utf-8"))
        visual_map = json.loads((map_path or Path(str(data.joinpath(
            "lc10a_registered_eyemap_hypothesis_v3.json")))).read_text(encoding="utf-8"))
        neurons = {int(n["body_id"]): n for n in circuit["neurons"]}
        cells = sorted(visual_map["cells"], key=lambda row: int(row["body_id"]))
        body_ids = np.array([int(row["body_id"]) for row in cells], dtype=np.int64)
        if len(set(body_ids)) != len(body_ids) or set(body_ids) != {
                body_id for body_id, n in neurons.items() if n["type"] == "LC10a"}:
            raise ValueError("Visual map must cover each selected LC10a exactly once")
        sides = np.array([row["side"] for row in cells])
        centers = np.array([row["preferred_abs_bearing_deg"] for row in cells],
                           dtype=np.float64)
        if (not np.all(np.isfinite(centers)) or np.any(centers < 0)
                or np.any(centers > 180)
                or any(neurons[int(body_id)]["side"] != side
                       for body_id, side in zip(body_ids, sides))):
            raise ValueError("Invalid mapped LC10a center or side")
        aotu = sorted((n for n in circuit["neurons"] if n["type"] in
                       ("AOTU019", "AOTU025")), key=lambda n: int(n["body_id"]))
        dn = sorted((n for n in circuit["neurons"] if n["type"] == "DNa02"),
                    key=lambda n: n["side"])
        if len(aotu) != 4 or {n["side"] for n in dn} != {"L", "R"}:
            raise ValueError("Expected bilateral AOTU019/AOTU025 and DNa02")
        lc_index = {int(value): i for i, value in enumerate(body_ids)}
        aotu_index = {int(n["body_id"]): i for i, n in enumerate(aotu)}
        dn_index = {int(n["body_id"]): i for i, n in enumerate(dn)}
        lc_to_aotu = np.zeros((len(body_ids), len(aotu)), dtype=np.float64)
        aotu_to_dn = np.zeros((len(aotu), 2), dtype=np.float64)
        for edge in circuit["connections"]:
            pre, post, count = int(edge["pre"]), int(edge["post"]), int(edge["synapse_count"])
            if count <= 0:
                raise ValueError("Nonpositive connection count")
            if pre in lc_index and post in aotu_index:
                if neurons[pre]["side"] != neurons[post]["side"]:
                    raise ValueError("Unexpected cross-side LC10a input")
                lc_to_aotu[lc_index[pre], aotu_index[post]] += count
            elif pre in aotu_index and post in dn_index:
                sign = {"acetylcholine": 1.0, "gaba": -1.0}.get(neurons[pre]["predicted_nt"])
                if sign is None:
                    raise ValueError("Unknown AOTU transmitter sign")
                aotu_to_dn[aotu_index[pre], dn_index[post]] += sign * count
            else:
                raise ValueError("Unexpected edge in selected pursuit circuit")
        if np.any(lc_to_aotu.sum(axis=0) == 0) or np.any(aotu_to_dn.sum(axis=1) == 0):
            raise ValueError("Selected pathway is incomplete")
        return cls(body_ids, sides, centers,
                   tuple(int(n["body_id"]) for n in aotu),
                   tuple(n["type"] for n in aotu),
                   tuple(n["side"] for n in aotu), lc_to_aotu, aotu_to_dn)

    def fixed_fly(self, bearing_deg: np.ndarray, *, width_deg: float = 18.0,
                  bridge: str = "intact") -> dict:
        """Project a hypothesized object response through two recorded edge layers.

        Gaussian width and unit peak per LC10a are engineering hypotheses.
        Output units are contact counts or their products, never firing rates.
        DNa02 columns are ordered left then right.
        """
        angles = np.asarray(bearing_deg, dtype=np.float64)
        if (angles.ndim != 1 or not np.all(np.isfinite(angles))
                or np.any(np.abs(angles) > 180) or not np.isfinite(width_deg)
                or width_deg <= 0):
            raise ValueError("Expected finite one-dimensional bearings in [-180,180]")
        if bridge not in ("intact", "removed", "side_swapped"):
            raise ValueError("Unknown output-bridge condition")
        active = np.where(angles[:, None] > 0, self.sides == "R",
                          np.where(angles[:, None] < 0, self.sides == "L", False))
        visual = np.exp(-0.5 * ((np.abs(angles[:, None]) - self.centers_deg) / width_deg) ** 2)
        visual *= active
        aotu = visual @ self.lc_to_aotu
        output_edges = (self.aotu_to_dn if bridge == "intact" else
                        np.zeros_like(self.aotu_to_dn) if bridge == "removed" else
                        self.aotu_to_dn[:, ::-1])
        dn = aotu @ output_edges
        return {"lc10a_hypothesis": visual, "aotu_contact_drive": aotu,
                "dna02_signed_contact_product": dn,
                "dna02_right_minus_left": dn[:, 1] - dn[:, 0]}

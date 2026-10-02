"""Offline response decomposition and one-factor probes, never production defaults."""
import argparse
import csv
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from .pursuit_motion_diagnostic import model
from .pursuit_reference import _nearest_lookup
from .pursuit_retinal_benchmark import (AuthorResponse, CAP, ROOT, load_response_fields,
                                       streams, table, trial)
from .pursuit_step4 import ActivityAdapter


def pairs(adapter):
    p = adapter.projection
    return [(next(i for i, (k, s) in enumerate(zip(p.aotu_types, p.aotu_sides)) if k==kind and s=="R"),
             next(i for i, (k, s) in enumerate(zip(p.aotu_types, p.aotu_sides)) if k==kind and s=="L"))
            for kind in ("AOTU019", "AOTU025")]


class Probe:
    def __init__(self, adapter, variant="baseline"):
        self.adapter = adapter
        self.variant = variant
        original = ActivityAdapter.build(adapter.projection)
        self.channel_peaks = original.response.max(axis=0)

    def activity_at(self, bearing, motion, *, direction_selective=True, condition="intact"):
        # Only these two probes alter the transformation stage; all others use
        # the actual baseline implementation with one changed adapter field.
        if self.variant not in ("channel_normalization", "linear_activation", "dn_quantization"):
            return self.adapter.activity_at(bearing, motion,
                direction_selective=direction_selective, condition=condition)
        a = self.adapter
        result = a.activity_at(bearing, motion, direction_selective=direction_selective,
                               condition=condition)
        if self.variant == "dn_quantization":
            grid = np.linspace(-2.25, 4., 1000)
            dn = _nearest_lookup(grid, grid, result["dn"])
            return {**result, "dn": dn, "signal": float(dn[1]-dn[0])}
        idx = int(np.copysign(np.floor(abs(bearing)+.5), bearing))+180
        raw = a.response[idx].copy()
        for i, (kind, side) in enumerate(zip(a.projection.aotu_types, a.projection.aotu_sides)):
            if direction_selective and kind == "AOTU019" and (
                    (side == "R" and motion < 0) or (side == "L" and motion > 0)):
                raw[i] *= .66
        if self.variant == "channel_normalization":
            # Change ONLY the denominator; keep baseline ELU shape and lookup resolution.
            raw *= np.array([a.peaks[k] for k in a.projection.aotu_types])/self.channel_peaks
            activity = np.array([_nearest_lookup(*a.lookups[k], min(float(v), a.peaks[k]))
                                 for k, v in zip(a.projection.aotu_types, raw)])
        else:
            activity = np.clip(raw/np.array([a.peaks[k] for k in a.projection.aotu_types]), 0., 1.)
        dn = np.clip(activity @ a.output_edges, -2.25, 4.)
        return {"aotu": activity, "dn": dn, "signal": float(dn[1]-dn[0])}


def probes(base):
    sym_input = base.response.copy()
    sym_output = base.output_edges.copy()
    canonical = np.sign(base.output_edges)
    for i, j in pairs(base):
        average = (base.response[:, i]+base.response[::-1, j])/2.
        sym_input[:, i], sym_input[:, j] = average, average[::-1]
        edge_average = (base.output_edges[i]+base.output_edges[j, ::-1])/2.
        sym_output[i], sym_output[j] = edge_average, edge_average[::-1]
    return {
        "baseline": Probe(base),
        "input_symmetry": Probe(replace(base, response=sym_input)),
        "output_symmetry": Probe(replace(base, output_edges=sym_output)),
        "channel_normalization": Probe(base, "channel_normalization"),
        "linear_activation": Probe(base, "linear_activation"),
        "canonical_output": Probe(replace(base, output_edges=canonical)),
        "dn_quantization": Probe(base, "dn_quantization")}


def decompose(base, bearing, motion):
    raw = base.response[bearing+180].copy()
    suppressed = raw.copy()
    for i, (kind, side) in enumerate(zip(base.projection.aotu_types, base.projection.aotu_sides)):
        if kind == "AOTU019" and ((side == "R" and motion<0) or (side == "L" and motion>0)):
            suppressed[i] *= .66
    result = base.activity_at(bearing, motion)
    contribution = result["aotu"]*(base.output_edges[:, 1]-base.output_edges[:, 0])
    dn_unclipped = result["aotu"] @ base.output_edges
    return {"bearing_deg": bearing, "motion_sign": motion,
        "raw_contacts": raw.tolist(), "suppressed_contacts": suppressed.tolist(),
        "normalized_contacts": (suppressed/np.array([base.peaks[k] for k in base.projection.aotu_types])).tolist(),
        "aotu": result["aotu"].tolist(), "signal_contributions": contribution.tolist(),
        "dn_unclipped": dn_unclipped.tolist(), "dn": result["dn"].tolist(),
        "signal": result["signal"], "command_deg_s": float(np.clip(65.*result["signal"], -CAP, CAP)),
        "aotu_clipped": bool(result["aotu_clipped"]), "dn_clipped": bool(result["dn_clipped"])}


def curve_stats(lookup):
    # lookup motion axis -1/0/+1; restrict to visible angles, map by +180.
    curve = lookup[:, 60:301, 0]
    return {"max_mirror_signal_mismatch": float(np.max(np.abs(curve+curve[::-1, ::-1]))),
        "stationary_signal_at_0": float(lookup[1, 180, 0]),
        "stationary_signal_at_105": float(lookup[1, 285, 0]),
        "stationary_signal_at_minus105": float(lookup[1, 75, 0]),
        "central_direction_switch_deg_s": float(65.*abs(lookup[2, 180, 0]-lookup[0, 180, 0])),
        "central_stationary_slope_per_deg": float((lookup[1, 183, 0]-lookup[1, 177, 0])/6.),
        "max_abs_signal": float(np.max(np.abs(curve)))}


def run(response_csv, destination=ROOT/"docs/evidence/pursuit_response_v1.json"):
    source_hash = hashlib.sha256(Path(response_csv).read_bytes()).hexdigest()
    manifest = json.loads((ROOT/"docs/evidence/pursuit_reference_source_v1.json").read_text())
    if source_hash != manifest["sha256"]["Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("Reference table hash mismatch")
    reference = AuthorResponse(load_response_fields(response_csv))
    base = model()
    variants = probes(base)
    lookups = {name: table(probe) for name, probe in variants.items()}
    lookups["reference"] = table(reference, author=True)
    stats = {name: curve_stats(lookup) for name, lookup in lookups.items()}
    samples = [decompose(base, b, m) for b in (-105, -60, -20, -5, -1, 0, 1, 5, 20, 60, 105)
               for m in (-1, 0, 1)]
    # The selected circuit has no DN clipping here, so the contribution sum
    # must reconstruct the actual output exactly.
    error = max(abs(sum(s["signal_contributions"])-s["signal"]) for s in samples)
    if error > 1e-12:
        raise AssertionError("Contribution decomposition failed")
    old = json.loads((ROOT/"docs/evidence/pursuit_retinal_v1.json").read_text())
    rows = []
    for case, values in streams().items():
        assert hashlib.sha256(np.asarray(values,dtype="<f8").tobytes()).hexdigest()==old["input_sha256"][case]
        for name, lookup in lookups.items():
            row = {"case": case, "variant": name, **trial(values, lookup)}
            if name in ("baseline", "reference"):
                old_name = "adapted_ds" if name=="baseline" else "author_ds"
                expected = next(r for r in old["rows"] if r["case"]==case and r["variant"]==old_name)
                if any(row[k] != expected[k] for k in ("mean_abs_error_deg", "settling_s", "visible_fraction", "saturation_fraction")):
                    raise AssertionError("Prior benchmark failed to reproduce")
            rows.append(row)
    family_means = {family: {name: float(np.mean([r["mean_abs_error_deg"] for r in rows
        if r["case"].startswith(family) and r["variant"]==name])) for name in lookups}
        for family in ("step", "sweep_25", "sweep_75", "smooth", "old")}
    channel_details = []
    map_path = ROOT/"src/fly_creature/data/lc10a_registered_eyemap_hypothesis_v3.json"
    map_cells = {int(c["body_id"]): c for c in json.loads(map_path.read_text())["cells"]}
    spread_summary = []
    original = ActivityAdapter.build(base.projection)
    for i, (kind, side) in enumerate(zip(base.projection.aotu_types, base.projection.aotu_sides)):
        weights = base.projection.lc_to_aotu[:, i]
        channel_details.append({"type": kind, "side": side,
            "body_id": base.projection.aotu_ids[i], "peak_bearing_deg": int(np.argmax(base.response[:, i])-180),
            "input_weighted_center_abs_deg": float(np.average(base.projection.centers_deg,weights=weights)),
            "channel_original_peak": float(original.response[:, i].max()), "shared_type_peak": base.peaks[kind],
            "raw_output_edges": base.projection.aotu_to_dn[i].tolist(),
            "normalized_output_edges": base.output_edges[i].tolist(),
            "wide_105_fraction_of_type_peak": float(base.response[285 if side=="R" else 75, i]/base.peaks[kind])})
        direct = np.array([map_cells[int(b)]["angle_spread_deg"] is not None for b in base.projection.body_ids])
        spreads = np.array([map_cells[int(b)]["angle_spread_deg"] or 0. for b in base.projection.body_ids])
        positive = direct & (weights>0)
        spread_summary.append({"type": kind, "side": side,
            "direct_input_contact_fraction": float(weights[direct].sum()/weights.sum()),
            "weighted_mean_upstream_angular_spread_deg": float(np.average(spreads[positive],weights=weights[positive])),
            "min_upstream_spread_deg": float(spreads[positive].min()),
            "max_upstream_spread_deg": float(spreads[positive].max()),
            "note": "Anatomical column spread, not measured LC10a response width; current simulation ignores it"})
    reference_samples = []
    for b in (0,20,60,105):
        r = reference.activity_at(b,0)
        canonical = variants["canonical_output"].activity_at(b,0)
        reference_samples.append({"bearing_deg": b,
            "reference_normalized_raw_right_019_025": [float(reference.r019[b+180]/reference.r019.max()),float(reference.r025[b+180]/reference.r025.max())],
            "reference_activated_right_019_025": [r["aotu"][0],r["aotu"][2]],
            "adapted_activated_right_019_025": [float(canonical["aotu"][0]),float(canonical["aotu"][3])],
            "reference_minus_canonical_adapted_signal": float(r["signal"]-canonical["signal"])})
    result = {"protocol": "pursuit_response_protocol.md", "source_table_sha256": source_hash,
        "prior_benchmark_sha256": hashlib.sha256((ROOT/"docs/evidence/pursuit_retinal_v1.json").read_bytes()).hexdigest(),
        "channel_details": channel_details, "curve_stats": stats, "contribution_reconstruction_max_error": error,
        "map_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
        "upstream_spread_audit": spread_summary, "reference_shape_samples": reference_samples,
        "samples": samples, "family_means_deg": family_means, "rows": rows}
    destination = Path(destination)
    destination.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    with destination.with_suffix(".csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    local = ROOT/"outputs/research/response-diagnosis"
    local.mkdir(parents=True,exist_ok=True)
    np.savez(local/"curves.npz",**lookups)
    plot(lookups, destination.with_suffix(".png"))
    print(json.dumps({"curve_stats": stats,"family_means_deg": family_means,"channels":channel_details},indent=2))
    return result


def plot(lookups, output):
    cache = ROOT/"outputs/research/response-diagnosis/matplotlib-cache"
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR",str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    angles=np.arange(-120,121)
    fig, axes=plt.subplots(1,3,figsize=(14,4.3),sharey=True)
    for m,axis in enumerate(axes):
        for name in ("reference","baseline","linear_activation","channel_normalization","canonical_output"):
            axis.plot(angles,65.*lookups[name][m,60:301,0],label=name.replace('_',' '),lw=1.5)
        axis.axhline(0,color='gray',lw=.6)
        axis.axhline(CAP,color='gray',ls=':',lw=.6);axis.axhline(-CAP,color='gray',ls=':',lw=.6)
        axis.set_title(('Motion left','Stationary input','Motion right')[m])
        axis.set_xlabel('Retinal bearing (degrees)');axis.grid(alpha=.2)
    axes[0].set_ylabel('Requested turning rate (degrees/s, before cap)')
    axes[-1].legend(fontsize=8)
    fig.suptitle('Steering response: fixed gain; one-factor diagnostic probes')
    fig.tight_layout();fig.savefig(output,dpi=160);plt.close(fig)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("response_csv",type=Path)
    parser.add_argument("--output",type=Path,default=ROOT/"docs/evidence/pursuit_response_v1.json")
    args=parser.parse_args();run(args.response_csv,args.output)

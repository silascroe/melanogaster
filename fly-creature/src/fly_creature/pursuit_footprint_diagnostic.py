"""Fixed-fly audit first, then consumed-case footprint replays and wiring controls."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from .pursuit_footprints import load_footprints, footprint_adapter
from .pursuit_motion_diagnostic import model
from .pursuit_retinal_benchmark import ROOT, streams, table, trial
from .pursuit_step4 import shuffled_projection

SEED=20261005


def peak_separation(adapter):
    peaks={}
    for i,(kind,side) in enumerate(zip(adapter.projection.aotu_types,adapter.projection.aotu_sides)):
        # Measure each channel only in its ipsilateral half of the visual field.
        drive=adapter.response[180:301,i] if side=="R" else adapter.response[60:181,i][::-1]
        peaks[kind,side]=int(np.argmax(drive))
    return float(np.mean([peaks['AOTU025',s]-peaks['AOTU019',s] for s in ('L','R')]))


def fixed_audit(base, rows):
    candidates={"baseline":base}
    audits={}
    for mode in ("footprint","signed_mean","recentered_footprint"):
        adapter,visual,direct=footprint_adapter(base,rows,mode)
        if not np.isfinite(visual).all() or visual.min()<0 or visual.max()>1+1e-12:
            raise AssertionError("Cell response must be finite and bounded")
        angles=np.arange(-180.,181.)[:,None]
        signs=np.where(base.projection.sides=="R",1.,-1.)
        baseline_visual=np.exp(-.5*((angles-base.projection.centers_deg*signs)/18.)**2)*np.clip(.5+angles*signs/15.,0.,1.)
        fallback_error=float(np.max(np.abs(visual[:,~direct]-baseline_visual[:,~direct])))
        if fallback_error>1e-14:
            raise AssertionError("Fallback response changed")
        direct_drive=visual[:,direct]@base.projection.lc_to_aotu[direct]
        fallback_drive=visual[:,~direct]@base.projection.lc_to_aotu[~direct]
        if not np.allclose(direct_drive+fallback_drive,adapter.response,rtol=0,atol=1e-10):
            raise AssertionError("Direct/fallback decomposition failed")
        if adapter.peaks is not base.peaks or not np.array_equal(adapter.output_edges,base.output_edges):
            raise AssertionError("Normalization changed")
        audits[mode]={"fallback_max_abs_error":fallback_error,"direct_cells":int(direct.sum()),
            "fallback_cells":int((~direct).sum()),"cell_response_min":float(visual.min()),"cell_response_max":float(visual.max()),
            "branches":[{"type":kind,"side":side,"peak_bearing_deg":int(np.argmax(adapter.response[:,i])-180),
                "peak_fraction_of_frozen_type_peak":float(adapter.response[:,i].max()/base.peaks[kind]),
                "visible_raw_clip_fraction":float(np.mean(adapter.response[60:301,i]>base.peaks[kind]+1e-9)),
                "wide105_raw_total":float(adapter.response[285 if side=="R" else 75,i]),
                "wide105_raw_direct":float(direct_drive[285 if side=="R" else 75,i]),
                "wide105_raw_fallback":float(fallback_drive[285 if side=="R" else 75,i])}
                for i,(kind,side) in enumerate(zip(base.projection.aotu_types,base.projection.aotu_sides))]}
        candidates[mode]=adapter
    return candidates,audits


def run(output=ROOT/"docs/evidence/pursuit_footprint_v1.json"):
    rows=load_footprints()
    base=model()
    candidates,audits=fixed_audit(base,rows)  # No behavior run before these invariants pass.
    lookups={name:table(adapter) for name,adapter in candidates.items()}
    spatial={name:peak_separation(adapter) for name,adapter in candidates.items()}
    spatial_shuffles={"baseline":[],"footprint":[]}
    rng=np.random.default_rng(SEED)
    for k in range(32):
        shuffled=model(shuffled_projection(base.projection,rng),base)
        candidate,_,_=footprint_adapter(shuffled,rows)
        spatial_shuffles['baseline'].append(peak_separation(shuffled))
        spatial_shuffles['footprint'].append(peak_separation(candidate))
        lookups[f"baseline_shuffle_{k:02}"]=table(shuffled)
        lookups[f"footprint_shuffle_{k:02}"]=table(candidate)
    old=json.loads((ROOT/"docs/evidence/pursuit_retinal_v1.json").read_text())
    scores=[]
    for case,values in streams().items():
        if hashlib.sha256(np.asarray(values,dtype="<f8").tobytes()).hexdigest()!=old["input_sha256"][case]:
            raise AssertionError("Consumed input stream changed")
        for name,lookup in lookups.items():
            metric=trial(values,lookup)
            if name=="baseline" or name.startswith("baseline_shuffle"):
                old_name="adapted_ds" if name=="baseline" else "shuffle_ds_"+name[-2:]
                expected=next(r for r in old["rows"] if r["case"]==case and r["variant"]==old_name)
                if any(metric[k]!=expected[k] for k in metric):
                    raise AssertionError("Prior baseline/shuffle metric changed")
            scores.append({"case":case,"variant":name,**metric})
    summary={}
    for family in ("step","sweep_25","sweep_75","smooth","old"):
        means={v:float(np.mean([r["mean_abs_error_deg"] for r in scores
            if r["case"].startswith(family) and r["variant"]==v])) for v in lookups}
        summary[family]={"means_deg":{k:v for k,v in means.items() if "shuffle" not in k},
            "baseline_beats_shuffles":sum(means["baseline"]<means[f"baseline_shuffle_{k:02}"] for k in range(32)),
            "footprint_beats_shuffles":sum(means["footprint"]<means[f"footprint_shuffle_{k:02}"] for k in range(32)),
            "footprint_shuffle_means_deg":[means[f"footprint_shuffle_{k:02}"] for k in range(32)]}
    signal_samples={name:{str(b):{str(m):float(lookup[m+1,b+180,0]) for m in (-1,0,1)}
                         for b in (-105,-60,-20,0,20,60,105)}
                    for name,lookup in lookups.items() if "shuffle" not in name}
    path=ROOT/"src/fly_creature/data/lc10a_column_footprints_v1.json"
    result={"protocol":"pursuit_footprint_protocol.md","footprint_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "shuffle_seed":SEED,"fixed_fly_audit":audits,"family_summary":summary,"signal_samples":signal_samples,
        "spatial_peak_separation_deg":spatial,"spatial_shuffle_peak_separations_deg":spatial_shuffles,
        "spatial_intact_beats_shuffles":{name:sum(spatial[name]>x for x in values)
                                          for name,values in spatial_shuffles.items()},
        "normalization":"Frozen baseline type peaks and output scales; no per-cell peak renormalization",
        "rows":scores}
    output=Path(output)
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    with output.with_suffix(".csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(scores[0]));writer.writeheader();writer.writerows(scores)
    plot(candidates,output.with_suffix(".png"))
    print(json.dumps({"family_summary":summary,"signal_at105":{name:values['105']['0'] for name,values in signal_samples.items()}},indent=2))
    return result


def plot(candidates,output):
    cache=ROOT/"outputs/research/footprint-diagnosis/matplotlib-cache"
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR",str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    angles=np.arange(-120,121)
    for name,a in candidates.items():
        weights=np.array([a.peaks[k] for k in a.projection.aotu_types])
        for i,(kind,side) in enumerate(zip(a.projection.aotu_types,a.projection.aotu_sides)):
            if side=="R":
                axes[0].plot(angles,a.response[60:301,i]/weights[i],label=name+' '+kind,lw=1.2)
        lookup=table(a)
        axes[1].plot(angles,65.*lookup[1,60:301,0],label=name,lw=1.4)
    axes[0].set_title('Right input fields, frozen normalization')
    axes[0].set_ylabel('Raw contact drive / baseline type peak')
    axes[1].set_title('Stationary steering response')
    axes[1].set_ylabel('Requested turning rate (degrees/s, before cap)')
    for axis in axes:
        axis.set_xlabel('Retinal bearing (degrees)');axis.grid(alpha=.2);axis.legend(fontsize=7)
    fig.tight_layout();fig.savefig(output,dpi=150);plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"docs/evidence/pursuit_footprint_v1.json")
    args=parser.parse_args();run(args.output)

"""Frozen offline held-recording population-tuning comparison."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import zipfile

import numpy as np

from .pursuit_physiology import ARCHIVES, P1_ARCHIVES, ROOT, extract, model_tables, read_recording, sha, visible_segments
from .pursuit_repeatability import DUPLICATE, cell, csv_write, record_loss
from .pursuit_temporal import inputs, observation_kernel

PREDICTORS = ("anatomy", "simple_spatial", "empirical", "empirical_unscaled", "constant", "zero")


def compact_lookups():
    from .pursuit_motion_diagnostic import model
    base = model()
    tables = {kind: np.zeros((2, 2, 361)) for kind in ARCHIVES}
    indices = {}
    for kind in ARCHIVES:
        for side in "LR":
            matches = [i for i, pair in enumerate(zip(base.projection.aotu_types, base.projection.aotu_sides))
                       if pair == (kind, side)]
            assert len(matches) == 1
            indices[kind, side] = matches[0]
    for direction, motion in enumerate((-1, 1)):
        for j, angle in enumerate(range(-180, 181)):
            r = base.activity_at(float(angle), motion)["aotu"]
            l = base.activity_at(float(-angle), -motion)["aotu"]
            for kind in ARCHIVES:
                tables[kind][0, direction, j] = (r[indices[kind,"R"]]+l[indices[kind,"L"]])/2
                peak = 35 if kind == "AOTU019" else 65
                tables[kind][1, direction, j] = np.exp(-.5*((angle-peak)/20)**2)
    # Independent existing builder also constructs footprint/shuffle variants;
    # compare only its unchanged anatomy and simple entries.
    names, original = model_tables()
    take = [names.index("baseline"), names.index("simple_spatial")]
    error = max(float(np.max(np.abs(tables[kind] -
                (original[kind,"R"][take]+original[kind,"L"][take,::-1,::-1])/2))) for kind in ARCHIVES)
    assert error < 1e-14
    return tables, error


def signature(r):
    return tuple(r[f] for f in ("condition", "type", "recording", "trial", "speed_deg_s", "direction", "center_bin"))


def collect(directory, tables):
    from scipy.signal import fftconvolve
    rows, audit, convolution_error, singletons = [], [], 0., 0
    for condition, archives in (("NoP1", ARCHIVES), ("P1", P1_ARCHIVES)):
        for kind, (filename, expected) in archives.items():
            path = directory/filename
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "md5").hexdigest()
            assert digest == expected, filename
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind+"/"+Path(member).stem.removesuffix("_int")
                    if identity == DUPLICATE:
                        audit.append(dict(condition=condition,recording=identity,excluded="known duplicate"))
                        continue
                    payload = archive.read(member)
                    time, dt, data = read_recording(payload)
                    pulses, rejected = extract(time,dt,data,identity,kind,"canonical")
                    segments = sum(len(visible_segments(data["int_panelps"][:,j])) for j in range(data["int_panelps"].shape[1]))
                    assert len(pulses)+sum(rejected.values()) == segments
                    quiet = [p for p in pulses if p["state"]=="quiescent"]
                    grouped = defaultdict(list)
                    radius, kernel = observation_kernel(dt)
                    for trial in sorted(set(p["trial"] for p in quiet)):
                        drive, singles = inputs(data["int_panelps"][:,trial],tables[kind])
                        singletons += singles
                        padded = np.pad(drive,((0,0),(radius,radius)))
                        response = fftconvolve(padded,kernel[None,:],mode="same",axes=1)[:,radius:radius+len(time)]
                        if trial == min(p["trial"] for p in quiet):
                            direct = np.convolve(padded[0],kernel,mode="same")[radius:radius+len(time)]
                            convolution_error = max(convolution_error,float(np.max(np.abs(direct-response[0]))))
                            assert convolution_error < 1e-12
                        for p in (p for p in quiet if p["trial"]==trial):
                            start, margin = p["start_sample"], p["margin"]
                            stop = start+len(p["position"])-2*margin
                            lo, hi = start-margin, stop+margin
                            baseline = (p["time"]>=-.250)&(p["time"]<=-.100)
                            x = response[:,start:stop].mean(axis=1)-response[:,lo:hi][:,baseline].mean(axis=1)
                            key = p["speed_deg_s"],p["direction"],int(round(p["center_deg"]/11.25)),trial
                            grouped[key].append((p["evoked_spikes_s"], x, p["center_deg"]))
                    for (speed,direction,center,trial),values in sorted(grouped.items()):
                        xs = np.mean([v[1] for v in values],axis=0)
                        rows.append(dict(condition=condition,type=kind,recording=identity,trial=trial,
                                         speed_deg_s=speed,direction=direction,center_bin=center,center_deg=center*11.25,
                                         actual_center_deg=float(np.mean([v[2] for v in values])),pulses=len(values),
                                         response_spikes_s=float(np.mean([v[0] for v in values])),
                                         anatomy_x=float(xs[0]),simple_spatial_x=float(xs[1])))
                    audit.append(dict(condition=condition,recording=identity,member=member,archive_md5=digest,
                                      member_sha256=hashlib.sha256(payload).hexdigest(),accepted=len(pulses),
                                      rejected=rejected,segments=segments,quiescent_pulses=len(quiet),trial_cells=len(grouped)))
                    print(f"{condition} {identity}: {len(quiet)} quiet pulses",flush=True)
    return rows,audit,dict(direct_convolution_max_error=convolution_error,singleton_segments=singletons)


def weights(rows):
    trials = Counter((r["recording"],r["trial"]) for r in rows)
    per_record = defaultdict(set)
    for r in rows:
        per_record[r["recording"]].add(r["trial"])
    w = np.array([1/(trials[r["recording"],r["trial"]]*len(per_record[r["recording"]])*len(per_record)) for r in rows])
    assert abs(w.sum()-1)<1e-12
    return w


def gain(x,y,w):
    xx = float(w @ (x*x))
    return max(0.,float(w @ (x*y))/xx) if xx>1e-14 else 0.


def correlation(x,y):
    return float(np.corrcoef(x,y)[0,1]) if np.std(x)>1e-12 and np.std(y)>1e-12 else None


def evaluate(observations):
    pools = defaultdict(list)
    for r in observations:
        pools[r["condition"],r["type"]].append(r)
    folds, records, shapes = [], [], []
    for (condition,kind),raw in sorted(pools.items()):
        grouped = defaultdict(lambda:defaultdict(list))
        for r in raw:
            grouped[r["recording"]][cell(r)].append(r)
        good = {rec:{s:v for s,v in gs.items() if len(v)>=4} for rec,gs in grouped.items()}
        means = {rec:{s:float(np.mean([r["response_spikes_s"] for r in v])) for s,v in gs.items()} for rec,gs in good.items()}
        for identity,gs in sorted(good.items()):
            others = {rec:m for rec,m in means.items() if rec != identity}
            outer_mean = {s:float(np.mean([m[s] for m in others.values() if s in m])) for s in gs
                          if sum(s in m for m in others.values())>=3}
            held = [r for s,v in gs.items() if s in outer_mean for r in v]
            train = []
            empirical_train = []
            for rec,g in sorted(good.items()):
                if rec==identity:
                    continue
                for s,values in sorted(g.items()):
                    eligible = [m[s] for name,m in others.items() if name != rec and s in m]
                    if len(eligible)>=3:
                        for r in values:
                            train.append(r)
                            empirical_train.append(float(np.mean(eligible)))
            assert held and train
            assert all(r["recording"]!=identity for r in train)
            w = weights(train)
            y = np.array([r["response_spikes_s"] for r in train])
            gains = {name:gain(np.array([r[name+"_x"] for r in train]),y,w) for name in ("anatomy","simple_spatial")}
            gains["empirical"] = gain(np.array(empirical_train),y,w)
            constant = float(w @ y)
            scored = []
            for r in held:
                s = cell(r)
                scored.append(dict(r,anatomy=r["anatomy_x"]*gains["anatomy"],
                                   simple_spatial=r["simple_spatial_x"]*gains["simple_spatial"],
                                   empirical=outer_mean[s]*gains["empirical"],empirical_unscaled=outer_mean[s],
                                   constant=constant,zero=0.))
            folds.extend(scored)
            cell_means = defaultdict(list)
            for r in scored:
                cell_means[cell(r)].append(r)
            cell_rows = []
            for (speed,direction,center),values in sorted(cell_means.items()):
                row = dict(condition=condition,type=kind,recording=identity,speed_deg_s=speed,direction=direction,
                           center_bin=center,center_deg=center*11.25,trials=len(values),
                           response_spikes_s=float(np.mean([r["response_spikes_s"] for r in values])))
                row.update({name:float(np.mean([r[name] for r in values])) for name in PREDICTORS})
                cell_rows.append(row)
            shapes.extend(cell_rows)
            entry = dict(condition=condition,type=kind,recording=identity,scored_trial_cells=len(scored),
                         scored_trials=len(set(r["trial"] for r in scored)),scored_cells=len(cell_rows),
                         calibration_trial_cells=len(train),calibration_recordings=len(set(r["recording"] for r in train)),
                         **{name+"_gain":value for name,value in gains.items()},constant_spikes_s=constant)
            entry.update({name+"_rmse":record_loss(scored,name) for name in PREDICTORS})
            ycells = np.array([r["response_spikes_s"] for r in cell_rows])
            entry.update({name+"_cell_correlation":correlation(np.array([r[name] for r in cell_rows]),ycells)
                          for name in ("anatomy","simple_spatial","empirical")})
            records.append(entry)
    return folds,records,shapes


def population_cells(shapes):
    groups = defaultdict(list)
    for r in shapes:
        groups[r["condition"],r["type"],r["speed_deg_s"],r["direction"],r["center_bin"]].append(r)
    result = []
    for (condition,kind,speed,direction,center),values in sorted(groups.items()):
        if len(values)<3:
            continue
        y = np.array([r["response_spikes_s"] for r in values])
        row = dict(condition=condition,type=kind,speed_deg_s=speed,direction=direction,center_deg=center*11.25,
                   recordings=len(values),measured_mean_spikes_s=float(y.mean()),
                   measured_sem_spikes_s=float(y.std(ddof=1)/np.sqrt(len(y))))
        row.update({name:float(np.mean([r[name] for r in values])) for name in PREDICTORS})
        result.append(row)
    return result


def summaries(records):
    result = []
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            selected = [r for r in records if (r["condition"],r["type"])==(condition,kind)]
            row = dict(condition=condition,type=kind,recordings=len(selected),scored_trial_cells=sum(r["scored_trial_cells"] for r in selected))
            row.update({name+"_rmse":float(np.mean([r[name+"_rmse"] for r in selected])) for name in PREDICTORS})
            for name in ("anatomy","simple_spatial","empirical"):
                values = [r[name+"_cell_correlation"] for r in selected if r[name+"_cell_correlation"] is not None]
                row[name+"_median_cell_correlation"] = float(np.median(values)) if values else None
                row[name+"_gain_range"] = [min(r[name+"_gain"] for r in selected),max(r[name+"_gain"] for r in selected)]
            for reference,candidate in (("constant","anatomy"),("simple_spatial","anatomy"),("anatomy","empirical"),("simple_spatial","empirical")):
                label = candidate+"_vs_"+reference
                row[label+"_reduction_percent"] = 100*(1-row[candidate+"_rmse"]/row[reference+"_rmse"])
                row[label+"_recordings_improved"] = sum(r[candidate+"_rmse"]<r[reference+"_rmse"] for r in selected)
            result.append(row)
    return result


def plot(path,cells):
    os.environ.setdefault("MPLCONFIGDIR",str(path.parent/"mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes = plt.subplots(4,2,figsize=(12,13),constrained_layout=True)
    for i,(kind,direction) in enumerate(( (k,d) for k in ARCHIVES for d in (-1,1))):
        for j,speed in enumerate((25,75)):
            ax = axes[i,j]
            selected = sorted([r for r in cells if (r["condition"],r["type"],r["direction"],r["speed_deg_s"])==("P1",kind,direction,speed)],key=lambda r:r["center_deg"])
            x = [r["center_deg"] for r in selected]
            ax.errorbar(x,[r["measured_mean_spikes_s"] for r in selected],yerr=[r["measured_sem_spikes_s"] for r in selected],
                        color="#333333",marker="o",markersize=3,capsize=2,label="Measured (recording SEM)")
            for field,color,label in (("anatomy","#2166ac","Frozen anatomy"),("simple_spatial","#d66024","Simple spatial"),("empirical","#278449","Other-recording template")):
                ax.plot(x,[r[field] for r in selected],color=color,label=label,linewidth=1.8)
            ax.set_title(f"P1 {kind} | direction {direction:+d} | {speed} deg/s")
            ax.set_xlabel("Nominal center (degrees, positive ipsilateral)")
            ax.set_ylabel("Evoked pulse mean (spikes/s)")
            ax.axhline(0,color="gray",linewidth=.5)
            ax.grid(alpha=.15)
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Matched population visual tuning: all predictions exclude the scored recording\nEmpirical template learns per-cell responses; no equal-complexity or causal claim",fontsize=12)
    fig.savefig(path,dpi=150,metadata={"Software":"Fly Creature population-tuning diagnostic"})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=ROOT/"outputs/research/aotu-recordings")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--repeatability-dir",type=Path,default=ROOT/"outputs/research/aotu-repeatability-v1")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    tables,lookup_error = compact_lookups()
    observations,audit,checks = collect(args.data_dir,tables)
    folds,records,shapes = evaluate(observations)
    cells = population_cells(shapes)
    for name,rows in (("observations",observations),("folds",folds),("recordings",records),("recording_cells",shapes),("population_cells",cells)):
        csv_write(args.output_dir/(name+".csv"),rows)
    # Match the previous assay's responses and common scoring set independently
    # of prediction values; previous artifacts are provenance references only.
    with (args.repeatability_dir/"observations.csv").open(encoding="utf-8",newline="") as stream:
        previous = list(csv.DictReader(stream))
    def csv_sig(r):
        return tuple(str(v) for v in signature(r))
    reference = {csv_sig(r):float(r["response_spikes_s"]) for r in previous}
    assert len(reference)==len(observations)==35484
    assert max(abs(r["response_spikes_s"]-reference[csv_sig(r)]) for r in observations)<1e-12
    with (args.repeatability_dir/"folds.csv").open(encoding="utf-8",newline="") as stream:
        previous_folds = list(csv.DictReader(stream))
    assert {csv_sig(r) for r in folds}=={csv_sig(r) for r in previous_folds}
    checks.update(compact_lookup_max_error=lookup_error,previous_response_and_coverage_match=True,
                  scored_trial_cells=len(folds),recordings=len(records))
    protected = [p for p in (ROOT/"src/fly_creature").glob("*.py") if p.name!=Path(__file__).name]
    protected += list((ROOT/"src/fly_creature/data").glob("*.json"))
    result = dict(protocol_sha256=sha(ROOT/"docs/pursuit_population_protocol.md"),implementation_sha256=sha(Path(__file__)),
                  frozen_component_sha256={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in sorted(protected)},
                  repeatability_observations_sha256=sha(args.repeatability_dir/"observations.csv"),
                  repeatability_folds_sha256=sha(args.repeatability_dir/"folds.csv"),
                  summary=summaries(records),checks=checks,archives=audit,
                  caveat="Empirical template has additional per-cell fitted values; identical final gain allowance is not equal model complexity.")
    (args.output_dir/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    plot(args.output_dir/"population_tuning.png",cells)
    print(json.dumps(result["summary"],indent=2),flush=True)


if __name__=="__main__":
    main()

"""Frozen nested-CV causal AOTU response-memory experiment; offline only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import numpy as np

from .pursuit_physiology import (ARCHIVES, P1_ARCHIVES, ROOT, SEED, extract,
    model_tables, read_recording, sha, visible_segments, write_csv)

GRID = [(tau, lag) for tau in (0, 40, 100, 200) for lag in (0, 40, 80)]
SCENARIOS = ("pooled", "all_L", "all_R")
REGIONS = ("window", "tail", "pulse_mean")
DUPLICATE = "AOTU019/2023_06_15_fly03"


def prefix(value):
    return np.concatenate((np.zeros((*value.shape[:-1], 1)), np.cumsum(value, axis=-1)), axis=-1)


def interval(sums, lo, hi):
    if hi <= lo:
        raise ValueError("Empty observation interval")
    return (sums[..., hi] - sums[..., lo]) / (hi - lo)


def lookups():
    original, tables = model_tables()
    names = ["baseline"] + [f"baseline_shuffle_{k:02}" for k in range(32)] + ["simple_spatial", "intercept_only"]
    indices = [original.index(n) for n in names]
    result = {}
    for kind in ARCHIVES:
        right = tables[kind, "R"][indices]
        left = tables[kind, "L"][indices, ::-1, ::-1]
        result[kind] = np.concatenate(((left + right) / 2, left, right), axis=0)
    return names, result


def inputs(position, tables):
    visible = np.isfinite(position)
    angle = np.where(visible, position, 0)
    if np.any(np.abs(angle) > 180):
        raise ValueError("Position outside frozen lookup field")
    bins = (np.sign(angle) * np.floor(np.abs(angle) + .5)).astype(int) + 180
    direction = np.zeros(len(position), dtype=int)
    singleton = 0
    for start, stop in visible_segments(position):
        if stop - start < 2:
            visible[start:stop] = False
            singleton += 1
        else:
            slope = np.polyfit(np.arange(stop-start), position[start:stop], 1)[0]
            direction[start:stop] = int(slope > 0)
    return tables[:, direction, bins] * visible, singleton


def observation_kernel(dt):
    radius = int(round(.250 / dt))
    kernel = np.exp(-.5 * (np.arange(-radius, radius+1) * dt / .05)**2)
    return radius, kernel / kernel.sum()


def arithmetic_checks(dt, tables):
    from scipy.signal import fftconvolve, lfilter
    radius, kernel = observation_kernel(dt)
    stimulus = np.zeros(1600)
    stimulus[400:900] = np.linspace(.2, 1, 500)
    extended = np.pad(stimulus, (radius, radius + 5000))
    observation = fftconvolve(extended, kernel, mode="same")
    errors = []
    for tau, lag in GRID:
        alpha = np.exp(-dt/(tau/1000)) if tau else 0
        delay = int(round(lag / 1000 / dt))
        state = lfilter([1-alpha], [1, -alpha], extended)
        delayed = np.r_[np.zeros(delay), state][:len(state)]
        direct = fftconvolve(delayed, kernel, mode="same")
        swapped = lfilter([1-alpha], [1, -alpha], observation)
        swapped = np.r_[np.zeros(delay), swapped][:len(swapped)]
        errors.append(float(np.max(np.abs(direct[radius:radius+1600] - swapped[radius:radius+1600]))))
    if max(errors) > 1e-12:
        raise AssertionError("Causal/observation filter order disagrees")
    # Explicit recurrence also checks unity gain, causal support and pure lag.
    alpha = np.exp(-dt/.100)
    x = np.zeros(500); x[100:] = 1
    manual = np.zeros_like(x)
    for i in range(len(x)):
        manual[i] = alpha * (manual[i-1] if i else 0) + (1-alpha)*x[i]
    fast = lfilter([1-alpha], [1, -alpha], x)
    if not np.allclose(manual, fast, rtol=0, atol=1e-14) or np.any(fast[:100]):
        raise AssertionError("Response recurrence is not causal")
    for kind in tables:
        if not np.array_equal(tables[kind][:35], (tables[kind][35:70]+tables[kind][70:])/2):
            raise AssertionError("Hemisphere pooling changed")
    return {"filter_order_max_abs_error": max(errors), "recurrence_max_abs_error": float(np.max(np.abs(manual-fast)))}


def recording_moments(time, dt, data, pulses, table, names):
    from scipy.signal import fftconvolve, lfilter
    # speed group x region x timing x scenario/variant x (xx, xy, yy)
    moments = np.zeros((3, 3, len(GRID), len(SCENARIOS)*len(names), 3))
    counts = np.zeros(3, dtype=int)
    examples = []
    singles = 0
    check_error = None
    radius, kernel = observation_kernel(dt)
    for trial in range(data["int_panelps"].shape[1]):
        selected = [p for p in pulses if p["trial"] == trial and p["state"] == "quiescent"]
        if not selected:
            continue
        drive, single = inputs(data["int_panelps"][:, trial], table)
        singles += single
        padded = np.pad(drive, ((0, 0), (radius, radius)))
        filtered = fftconvolve(padded, kernel[None, :], mode="same", axes=1)
        if check_error is None:
            direct = np.convolve(padded[0], kernel, mode="same")
            check_error = float(np.max(np.abs(direct-filtered[0])))
            if check_error > 1e-12:
                raise AssertionError("Full-trial static observation filter disagrees")
        del drive, padded
        samples = np.arange(0, len(time), 7)
        rate = data["int_spikert"][samples, trial]
        ys, yys = prefix(rate), prefix(rate**2)
        specs = []
        for p in selected:
            start = p["start_sample"]; stop = start + len(p["position"]) - 2*p["margin"]
            lo, hi = start-p["margin"], stop+p["margin"]
            mask = np.flatnonzero((p["time"] >= -.250) & (p["time"] <= -.100))
            baselo, basehi = lo+int(mask[0]), lo+int(mask[-1])+1
            bounds = [(lo, hi), (stop+int(np.ceil(.050/dt)), hi), (start, stop)]
            bounds = [(int(np.searchsorted(samples, a)), int(np.searchsorted(samples, b))) for a,b in bounds]
            specs.append((p, baselo, basehi, bounds))
            counts[0] += 1; counts[1 if p["speed_deg_s"] == 25 else 2] += 1
        example_predictions = {}
        for tau in (0, 40, 100, 200):
            alpha = np.exp(-dt/(tau/1000)) if tau else 0
            state = filtered if tau == 0 else lfilter([1-alpha], [1, -alpha], filtered, axis=1)
            native_sum = prefix(state)
            for lag in (0, 40, 80):
                k = GRID.index((tau, lag)); delay = int(round(lag/1000/dt))
                prediction = state[:, radius+samples-delay]
                xs, xxs, xys = prefix(prediction), prefix(prediction**2), prefix(prediction*rate)
                for p, baselo, basehi, bounds in specs:
                    bx = interval(native_sum, baselo+radius-delay, basehi+radius-delay)
                    by = p["baseline_spikes_s"]
                    speed = 1 if p["speed_deg_s"] == 25 else 2
                    for region, (a,b) in enumerate(bounds):
                        mx, my = interval(xs,a,b), interval(ys,a,b)
                        if region == 2:
                            xx, xy, yy = (mx-bx)**2, (mx-bx)*(my-by), (my-by)**2
                        else:
                            xx = interval(xxs,a,b)-2*bx*mx+bx**2
                            xy = interval(xys,a,b)-bx*my-by*mx+bx*by
                            yy = interval(yys,a,b)-2*by*my+by**2
                        value = np.stack((np.maximum(xx,0), xy, np.full_like(xx,max(float(yy),0))), axis=-1)
                        moments[0,region,k] += value; moments[speed,region,k] += value
                        if check_error is not None and "direct_moment_checked" not in example_predictions:
                            g = 3.25
                            explicit = np.mean((g*(prediction[0,a:b]-bx[0])-(rate[a:b]-by))**2)
                            if region != 2 and abs(explicit-(g*g*xx[0]-2*g*xy[0]+yy)) > 1e-8:
                                raise AssertionError("Direct error disagrees with moments")
                            example_predictions["direct_moment_checked"] = True
                    target = 33.75 if p["type"] == "AOTU019" else 56.25
                    if p["direction"] == 1 and abs(p["center_deg"]-target)<1:
                        key = (p["trial"], p["start_sample"])
                        a,b = bounds[0]
                        if key not in example_predictions:
                            example_predictions[key] = {"fly": p["fly"], "type": p["type"], "speed": p["speed_deg_s"],
                                "duration_s": p["duration_s"], "time": time[samples[a:b]]-time[p["start_sample"]],
                                "measured": rate[a:b]-by, "predictions": np.zeros((len(GRID),2,b-a))}
                        example_predictions[key]["predictions"][k] = prediction[[0,names.index("simple_spatial")],a:b]-bx[[0,names.index("simple_spatial")],None]
        examples.extend(v for key,v in example_predictions.items() if isinstance(key,tuple))
        print(f"  trial {trial+1}/{data['int_panelps'].shape[1]}: {len(selected)} quiescent pulses", flush=True)
    for speed, count in enumerate(counts):
        if count:
            moments[speed] /= count
    return moments, counts, examples, {"singleton_segments_zeroed": singles, "static_filter_error": check_error}


def collect(data_dir, names, tables):
    records, audit, examples = [], [], []
    for condition, archives in (("NoP1",ARCHIVES),("P1",P1_ARCHIVES)):
        for kind,(filename,expected) in archives.items():
            path = data_dir/filename
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream,"md5").hexdigest()
            if digest != expected:
                raise ValueError("Archive checksum mismatch")
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind+"/"+Path(member).stem.removesuffix("_int")
                    if identity == DUPLICATE:
                        audit.append({"condition":condition,"fly":identity,"excluded_duplicate":True})
                        continue
                    payload = archive.read(member)
                    time,dt,data = read_recording(payload)
                    pulses,rejected = extract(time,dt,data,identity,kind,"R")  # canonical; physical side unused
                    moments,counts,example,checks = recording_moments(time,dt,data,pulses,tables[kind],names)
                    item = {"condition":condition,"type":kind,"fly":identity,"moments":moments,"counts":counts}
                    records.append(item)
                    examples.extend({**e,"condition":condition} for e in example)
                    finite = sum(len(visible_segments(data["int_panelps"][:,j])) for j in range(data["int_panelps"].shape[1]))
                    if len(pulses)+sum(rejected.values()) != finite:
                        raise AssertionError("Finite stimulus count mismatch")
                    audit.append({"condition":condition,"fly":identity,"member_sha256":hashlib.sha256(payload).hexdigest(),
                        "archive_md5":digest,"accepted_pulses":len(pulses),"quiescent_pulses":int(counts[0]),
                        "rejected":rejected,"finite_segments":finite,"dt_s":dt,**checks})
                    print(condition,identity,"complete",flush=True)
    return records,audit,examples


def fitted_gain(moment):
    return np.maximum(0, np.divide(moment[...,1],moment[...,0],out=np.zeros_like(moment[...,1]),where=moment[...,0]>1e-14))


def error(moment,gain):
    return np.sqrt(np.maximum(gain**2*moment[...,0]-2*gain*moment[...,1]+moment[...,2],0))


def nested_folds(records,names):
    rows = []
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            group = [r for r in records if r["condition"]==condition and r["type"]==kind]
            for train_speed,test_speed,label in ((0,0,"matched"),(1,2,"25_to_75"),(2,1,"75_to_25")):
                for held in group:
                    train = [r for r in group if r["fly"]!=held["fly"] and r["counts"][train_speed]]
                    if len(train)<3 or not held["counts"][test_speed]:
                        continue
                    train_values = np.stack([r["moments"][train_speed,0] for r in train])
                    total = train_values.sum(axis=0)
                    inner = []
                    for i,r in enumerate(train):
                        gain = fitted_gain((total-train_values[i])/(len(train)-1))
                        inner.append(error(train_values[i],gain))
                    timing = np.argmin(np.mean(inner,axis=0),axis=0)
                    train_mean = total/len(train)
                    gains = fitted_gain(train_mean)
                    for scenario,offset in zip(SCENARIOS,range(0,len(SCENARIOS)*len(names),len(names))):
                        for v,name in enumerate(names):
                            col = offset+v
                            for mode,k in (("static",0),("temporal",int(timing[col]))):
                                g = float(gains[k,col]); tau,lag = GRID[k]
                                metrics = error(held["moments"][test_speed,:,k,col],g)
                                rows.append({"condition":condition,"type":kind,"scenario":scenario,"transfer":label,
                                    "fly":held["fly"],"variant":name,"mode":mode,"train_recordings":len(train),
                                    "held_pulses":int(held["counts"][test_speed]),"tau_ms":tau,"lag_ms":lag,"gain":g,
                                    **{region+"_rmse_spikes_s":float(metrics[j]) for j,region in enumerate(REGIONS)}})
    return rows


def summary_rows(folds):
    groups = defaultdict(list)
    for r in folds:
        groups[r["condition"],r["type"],r["scenario"],r["transfer"],r["variant"]].append(r)
    summary = []
    for (condition,kind,scenario,transfer,variant),rows in sorted(groups.items()):
        static = {r["fly"]:r for r in rows if r["mode"]=="static"}
        temporal = {r["fly"]:r for r in rows if r["mode"]=="temporal"}
        for mode,values in (("static",static),("temporal",temporal)):
            scores = [r["window_rmse_spikes_s"] for r in values.values()]
            changes = [static[f]["window_rmse_spikes_s"]-temporal[f]["window_rmse_spikes_s"] for f in static]
            smean = np.mean([r["window_rmse_spikes_s"] for r in static.values()])
            summary.append({"condition":condition,"type":kind,"scenario":scenario,"transfer":transfer,"variant":variant,"mode":mode,
                "recordings":len(values),"pulses":sum(r["held_pulses"] for r in values.values()),
                "window_rmse_spikes_s":float(np.mean(scores)),"window_rmse_sem":float(np.std(scores,ddof=1)/np.sqrt(len(scores))),
                "tail_rmse_spikes_s":float(np.mean([r["tail_rmse_spikes_s"] for r in values.values()])),
                "pulse_mean_rmse_spikes_s":float(np.mean([r["pulse_mean_rmse_spikes_s"] for r in values.values()])),
                "temporal_reduction_percent":float(100*(smean-np.mean([r["window_rmse_spikes_s"] for r in temporal.values()]))/smean),
                "paired_improvement_mean":float(np.mean(changes)),"paired_improvement_sem":float(np.std(changes,ddof=1)/np.sqrt(len(changes))),
                "fraction_recordings_improved":float(np.mean(np.asarray(changes)>0)),
                "selected_timing_counts":dict(Counter(f"{r['tau_ms']}/{r['lag_ms']}" for r in temporal.values()))})
    return summary


def plot_examples(path,examples,folds):
    os.environ.setdefault("MPLCONFIGDIR",str(path.parent/"mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    coeff={(r["condition"],r["type"],r["fly"],r["variant"],r["mode"]):r for r in folds
        if r["scenario"]=="pooled" and r["transfer"]=="matched"}
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout="constrained")
    for row,kind in enumerate(ARCHIVES):
        for col,speed in enumerate((25,75)):
            group=[e for e in examples if e["condition"]=="P1" and e["type"]==kind and e["speed"]==speed]
            duration=float(np.median([e["duration_s"] for e in group]))
            grid=np.arange(-.240,duration+.240,.010)
            animals=defaultdict(list)
            for e in group:
                traces=[np.interp(grid,e["time"],e["measured"])]
                for variant,v in (("baseline",0),("simple_spatial",1)):
                    for mode in ("static","temporal"):
                        r=coeff[e["condition"],kind,e["fly"],variant,mode]
                        k=GRID.index((r["tau_ms"],r["lag_ms"]))
                        traces.append(np.interp(grid,e["time"],e["predictions"][k,v])*r["gain"])
                animals[e["fly"]].append(traces)
            values=np.stack([np.mean(v,axis=0) for v in animals.values()])
            mean=values.mean(axis=0); sem=values[:,0].std(axis=0,ddof=1)/np.sqrt(len(values))
            ax=axes[row,col]
            for i,label in enumerate(("measured","anatomy static","anatomy temporal","simple static","simple temporal")):
                ax.plot(grid,mean[i],label=label,color=("black","#56B4E9","#0072B2","#8CD8BD","#009E73")[i])
            ax.fill_between(grid,mean[0]-sem,mean[0]+sem,color="black",alpha=.12)
            ax.axvspan(0,duration,color="gray",alpha=.08)
            ax.set(title=f"{kind}: {speed} deg/s, {len(animals)} recordings",xlabel="Seconds from visible onset",ylabel="Evoked spikes/s")
    axes[0,0].legend(fontsize=8)
    fig.suptitle("P1 archive: held-recording temporal predictions, pooled model hemispheres\nKnown duplicate excluded; fixed positions and direction, recording SEM")
    fig.savefig(path,dpi=150,metadata={"Software":"Fly Creature temporal diagnostic"})
    plt.close(fig)


def run(data_dir,output_dir,reuse_cache=None):
    output_dir.mkdir(parents=True,exist_ok=True)
    frozen_paths=[ROOT/"src/fly_creature"/name for name in ("pursuit_controller.py","pursuit_activity.py","pursuit_step4.py",
        "pursuit_delay_diagnostic.py","pursuit_physiology.py","data/visual_steering_v1.json",
        "data/lc10a_registered_eyemap_hypothesis_v3.json","data/lc10a_column_footprints_v1.json")]
    frozen={str(p.relative_to(ROOT)):sha(p) for p in frozen_paths}
    source_hash=sha(Path(__file__)); protocol_hash=sha(ROOT/"docs/pursuit_temporal_protocol.md")
    names,tables=lookups()
    checks=arithmetic_checks(.0015000000000000568,tables)
    records,audit,examples=collect(data_dir,names,tables)
    folds=nested_folds(records,names)
    summary=summary_rows(folds)
    if frozen!={str(p.relative_to(ROOT)):sha(p) for p in frozen_paths}:
        raise AssertionError("Frozen source/input changed")
    ranks=[]
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            for scenario in SCENARIOS:
                for transfer in ("matched","25_to_75","75_to_25"):
                    group=[r for r in summary if r["condition"]==condition and r["type"]==kind and r["scenario"]==scenario and r["transfer"]==transfer and r["mode"]=="temporal"]
                    if not group: continue
                    scores={r["variant"]:r["window_rmse_spikes_s"] for r in group}
                    ranks.append({"condition":condition,"type":kind,"scenario":scenario,"transfer":transfer,
                        "baseline_beats_shuffles":sum(scores["baseline"]<scores[f"baseline_shuffle_{k:02}"] for k in range(32)),
                        "baseline_advantage_vs_simple_percent":100*(scores["simple_spatial"]-scores["baseline"])/scores["simple_spatial"]})
    gates={kind:all(r["temporal_reduction_percent"]>=5 and r["fraction_recordings_improved"]>=.6 for r in summary
        if r["condition"]=="P1" and r["type"]==kind and r["scenario"]=="pooled" and r["transfer"]=="matched" and r["variant"]=="baseline") for kind in ARCHIVES}
    result={"protocol":"pursuit_temporal_protocol.md","protocol_sha256":protocol_hash,"source_sha256":source_hash,"seed":SEED,
        "grid":GRID,"variants":names,"excluded_duplicate":DUPLICATE,"audit":audit,"summary":summary,"ranks":ranks,
        "promising_temporal_benefit_gate":gates,"frozen_code_and_input_sha256":frozen,
        "checks":{**checks,"frozen_hashes_unchanged":True,"held_recordings_excluded_from_all_training":True},
        "limitations":["Pooled hemispheres are a declared model average, not recovered physical side",
            "Archive conditions lack per-trial stimulation verification","Evoked baseline uses recorded pre-stimulus activity",
            "Single-pole dynamics are a hypothesis; no identified neural mechanism or causal P1 effect",
            "Evaluation uses an every-seventh-native-sample grid; prior raw-rate benchmark is a different estimand",
            "Previously inspected dataset is not a new cohort; nested holdouts protect this parameter selection only"]}
    write_csv(output_dir/"folds.csv",folds)
    flat=[{k:v for k,v in r.items() if k!="selected_timing_counts"} for r in summary]
    write_csv(output_dir/"summary.csv",flat)
    write_csv(output_dir/"ranks.csv",ranks)
    (output_dir/"report.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")
    plot_examples(output_dir/"temporal.png",examples,folds)
    print(json.dumps({"gates":gates,"primary":[r for r in summary if r["condition"]=="P1" and r["scenario"]=="pooled" and r["transfer"]=="matched" and r["variant"] in ("baseline","simple_spatial") and r["mode"]=="temporal"]},indent=2))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    run(args.data_dir,args.output_dir)


if __name__=="__main__":
    main()

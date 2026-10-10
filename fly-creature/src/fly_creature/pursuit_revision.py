"""Bounded offline directional-skew/visible-offset candidate with wiring controls."""
import argparse
from collections import defaultdict
import csv
import hashlib
import itertools
import json
from pathlib import Path
import zipfile

import numpy as np

from .pursuit_physiology import ARCHIVES,P1_ARCHIVES,ROOT,extract,read_recording,sha,visible_segments
from .pursuit_repeatability import DUPLICATE,cell,csv_write
from .pursuit_population import weights,signature
from .pursuit_temporal import lookups,inputs,observation_kernel

BOUND = 22.5


def collect(directory):
    from scipy.signal import fftconvolve
    names,tables = lookups()
    names = names[:-1]+["flat_visible"]
    tables = {kind:table[:35].copy() for kind,table in tables.items()}
    for table in tables.values():table[-1].fill(1.)
    feature_tables = {}
    for kind,table in tables.items():
        derivative = np.gradient(table,axis=-1)*np.array([-1,1])[None,:,None]
        feature_tables[kind] = np.concatenate((table+BOUND*derivative,table-BOUND*derivative,np.ones((1,2,361))),axis=0)
    observations,features,audit = [],[],[]
    convolution_error = 0.
    for condition,archives in (("NoP1",ARCHIVES),("P1",P1_ARCHIVES)):
        for kind,(filename,expected) in archives.items():
            path = directory/filename
            with path.open("rb") as stream:digest = hashlib.file_digest(stream,"md5").hexdigest()
            assert digest==expected
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind+"/"+Path(member).stem.removesuffix("_int")
                    if identity==DUPLICATE:continue
                    payload = archive.read(member)
                    time,dt,data = read_recording(payload)
                    pulses,rejected = extract(time,dt,data,identity,kind,"canonical")
                    assert len(pulses)+sum(rejected.values())==sum(len(visible_segments(data["int_panelps"][:,t])) for t in range(data["int_panelps"].shape[1]))
                    quiet = [p for p in pulses if p["state"]=="quiescent"]
                    radius,kernel = observation_kernel(dt)
                    grouped = defaultdict(list)
                    for trial in sorted(set(p["trial"] for p in quiet)):
                        drive,single = inputs(data["int_panelps"][:,trial],feature_tables[kind])
                        assert single==0
                        padded = np.pad(drive,((0,0),(radius,radius)))
                        filtered = fftconvolve(padded,kernel[None,:],mode="same",axes=1)[:,radius:radius+len(time)]
                        if trial==min(p["trial"] for p in quiet):
                            direct = np.convolve(padded[0],kernel,mode="same")[radius:radius+len(time)]
                            convolution_error = max(convolution_error,float(np.max(np.abs(direct-filtered[0]))))
                            assert convolution_error<1e-12
                        for p in (p for p in quiet if p["trial"]==trial):
                            start,margin = p["start_sample"],p["margin"]
                            stop = start+len(p["position"])-2*margin
                            lo,hi = start-margin,stop+margin
                            pre = (p["time"]>=-.250)&(p["time"]<=-.100)
                            raw = filtered[:,start:stop].mean(axis=1)-filtered[:,lo:hi][:,pre].mean(axis=1)
                            x = np.stack((raw[:35],raw[35:70],np.full(35,-raw[-1])),axis=1)
                            key = p["speed_deg_s"],p["direction"],int(round(p["center_deg"]/11.25)),trial
                            grouped[key].append((p["evoked_spikes_s"],x))
                    for (speed,direction,center,trial),values in sorted(grouped.items()):
                        observations.append(dict(condition=condition,type=kind,recording=identity,trial=trial,speed_deg_s=speed,
                                                 direction=direction,center_bin=center,response_spikes_s=float(np.mean([v[0] for v in values]))))
                        features.append(np.mean([v[1] for v in values],axis=0))
                    audit.append(dict(condition=condition,recording=identity,archive_md5=digest,member_sha256=hashlib.sha256(payload).hexdigest(),
                                      accepted=len(pulses),rejected=rejected,quiet=len(quiet)))
                    print(f"{condition} {identity}: {len(quiet)} pulses",flush=True)
    return observations,np.asarray(features),names,audit,convolution_error


def constrained_fit(gram,rhs):
    """Exact three-variable NNLS via active sets; independent SciPy checks follow."""
    best = np.zeros(3); score = 0.
    for size in (1,2,3):
        for subset in itertools.combinations(range(3),size):
            ids = list(subset)
            beta = np.linalg.lstsq(gram[np.ix_(ids,ids)],rhs[ids],rcond=None)[0]
            if np.any(beta< -1e-10):continue
            b = np.zeros(3);b[ids] = np.maximum(0.,beta)
            candidate = float(b @ gram @ b-2*b @ rhs)
            if candidate<score-1e-12:best,score = b,candidate
    return best


def selections(rows):
    grouped = defaultdict(lambda:defaultdict(list))
    for i,r in enumerate(rows):grouped[r["recording"]][cell(r)].append(i)
    good = {rec:{s:ids for s,ids in gs.items() if len({rows[i]["trial"] for i in ids})>=4} for rec,gs in grouped.items()}
    for identity,gs in sorted(good.items()):
        others = {rec:g for rec,g in good.items() if rec!=identity}
        held = [i for s,ids in gs.items() if sum(s in g for g in others.values())>=3 for i in ids]
        train = [i for rec,g in others.items() for s,ids in g.items() if sum(s in third for name,third in others.items() if name!=rec)>=3 for i in ids]
        yield identity,train,held


def loss(rows,pred,y):
    trials = defaultdict(list)
    for r,p,t in zip(rows,pred,y):trials[r["trial"]].append((p-t)**2)
    return float(np.sqrt(np.mean([np.mean(v) for v in trials.values()])))


def evaluate(rows,x,names):
    from scipy.optimize import nnls
    folds,summary,ranks = [],[],[]
    checks = dict(nnls_objective_max_error=0.,native_static_feature_max_error=0.)
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            ids = [i for i,r in enumerate(rows) if (r["condition"],r["type"])==(condition,kind)]
            rs = [rows[i] for i in ids];xs = x[ids]
            ys = np.array([r["response_spikes_s"] for r in rs])
            case_folds = []
            for identity,train,held in selections(rs):
                tr = [rs[i] for i in train];hr = [rs[i] for i in held]
                assert train and held and all(r["recording"]!=identity for r in tr)
                w = weights(tr);tx = xs[train];ty = ys[train]
                grams = np.einsum("i,imj,imk->mjk",w,tx,tx)
                rhs = np.einsum("i,imj,i->mj",w,tx,ty)
                for m,name in enumerate(names):
                    beta = constrained_fit(grams[m],rhs[m])
                    # Independently solve the actual weighted design for every fold.
                    independent,_ = nnls(np.sqrt(w)[:,None]*tx[:,m],np.sqrt(w)*ty,maxiter=100)
                    objective = lambda b: float(b @ grams[m] @ b-2*b @ rhs[m])
                    delta = abs(objective(beta)-objective(independent))
                    checks["nnls_objective_max_error"] = max(checks["nnls_objective_max_error"],delta)
                    assert delta<1e-8
                    f = (tx[:,m,0]+tx[:,m,1])/2
                    g = max(0.,float(w @ (f*ty))/float(w @ (f*f))) if float(w @ (f*f))>1e-14 else 0.
                    hx = xs[held,m];hy = ys[held]
                    static = g*(hx[:,0]+hx[:,1])/2
                    candidate = hx @ beta
                    total = float(beta[0]+beta[1])
                    row = dict(condition=condition,type=kind,recording=identity,variant=name,train_trial_cells=len(train),held_trial_cells=len(held),
                               static_rmse=loss(hr,static,hy),candidate_rmse=loss(hr,candidate,hy),static_gain=g,
                               u=float(beta[0]),v=float(beta[1]),q=float(beta[2]),gain=total,
                               equivalent_skew_deg=BOUND*float(beta[0]-beta[1])/total if total>1e-12 else 0.,
                               visible_offset=-float(beta[2]))
                    assert abs(row["equivalent_skew_deg"])<=BOUND+1e-10 and min(beta)>=0
                    case_folds.append(row)
            folds.extend(case_folds)
            for name in names:
                selected = [r for r in case_folds if r["variant"]==name]
                base = float(np.mean([r["static_rmse"] for r in selected]))
                candidate = float(np.mean([r["candidate_rmse"] for r in selected]))
                summary.append(dict(condition=condition,type=kind,variant=name,recordings=len(selected),
                                    static_rmse=base,candidate_rmse=candidate,reduction_percent=100*(1-candidate/base),
                                    recordings_improved=sum(r["candidate_rmse"]<r["static_rmse"] for r in selected),
                                    median_equivalent_skew_deg=float(np.median([r["equivalent_skew_deg"] for r in selected])),
                                    median_visible_offset=float(np.median([r["visible_offset"] for r in selected]))))
            ss = {r["variant"]:r for r in summary if (r["condition"],r["type"])==(condition,kind)}
            intact,simple = ss["baseline"],ss["simple_spatial"]
            beat = sum(intact["candidate_rmse"]<ss[f"baseline_shuffle_{k:02}"]["candidate_rmse"] for k in range(32))
            advantage = 100*(1-intact["candidate_rmse"]/simple["candidate_rmse"])
            ranks.append(dict(condition=condition,type=kind,shuffle_aggregates_beaten=beat,anatomy_vs_simple_percent=advantage,
                              predictive_gate=intact["reduction_percent"]>=5 and intact["recordings_improved"]>=.6*intact["recordings"],
                              wiring_gate=advantage>=1 and beat>=30))
    return folds,summary,ranks,checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",type=Path,default=ROOT/"outputs/research/aotu-recordings")
    p.add_argument("--output-dir",type=Path,required=True)
    args = p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    rows,x,names,audit,error = collect(args.data_dir)
    csv_write(args.output_dir/"observations.csv",rows)
    np.savez(args.output_dir/"features.npz",features=x)
    (args.output_dir/"feature_names.json").write_text(json.dumps(names)+"\n",encoding="utf-8",newline="\n")
    # Static features and common fold counts must reproduce the preceding assay.
    with (ROOT/"outputs/research/aotu-population-v1/observations.csv").open(encoding="utf-8",newline="") as stream:
        previous = {tuple(str(r[f]) for f in ("condition","type","recording","trial","speed_deg_s","direction","center_bin")):r for r in csv.DictReader(stream)}
    assert len(rows)==len(previous)==35484
    static_error = 0.
    for r,features in zip(rows,x):
        ref = previous[tuple(str(v) for v in signature(r))]
        assert abs(r["response_spikes_s"]-float(ref["response_spikes_s"]))<1e-12
        for m,key in ((0,"anatomy_x"),(33,"simple_spatial_x")):
            static_error = max(static_error,abs(float((features[m,0]+features[m,1])/2)-float(ref[key])))
    assert static_error<1e-12
    folds,summary,ranks,checks = evaluate(rows,x,names)
    checks.update(native_convolution_max_error=error,native_static_feature_max_error=static_error)
    for name,values in (("folds",folds),("summary",summary),("ranks",ranks)):
        csv_write(args.output_dir/(name+".csv"),values)
    protected = json.loads((ROOT/"outputs/research/aotu-population-v1/report.json").read_text(encoding="utf-8"))["frozen_component_sha256"]
    assert all(sha(ROOT/path)==digest for path,digest in protected.items())
    result = dict(protocol_sha256=sha(ROOT/"docs/pursuit_revision_protocol.md"),implementation_sha256=sha(Path(__file__)),
                  frozen_component_sha256=protected,checks=checks,summary=summary,ranks=ranks,archives=audit,
                  primary_predictive_gate=all(r["predictive_gate"] for r in ranks if r["condition"]=="P1"),
                  primary_wiring_gate=all(r["wiring_gate"] for r in ranks if r["condition"]=="P1"))
    (args.output_dir/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(ranks,indent=2),flush=True)


if __name__=="__main__":main()

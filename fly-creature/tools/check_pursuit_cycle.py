"""Independent saved-data checks for the pursuit improvement cycle."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def csv_rows(path):
    with path.open(encoding="utf-8",newline="") as stream:return list(csv.DictReader(stream))


def stim(r):return tuple(r[f] for f in ("speed_deg_s","direction","center_bin"))


def hierarchy(rows,values):
    grouped = defaultdict(lambda:defaultdict(list))
    for r,v in zip(rows,values):grouped[r["recording"]][r["trial"]].append(v)
    return float(np.mean([np.mean([np.mean(v) for v in ts.values()]) for ts in grouped.values()]))


def history(first,repeat):
    files = ("report.json","observations.csv","recording_cells.csv","population_cells.csv","history.png")
    assert all((first/n).read_bytes()==(repeat/n).read_bytes() for n in files)
    rows = csv_rows(first/"observations.csv")
    recorded = csv_rows(first/"recording_cells.csv")
    points = csv_rows(first/"population_cells.csv")
    report = json.loads((first/"report.json").read_text())
    assert len(rows)==report["quiet_pulses"]==35484
    max_error = 0.
    for r in rows:
        for label in ("near","early","far"):
            assert bool(r[label+"_baseline"])==bool(r[label+"_evoked"])
            if r[label+"_baseline"]:
                max_error = max(max_error,abs(float(r[label+"_evoked"])-(float(r["mean_spikes_s"])-float(r[label+"_baseline"]))))
    lookup = defaultdict(list)
    for r in rows:lookup[r["condition"],r["type"],r["recording"],*stim(r)].append(r)
    means = defaultdict(list)
    for r in recorded:
        center = str(int(round(float(r["center_deg"])/11.25)))
        raw = lookup[r["condition"],r["type"],r["recording"],r["speed_deg_s"],r["direction"],center]
        stratum = r["stratum"]
        filtered = [v for v in raw if stratum=="original" or
                    (all(v[b+"_evoked"] for b in ("near","early","far")) and
                     float(v["hidden_gap_s"])>=(2 if stratum=="isolated_2s" else .995 if stratum=="nominal_1s" else 1) and
                     (stratum!="first" or v["first_stimulus"]=="True"))]
        ts = defaultdict(list)
        for v in filtered:ts[v["trial"]].append(float(v[r["baseline"]+"_evoked"]))
        assert len(ts)==int(r["trials"])>=4
        expected = np.mean([np.mean(v) for v in ts.values()])
        max_error = max(max_error,abs(expected-float(r["evoked"])))
        means[r["condition"],r["type"],r["stratum"],r["baseline"],r["speed_deg_s"],r["direction"],r["center_deg"]].append(float(r["evoked"]))
    for r in points:
        ys = means[tuple(r[f] for f in ("condition","type","stratum","baseline","speed_deg_s","direction","center_deg"))]
        assert len(ys)==int(r["recordings"])>=3
        max_error = max(max_error,abs(np.mean(ys)-float(r["evoked"])))
    assert max_error<1e-10
    root = Path(__file__).resolve().parents[1]
    previous = csv_rows(root/"outputs/research/aotu-repeatability-v1/observations.csv")
    key = lambda r:tuple(r[f] for f in ("condition","type","recording","trial","speed_deg_s","direction","center_bin"))
    old = {key(r):float(r["response_spikes_s"]) for r in previous}
    assert len(old)==len(rows) and all(abs(float(r["near_evoked"])-old[key(r)])<1e-10 for r in rows)
    initial = json.loads((root/"outputs/research/aotu-history-v1/report.json").read_text())
    assert [s for s in report["summary"] if s["stratum"]!="nominal_1s"]==initial["summary"]
    assert sum(a["accepted"] for a in report["archives"])==65416
    assert sum(sum(a["rejected"].values()) for a in report["archives"])==158
    result = dict(byte_identical_repeat=True,paired_reference_arithmetic_max_error=max_error,
                  near_response_matches_previous=True,initial_frozen_strata_unchanged=True,
                  recording_and_population_aggregates_reconstructed=True,quiet_pulses=len(rows))
    (first/"checks.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    return result


def revision(first,repeat):
    from scipy.optimize import nnls
    files = ("report.json","observations.csv","features.npz","feature_names.json","folds.csv","summary.csv","ranks.csv","revision.png")
    equal = {n:(first/n).read_bytes()==(repeat/n).read_bytes() for n in files}
    assert all(equal.values())
    rows = csv_rows(first/"observations.csv");folds = csv_rows(first/"folds.csv")
    x = np.load(first/"features.npz")["features"]
    names = json.loads((first/"feature_names.json").read_text())
    report = json.loads((first/"report.json").read_text())
    root = Path(__file__).resolve().parents[1]
    assert hashlib.sha256((root/"src/fly_creature/pursuit_revision.py").read_bytes()).hexdigest()==report["implementation_sha256"]
    assert hashlib.sha256((root/"docs/pursuit_revision_protocol.md").read_bytes()).hexdigest()==report["protocol_sha256"]
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==v for p,v in report["frozen_component_sha256"].items())
    groups = defaultdict(lambda:defaultdict(list))
    for i,r in enumerate(rows):groups[r["condition"],r["type"],r["recording"]][stim(r)].append(i)
    good = {k:{s:vs for s,vs in gs.items() if len({rows[i]["trial"] for i in vs})>=4} for k,gs in groups.items()}
    cached = {}
    max_prediction,max_loss,max_opt = 0.,0.,0.
    prior = { (r["condition"],r["type"],r["recording"]):r for r in csv_rows(root/"outputs/research/aotu-population-v1/recordings.csv")}
    for f in folds:
        k = f["condition"],f["type"],f["recording"]
        if k not in cached:
            others = {other:g for other,g in good.items() if other[:2]==k[:2] and other!=k}
            held = [i for s,vs in good[k].items() if sum(s in g for g in others.values())>=3 for i in vs]
            train = [i for other,g in others.items() for s,vs in g.items() if sum(s in third for name,third in others.items() if name!=other)>=3 for i in vs]
            tr = [rows[i] for i in train];hr = [rows[i] for i in held]
            bytrial = defaultdict(list)
            for j,r in enumerate(tr):bytrial[r["recording"],r["trial"]].append(j)
            trial_count = defaultdict(set)
            for r in tr:trial_count[r["recording"]].add(r["trial"])
            w = np.array([1/(len(trial_count)*len(trial_count[r["recording"]])*len(bytrial[r["recording"],r["trial"]])) for r in tr])
            assert len(train)==int(prior[k]["calibration_trial_cells"]) and len(held)==int(prior[k]["scored_trial_cells"])
            cached[k] = train,held,tr,hr,w
        train,held,tr,hr,w = cached[k]
        assert len(train)==int(f["train_trial_cells"]) and len(held)==int(f["held_trial_cells"])
        m = names.index(f["variant"])
        tx,hx = x[train,m],x[held,m]
        y = np.array([float(rows[i]["response_spikes_s"]) for i in train])
        hy = np.array([float(rows[i]["response_spikes_s"]) for i in held])
        beta = np.array([float(f[b]) for b in ("u","v","q")])
        independent,_ = nnls(np.sqrt(w)[:,None]*tx,np.sqrt(w)*y,maxiter=100)
        max_opt = max(max_opt,abs(hierarchy(tr,(tx@beta-y)**2)-hierarchy(tr,(tx@independent-y)**2)))
        base = (tx[:,0]+tx[:,1])/2
        denom = hierarchy(tr,base*base)
        g = max(0.,hierarchy(tr,base*y)/denom) if denom>1e-14 else 0.
        for field,pred in (("static_rmse",g*(hx[:,0]+hx[:,1])/2),("candidate_rmse",hx@beta)):
            error = np.sqrt(hierarchy(hr,(pred-hy)**2))
            max_loss = max(max_loss,abs(error-float(f[field])))
        max_prediction = max(max_prediction,abs(g-float(f["static_gain"])))
        assert min(beta)>=0 and abs(float(f["equivalent_skew_deg"]))<=22.5+1e-10
        if f["variant"]=="baseline":assert abs(float(f["static_rmse"])-float(prior[k]["anatomy_rmse"]))<1e-10
        if f["variant"]=="simple_spatial":assert abs(float(f["static_rmse"])-float(prior[k]["simple_spatial_rmse"]))<1e-10
    assert max_loss<1e-10 and max_opt<1e-8 and max_prediction<1e-9
    summaries = csv_rows(first/"summary.csv")
    indexed = {}
    for s in summaries:
        fs = [f for f in folds if all(f[k]==s[k] for k in ("condition","type","variant"))]
        static = float(np.mean([float(f["static_rmse"]) for f in fs]))
        candidate = float(np.mean([float(f["candidate_rmse"]) for f in fs]))
        wins = sum(float(f["candidate_rmse"])<float(f["static_rmse"]) for f in fs)
        assert len(fs)==int(s["recordings"]) and wins==int(s["recordings_improved"])
        assert abs(static-float(s["static_rmse"]))<1e-10 and abs(candidate-float(s["candidate_rmse"]))<1e-10
        assert abs(100*(static-candidate)/static-float(s["reduction_percent"]))<1e-10
        indexed[s["condition"],s["type"],s["variant"]] = s
    for r in csv_rows(first/"ranks.csv"):
        k = r["condition"],r["type"]
        a,b = indexed[*k,"baseline"],indexed[*k,"simple_spatial"]
        beaten = sum(float(a["candidate_rmse"])<float(indexed[*k,f"baseline_shuffle_{i:02d}"]["candidate_rmse"]) for i in range(32))
        advantage = 100*(float(b["candidate_rmse"])-float(a["candidate_rmse"]))/float(b["candidate_rmse"])
        predictive = float(a["reduction_percent"])>=5 and int(a["recordings_improved"])>=.6*int(a["recordings"])
        assert beaten==int(r["shuffle_aggregates_beaten"]) and abs(advantage-float(r["anatomy_vs_simple_percent"]))<1e-10
        assert r["predictive_gate"]==str(predictive) and r["wiring_gate"]==str(advantage>=1 and beaten>=30)
    result = dict(byte_identical_repeat=equal,independently_reconstructed_recording_fits=len(folds),
                  independent_loss_max_error=max_loss,independent_static_gain_max_error=max_prediction,
                  independent_nnls_mse_max_error=max_opt,exact_previous_coverage_and_static_errors=True,
                  summaries_wiring_ranks_and_acceptance_gates_reconstructed=True,
                  source_and_frozen_components_unchanged=True)
    (first/"checks.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history",nargs=2,type=Path)
    p.add_argument("--revision",nargs=2,type=Path)
    a = p.parse_args()
    if a.history:print(json.dumps(history(*a.history),indent=2))
    if a.revision:print(json.dumps(revision(*a.revision),indent=2))


if __name__=="__main__":main()

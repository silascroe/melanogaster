"""Independently reconstruct the saved held-recording comparison and plot table."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

FIELDS = ("anatomy","simple_spatial","empirical","empirical_unscaled","constant","zero")


def load(path):
    with path.open(encoding="utf-8",newline="") as stream:
        rows = list(csv.DictReader(stream))
    numeric = {"trial","speed_deg_s","direction","center_bin","center_deg","response_spikes_s","anatomy_x","simple_spatial_x",
               "scored_trial_cells","calibration_trial_cells","calibration_recordings","recordings","measured_mean_spikes_s","measured_sem_spikes_s"}
    numeric.update(FIELDS)
    for r in rows:
        for k in numeric & r.keys():
            r[k] = float(r[k])
    return rows


def rec(r):
    return r["condition"],r["type"],r["recording"]


def stim(r):
    return r["speed_deg_s"],r["direction"],r["center_deg"]


def hierarchical_mean(rows,values):
    grouped = defaultdict(lambda:defaultdict(list))
    for r,v in zip(rows,values):
        grouped[r["recording"]][r["trial"]].append(v)
    return float(np.mean([np.mean([np.mean(v) for v in ts.values()]) for ts in grouped.values()]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first",type=Path)
    parser.add_argument("repeat",type=Path)
    args = parser.parse_args()
    artifacts = ("report.json","observations.csv","folds.csv","recordings.csv","recording_cells.csv","population_cells.csv","population_tuning.png")
    equality = {name:(args.first/name).read_bytes()==(args.repeat/name).read_bytes() for name in artifacts}
    assert all(equality.values())
    report = json.loads((args.first/"report.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    source = {"docs/pursuit_population_protocol.md":report["protocol_sha256"],
              "src/fly_creature/pursuit_population.py":report["implementation_sha256"],**report["frozen_component_sha256"]}
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==v for p,v in source.items())
    observations = load(args.first/"observations.csv")
    folds = load(args.first/"folds.csv")
    recordings = load(args.first/"recordings.csv")
    population = load(args.first/"population_cells.csv")
    grouped = defaultdict(lambda:defaultdict(list))
    for r in observations:
        grouped[rec(r)][stim(r)].append(r)
    good = {k:{s:v for s,v in g.items() if len(v)>=4} for k,g in grouped.items()}
    means = {k:{s:np.mean([r["response_spikes_s"] for r in v]) for s,v in g.items()} for k,g in good.items()}
    by_fold = defaultdict(list)
    for r in folds:
        by_fold[rec(r)].append(r)
    prediction_error,gain_error,loss_error,correlation_error = 0.,0.,0.,0.
    for rr in recordings:
        k = rec(rr)
        candidates = {other:m for other,m in means.items() if other[:2]==k[:2] and other!=k}
        train,empirical = [],[]
        for other,gs in good.items():
            if other not in candidates:
                continue
            for s,values in gs.items():
                predictors = [m[s] for third,m in candidates.items() if third!=other and s in m]
                if len(predictors)>=3:
                    train.extend(values)
                    empirical.extend([float(np.mean(predictors))]*len(values))
        assert len(train)==rr["calibration_trial_cells"]
        assert len({rec(r) for r in train})==rr["calibration_recordings"]
        assert all(rec(r)!=k for r in train)
        y = np.array([r["response_spikes_s"] for r in train])
        gains = {}
        for name in ("anatomy","simple_spatial","empirical"):
            x = np.array(empirical) if name=="empirical" else np.array([r[name+"_x"] for r in train])
            numerator = hierarchical_mean(train,x*y)
            denominator = hierarchical_mean(train,x*x)
            g = max(0.,numerator/denominator) if denominator>1e-14 else 0.
            gains[name] = g
            gain_error = max(gain_error,abs(g-float(rr[name+"_gain"])))
        constant = hierarchical_mean(train,y)
        gain_error = max(gain_error,abs(constant-float(rr["constant_spikes_s"])))
        selected = by_fold[k]
        assert len(selected)==rr["scored_trial_cells"]
        expected_coverage = {(r["trial"],s) for s,vs in good[k].items()
                             if sum(s in m for m in candidates.values())>=3 for r in vs}
        assert {(r["trial"],stim(r)) for r in selected}==expected_coverage
        for r in selected:
            s = stim(r)
            template = float(np.mean([m[s] for m in candidates.values() if s in m]))
            predictions = dict(anatomy=r["anatomy_x"]*gains["anatomy"],simple_spatial=r["simple_spatial_x"]*gains["simple_spatial"],
                               empirical=template*gains["empirical"],empirical_unscaled=template,constant=constant,zero=0.)
            prediction_error = max(prediction_error,max(abs(value-r[field]) for field,value in predictions.items()))
        for field in FIELDS:
            error = np.sqrt(hierarchical_mean(selected,[(r[field]-r["response_spikes_s"])**2 for r in selected]))
            loss_error = max(loss_error,abs(error-float(rr[field+"_rmse"])))
        shape_cells = defaultdict(list)
        for r in selected:
            shape_cells[stim(r)].append(r)
        ycell = np.array([np.mean([r["response_spikes_s"] for r in vs]) for vs in shape_cells.values()])
        for field in ("anatomy","simple_spatial","empirical"):
            xcell = np.array([np.mean([r[field] for r in vs]) for vs in shape_cells.values()])
            saved = rr[field+"_cell_correlation"]
            if np.std(xcell)<=1e-12 or np.std(ycell)<=1e-12:
                assert saved==""
            else:
                expected = np.corrcoef(xcell,ycell)[0,1]
                correlation_error = max(correlation_error,abs(expected-float(saved)))
    # Reconstruct plotted means directly from held trial predictions, without
    # using the intermediate recording-cell table created by the runner.
    by_cell = defaultdict(lambda:defaultdict(list))
    for r in folds:
        by_cell[r["condition"],r["type"],*stim(r)][r["recording"]].append(r)
    plot_error = 0.
    expected_plot_keys = {k for k,vs in by_cell.items() if len(vs)>=3}
    assert { (r["condition"],r["type"],*stim(r)) for r in population}==expected_plot_keys
    for r in population:
        group = by_cell[r["condition"],r["type"],*stim(r)]
        assert len(group)==r["recordings"]
        ys = [np.mean([v["response_spikes_s"] for v in vs]) for vs in group.values()]
        expected = dict(measured_mean_spikes_s=np.mean(ys),measured_sem_spikes_s=np.std(ys,ddof=1)/np.sqrt(len(ys)))
        expected.update({f:np.mean([np.mean([v[f] for v in vs]) for vs in group.values()]) for f in FIELDS})
        plot_error = max(plot_error,max(abs(value-r[field]) for field,value in expected.items()))
    assert prediction_error<1e-10 and gain_error<1e-9 and loss_error<1e-10 and plot_error<1e-10 and correlation_error<1e-10
    retained = [r for r in report["archives"] if "excluded" not in r]
    assert len(retained)==69 and len(observations)==35484 and len(folds)==34554
    assert sum(r["accepted"] for r in retained)==65416 and sum(sum(r["rejected"].values()) for r in retained)==158
    assert not any(r["recording"]=="AOTU019/2023_06_15_fly03" for r in observations)
    result = dict(byte_identical_repeat=equality,source_and_frozen_component_hashes_current=True,
                  reconstructed_outer_recordings=len(recordings),independent_predictions=len(folds),
                  independent_gain_max_error=gain_error,independent_prediction_max_error=prediction_error,
                  independent_loss_max_error=loss_error,independent_plot_mean_max_error=plot_error,
                  independent_cell_correlation_max_error=correlation_error,
                  inner_and_outer_recording_exclusion_and_coverage=True,interval_counts_and_duplicate_exclusion=True,
                  artifact_sha256={n:hashlib.sha256((args.first/n).read_bytes()).hexdigest() for n in artifacts})
    (args.first/"checks.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()

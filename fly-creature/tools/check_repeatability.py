"""Independent saved-artifact checks for the offline repeatability diagnostic."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

FEATURES = ("forward_on_mm_s", "abs_angular_on_deg_s", "forward_pre_mm_s", "abs_angular_pre_deg_s")


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def key(r):
    return tuple(r[f] for f in ("condition", "type", "recording"))


def stimulus(r):
    return tuple(r[f] for f in ("speed_deg_s", "direction", "center_bin"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("repeat", type=Path)
    args = parser.parse_args()
    equal = {name: (args.first/name).read_bytes() == (args.repeat/name).read_bytes()
             for name in ("report.json", "observations.csv", "folds.csv", "recordings.csv", "repeatability.png")}
    assert all(equal.values())
    observations = rows(args.first/"observations.csv")
    folds = rows(args.first/"folds.csv")
    recordings = rows(args.first/"recordings.csv")
    report = json.loads((args.first/"report.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    for field, path in (("protocol_sha256", root/"docs/pursuit_repeatability_protocol.md"),
                        ("implementation_sha256", root/"src/fly_creature/pursuit_repeatability.py")):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == report[field]
    by_record = defaultdict(lambda: defaultdict(list))
    for r in observations:
        by_record[key(r)][stimulus(r)].append(r)
    good = {k: {s:v for s,v in groups.items() if len(v)>=4} for k,groups in by_record.items()}
    indexed = defaultdict(list)
    for r in folds:
        indexed[key(r),r["trial"]].append(r)
    max_error, ridge_error = 0., 0.
    checked_recordings = set()
    for (k,trial), held in indexed.items():
        groups = {s:[r for r in v if r["trial"] != trial] for s,v in good[k].items()}
        train = [r for v in groups.values() for r in v]
        by_trial = defaultdict(list)
        for r in train:
            by_trial[r["trial"]].append(r)
        blind = np.mean([np.mean([float(r["response_spikes_s"]) for r in v]) for v in by_trial.values()])
        for r in held:
            s = stimulus(r)
            assert len(groups[s]) == int(r["same_cell_training_trials"]) >= 3
            assert len(by_trial) == int(r["training_trials"])
            same = np.mean([float(v["response_spikes_s"]) for v in groups[s]])
            others = [np.mean([float(v["response_spikes_s"]) for v in g[s]])
                      for other,g in good.items() if other[:2]==k[:2] and other!=k and s in g]
            assert len(others) == int(r["other_recording_count"]) >= 3
            max_error = max(max_error, abs(same-float(r["same_recording"])),
                            abs(blind-float(r["stimulus_blind"])),
                            abs(np.mean(others)-float(r["other_recordings"])))
        # Different numerical route: solve the weighted, augmented least-squares
        # problem directly, once per recording, without its held trial.
        if k not in checked_recordings:
            ym = {s:np.mean([float(r["response_spikes_s"]) for r in v]) for s,v in groups.items()}
            xm = {s:np.mean([[float(r[f]) for f in FEATURES] for r in v],axis=0) for s,v in groups.items()}
            x = np.array([[float(r[f]) for f in FEATURES] for r in train])-np.stack([xm[stimulus(r)] for r in train])
            y = np.array([float(r["response_spikes_s"])-ym[stimulus(r)] for r in train])
            w = np.array([1/len(by_trial[r["trial"]])/len(by_trial) for r in train])
            scale = np.sqrt(np.sum(w[:,None]*x*x,axis=0))
            scale[scale<=1e-12] = 1.
            design = np.vstack([np.sqrt(w)[:,None]*x/scale, np.sqrt(.1)*np.eye(4)])
            target = np.r_[np.sqrt(w)*y,np.zeros(4)]
            beta = np.linalg.lstsq(design,target,rcond=None)[0]
            for r in held:
                s = stimulus(r)
                estimate = ym[s]+((np.array([float(r[f]) for f in FEATURES])-xm[s])/scale)@beta
                ridge_error = max(ridge_error,abs(estimate-float(r["motor_augmented"])))
            checked_recordings.add(k)
    assert max_error<1e-10 and ridge_error<1e-10
    assert len(checked_recordings)==69 and len(observations)==35484
    for r in recordings:
        selected = [v for (k,t),vs in indexed.items() if k==key(r) for v in vs]
        assert len(selected)==int(r["scored_trial_cells"])
        for field in ("same_recording", "stimulus_blind", "other_recordings", "motor_augmented"):
            sq = defaultdict(list)
            for v in selected:
                sq[v["trial"]].append((float(v[field])-float(v["response_spikes_s"]))**2)
            error = np.sqrt(np.mean([np.mean(v) for v in sq.values()]))
            assert abs(error-float(r[field+"_rmse"]))<1e-10
    retained = [r for r in report["archives"] if "excluded" not in r]
    assert len(retained)==69 and sum(r["accepted"] for r in retained)==65416
    assert sum(sum(r["rejected"].values()) for r in retained)==158
    assert all("2023_06_15_fly03" not in r["recording"] for r in observations)
    checks = dict(byte_identical_repeat=equal, independently_checked_fold_rows=len(folds),
                  protocol_and_implementation_hashes_current=True,
                  independent_mean_max_error=max_error, augmented_least_squares_max_error=ridge_error,
                  independent_ridge_recordings=len(checked_recordings), recording_loss_checks=True,
                  duplicate_exclusion_and_interval_counts=True,
                  artifact_sha256={n:hashlib.sha256((args.first/n).read_bytes()).hexdigest() for n in equal})
    (args.first/"checks.json").write_text(json.dumps(checks,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(checks,indent=2))


if __name__ == "__main__":
    main()

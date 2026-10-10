"""Independently refit and verify the recorded-AOTU LC10a benchmark outputs."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import zipfile

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parent
sys.path.insert(0,str(ROOT/"src"))

from fly_creature.lc10a_response import LC10aVisualResponse, RetinalMotionFrontEnd, causal_envelope
from fly_creature.pursuit_activity import ActivityProjection
from fly_creature.pursuit_physiology import ARCHIVES,P1_ARCHIVES,read_recording,sha
from fly_creature.retina import RetinalRenderer


OUT=ROOT/"outputs/research/lc10a-recorded-benchmark-v1"
OBS=ROOT/"outputs/research/aotu-population-v1/observations.csv"
OLD_FOLDS=ROOT/"outputs/research/aotu-population-v1/folds.csv"
CONTRACT=ROOT/"docs/evidence/lc10a_benchmark_contract_v1.json"
PROTOCOL=ROOT/"docs/evidence/lc10a_benchmark_protocol_v1.json"
DUPLICATE="AOTU019/2023_06_15_fly03"
TOL=1e-10


def read_csv(path):
    with path.open(newline="",encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def key(row):
    return (str(row["condition"]),str(row["type"]),str(row["recording"]),
        int(row["trial"]),int(row["speed_deg_s"]),int(row["direction"]),int(row["center_bin"]))


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        allow_nan=False).encode()).hexdigest()


def close(a,b,tol=TOL):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=tol


def rebuild_scores(observations,raw,new_names,contract,old_folds):
    all_names=new_names+["legacy_intact","legacy_simple","constant","zero"]
    if raw.shape!=(len(observations),len(all_names)):
        raise ValueError("Saved raw predictor dimensions do not match observation table")
    key_index={key(row):i for i,row in enumerate(observations)}
    if len(key_index)!=len(observations):
        raise ValueError("Historical observation signatures are duplicated")
    old={key(row):row for row in old_folds}
    groups=defaultdict(list)
    for i,row in enumerate(observations):
        groups[(str(row["condition"]),str(row["type"]))].append(i)
    frozen={(row["condition"],row["type"],row["recording"]):row for row in contract["folds"]}
    recording_rows=[]
    held_keys=[];held_targets=[];held_predictions=[]
    for (condition,kind),indexes in sorted(groups.items()):
        recordings=defaultdict(lambda:defaultdict(list))
        for i in indexes:
            row=observations[i]
            cell=(int(row["speed_deg_s"]),int(row["direction"]),int(row["center_bin"]))
            recordings[str(row["recording"])][cell].append(i)
        eligible={record:{cell:items for cell,items in cells.items() if len(items)>=4}
                  for record,cells in recordings.items()}
        for held_record,held_cells in sorted(eligible.items()):
            train_groups={record:cells for record,cells in eligible.items() if record!=held_record}
            held=sorted((i for cell,items in held_cells.items()
                if sum(cell in cells for cells in train_groups.values())>=3 for i in items),
                key=lambda i:key(observations[i]))
            train=sorted((i for train_record,cells in train_groups.items()
                for cell,items in cells.items()
                if sum(cell in other for record,other in train_groups.items()
                       if record!=train_record)>=3 for i in items),
                key=lambda i:key(observations[i]))
            if not held or not train:
                raise ValueError(f"Empty frozen fold for {held_record}")
            rec_trials=defaultdict(set);trial_cell_counts=defaultdict(int)
            for i in train:
                row=observations[i];record=str(row["recording"]);trial=int(row["trial"])
                rec_trials[record].add(trial);trial_cell_counts[record,trial]+=1
            weights=np.asarray([1.0/(trial_cell_counts[
                str(observations[i]["recording"]),int(observations[i]["trial"])]
                *len(rec_trials[str(observations[i]["recording"])])*len(rec_trials))
                for i in train],dtype=np.float64)
            y=np.asarray([float(observations[i]["response_spikes_s"]) for i in train])
            held_signature=[key(observations[i]) for i in held]
            train_signature=[key(observations[i]) for i in train]
            fixed=frozen[condition,kind,held_record]
            if digest(held_signature)!=fixed["held_signature_sha256"]:
                raise ValueError(f"Held signature mismatch for {held_record}")
            if digest(train_signature)!=fixed["train_signature_sha256"]:
                raise ValueError(f"Train signature mismatch for {held_record}")
            if digest(y.tolist())!=fixed["train_target_sha256"]:
                raise ValueError(f"Training targets mismatch for {held_record}")
            if digest(weights.tolist())!=fixed["train_weights_sha256"]:
                raise ValueError(f"Training weights mismatch for {held_record}")
            x=raw[train]
            xx=np.sum(weights[:,None]*x*x,axis=0,dtype=np.float64)
            xy=np.sum(weights[:,None]*x*y[:,None],axis=0,dtype=np.float64)
            gain=np.maximum(0.0,np.divide(xy,xx,out=np.zeros_like(xy),where=xx!=0))
            for offset,legacy_name in enumerate(("anatomy","simple_spatial")):
                j=len(new_names)+offset
                if not close(gain[j],fixed["legacy_gains"][legacy_name]):
                    raise ValueError(f"Historical {legacy_name} gain mismatch: {held_record}")
            gain[len(new_names)+2]=float(weights@y)
            gain[len(new_names)+3]=0.0
            hy=np.asarray([float(observations[i]["response_spikes_s"]) for i in held])
            pred=raw[held]*gain[None,:]
            cell_rows=defaultdict(list)
            for local,i in enumerate(held):
                row=observations[i]
                cell_rows[(int(row["speed_deg_s"]),int(row["direction"]),int(row["center_bin"]))].append(local)
            cells=sorted(cell_rows)
            per_cell_pred=np.stack([pred[cell_rows[cell]].mean(axis=0) for cell in cells])
            per_cell_y=np.asarray([hy[cell_rows[cell]].mean() for cell in cells])
            rmse=np.sqrt(np.mean((per_cell_pred-per_cell_y[:,None])**2,axis=0))
            for j,name in enumerate(all_names):
                recording_rows.append({"condition":condition,"type":kind,"recording":held_record,
                    "predictor":name,"gain":float(gain[j]),"degenerate":bool(xx[j]==0),
                    "train_trial_cells":len(train),"train_recordings":len(rec_trials),
                    "held_trial_cells":len(held),"scored_cells":len(cells),
                    "rmse_spikes_s":float(rmse[j])})
            held_keys.extend(held_signature)
            held_targets.extend(hy.tolist())
            held_predictions.extend(pred.tolist())
    return (recording_rows,all_names,held_keys,np.asarray(held_targets),
            np.asarray(held_predictions))


def canonical_replay(data_dir:Path,output_dir:Path,witness_manifest:list[dict],
                     expected_runner_sha:str) -> dict:
    """Replay complete witness trials through renderer and public 2D component."""
    projection=ActivityProjection.from_packaged_data()
    response=LC10aVisualResponse(projection=projection)
    renderer=RetinalRenderer()
    archive_map={"NoP1":ARCHIVES,"P1":P1_ARCHIVES}
    results=[]
    for item in witness_manifest:
        condition,kind=item["condition"],item["type"]
        filename,_=archive_map[condition][kind]
        with zipfile.ZipFile(data_dir/filename) as archive:
            member=next(name for name in sorted(archive.namelist()) if name.endswith("_int.mat")
                and kind+"/"+Path(name).stem.removesuffix("_int")==item["recording"])
            payload=archive.read(member)
            member_sha=hashlib.sha256(payload).hexdigest()
            native,dt,data=read_recording(payload)
        witness_path=output_dir/item["witness_archive"]
        with np.load(witness_path,allow_pickle=False) as saved_witness:
            if str(saved_witness["source_sha"])!=expected_runner_sha:
                raise ValueError("Saved witness was generated by different runner source")
            if str(saved_witness["member_sha"])!=member_sha:
                raise ValueError("Saved witness input recording hash mismatch")
            saved_movies={"canonical":np.asarray(saved_witness["canonical"],dtype=np.float64),
                          "mirror":np.asarray(saved_witness["mirror"],dtype=np.float64)}
        trial=int(item["trial"])
        position=data["int_panelps"][:,trial]
        elapsed=native-native[0]
        grid_error=float(np.max(np.abs(elapsed-np.arange(len(elapsed))*dt),initial=0.0))
        if grid_error>1e-9 or len(position)!=int(item["native_samples"]):
            raise ValueError("Independent witness native grid/sample count mismatch")
        for side,label,expected_sha in (
            ("canonical","canonical",item["canonical_activity_sha256"]),
            ("mirror","mirror",item["mirror_activity_sha256"])):
            stimulus=position if side=="canonical" else -position
            frontend=RetinalMotionFrontEnd()
            features=np.empty((len(stimulus),len(projection.body_ids)),dtype=np.float64)
            for start in range(0,len(stimulus),32):
                stop=min(len(stimulus),start+32)
                contrasts=np.empty((stop-start,renderer.height_px,renderer.width_px),dtype=np.float64)
                motions=np.empty_like(contrasts)
                for local,index in enumerate(range(start,stop)):
                    center=stimulus[index]
                    probe={"target_present":bool(np.isfinite(center)),"shape":"rectangle",
                        "width_deg":11.25,"height_deg":60.0,
                        "center_azimuth_deg":float(center) if np.isfinite(center) else 0.0,
                        "center_elevation_deg":0.0,"azimuth_velocity_deg_s":0.0,
                        "onset_s":0.0,"visible_duration_s":float(elapsed[-1]+dt),
                        "weber_contrast":-1.0,
                        "surround":"uniform"}
                    image=renderer.render_linear(probe,float(elapsed[index]))
                    contrasts[local],motions[local]=frontend.step(image,float(elapsed[index]))
                features[start:stop]=response.spatial_features(
                    contrasts,motions,ablation="primary")[0]
            activity=causal_envelope(features,dt)
            saved=saved_movies[side]
            if saved.shape!=activity.shape:
                raise ValueError(f"Independent {side} activity shape mismatch")
            if not np.isfinite(saved).all() or not np.isfinite(activity).all():
                raise ValueError(f"Independent {side} activity contains nonfinite values")
            difference=np.abs(saved-activity)
            maximum=float(difference.max(initial=0.0))
            if maximum>1e-10:
                raise ValueError(f"Independent {side} replay feature/activity mismatch {maximum}")
            direct_hash=hashlib.sha256(np.asarray(activity,dtype="<f8").tobytes()).hexdigest()
            if item[f"{label}_activity_sha256"]==direct_hash:
                hash_match=True
            else:
                hash_match=False  # BLAS roundoff may alter bytes; numerical parity is decisive.
            results.append({"condition":condition,"type":kind,"recording":item["recording"],
                "trial":trial,"movie":side,"native_samples":len(position),
                "finite_samples":int(np.isfinite(position).sum()),
                "grid_error_s":grid_error,"max_abs_activity_difference":maximum,
                "exact_byte_hash_match":hash_match,"public_2d_replay_pass":True})
    return {"status":"pass","witness_trials":len(witness_manifest),
        "complete_movie_replays":len(results),"max_abs_activity_difference":
            max(r["max_abs_activity_difference"] for r in results),"results":results}


def run(output_dir:Path=OUT,data_dir:Path=ROOT/"outputs/research/aotu-recordings") -> dict:
    report=json.loads((output_dir/"report.json").read_text(encoding="utf-8"))
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    contract=json.loads(CONTRACT.read_text(encoding="utf-8"))
    if report["status"]!="complete" or report["contract_sha256"]!=sha(CONTRACT):
        raise ValueError("Benchmark report status/contract hash mismatch")
    if report["protocol_sha256"]!=sha(ROOT/"docs/lc10a_response_benchmark_protocol.md"):
        raise ValueError("Benchmark protocol hash mismatch")
    runner=ROOT/"src/fly_creature/lc10a_response_benchmark.py"
    if report["runner_sha256"]!=sha(runner):
        raise ValueError("Frozen scoring source changed after result generation")
    review=json.loads(Path(report["preflight_review"]).read_text(encoding="utf-8"))
    if review.get("status")!="pass":
        raise ValueError("Input/legacy preflight did not pass")
    observations=read_csv(OBS)
    historical_folds=read_csv(OLD_FOLDS)
    predictor_path=output_dir/"trial_cell_predictors.npz"
    held_path=output_dir/"held_predictions.npz"
    with np.load(predictor_path,allow_pickle=False) as saved:
        raw_new=saved["predictions"].astype(np.float64)
        new_names=[str(value) for value in saved["predictor_names"]]
        row_keys=[tuple(json.loads(str(value))) for value in saved["keys"]]
        targets=saved["targets"].astype(np.float64)
    expected_keys=[key(row) for row in observations]
    if row_keys!=expected_keys:
        raise ValueError("Saved raw predictors do not align with immutable observation signatures")
    if len(new_names)!=protocol["new_predictor_count"] or len(set(new_names))!=len(new_names):
        raise ValueError("Saved predictor list differs from frozen 345-predictor budget")
    if raw_new.shape!=(len(observations),345) or not np.isfinite(raw_new).all():
        raise ValueError("Saved full predictor matrix is missing/nonfinite")
    if len(targets)!=len(observations) or not np.array_equal(targets,
        np.asarray([float(row["response_spikes_s"]) for row in observations])):
        raise ValueError("Saved observations targets differ from historical artifact")
    legacy=np.asarray([[float(row["anatomy_x"]),float(row["simple_spatial_x"]),1.0,0.0]
        for row in observations],dtype=np.float64)
    raw=np.concatenate((raw_new,legacy),axis=1)
    rebuilt,all_names,held_keys,held_targets,held_values=rebuild_scores(
        observations,raw,new_names,contract,historical_folds)
    reported=read_csv(output_dir/"recording_scores.csv")
    index={(r["condition"],r["type"],r["recording"],r["predictor"]):r for r in reported}
    if len(index)!=len(reported) or len(index)!=len(rebuilt):
        raise ValueError("Saved recording score table has duplicate/missing entries")
    max_gain=max_rmse=0.0
    for row in rebuilt:
        key4=(row["condition"],row["type"],row["recording"],row["predictor"])
        stored=index[key4]
        if not math.isfinite(float(stored["gain"])) or not math.isfinite(float(stored["rmse_spikes_s"])):
            raise ValueError(f"Saved recording score contains nonfinite values: {key4}")
        gain_error=abs(row["gain"]-float(stored["gain"]))
        rmse_error=abs(row["rmse_spikes_s"]-float(stored["rmse_spikes_s"]))
        max_gain=max(max_gain,gain_error);max_rmse=max(max_rmse,rmse_error)
        if gain_error>TOL or rmse_error>TOL or row["degenerate"]!=(stored["degenerate"].lower()=="true"):
            raise ValueError(f"Independent fold/gain/RMSE mismatch: {key4}")
    with np.load(held_path,allow_pickle=False) as saved:
        held_saved=np.asarray(saved["predictions"],dtype=np.float64)
        saved_keys=[tuple(json.loads(str(value))) for value in saved["keys"]]
        saved_names=[str(value) for value in saved["predictor_names"]]
        saved_targets=np.asarray(saved["targets"],dtype=np.float64)
    if held_saved.shape!=held_values.shape or not np.isfinite(held_saved).all():
        raise ValueError("Saved out-of-fold predictions have wrong shape or nonfinite values")
    held_error=float(np.max(np.abs(held_saved-held_values),initial=0.0))
    if saved_names!=all_names or saved_keys!=held_keys or held_error>TOL or not np.array_equal(saved_targets,held_targets):
        raise ValueError("Saved out-of-fold predictions disagree with independent refit")
    # Independently inspect aggregate primary gates, not only the CSV values.
    gate_report={}
    for kind in ("AOTU019","AOTU025"):
        rows=[r for r in rebuilt if r["condition"]=="P1" and r["type"]==kind]
        score={(r["recording"],r["predictor"]):r["rmse_spikes_s"] for r in rows}
        mean=lambda name:float(np.mean([r["rmse_spikes_s"] for r in rows if r["predictor"]==name]))
        intact=mean("primary:intact");legacy_mean=mean("legacy_intact")
        spatial=mean("primary:matched_spatial")
        shuffles=sum(mean(f"primary:shuffle_{i:02}")>intact for i in range(32))
        records=sorted({r["recording"] for r in rows})
        wins=sum(score[rec,"primary:intact"]<score[rec,"legacy_intact"] for rec in records)
        reduction=1.0-intact/legacy_mean if legacy_mean else None
        spatial_reduction=1.0-intact/spatial if spatial else None
        expected={"legacy_rmse_reduction_fraction":reduction,
            "legacy_recording_wins":wins,"shuffle_strict_wins":shuffles,
            "spatial_rmse_reduction_fraction":spatial_reduction}
        gate_report[kind]=expected
        announced=report["scores"]["primary_gates"][kind]
        for field,value in expected.items():
            if not close(announced[field],value):
                raise ValueError(f"Primary gate field disagrees with recomputation: {kind}/{field}")
    representation=read_csv(output_dir/"representation.csv")
    if not representation or any(not math.isfinite(float(r["max_peak_excess"]))
        or float(r["max_peak_excess"])>1e-9 for r in representation):
        raise ValueError("Representation/peak gate is missing or failed")
    sensor=canonical_replay(data_dir,output_dir,report["independent_replay_witnesses"],
                            report["runner_sha256"])
    result={"status":"pass","independent_fold_reconstruction":"pass",
        "recording_score_rows":len(rebuilt),"predictors":len(all_names),
        "max_gain_difference":max_gain,"max_recording_rmse_difference":max_rmse,
        "held_prediction_max_abs_difference":held_error,"primary_gate_reconstruction":gate_report,
        "representation_rows":len(representation),"representation_peak_overflow":"none",
        "sensor_replay":sensor}
    (output_dir/"check_report.json").write_text(json.dumps(result,indent=2,sort_keys=True,
        allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUT)
    parser.add_argument("--data-dir",type=Path,default=ROOT/"outputs/research/aotu-recordings")
    args=parser.parse_args()
    result=run(args.output_dir,args.data_dir)
    print(json.dumps({"status":result["status"],"recording_score_rows":result["recording_score_rows"],
        "predictors":result["predictors"],"held_prediction_max_abs_difference":
        result["held_prediction_max_abs_difference"],"sensor_replay":result["sensor_replay"]["status"]},
        indent=2),flush=True)


if __name__=="__main__":
    main()

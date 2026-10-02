"""Offline target-history and paired baseline sensitivity audit."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from .pursuit_physiology import ARCHIVES,P1_ARCHIVES,ROOT,extract,read_recording,sha,visible_segments
from .pursuit_repeatability import DUPLICATE,cell,csv_write

WINDOWS = {"near":(-.250,-.100),"early":(-.550,-.400),"far":(-.950,-.800)}


def collect(directory):
    rows,audit = [],[]
    for condition,archives in (("NoP1",ARCHIVES),("P1",P1_ARCHIVES)):
        for kind,(name,expected) in archives.items():
            path = directory/name
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream,"md5").hexdigest()
            assert digest==expected
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity = kind+"/"+Path(member).stem.removesuffix("_int")
                    if identity==DUPLICATE:
                        continue
                    payload = archive.read(member)
                    time,dt,data = read_recording(payload)
                    pulses,rejected = extract(time,dt,data,identity,kind,"canonical")
                    segments = [visible_segments(data["int_panelps"][:,t]) for t in range(data["int_panelps"].shape[1])]
                    assert len(pulses)+sum(rejected.values())==sum(map(len,segments))
                    quiet = [p for p in pulses if p["state"]=="quiescent"]
                    for p in quiet:
                        start,trial,margin = p["start_sample"],p["trial"],p["margin"]
                        stop = start+len(p["position"])-2*margin
                        previous = [(a,b) for a,b in segments[trial] if b<=start]
                        prev = previous[-1] if previous else None
                        gap = (start-(prev[1] if prev else 0))*dt
                        r = dict(condition=condition,type=kind,recording=identity,trial=trial,
                                 speed_deg_s=p["speed_deg_s"],direction=p["direction"],
                                 center_bin=int(round(p["center_deg"]/11.25)),start_sample=start,
                                 onset_s=float(time[start]-time[0]),hidden_gap_s=float(gap),first_stimulus=not bool(prev),
                                 previous_center_deg=float(np.mean(data["int_panelps"][prev[0]:prev[1],trial])) if prev else None,
                                 previous_direction=int(np.sign(data["int_panelps"][prev[1]-1,trial]-data["int_panelps"][prev[0],trial])) if prev else None,
                                 mean_spikes_s=p["mean_spikes_s"],
                                 tail_spikes_s=float(data["int_spikert"][stop+int(np.ceil(.1/dt)):stop+margin,trial].mean()))
                        for label,(lo,hi) in WINDOWS.items():
                            rel = time-time[start]
                            mask = (rel>=lo)&(rel<=hi)
                            valid = time[start]+lo>=time[0] and mask.any() and not np.isfinite(data["int_panelps"][mask,trial]).any()
                            r[label+"_baseline"] = float(data["int_spikert"][mask,trial].mean()) if valid else None
                            r[label+"_evoked"] = p["mean_spikes_s"]-r[label+"_baseline"] if valid else None
                        assert r["near_evoked"] is not None and abs(r["near_evoked"]-p["evoked_spikes_s"])<1e-10
                        rows.append(r)
                    audit.append(dict(condition=condition,recording=identity,archive_md5=digest,member_sha256=hashlib.sha256(payload).hexdigest(),
                                      accepted=len(pulses),rejected=rejected,quiet=len(quiet)))
                    print(f"{condition} {identity}: {len(quiet)} quiet pulses",flush=True)
    return rows,audit


def aggregate(rows):
    records,cells,coverage = [],[],[]
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            pool = [r for r in rows if (r["condition"],r["type"])==(condition,kind)]
            for stratum in ("original","isolated_1s","isolated_2s","first","nominal_1s"):
                selected = [r for r in pool if stratum=="original" or
                            (all(r[label+"_evoked"] is not None for label in WINDOWS) and
                             (r["hidden_gap_s"]>= (2 if stratum=="isolated_2s" else .995 if stratum=="nominal_1s" else 1)) and
                             (stratum!="first" or r["first_stimulus"]))]
                grouped = defaultdict(lambda:defaultdict(lambda:defaultdict(list)))
                for r in selected:
                    grouped[r["recording"]][cell(r)][r["trial"]].append(r)
                good = {rec:{s:ts for s,ts in gs.items() if len(ts)>=4} for rec,gs in grouped.items()}
                coverage.append(dict(condition=condition,type=kind,stratum=stratum,pulses=len(selected),
                                     eligible_recordings=sum(bool(g) for g in good.values()),
                                     gap_quantiles=np.quantile([r["hidden_gap_s"] for r in selected],[0,.1,.5,.9,1]).tolist() if selected else []))
                cell_means = defaultdict(list)
                for identity,gs in good.items():
                    for s,ts in gs.items():
                        trial_rows = list(ts.values())
                        for baseline in ("near",) if stratum=="original" else WINDOWS:
                            response = float(np.mean([np.mean([r[baseline+"_evoked"] for r in vs]) for vs in trial_rows]))
                            rate = float(np.mean([np.mean([r["mean_spikes_s"] for r in vs]) for vs in trial_rows]))
                            ref = float(np.mean([np.mean([r[baseline+"_baseline"] for r in vs]) for vs in trial_rows]))
                            row = dict(condition=condition,type=kind,stratum=stratum,baseline=baseline,recording=identity,
                                       speed_deg_s=s[0],direction=s[1],center_deg=s[2]*11.25,trials=len(ts),
                                       evoked=response,rate=rate,reference=ref)
                            records.append(row)
                            cell_means[baseline,*s].append(row)
                for (baseline,speed,direction,center),values in sorted(cell_means.items()):
                    if len(values)<3:
                        continue
                    y = np.array([r["evoked"] for r in values])
                    cells.append(dict(condition=condition,type=kind,stratum=stratum,baseline=baseline,
                                      speed_deg_s=speed,direction=direction,center_deg=center*11.25,recordings=len(values),
                                      evoked=float(y.mean()),sem=float(y.std(ddof=1)/np.sqrt(len(y))),
                                      rate=float(np.mean([r["rate"] for r in values])),reference=float(np.mean([r["reference"] for r in values]))))
    return records,cells,coverage


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir",type=Path,default=ROOT/"outputs/research/aotu-recordings")
    p.add_argument("--output-dir",type=Path,required=True)
    args = p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    rows,audit = collect(args.data_dir)
    records,cells,coverage = aggregate(rows)
    for name,values in (("observations",rows),("recording_cells",records),("population_cells",cells)):
        csv_write(args.output_dir/(name+".csv"),values)
    summary = []
    for condition in ("NoP1","P1"):
        for kind in ARCHIVES:
            for stratum in ("original","isolated_1s","isolated_2s","first","nominal_1s"):
                for baseline in ("near",) if stratum=="original" else WINDOWS:
                    selected = [r for r in records if (r["condition"],r["type"],r["stratum"],r["baseline"])==(condition,kind,stratum,baseline) and r["center_deg"]<=0]
                    byrecord = defaultdict(list)
                    for r in selected:byrecord[r["recording"]].append(r["evoked"])
                    ys = [float(np.mean(v)) for v in byrecord.values()]
                    points = [r for r in cells if (r["condition"],r["type"],r["stratum"],r["baseline"])==(condition,kind,stratum,baseline)]
                    peaks = {}
                    for speed in (25,75):
                        for direction in (-1,1):
                            vs = [r for r in points if (r["speed_deg_s"],r["direction"])==(speed,direction)]
                            if vs:peaks[f"{speed}/{direction}"] = max(vs,key=lambda r:r["evoked"])["center_deg"]
                    summary.append(dict(condition=condition,type=kind,stratum=stratum,baseline=baseline,
                                        nonpreferred_recordings=len(ys),nonpreferred_mean=float(np.mean(ys)) if ys else None,
                                        nonpreferred_negative_recordings=sum(y<0 for y in ys),peak_centers_deg=peaks))
    report = dict(protocol_sha256=sha(ROOT/"docs/pursuit_goal_protocol.md"),implementation_sha256=sha(Path(__file__)),
                  posthoc_sensitivity_sha256=sha(ROOT/"docs/pursuit_history_sensitivity.md"),
                  archives=audit,coverage=coverage,summary=summary,quiet_pulses=len(rows))
    (args.output_dir/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(coverage,indent=2),flush=True)


if __name__=="__main__":main()

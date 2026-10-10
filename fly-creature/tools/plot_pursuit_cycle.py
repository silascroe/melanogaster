"""Deterministic inspection figures from saved pursuit goal artifacts."""
import argparse
from collections import defaultdict
import csv
import os
from pathlib import Path

import numpy as np


def rows(path):
    with path.open(encoding="utf-8",newline="") as stream:return list(csv.DictReader(stream))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history",type=Path)
    p.add_argument("--revision",type=Path)
    args = p.parse_args()
    target = args.history or args.revision
    os.environ.setdefault("MPLCONFIGDIR",str(target/"mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if args.history:
        cells = rows(args.history/"population_cells.csv")
        fig,axes = plt.subplots(4,2,figsize=(12,12),constrained_layout=True)
        for i,(kind,direction) in enumerate(( (k,d) for k in ("AOTU019","AOTU025") for d in (-1,1))):
            for j,speed in enumerate((25,75)):
                ax = axes[i,j]
                for baseline,color in (("near","#2166ac"),("early","#d66024"),("far","#278449")):
                    selected = sorted([r for r in cells if (r["condition"],r["type"],r["stratum"],r["baseline"],r["speed_deg_s"],r["direction"])==
                                       ("P1",kind,"nominal_1s",baseline,str(speed),str(direction))],key=lambda r:float(r["center_deg"]))
                    ax.plot([float(r["center_deg"]) for r in selected],[float(r["evoked"]) for r in selected],marker="o",markersize=3,color=color,label=baseline+" baseline")
                ax.axhline(0,color="gray",linewidth=.5)
                ax.set_title(f"{kind} | direction {direction:+d} | {speed} deg/s")
                ax.set_xlabel("Nominal center (degrees, ipsilateral positive)")
                ax.set_ylabel("Evoked pulse mean (spikes/s)")
        axes[0,0].legend(fontsize=8)
        fig.suptitle("Paired reference windows on identical nominal-one-second isolated pulses\nTiming-tolerance sensitivity; earlier baselines can include previous-target tails",fontsize=12)
        fig.savefig(args.history/"history.png",dpi=150,metadata={"Software":"Fly Creature pursuit goal"});plt.close(fig)
    if args.revision:
        observations = rows(args.revision/"observations.csv")
        fits = rows(args.revision/"folds.csv")
        x = np.load(args.revision/"features.npz")["features"]
        params = {(r["condition"],r["type"],r["recording"],r["variant"]):r for r in fits}
        grouped = defaultdict(lambda:defaultdict(list))
        for r,features in zip(observations,x):
            if r["condition"]!="P1":continue
            key = r["condition"],r["type"],r["recording"]
            entry = {"measured":float(r["response_spikes_s"])}
            for name,index in (("baseline",0),("simple_spatial",33)):
                f = params[*key,name]
                b = np.array([float(f[k]) for k in ("u","v","q")])
                entry[name] = float(features[index]@b)
                entry[name+"_static"] = float((features[index,0]+features[index,1])/2)*float(f["static_gain"])
            grouped[r["type"],r["speed_deg_s"],r["direction"],r["center_bin"]][r["recording"]].append(entry)
        # Match scoring: only cells with four trials in a recording, and at
        # least three other eligible recordings, participate in held plots.
        cells = []
        for (kind,speed,direction,center),byrecord in grouped.items():
            eligible = {k:v for k,v in byrecord.items() if len(v)>=4}
            if len(eligible)<4:continue
            cell = dict(type=kind,speed=int(speed),direction=int(direction),center=float(center)*11.25,recordings=len(eligible))
            cell.update({f:float(np.mean([np.mean([v[f] for v in vs]) for vs in eligible.values()])) for f in ("measured","baseline","simple_spatial","baseline_static","simple_spatial_static")})
            cells.append(cell)
        fig,axes = plt.subplots(4,2,figsize=(12,12),constrained_layout=True)
        for i,(kind,direction) in enumerate(( (k,d) for k in ("AOTU019","AOTU025") for d in (-1,1))):
            for j,speed in enumerate((25,75)):
                ax = axes[i,j]
                selected = sorted([r for r in cells if (r["type"],r["direction"],r["speed"])==(kind,direction,speed)],key=lambda r:r["center"])
                for f,color,label,style in (("measured","#222222","Measured","-"),("baseline_static","#2166ac","Frozen anatomy","--"),
                                            ("baseline","#2166ac","Corrected anatomy","-"),("simple_spatial","#d66024","Corrected simple","-")):
                    ax.plot([r["center"] for r in selected],[r[f] for r in selected],linestyle=style,color=color,label=label,marker="o" if f=="measured" else None,markersize=3)
                ax.axhline(0,color="gray",linewidth=.5)
                ax.set_title(f"{kind} | direction {direction:+d} | {speed} deg/s")
                ax.set_xlabel("Nominal center (degrees, ipsilateral positive)")
                ax.set_ylabel("Evoked pulse mean (spikes/s)")
        axes[0,0].legend(fontsize=8)
        fig.suptitle("Exploratory held-recording correction: matched nuisance terms for every wiring/control\nSigned evoked responses are a phenomenological diagnostic, not a biophysical neuron",fontsize=12)
        fig.savefig(args.revision/"revision.png",dpi=150,metadata={"Software":"Fly Creature pursuit goal"});plt.close(fig)


if __name__=="__main__":main()

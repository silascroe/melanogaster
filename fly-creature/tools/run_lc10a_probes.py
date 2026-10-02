"""Render a finite-angular probe matrix and save image/timing diagnostics only."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from fly_creature.retina import RetinalRenderer, write_gray_png  # noqa: E402


EXAMPLES = ("width_5_R","width_30_R","height_60_R",
            "dot10_dir1_unstimulated_R","dot25_dir-1_P1_stimulated_R",
            "surround_75_R","contrast_1_R","bar_25_1_15_R")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_probes(path: Path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        probes = list(csv.DictReader(stream))
    if not probes or len({p["probe_id"] for p in probes})!=len(probes):
        raise ValueError("Probe CSV is empty or has duplicate IDs")
    return probes


def write_preview(output: Path, cards):
    width,height,columns,rows,scale = 1460,960,4,2,2
    cell_w,cell_h = width//columns,height//rows
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#d8e0e5"/>']
    for i,(probe,label,time_s,png_path) in enumerate(cards):
        x,y = (i%columns)*cell_w,(i//columns)*cell_h
        encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
        title = html.escape(f"{probe} — {label}, t={time_s:.3f}s")
        parts.append(f'<text x="{x+10}" y="{y+22}" font-family="sans-serif" font-size="16">{title}</text>')
        parts.append(f'<image x="{x+10}" y="{y+35}" width="{RetinalRenderer().width_px*scale}" height="{RetinalRenderer().height_px*scale}" image-rendering="pixelated" href="data:image/png;base64,{encoded}"/>')
    parts.append("</svg>")
    output.write_text("\n".join(parts)+"\n",encoding="utf-8",newline="\n")


def run(matrix: Path, out: Path, sample_interval: float):
    if not math.isfinite(sample_interval) or sample_interval<0:
        raise ValueError("Sample interval must be finite and nonnegative")
    probes=load_probes(matrix)
    out.mkdir(parents=True,exist_ok=True)
    renderer=RetinalRenderer()
    selected={name for name in EXAMPLES}
    by_id={p["probe_id"]:p for p in probes}
    missing=selected-set(by_id)
    if missing:raise ValueError(f"Contract examples missing from matrix: {sorted(missing)}")
    time_rows=[];summary=[];cards=[]
    for probe in probes:
        trial=float(probe.get("trial_duration_s",3.) or 3.)
        if trial<=0 or not math.isfinite(trial):raise ValueError("Invalid probe trial duration")
        step=float(probe["dt_s"])
        if step<=0 or not math.isfinite(step):raise ValueError("Invalid probe time step")
        if sample_interval>0 and sample_interval<step-1e-12:
            raise ValueError("Diagnostic sample interval cannot be finer than probe dt_s")
        times=np.arange(0.,trial-1e-12,step if sample_interval<=0 else sample_interval)
        onset=float(probe["onset_s"]);duration=float(probe["visible_duration_s"])
        preview_times=(onset+min(step,duration/4),onset+duration/2,
                       onset+duration-min(step,duration/4))
        preview_indices={int(np.argmin(np.abs(times-t))) for t in preview_times}
        all_hash=hashlib.sha256();target_areas=[];means=[];lo=math.inf;hi=-math.inf
        for frame_index,time_s in enumerate(times):
            linear=renderer.render_linear(probe,float(time_s))
            gray=np.rint(np.clip(linear,0.,2.)*127.5).astype(np.uint8)
            all_hash.update(gray.tobytes())
            means.append(float(linear.mean()));lo=min(lo,float(linear.min()));hi=max(hi,float(linear.max()))
            geometry=renderer._coverage(probe,float(time_s))
            area=0.
            if geometry is not None:area=float(geometry[1].sum())
            target_areas.append(area)
            time_rows.append(dict(probe_id=probe["probe_id"],time_s=f"{time_s:.6f}",
                                  mean_luminance=f"{means[-1]:.8f}",target_visible_pixel_area=f"{area:.8f}"))
            if probe["probe_id"] in selected and frame_index in preview_indices:
                label=("early","middle","late")[min(range(3),key=lambda j:abs(float(time_s)-preview_times[j]))]
                image_path=out/f"{probe['probe_id']}_{label}.png"
                write_gray_png(image_path,gray)
                cards.append((probe["probe_id"],label,float(time_s),image_path))
        summary.append(dict(probe_id=probe["probe_id"],family=probe["family"],eye=probe["eye"],
                            sampled_frames=len(times),visible_sampled_frames=sum(a>0 for a in target_areas),
                            max_fractional_target_area_px=f"{max(target_areas,default=0.):.8f}",
                            mean_frame_luminance=f"{np.mean(means):.8f}",min_luminance=f"{lo:.8f}",
                            max_luminance=f"{hi:.8f}",sampled_frames_sha256=all_hash.hexdigest()))
    for filename,rows in (("trace.csv",time_rows),("summary.csv",summary)):
        with (out/filename).open("w",encoding="utf-8",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator="\n")
            writer.writeheader();writer.writerows(rows)
    write_preview(out/"retina_preview.svg",cards)
    try:matrix_label=matrix.resolve().relative_to(ROOT).as_posix()
    except ValueError:matrix_label=matrix.name
    report=dict(status="retinal stimulus rendering only; no LC10a neural response generated",
                input_matrix=matrix_label,input_sha256=digest(matrix),
                renderer_sha256=digest(ROOT/"src/fly_creature/retina.py"),
                runner_sha256=digest(Path(__file__)),grid=dict(width_px=renderer.width_px,
                height_px=renderer.height_px,pixel_pitch_deg=renderer.pitch,
                oversample_per_axis=renderer.oversample,linear_luminance_png_range=[0,2]),
                sample_interval_s=sample_interval if sample_interval>0 else "per-probe dt_s",
                probes=len(probes),trace_rows=len(time_rows),
                render_rule="eight-by-eight subpixel coverage; target alpha-mixed over instantaneous background",
                previews=[p.name for _,_,_,p in cards],summary_sha256=digest(out/"summary.csv"),
                trace_sha256=digest(out/"trace.csv"),preview_sha256=digest(out/"retina_preview.svg"))
    (out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix",type=Path,default=ROOT/"docs/evidence/lc10a_sensor_probes_v1.csv")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--sample-interval-s",type=float,default=0.,
                        help="optional diagnostic downsampling interval; defaults to each probe's dt_s")
    args=parser.parse_args()
    print(json.dumps(run(args.matrix,args.output_dir,args.sample_interval_s),indent=2))


if __name__=="__main__":main()

"""Phase A metadata-only archive audit; neural response datasets are forbidden.

Run with --fetch to obtain the DNa02 archive. Never reads rate/voltage values,
fits a predictor, or changes the frozen pursuit readers or production code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import zipfile

import h5py
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fly_creature.pursuit_physiology import ARCHIVES, P1_ARCHIVES, visible_segments

OUT = ROOT / "outputs/research/downstream-readiness-v1"
DN_NAME = "DNa02 Motion Pulse.zip"
DN_SIZE = 260077425
DN_MD5 = "a650c298d8e5368109f9c295b01c7171"
FORBIDDEN = {"int_spikert", "int_voltage"}
ALLOWED = {"int_time", "int_panelps", "int_forward", "int_angular", "int_sideway", "int_optostm"}
DUPLICATE = "AOTU019/2023_06_15_fly03"


def file_hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024*1024):
            md5.update(chunk)
            sha.update(chunk)
    return dict(bytes=path.stat().st_size, md5=md5.hexdigest(), sha256=sha.hexdigest())


def fetch(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / DN_NAME
    if path.exists():
        info = file_hashes(path)
        if info["bytes"] != DN_SIZE or info["md5"] != DN_MD5:
            raise ValueError("Existing DNa02 archive fails checksum; preserved for inspection")
        return path
    url = "https://zenodo.org/api/records/15474938/files/"+urllib.parse.quote(DN_NAME)+"/content"
    partial = directory/(DN_NAME+".partial")
    # Zenodo can end a long transfer early. Resume bounded chunks with exact
    # Content-Range checks, then verify the complete archive before use.
    count = partial.stat().st_size if partial.exists() else 0
    if count > DN_SIZE:
        raise ValueError("Oversized partial download; preserved for inspection")
    while count < DN_SIZE:
        end = min(count+32*1024*1024, DN_SIZE)-1
        request = urllib.request.Request(url, headers={"Range": f"bytes={count}-{end}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            expected_range = f"bytes {count}-{end}/{DN_SIZE}"
            if response.status != 206 or response.headers.get("Content-Range") != expected_range:
                raise ValueError("Server did not honor the exact requested download range")
            initial = count
            with partial.open("ab") as stream:
                while chunk := response.read(min(1024*1024, end+1-count)):
                    stream.write(chunk)
                    count += len(chunk)
                    if count == end+1:
                        break
            if count <= initial:
                raise ValueError("Download made no progress; partial preserved")
            print(f"DNa02 download: {count/1e6:.0f}/{DN_SIZE/1e6:.0f} MB", flush=True)
    info = file_hashes(partial)
    if info["bytes"] != DN_SIZE or info["md5"] != DN_MD5:
        raise ValueError("Downloaded archive fails checksum; partial preserved")
    partial.replace(path)
    print("DNa02 archive size/MD5 verified", flush=True)
    return path


def read_allowed(group, name, access_log):
    if name not in ALLOWED or name in FORBIDDEN:
        raise ValueError(f"Forbidden numerical dataset access: {name}")
    access_log.add(name)
    return np.asarray(group[name], dtype=np.float64).T


def metadata_recording(payload):
    accesses = set()
    with h5py.File(io.BytesIO(payload), "r") as f:
        schema = {}
        for name in sorted(f.keys()):
            obj = f[name]
            if isinstance(obj, h5py.Dataset):
                schema[name] = dict(matlab_storage_shape=list(obj.shape), dtype=str(obj.dtype),
                    numerical_values_read=False)
        for name in ("int_time", "int_panelps", "int_forward", *FORBIDDEN):
            if name not in schema:
                raise ValueError(f"Missing required schema field: {name}")
        native = read_allowed(f, "int_time", accesses).ravel()
        pos = read_allowed(f, "int_panelps", accesses)
        forward = read_allowed(f, "int_forward", accesses)
        opto = read_allowed(f, "int_optostm", accesses) if "int_optostm" in f else None
        for name in accesses:
            schema[name]["numerical_values_read"] = True
    dt = float(np.median(np.diff(native)))
    if not np.isfinite(native).all() or dt <= 0 or not np.allclose(np.diff(native), dt, atol=1e-9):
        raise ValueError("Native time grid is not uniform and finite")
    if pos.ndim != 2 or forward.shape != pos.shape or pos.shape[0] != len(native):
        raise ValueError("Position/movement/native time dimensions disagree")
    for name in FORBIDDEN | {"int_angular", "int_sideway"}:
        if name not in schema:
            raise ValueError(f"Missing required schema field: {name}")
        if tuple(schema[name]["matlab_storage_shape"])[::-1] != pos.shape:
            raise ValueError(f"Stored dataset shape mismatch: {name}")
    if np.isinf(pos).any() or not np.isfinite(forward).all():
        raise ValueError("Invalid position/movement values")
    info = dict(schema=schema, numerical_datasets_read=sorted(accesses), native_samples=len(native),
        trials=pos.shape[1], dt_s=dt, grid_error_s=float(np.max(
            np.abs(native-native[0]-np.arange(len(native))*dt))),
        optostimulation_flag_present=opto is not None)
    if opto is not None:
        info["optostimulation_metadata"] = dict(shape=list(opto.shape), finite=bool(np.isfinite(opto).all()),
            unique_values=np.unique(opto).tolist())
    return native, dt, pos, forward, info


def extract_metadata(native, dt, position, forward):
    """Same geometric/movement exclusions as extract(), without any rate access."""
    margin = int(round(.250/dt))
    pulses, rejects, gaps = [], Counter(), []
    segments = 0
    for trial in range(position.shape[1]):
        pos = position[:, trial]
        visible = visible_segments(pos)
        segments += len(visible)
        previous_stop = None
        for start, stop in visible:
            preceding_gap = None if previous_stop is None else float((start-previous_stop)*dt)
            if previous_stop is not None:
                gaps.append(float((start-previous_stop)*dt))
            previous_stop = stop
            if start == 0 or stop == len(native):
                rejects["boundary_segment"] += 1
                continue
            duration = (stop-start)*dt
            speed = min((25,75), key=lambda s: abs(duration-22.5/s))
            if abs(duration-22.5/speed) > .20*(22.5/speed):
                rejects["duration"] += 1
                continue
            p = pos[start:stop]
            if abs(abs(p[-1]-p[0])-22.5) > 3:
                rejects["span"] += 1
                continue
            t = native[start:stop]-native[start]
            slope, intercept = np.polyfit(t, p, 1)
            residual = float(np.sum((p-(intercept+slope*t))**2))
            variance = float(np.sum((p-p.mean())**2))
            r2 = 1-residual/variance if variance else 0
            if abs(abs(slope)-speed) > .1*speed or r2 < .98:
                rejects["slope_or_r2"] += 1
                continue
            lo, hi = start-margin, stop+margin
            if lo < 0 or hi > len(native):
                rejects["observation_boundary"] += 1
                continue
            if np.isfinite(pos[lo:start]).any() or np.isfinite(pos[stop:hi]).any():
                rejects["neighboring_stimulus"] += 1
                continue
            movement = forward[start:stop,trial]
            state = ("quiescent" if np.mean(np.abs(movement)<=.5)>=.5 else
                     "running" if np.mean(movement>2)>=.75 else "mixed")
            rel = native[lo:hi]-native[start]
            center = float((p[0]+p[-1])/2)
            pulses.append(dict(trial=trial, start_sample=int(start), stop_sample=int(stop),
                speed=int(speed), direction=1 if slope>0 else -1, center_bin=int(round(center/11.25)),
                center_deg=center, slope_deg_s=float(slope), span_deg=float(p[-1]-p[0]),
                duration_s=float(duration), state=state,
                baseline_samples=int(np.sum((rel>=-.250)&(rel<=-.100))),
                preceding_gap_s=preceding_gap))
    assert len(pulses)+sum(rejects.values()) == segments
    return pulses, dict(rejects), gaps


def coverage(pulses):
    cells = defaultdict(set)
    for p in pulses:
        if p["speed"]==25 and p["state"]=="quiescent":
            cells[(p["speed"],p["direction"],p["center_bin"])].add(p["trial"])
    return {k: sorted(v) for k,v in cells.items() if len(v)>=4}


def audit(data_dir):
    OUT.mkdir(parents=True, exist_ok=True)
    dn = data_dir/DN_NAME
    specs = [("unresolved", "DNa02", dn, DN_MD5)]
    old_dir = ROOT/"outputs/research/aotu-recordings"
    for condition, archives in (("P1",P1_ARCHIVES),("NoP1",ARCHIVES)):
        specs += [(condition,kind,old_dir/name,md5) for kind,(name,md5) in archives.items()]
    records, archive_info, eligible, member_hashes = [], [], {}, defaultdict(list)
    excluded = []
    for condition, kind, path, expected in specs:
        info = file_hashes(path)
        if info["md5"] != expected or (kind=="DNa02" and info["bytes"] != DN_SIZE):
            raise ValueError(f"Archive integrity failure: {path.name}")
        info.update(condition=condition, type=kind, filename=path.name)
        with zipfile.ZipFile(path) as z:
            # zipfile.read checks each member CRC; no extraction into arbitrary paths.
            inventory = []
            for entry in sorted(z.infolist(), key=lambda x:x.filename):
                if entry.is_dir():
                    continue
                payload = z.read(entry)
                sha = hashlib.sha256(payload).hexdigest()
                inventory.append(dict(member=entry.filename, bytes=len(payload), crc32=f"{entry.CRC:08x}", sha256=sha))
                if entry.filename.endswith("trackLR.mat"):
                    meta = loadmat(io.BytesIO(payload))
                    info["trackLR"] = {k:dict(shape=list(v.shape), values=np.asarray(v).tolist())
                        for k,v in meta.items() if not k.startswith("__")}
                if not entry.filename.endswith("_int.mat"):
                    continue
                identity = kind+"/"+Path(entry.filename).stem.removesuffix("_int")
                member_hashes[sha].append([condition,identity])
                if identity == DUPLICATE:
                    excluded.append(dict(condition=condition,recording=identity,reason="frozen known duplicate"))
                    continue
                native, dt, pos, fwd, rec = metadata_recording(payload)
                ps, reject, gaps = extract_metadata(native,dt,pos,fwd)
                cov = coverage(ps)
                eligible[condition,kind,identity] = cov
                rec.update(condition=condition,type=kind,recording=identity,member=entry.filename,
                    member_sha256=sha,accepted_pulses=len(ps),rejections=reject,
                    states=dict(Counter(p["state"] for p in ps)),
                    speeds=dict(Counter(p["speed"] for p in ps)),
                    speed_state_counts=dict(Counter(f"{p['speed']}/{p['state']}" for p in ps)),
                    eligible_25_quiet_cells=[dict(speed=k[0],direction=k[1],center_bin=k[2],trials=v)
                        for k,v in sorted(cov.items())],
                    gap_quantiles_s=np.quantile(gaps,[0,.25,.5,.75,1]).tolist() if gaps else [],
                    baseline_sample_counts=sorted({p["baseline_samples"] for p in ps}),
                    eligible_quiet_gap_quantiles_s=np.quantile(
                        [p["preceding_gap_s"] for p in ps if p["speed"]==25
                         and p["state"]=="quiescent" and p["preceding_gap_s"] is not None],
                        [0,.25,.5,.75,1]).tolist() if any(p["speed"]==25 and p["state"]=="quiescent"
                            and p["preceding_gap_s"] is not None for p in ps) else [],
                    center_bin_max_error_deg=max((abs(p["center_deg"]-11.25*p["center_bin"])
                        for p in ps),default=0),
                    direction_slope_ranges={str(d):[min(p["slope_deg_s"] for p in ps if p["direction"]==d),
                        max(p["slope_deg_s"] for p in ps if p["direction"]==d)] for d in (-1,1)
                        if any(p["direction"]==d for p in ps)})
                records.append(rec)
                (OUT/(condition+"_"+identity.replace("/","_")+"_pulses.json")).write_text(
                    json.dumps(ps,indent=2,allow_nan=False)+"\n",encoding="utf-8")
                print(condition,identity,"metadata:",len(ps),"pulses,",len(cov),"repeat-supported cells",flush=True)
            info["inventory"] = inventory
        archive_info.append(info)
    candidates = {}
    for condition in ("P1","NoP1"):
        support = {}
        for kind, cond in (("DNa02","unresolved"),("AOTU019",condition),("AOTU025",condition)):
            cells = defaultdict(list)
            for (c,k,identity), cov in eligible.items():
                if c==cond and k==kind:
                    for cell in cov:
                        cells[cell].append(identity)
            support[kind] = {cell:ids for cell,ids in cells.items() if len(ids)>=4}
        # The inhibitory pathway uses (-theta,-direction); the same-side
        # control also needs its unmirrored cell. Freeze their joint coverage.
        common = sorted(cell for cell in support["DNa02"]
            if cell in support["AOTU019"] and cell in support["AOTU025"]
            and (cell[0],-cell[1],-cell[2]) in support["AOTU019"])
        dn_records = sorted({i for cell in common for i in support["DNa02"][cell]})
        candidates[condition] = dict(common_cells=[dict(speed=x[0],direction=x[1],center_bin=x[2],
            recordings={k: support[k][x] for k in support},
            mirrored_aotu019_recordings=support["AOTU019"][(x[0],-x[1],-x[2])]) for x in common],
            eligible_dna02_recordings=dn_records, coverage_pass=len(dn_records)>=6 and bool(common))
    duplicates = [items for items in member_hashes.values() if len(items)>1]
    dn_animals = {r["recording"].split("/")[1] for r in records if r["type"]=="DNa02"}
    aotu_animals = {r["recording"].split("/")[1] for r in records if r["type"]!="DNa02"}
    report = dict(schema_version=1,phase="A",date="2026-10-09",status="stop",
        response_values_read=False,fit_performed=False,archives=archive_info,recordings=records,
        exclusions=excluded,identical_member_groups=duplicates,
        filename_animal_label_overlap=sorted(dn_animals&aotu_animals),
        animal_identity_limitation="Date/fly labels are not independently validated animal IDs; tracker mapping unavailable.",
        cohort_candidates=candidates,
        prospective_cohort="P1, 25 deg/s (primary preprint and pinned loader; per-member state not retained)",
        source_audit="docs/pursuit_downstream_metadata_sources.md",
        unresolved=["Archive-specific target width/height/contrast provenance is not retained in these files",
                    "Per-member stimulation timing and source tracker association are unavailable"],
        next_action="Resolve metadata/source boundaries; do not open neural responses or fit Phase B.",
        audit_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/"audit.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Metadata audit saved:",OUT/"audit.json",flush=True)
    return report


def write_compact(report):
    """Preserve metadata provenance/coverage, leaving pulse traces ignored."""
    compact = {k:v for k,v in report.items() if k not in {"archives", "recordings"}}
    compact["archives"] = [{k:v for k,v in a.items() if k != "inventory"}
        for a in report["archives"]]
    # Keep all member hashes and numerical-access declarations, not large
    # signal schemas repeated for each recording. Those remain in audit.json.
    compact["recordings"] = [{k:v for k,v in r.items() if k != "schema"}
        for r in report["recordings"]]
    compact["dna02_schema"] = next(r["schema"] for r in report["recordings"]
        if r["type"]=="DNa02")
    compact["source_note_sha256"] = hashlib.sha256(
        (ROOT/"docs/pursuit_downstream_metadata_sources.md").read_bytes()).hexdigest()
    compact["synthetic_checker_sha256"] = hashlib.sha256(
        (ROOT/"tools/check_downstream_metadata_audit.py").read_bytes()).hexdigest()
    path = ROOT/"docs/evidence/pursuit_downstream_readiness_v1.json"
    path.write_text(json.dumps(compact,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("Compact metadata evidence saved:",path,flush=True)
    dn = [r for r in report["recordings"] if r["type"]=="DNa02"]
    lines = ["# Downstream comparison: Phase A readiness", "",
        "Codex, 2026-10-09. **STOP before Phase B: required metadata remains unresolved.**", "",
        "This is a metadata result, not a failed neural prediction. No DNa02 neural",
        "response values were opened, no predictor was fitted, and no production",
        "controller changed. The [frozen contract](pursuit_downstream_contract.md)",
        "retains its original coverage and performance requirements.", "",
        "## What was checked", "",
        f"Verified five public archive MD5 values and every ZIP member CRC; retained {len(report['recordings'])}",
        "recording units (11 DNa02 and 69 AOTU). The two copies of the previously",
        "excluded AOTU019/2023_06_15_fly03 remain excluded. Archive and retained",
        "member SHA-256 values are in the [compact evidence](evidence/pursuit_downstream_readiness_v1.json).",
        "Numerical reads were limited to time, target position and forward movement",
        "(plus an optostimulation indicator if present). Neural and other movement",
        "dataset shapes/dtypes were inspected without reading their values.", "",
        "| DNa02 recording | Trials | Accepted pulses | Quiet 25°/s pulses | Cells with ≥4 distinct trials |",
        "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {r['recording'].split('/')[1]} | {r['trials']} | {r['accepted_pulses']} | "
        f"{r['speed_state_counts'].get('25/quiescent',0)} | {len(r['eligible_25_quiet_cells'])} |" for r in dn]
    lines += ["", "## Common coverage", "",
        "Each retained cell requires ≥4 distinct trials within a recording and",
        "support in ≥4 recordings per neuron type. Inhibitory crossover also requires",
        "AOTU019 support at the mirrored center/direction; same-side controls retain",
        "the unmirrored cell. At least six DNa02 recording units are required.", "",
        "| AOTU comparison cohort | Joint stimulus cells | Eligible DNa02 units | Coverage gate |",
        "| --- | ---: | ---: | --- |"]
    lines += [f"| {c} | {len(v['common_cells'])} | {len(v['eligible_dna02_recordings'])} | "
        f"{'pass' if v['coverage_pass'] else 'stop'} |" for c,v in report['cohort_candidates'].items()]
    lines += ["", "P1 at 25°/s is the prospective source-supported comparison. NoP1 counts",
        "are an inventory sensitivity, not an alternative selected by response fit.",
        "Cell/recording/trial IDs and the mirrored-input support are saved as metadata",
        "candidates; no Phase B fold manifest is approved while required gates are unresolved.", "",
        "## Timing and signal checks", "",
        f"All 80 time axes have 1.5 ms steps; maximum uniform-grid discrepancy is "
        f"{max(r['grid_error_s'] for r in report['recordings']):.3g} seconds.",
        "Every accepted pulse has 100 native samples in the inclusive baseline window.",
        f"DNa02 accepted absolute slopes span "
        f"{min(abs(x) for r in dn for v in r['direction_slope_ranges'].values() for x in v):.3f}–"
        f"{max(abs(x) for r in dn for v in r['direction_slope_ranges'].values() for x in v):.3f}°/s; "
        "25°/s is the nominal speed class, not an assertion of exact measured speed.",
        f"Largest DNa02 center deviation from its 11.25° bin is "
        f"{max(r['center_bin_max_error_deg'] for r in dn):.3f}°.",
        "Typical hidden gaps are about one second. Short artifact fragments occur in",
        "the all-segment inventory; duration and hidden-margin exclusions remain active.",
        "Eligible-quiet gap distributions are retained separately. No optostimulation",
        "channel is present in any of the 80 saved recordings.", "",
        "## Source constraints and readiness", "",
        "The [primary-source audit](pursuit_downstream_metadata_sources.md) supports P1",
        "treatment and identical 50 ms Gaussian spike-rate smoothing for all three",
        "types. Saved rates must not be smoothed a second time. Coordinates have",
        "already been normalized to the recorded cell's side. Use canonical population",
        "assumptions rather than assigning physical sides from an unverified tracker order.", "",
        "Target dimensions/contrast and per-member stimulation timing are not retained",
        "in the interpolated arrays. External pattern lookup files, original recording",
        "metadata and tracker associations are unavailable in the pinned checkout.",
        "The known acquisition defect assigning sweep range to sweepRate also means",
        "actual position chronology, not that metadata field, determines speed.", "",
        "Native steps, baseline sample counts, direction slopes, center-bin errors and",
        "all-segment/eligible-quiet gap distributions are in the evidence. These checks",
        "preserve actual chronology; they do not insert the paper's nominal cadence.",
        "Stored physical units follow depositor/source conventions, not per-file calibration.",
        f"Byte-identical member groups: {len(report['identical_member_groups'])}; cross-cohort",
        f"DNa02/AOTU date-fly filename overlap: {len(report['filename_animal_label_overlap'])}.",
        "Filename labels are recording units, not independently certified animal IDs.", "",
        "**Decision:** Required stimulus/state provenance is unresolved; do not access",
        "DNa02 responses or fit Phase B. Recover pattern/recording metadata or an explicit",
        "author mapping first. If unavailable, leave this physiological comparison stopped",
        "rather than substituting a better-fitting cohort or tuning a new neural model.", "",
        "## Reproduce and check", "", "From the workspace root, with physiology-research dependencies:", "",
        "```powershell",
        r".\.venv\Scripts\python.exe fly-creature/tools/audit_downstream_recordings.py --fetch --write-evidence",
        r".\.venv\Scripts\python.exe fly-creature/tools/check_downstream_metadata_audit.py --report fly-creature/outputs/research/downstream-readiness-v1/audit.json",
        "```", "",
        "The synthetic checker traps neural numerical reads, matches reference pulse",
        "exclusions and verifies distinct-trial coverage/first-pulse gaps. Its real-artifact",
        "check independently reconstructs every recording's coverage from saved metadata",
        "and checks the no-response-access declarations. Full metadata pulse files and",
        "downloads remain ignored; compact provenance and coverage are committed.", ""]
    (ROOT/"docs/pursuit_downstream_readiness.md").write_text("\n".join(lines),encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=OUT/"archives")
    parser.add_argument("--fetch",action="store_true")
    parser.add_argument("--write-evidence",action="store_true")
    args = parser.parse_args()
    if args.fetch:
        fetch(args.data_dir)
    report = audit(args.data_dir)
    if args.write_evidence:
        write_compact(report)

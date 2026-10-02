"""Portable offline column-mixture sensory candidate; production never imports it."""
from dataclasses import replace
from importlib.resources import files
import json
from pathlib import Path

import numpy as np


def load_footprints(path=None):
    path=path or Path(str(files("fly_creature").joinpath("data/lc10a_column_footprints_v1.json")))
    data=json.loads(Path(path).read_text())
    if data["schema_version"]!=1:
        raise ValueError("Unsupported footprint schema")
    rows=data["cells"]
    if len({int(c["body_id"]) for c in rows})!=len(rows):
        raise ValueError("Duplicate footprint cell")
    for cell in rows:
        if cell["side"] not in ("L","R"):
            raise ValueError("Invalid footprint side")
        if cell["method"] not in ("registered_columns","unchanged_center_fallback"):
            raise ValueError("Unknown footprint method")
        if bool(cell["columns"])!=(cell["method"]=="registered_columns"):
            raise ValueError("Footprint method and columns disagree")
        values=[cell["fallback_center_deg"],cell["mean_angle_deg"]]
        for column in cell["columns"]:
            if not isinstance(column["contacts"],int) or column["contacts"]<=0:
                raise ValueError("Invalid footprint contact count")
            values.append(column["angle_deg"])
        if not np.isfinite(values).all() or np.any(np.abs(values)>180):
            raise ValueError("Invalid footprint angle")
        if cell["columns"]:
            mean=np.average([c["angle_deg"] for c in cell["columns"]],
                            weights=[c["contacts"] for c in cell["columns"]])
            if abs(mean-cell["mean_angle_deg"])>1e-10:
                raise ValueError("Stored footprint mean mismatch")
    return rows


def visual_response(projection, rows, angles, *, mode="footprint", width_deg=18., overlap_deg=15.):
    if mode not in ("footprint","signed_mean","recentered_footprint"):
        raise ValueError("Unknown footprint mode")
    angles=np.asarray(angles,dtype=float)
    if angles.ndim!=1 or not np.isfinite(angles).all() or np.any(np.abs(angles)>180):
        raise ValueError("Invalid bearing array")
    if not np.isfinite(width_deg) or width_deg<=0 or not np.isfinite(overlap_deg) or overlap_deg<=0:
        raise ValueError("Invalid kernel/aperture width")
    index={int(c["body_id"]):c for c in rows}
    if set(index)!=set(map(int,projection.body_ids)):
        raise ValueError("Footprints must cover selected LC10a exactly")
    result=np.empty((len(angles),len(rows)))
    direct=np.zeros(len(rows),dtype=bool)
    for i,body_id in enumerate(projection.body_ids):
        cell=index[int(body_id)]
        if cell["side"]!=projection.sides[i] or abs(cell["fallback_center_deg"]-projection.centers_deg[i])>1e-10:
            raise ValueError("Footprint identity/center mismatch")
        sign=1. if cell["side"]=="R" else -1.
        aperture=np.clip(.5+angles*sign/overlap_deg,0.,1.)
        columns=cell["columns"]
        direct[i]=bool(columns)
        if not columns:
            centers=np.array([cell["fallback_center_deg"]]);weights=np.ones(1)
        elif mode=="signed_mean":
            # Match the existing map's four-decimal center precision so this
            # control isolates unclipping rather than minute rounding changes.
            centers=np.array([round(cell["mean_angle_deg"],4)]);weights=np.ones(1)
        else:
            centers=np.array([c["angle_deg"] for c in columns])
            weights=np.array([c["contacts"] for c in columns],dtype=float)
            weights/=weights.sum()
            if mode=="recentered_footprint":
                centers+=cell["fallback_center_deg"]-cell["mean_angle_deg"]
        gaussian=np.exp(-.5*((angles[:,None]-centers*sign)/width_deg)**2)
        result[:,i]=(gaussian@weights)*aperture
    return result,direct


def footprint_adapter(base, rows, mode="footprint"):
    angles=np.arange(-180.,181.)
    visual,direct=visual_response(base.projection,rows,angles,mode=mode,width_deg=base.width_deg)
    response=visual@base.projection.lc_to_aotu
    return replace(base,response=response),visual,direct

"""Frozen offline recorded-AOTU benchmark for the LC10a image-response rule.

This research runner is deliberately isolated from the playable creature. It
uses the packaged 275-cell MaleCNS projection, local checksum-pinned pulse
archives, fixed contact controls, and the predeclared fitting budget.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import zipfile

import numpy as np
from scipy.signal import fftconvolve, lfilter

from .lc10a_response import ABLATIONS, LC10aVisualResponse, RetinalMotionFrontEnd, causal_envelope
from .pursuit_activity import ActivityProjection
from .pursuit_physiology import ARCHIVES, P1_ARCHIVES, ROOT, extract, read_recording, sha
from .pursuit_population import compact_lookups
from .pursuit_temporal import observation_kernel
from .retina import RetinalRenderer


CONTRACT_PATH = ROOT / "docs/evidence/lc10a_benchmark_contract_v1.json"
PROTOCOL_PATH = ROOT / "docs/lc10a_response_benchmark_protocol.md"
OBSERVATION_PATH = ROOT / "outputs/research/aotu-population-v1/observations.csv"
FOLD_PATH = ROOT / "outputs/research/aotu-population-v1/folds.csv"
OUTPUT_DIR = ROOT / "outputs/research/lc10a-recorded-benchmark-v1"
DUPLICATE = "AOTU019/2023_06_15_fly03"
GEOMETRIES = {
    "primary": (11.25, 60.0, 1.0),
    "width_half": (5.625, 60.0, 1.0),
    "width_double": (22.5, 60.0, 1.0),
    "height_half": (11.25, 30.0, 1.0),
    "contrast_half": (11.25, 60.0, 0.5),
}
CONFIGURATIONS = [
    ("primary", "primary"),
    ("contrast_half", "primary"),
    *((name, name) for name in ABLATIONS if name != "primary"),
    ("width_half", "primary"), ("width_double", "primary"),
    ("height_half", "primary"),
]
PEAKS = {"AOTU019": 5063.997426161673, "AOTU025": 2440.4230502689747}


def _array_hash(value: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(value, dtype="<f8").tobytes(order="C")).hexdigest()


def _json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _key(row: dict) -> tuple:
    return (str(row["condition"]), str(row["type"]), str(row["recording"]),
            int(row["trial"]), int(row["speed_deg_s"]), int(row["direction"]),
            int(row["center_bin"]))


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if rows:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def _load_controls(contract: dict, projection: ActivityProjection) -> tuple[list[str], np.ndarray, dict]:
    """Construct and hash-check the exact four-column control matrices."""
    wiring = contract["wiring"]
    base = projection.lc_to_aotu.astype(np.float64, copy=True)
    if not np.array_equal(projection.body_ids, np.asarray(wiring["body_ids"], dtype=np.int64)):
        raise ValueError("Packaged LC10a order differs from the frozen contract")
    if list(projection.aotu_ids) != [10005, 10070, 516361, 519926]:
        raise ValueError("Packaged AOTU output order differs from the contract")
    if _array_hash(base) != wiring["intact_weight_sha256"]:
        raise ValueError("Intact contact matrix hash mismatch")
    spatial, flat = np.zeros_like(base), np.zeros_like(base)
    totals = np.asarray(wiring["contact_totals"], dtype=np.float64)
    for col, (kind, side) in enumerate(zip(projection.aotu_types, projection.aotu_sides)):
        indexes = np.flatnonzero(projection.sides == side)
        preferred = 35.0 if kind == "AOTU019" else 65.0
        q = np.exp(-0.5 * ((projection.centers_deg[indexes] - preferred) / 20.0) ** 2)
        total = float(base[:, col].sum())
        spatial[indexes, col] = q / q.sum() * total
        flat[indexes, col] = total / len(indexes)
    if _array_hash(spatial) != wiring["spatial_weight_sha256"]:
        raise ValueError("Matched-spatial matrix hash mismatch")
    if _array_hash(flat) != wiring["flat_weight_sha256"]:
        raise ValueError("Flat matrix hash mismatch")
    names, matrices = ["intact", "matched_spatial", "flat"], [base, spatial, flat]
    for expected in wiring["shuffles"]:
        matrix = base[np.asarray(expected["source_row_indices"], dtype=np.int64)]
        if _array_hash(matrix) != expected["weight_sha256"]:
            raise ValueError(f"Shuffle {expected['index']:02} matrix hash mismatch")
        names.append(f"shuffle_{expected['index']:02}")
        matrices.append(matrix)
    return names, np.stack(matrices), {
        "matrix_hashes": {name: _array_hash(matrix) for name, matrix in zip(names, matrices)},
        "contact_totals": totals.tolist(), "shuffle_count": len(wiring["shuffles"])}


def _horizontal_coverage(renderer: RetinalRenderer, centers: np.ndarray,
                         width_deg: float) -> np.ndarray:
    """Exact horizontal subpixel coverage for the existing 8x rectangle renderer."""
    positions = np.asarray(centers, dtype=np.float64)
    sub = renderer.oversample
    xs = renderer.az_min + (np.arange(renderer.width_px * sub) + 0.5) * renderer.pitch / sub
    result = np.zeros((len(positions), renderer.width_px), dtype=np.float64)
    finite = np.isfinite(positions)
    for start in range(0, len(positions), 1024):
        stop = min(len(positions), start + 1024)
        valid = finite[start:stop]
        if valid.any():
            inside = np.abs(xs[None, :] - positions[start:stop, None]) <= width_deg / 2
            inside &= valid[:, None]
            result[start:stop] = inside.reshape(stop-start, renderer.width_px, sub).mean(axis=2)
    return result


def _vertical_coverage(renderer: RetinalRenderer, height_deg: float) -> np.ndarray:
    sub = renderer.oversample
    ys = renderer.el_min + (renderer.height_px * sub - 1 -
        np.arange(renderer.height_px * sub) + 0.5) * renderer.pitch / sub
    return (np.abs(ys) <= height_deg / 2).reshape(renderer.height_px, sub).mean(axis=1)


def _motion_profile(dark: np.ndarray, dt: float) -> np.ndarray:
    """Vectorized public front-end recurrence for a uniform native time grid."""
    if len(dark) == 0:
        return np.empty_like(dark)
    decay = math.exp(-dt / 0.020)
    previous = np.zeros_like(dark)
    previous[1:] = dark[:-1]
    delayed = lfilter([1.0-decay], [1.0, -decay], previous, axis=0)
    pairs = delayed[:, :-1] * dark[:, 1:] - delayed[:, 1:] * dark[:, :-1]
    motion = np.empty_like(dark)
    motion[:, 0], motion[:, -1] = pairs[:, 0], pairs[:, -1]
    motion[:, 1:-1] = (pairs[:, :-1] + pairs[:, 1:]) * 0.5
    return motion


def _rectangle_dot(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Exact per-cell dot for subpixel rectangles: two edges plus full interior."""
    rows, width = values.shape
    cells = weights.shape[0]
    occupied = values != 0.0
    active = occupied.any(axis=1)
    first = occupied.argmax(axis=1)
    last = width-1-occupied[:, ::-1].argmax(axis=1)
    peak = values.max(axis=1, initial=0.0)
    interior_bad = np.zeros(rows, dtype=bool)
    for i in np.flatnonzero(active & (last > first+1)):
        interior_bad[i] = not np.all(values[i, first[i]+1:last[i]] == peak[i])
    out = np.zeros((rows,cells),dtype=np.float64)
    single = active & (first==last)
    if single.any():
        out[single] = values[single,first[single],None] * weights[:,first[single]].T
    multi = active & (first<last) & ~interior_bad
    if multi.any():
        prefix=np.concatenate((np.zeros((cells,1),dtype=np.float64),
                               np.cumsum(weights,axis=1,dtype=np.float64)),axis=1)
        f,l=first[multi],last[multi]
        interior=prefix[:,l].T-prefix[:,f+1].T
        left=values[multi,f,None]*weights[:,f].T
        right=values[multi,l,None]*weights[:,l].T
        out[multi]=left+interior*peak[multi,None]+right
    fallback=interior_bad
    if fallback.any():
        out[fallback]=values[fallback]@weights.T
    return out


def _sparse_dot(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Exact dot for the short-support Reichardt motion profiles."""
    rows,width=values.shape
    counts=np.count_nonzero(values,axis=1)
    max_count=int(counts.max(initial=0))
    out=np.zeros((rows,weights.shape[0]),dtype=np.float64)
    if max_count==0:
        return out
    mask=values!=0.0
    source_rows,source_cols=np.nonzero(mask)
    rank=np.cumsum(mask,axis=1)[source_rows,source_cols]-1
    columns=np.zeros((rows,max_count),dtype=np.int16)
    amplitudes=np.zeros((rows,max_count),dtype=np.float64)
    columns[source_rows,rank]=source_cols
    amplitudes[source_rows,rank]=values[source_rows,source_cols]
    row_index=np.arange(rows)
    for offset in range(max_count):
        out += amplitudes[:,offset,None]*weights[:,columns[:,offset]].T
    return out


def _vertical_extrema(response: LC10aVisualResponse,
                      vertical: np.ndarray) -> tuple[float, float]:
    """Return the center-row coefficients after proving the max-row shortcut.

    For these centered apertures the center coefficient peaks at the two
    middle rows, while surround/center is smallest there. For any nonnegative
    horizontal center/surround drives, each rectified DoG therefore reaches
    its maximum at those rows. The primary 60-degree aperture spans the full
    vertical panel, so all rows are equivalent. This avoids materializing a
    time-by-row-by-cell tensor without changing the frozen max-pooling rule.
    """
    center = response.center_y @ vertical
    surround = response.surround_y @ vertical
    if (center.ndim != 1 or surround.shape != center.shape or len(center) != 32
            or not np.all(np.isfinite(center)) or not np.all(np.isfinite(surround))
            or np.any(center <= 0.0) or np.any(surround < 0.0)):
        raise ValueError("Unexpected vertical receptive-field coefficients")
    middle = len(center) // 2 - 1
    center_pair = center[middle:middle+2]
    surround_pair = surround[middle:middle+2]
    ratio = surround / center
    if (np.max(center) > np.max(center_pair) + 1e-12
            or np.min(ratio) < np.min(ratio[middle:middle+2]) - 1e-12):
        raise ValueError("Centered vertical max-pooling shortcut failed its coefficient gate")
    return float(np.mean(center_pair)), float(np.mean(surround_pair))


def _vertical_mean_dog(center_drive: np.ndarray, surround_drive: np.ndarray,
                       center_y: np.ndarray, surround_y: np.ndarray) -> np.ndarray:
    """Exact mean of rectified vertical DoG using sorted coefficient ratios."""
    ratio = surround_y / center_y
    order = np.argsort(ratio, kind="stable")
    sorted_ratio = ratio[order]
    prefix_center = np.concatenate(([0.0], np.cumsum(center_y[order], dtype=np.float64)))
    prefix_surround = np.concatenate(([0.0], np.cumsum(surround_y[order], dtype=np.float64)))
    threshold = np.divide(center_drive, surround_drive,
        out=np.full_like(center_drive, np.inf), where=surround_drive > 0.0)
    included = np.searchsorted(sorted_ratio, threshold, side="left")
    mean = (center_drive * prefix_center[included]
            - surround_drive * prefix_surround[included]) / len(center_y)
    np.maximum(mean, 0.0, out=mean)
    return mean


def _horizontal_components(response: LC10aVisualResponse, dark: np.ndarray,
                           motion: np.ndarray) -> dict[str, np.ndarray]:
    """Cache horizontal drives shared by the frozen ablations/geometries."""
    count, cells = len(dark), len(response.body_ids)
    result = {name: np.empty((count, cells), dtype=np.float64) for name in (
        "static_center", "static_surround", "motion_center", "motion_surround",
        "neutral_center", "neutral_surround")}
    for start in range(0, count, 1024):
        stop = min(count, start + 1024)
        result["static_center"][start:stop] = _rectangle_dot(
            dark[start:stop], response.center_x)
        result["static_surround"][start:stop] = _rectangle_dot(
            dark[start:stop], response.surround_x)
        for side, sign in (("L", -1.0), ("R", 1.0)):
            indexes = np.flatnonzero(response.sides == side)
            current = motion[start:stop]
            preferred = sign * current
            directed = np.maximum(preferred, 0.0) + 0.5 * np.maximum(-preferred, 0.0)
            neutral = 0.75 * np.abs(current)
            result["motion_center"][start:stop, indexes] = _sparse_dot(
                directed, response.center_x[indexes])
            result["motion_surround"][start:stop, indexes] = _sparse_dot(
                directed, response.surround_x[indexes])
            result["neutral_center"][start:stop, indexes] = _sparse_dot(
                neutral, response.center_x[indexes])
            result["neutral_surround"][start:stop, indexes] = _sparse_dot(
                neutral, response.surround_x[indexes])
    return result


def _features_from_components(response: LC10aVisualResponse,
                              components: dict[str, np.ndarray],
                              vertical: np.ndarray, ablation: str,
                              scale: float=1.0) -> np.ndarray:
    """Recombine cached horizontal drives with a frozen response rule."""
    if ablation not in ABLATIONS:
        raise ValueError(f"Unknown ablation: {ablation}")
    center_y = response.center_y @ vertical
    surround_y = response.surround_y @ vertical
    center_peak, surround_at_peak = _vertical_extrema(response, vertical)
    count, cells = components["static_center"].shape
    output = np.empty((count, cells), dtype=np.float64)
    remove_surround = ablation == "no_surround"
    neutral = ablation == "direction_neutral"
    static_weight = 0.0 if ablation == "no_static" else 0.25
    motion_weight = 1.0 if neutral else 0.75
    motion_center_name = "neutral_center" if neutral else "motion_center"
    motion_surround_name = "neutral_surround" if neutral else "motion_surround"
    full_vertical = ablation == "vertical_mean"
    contrast_scale = float(scale)
    motion_scale = contrast_scale * contrast_scale
    for start in range(0, count, 4096):
        stop = min(count, start + 4096)
        if static_weight:
            static_center = components["static_center"][start:stop] * contrast_scale
            if remove_surround:
                if full_vertical:
                    static = static_center * float(np.mean(center_y))
                else:
                    static = static_center * center_peak
            else:
                static_surround = components["static_surround"][start:stop] * contrast_scale
                if full_vertical:
                    static = _vertical_mean_dog(static_center, static_surround,
                                                center_y, surround_y)
                else:
                    static = np.maximum(static_center * center_peak -
                        static_surround * surround_at_peak, 0.0)
        else:
            static = 0.0
        motion_center = components[motion_center_name][start:stop] * motion_scale
        if remove_surround:
            if full_vertical:
                moving = motion_center * float(np.mean(center_y))
            else:
                moving = motion_center * center_peak
        else:
            motion_surround = components[motion_surround_name][start:stop] * motion_scale
            if full_vertical:
                moving = _vertical_mean_dog(motion_center, motion_surround,
                                            center_y, surround_y)
            else:
                moving = np.maximum(motion_center * center_peak -
                    motion_surround * surround_at_peak, 0.0)
        output[start:stop] = static_weight * static + motion_weight * moving
    if not np.all(np.isfinite(output)) or np.any(output < -1e-12):
        raise FloatingPointError("Invalid optimized LC10a feature")
    output[output < 0.0] = 0.0
    return output


def _separable_features(response: LC10aVisualResponse, dark: np.ndarray,
                        motion: np.ndarray, vertical: np.ndarray,
                        ablation: str, scale: float=1.0) -> np.ndarray:
    """Exact separable counterpart to the public 2D pooling for rectangles."""
    components = _horizontal_components(response, dark, motion)
    return _features_from_components(response, components, vertical, ablation, scale)


def _movie_state(position: np.ndarray, elapsed: np.ndarray, dt: float,
                 renderer: RetinalRenderer, width: float, contrast: float) -> dict:
    if len(elapsed) != len(position):
        raise ValueError("Native movie/time length mismatch")
    grid_error = float(np.max(np.abs(elapsed - np.arange(len(elapsed))*dt), initial=0.0))
    if grid_error > 1e-9:
        raise ValueError(f"Native time grid exceeds contract: {grid_error}")
    dark = _horizontal_coverage(renderer, position, width) * abs(contrast)
    mirror_dark = dark[:, ::-1].copy()
    motion = _motion_profile(dark, dt)
    mirror_motion = _motion_profile(mirror_dark, dt)
    return {"dark":dark,"mirror_dark":mirror_dark,"motion":motion,
        "mirror_motion":mirror_motion,"grid_error_s":grid_error,
        "finite_samples":int(np.isfinite(position).sum())}


def _activity_from_state(state: dict, dt: float, response: LC10aVisualResponse,
                         vertical: np.ndarray, ablation: str, scale: float=1.0
                         ) -> tuple[np.ndarray,np.ndarray,dict]:
    canonical_features=_separable_features(response,state["dark"],state["motion"],
                                            vertical,ablation,scale=scale)
    mirror_features=_separable_features(response,state["mirror_dark"],state["mirror_motion"],
                                         vertical,ablation,scale=scale)
    canonical=causal_envelope(canonical_features,dt,instantaneous=ablation=="instantaneous")
    mirrored=causal_envelope(mirror_features,dt,instantaneous=ablation=="instantaneous")
    info={"grid_error_s":state["grid_error_s"],"finite_samples":state["finite_samples"],
        "feature_max":float(max(canonical.max(initial=0.0),mirrored.max(initial=0.0)))}
    return canonical,mirrored,info


def _activity_pair_from_components(response: LC10aVisualResponse,
                                   components: tuple[dict[str,np.ndarray],
                                                     dict[str,np.ndarray]],
                                   vertical: np.ndarray, ablation: str,
                                   scale: float, dt: float
                                   ) -> tuple[np.ndarray,np.ndarray]:
    """Build canonical and mirrored histories from a shared sensory replay."""
    canonical_features=_features_from_components(response,components[0],vertical,
                                                  ablation,scale)
    canonical=causal_envelope(canonical_features,dt,
                              instantaneous=ablation=="instantaneous")
    del canonical_features
    mirrored_features=_features_from_components(response,components[1],vertical,
                                                 ablation,scale)
    mirrored=causal_envelope(mirrored_features,dt,
                             instantaneous=ablation=="instantaneous")
    del mirrored_features
    return canonical,mirrored


def _movie_activity(position: np.ndarray, elapsed: np.ndarray, dt: float,
                    renderer: RetinalRenderer, response: LC10aVisualResponse,
                    width: float, height: float, contrast: float,
                    ablation: str) -> tuple[np.ndarray, np.ndarray, dict]:
    state=_movie_state(position,elapsed,dt,renderer,width,contrast)
    vertical=_vertical_coverage(renderer,height)
    canonical,mirrored,info=_activity_from_state(state,dt,response,vertical,ablation)
    return canonical,mirrored,info


def _canonical_parity(data_dir: Path, renderer: RetinalRenderer,
                      response: LC10aVisualResponse) -> dict:
    """Compare actual native rectangles, history, and pooling with the public 2D path."""
    pixel_error = motion_error = feature_error = 0.0
    contrast_scale_error = 0.0
    frame_checks = 0
    block_checks = 0
    for archives in (ARCHIVES, P1_ARCHIVES):
        for kind, (filename, _) in archives.items():
            with zipfile.ZipFile(data_dir/filename) as archive:
                member = next(n for n in sorted(archive.namelist()) if n.endswith("_int.mat")
                    and kind+"/"+Path(n).stem.removesuffix("_int") != DUPLICATE)
                native, dt, signals = read_recording(archive.read(member))
            pos = signals["int_panelps"][:, 0]
            if not np.isfinite(pos).any():
                continue
            finite = np.flatnonzero(np.isfinite(pos))
            first = max(0, int(finite[0])-1)
            stop = min(len(pos), first+256)
            block = pos[first:stop]
            elapsed = native[first:stop]-native[0]
            for width, height, contrast in ((11.25,60.,1.),(5.625,60.,1.),
                    (22.5,60.,1.),(11.25,30.,1.),(11.25,60.,.5)):
                dark = _horizontal_coverage(renderer, block, width)*contrast
                vertical = _vertical_coverage(renderer, height)
                for mirror in (False, True):
                    movie = dark[:,::-1].copy() if mirror else dark
                    fast_motion = _motion_profile(movie,dt)
                    base_movie = _horizontal_coverage(renderer, block, width)
                    if mirror:
                        base_movie = base_movie[:,::-1].copy()
                    base_motion = _motion_profile(base_movie,dt)
                    front = RetinalMotionFrontEnd()
                    feature_samples = set(np.linspace(0, len(block)-1, min(6, len(block)),
                                                       dtype=int).tolist())
                    for i, center in enumerate(block):
                        probe = {"target_present":bool(np.isfinite(center)),"shape":"rectangle",
                            "width_deg":width,"height_deg":height,
                            "center_azimuth_deg":float(-center if mirror else center) if np.isfinite(center) else 0.,
                            "center_elevation_deg":0.,"azimuth_velocity_deg_s":0.,
                            "onset_s":0.,"visible_duration_s":100.,"weber_contrast":-contrast,
                            "surround":"uniform"}
                        image=renderer.render_linear(probe,float(elapsed[i]))
                        pixel_error=max(pixel_error,float(np.max(np.abs((1.-image)-
                            movie[i][None,:]*vertical[:,None]))))
                        abs_contrast,direct_motion=front.step(image,float(elapsed[i]))
                        motion_error=max(motion_error,float(np.max(np.abs(direct_motion-
                            fast_motion[i][None,:]*vertical[:,None]))))
                        if i in feature_samples:
                            for ablation in ABLATIONS:
                                direct,_,_=response.spatial_features(abs_contrast,direct_motion,
                                    ablation=ablation)
                                fast=_separable_features(response,movie[i:i+1],fast_motion[i:i+1],
                                    vertical,ablation)
                                feature_error=max(feature_error,float(np.max(np.abs(direct-fast))))
                                if contrast == 0.5:
                                    scaled=_separable_features(response,base_movie[i:i+1],
                                        base_motion[i:i+1],vertical,ablation,scale=contrast)
                                    contrast_scale_error=max(contrast_scale_error,
                                        float(np.max(np.abs(scaled-fast))))
                        frame_checks+=1
                    block_checks+=len(block)
    if pixel_error>1e-12 or motion_error>1e-10 or feature_error>1e-10:
        raise AssertionError(f"Separable parity failed: pixel={pixel_error}, motion={motion_error}, feature={feature_error}")
    return {"actual_native_frames_checked":frame_checks,"contiguous_history_steps":block_checks,
        "five_geometries_both_mirrors_all_ablations":True,"pixel_max_abs_error":pixel_error,
        "motion_max_abs_error":motion_error,"feature_max_abs_error":feature_error,
        "contrast_scale_feature_max_abs_error":contrast_scale_error}


def _config_predictors(control_names: list[str], control_mats: np.ndarray,
                       label: str, ablation: str) -> tuple[list[str], np.ndarray]:
    include_flat = label == "primary" or ablation == "primary"
    selected = [0, 1, *([2] if include_flat else []), *range(3, len(control_names))]
    names = [f"{label}:{control_names[i]}" for i in selected]
    return names, control_mats[selected]


def _predict_config(canonical: np.ndarray, mirrored: np.ndarray, matrices: np.ndarray,
                    projection: ActivityProjection, kind: str, names: list[str],
                    lookups: dict, dt: float) -> tuple[np.ndarray, list[dict]]:
    """Project all four outputs on both replays; decode only the matched type."""
    order = list(zip(projection.aotu_types, projection.aotu_sides))
    right_index = order.index((kind, "R"))
    left_index = order.index((kind, "L"))
    candidates = len(names)
    raw_right = np.zeros((len(canonical),candidates*4),dtype=np.float64)
    raw_left = np.zeros_like(raw_right)
    # The frozen graph has no cross-hemisphere LC10a contacts. Split by that
    # structural zero pattern so BLAS never multiplies the three-quarters of
    # matrix entries that are identically zero. Shuffles are within-side only.
    for activity, raw in ((canonical,raw_right),(mirrored,raw_left)):
        for side in ("L","R"):
            cell_index=np.flatnonzero(projection.sides==side)
            output_index=[i for i,out_side in enumerate(projection.aotu_sides)
                          if out_side==side]
            side_weights=matrices[:,cell_index,:][:,:,output_index].transpose(1,0,2).reshape(
                len(cell_index),candidates*len(output_index))
            side_raw=activity[:,cell_index]@side_weights
            for local,column in enumerate(output_index):
                raw[:,column::4]=side_raw[:,local::len(output_index)]
    decoded_right = np.empty((len(canonical), candidates), dtype=np.float64)
    decoded_left = np.empty_like(decoded_right)
    summaries = []
    overflows = []
    for movie_name, raw in (("canonical", raw_right), ("mirror", raw_left)):
        for col, (out_type, out_side) in enumerate(order):
            channel = raw[:, col::4]
            grid, values, peak = lookups[out_type]
            maximum = np.max(channel, axis=0, initial=0.0)
            minimum = np.min(channel, axis=0, initial=0.0)
            excess = np.maximum(maximum-peak, 0.0)
            clipped=np.minimum(channel,peak)
            step=(grid[-1]-grid[0])/(len(grid)-1)
            bin_index=np.floor(np.clip((clipped-grid[0])/step,0,len(grid)-1)+0.5).astype(np.int32)
            # This is the same uniform-grid nearest lookup as _nearest_lookup,
            # with indices retained for quantization accounting instead of
            # calculating them a second time for the activation values.
            activated=values[bin_index]
            for ci, name in enumerate(names):
                occupied=np.bincount(bin_index[:,ci],minlength=len(grid))
                summaries.append({"predictor": name, "movie": movie_name,
                    "column": f"{out_type}_{out_side}", "raw_min": float(minimum[ci]),
                    "raw_max": float(maximum[ci]), "peak": peak,
                    "max_peak_excess": float(excess[ci]),
                    "endpoint_excess_samples": int(np.sum(channel[:,ci]>peak)),
                    "positive_raw_samples": int(np.sum(channel[:,ci]>0)),
                    "positive_to_zero_lookup_samples": int(np.sum((channel[:,ci]>0)&(activated[:,ci]==0))),
                    "occupied_lookup_bins": int(np.count_nonzero(occupied)),
                    "occupied_bin_ids":np.flatnonzero(occupied).tolist(),
                    "trace_samples":len(canonical),
                    "final_lookup_bin_samples": int(occupied[-1])})
                if excess[ci]>1e-9:
                    overflows.append(summaries[-1])
            if movie_name=="canonical" and out_side=="R" and out_type==kind:
                decoded_right[:]=activated
            elif movie_name=="mirror" and out_side=="L" and out_type==kind:
                decoded_left[:]=activated
    if overflows:
        raise OverflowError(json.dumps(overflows[:8],sort_keys=True))
    response = 0.5 * (decoded_right + decoded_left)
    radius, kernel = observation_kernel(dt)
    padded = np.pad(response, ((radius, radius), (0, 0)))
    filtered = fftconvolve(padded, kernel[:, None], mode="same", axes=0)
    return filtered[radius:radius+len(response)], summaries


def _merge_representation(accumulator: dict, rows: list[dict]) -> None:
    """Aggregate exact quantization/overflow facts without retaining per-trial dumps."""
    additive=("endpoint_excess_samples","positive_raw_samples",
        "positive_to_zero_lookup_samples","final_lookup_bin_samples","trace_samples")
    for row in rows:
        key=(row["condition"],row["type"],row["recording"],row["configuration"],
             row["predictor"],row["movie"],row["column"])
        current=accumulator.get(key)
        if current is None:
            current={field:row[field] for field in (
                "condition","type","recording","configuration","predictor","movie","column",
                "raw_min","raw_max","peak","max_peak_excess")}
            current.update({field:int(row[field]) for field in additive})
            current["_bin_ids"]=set(int(v) for v in row["occupied_bin_ids"])
            accumulator[key]=current
        else:
            current["raw_min"]=min(current["raw_min"],row["raw_min"])
            current["raw_max"]=max(current["raw_max"],row["raw_max"])
            current["max_peak_excess"]=max(current["max_peak_excess"],row["max_peak_excess"])
            for field in additive: current[field]+=int(row[field])
            current["_bin_ids"].update(int(v) for v in row["occupied_bin_ids"])


def _representation_rows(accumulator: dict) -> list[dict]:
    result=[]
    for key in sorted(accumulator):
        row=dict(accumulator[key])
        row["occupied_lookup_bins"]=len(row.pop("_bin_ids"))
        result.append(row)
    return result


def _checkpoint_representation(accumulator: dict) -> list[dict]:
    return [{**{k:v for k,v in row.items() if k!="_bin_ids"},
             "occupied_bin_ids":sorted(row["_bin_ids"])}
            for _,row in sorted(accumulator.items())]


def _calibrate_and_score(raw_predictions: np.ndarray, observations: list[dict],
                         candidate_names: list[str], contract_folds: list[dict],
                         historical_folds: list[dict]) -> tuple[list[dict], list[dict], np.ndarray, np.ndarray, list[tuple]]:
    """Rebuild every fold, fixed gain, cell mean, score, and held prediction."""
    names = candidate_names + ["legacy_intact", "legacy_simple", "constant", "zero"]
    if raw_predictions.shape != (len(observations), len(names)):
        raise ValueError("Prediction matrix and frozen row order disagree")
    keyed = {_key(row): i for i, row in enumerate(observations)}
    if len(keyed) != len(observations):
        raise ValueError("Duplicate target signature")
    by_group = defaultdict(list)
    for i, row in enumerate(observations):
        by_group[(str(row["condition"]), str(row["type"]))].append(i)
    contract_lookup = {(f["condition"], f["type"], f["recording"]): f for f in contract_folds}
    old_lookup = {_key(row): row for row in historical_folds}
    fold_rows, score_rows = [], []
    held_keys, held_targets, held_values = [], [], []
    for (condition, kind), indexes in sorted(by_group.items()):
        groups = defaultdict(lambda: defaultdict(list))
        for i in indexes:
            row = observations[i]
            groups[str(row["recording"])][(int(row["speed_deg_s"]), int(row["direction"]),
                                           int(row["center_bin"]))].append(i)
        eligible = {rec: {cell: members for cell, members in cells.items() if len(members) >= 4}
                    for rec, cells in groups.items()}
        for held_rec, held_cells in sorted(eligible.items()):
            other = {rec: cells for rec, cells in eligible.items() if rec != held_rec}
            held = sorted((i for cell, members in held_cells.items()
                           if sum(cell in cells for cells in other.values()) >= 3
                           for i in members), key=lambda i: _key(observations[i]))
            train = sorted((i for train_rec, cells in other.items() for cell, members in cells.items()
                            if sum(cell in rest for rec, rest in other.items() if rec != train_rec) >= 3
                            for i in members), key=lambda i: _key(observations[i]))
            if not held or not train:
                raise ValueError(f"Empty fold for {held_rec}")
            per_record_trials = defaultdict(set)
            per_trial_cell_counts = defaultdict(int)
            for i in train:
                row = observations[i]
                rec, trial = str(row["recording"]), int(row["trial"])
                per_record_trials[rec].add(trial)
                per_trial_cell_counts[(rec, trial)] += 1
            n_records = len(per_record_trials)
            weights = np.asarray([
                1.0/(per_trial_cell_counts[(str(observations[i]["recording"]),
                      int(observations[i]["trial"]))]
                      * len(per_record_trials[str(observations[i]["recording"])]) * n_records)
                for i in train], dtype=np.float64)
            if abs(float(weights.sum())-1.0) > 1e-12:
                raise ValueError(f"Hierarchical calibration weights fail for {held_rec}")
            train_signatures = [_key(observations[i]) for i in train]
            held_signatures = [_key(observations[i]) for i in held]
            frozen = contract_lookup[(condition, kind, held_rec)]
            for field, signatures in (("train_signature_sha256", train_signatures),
                                      ("held_signature_sha256", held_signatures)):
                if _json_hash(signatures) != frozen[field]:
                    raise ValueError(f"Frozen {field} differs: {held_rec}")
            y = np.asarray([float(observations[i]["response_spikes_s"]) for i in train])
            if _json_hash(y.tolist()) != frozen["train_target_sha256"]:
                raise ValueError(f"Frozen training targets differ: {held_rec}")
            if _json_hash(weights.tolist()) != frozen["train_weights_sha256"]:
                raise ValueError(f"Frozen training weights differ: {held_rec}")
            x = raw_predictions[train]
            xx = np.sum(weights[:, None]*x*x, axis=0, dtype=np.float64)
            xy = np.sum(weights[:, None]*x*y[:, None], axis=0, dtype=np.float64)
            gains = np.maximum(0.0, np.divide(xy, xx, out=np.zeros_like(xy), where=xx != 0))
            # Historical comparators are recalibrated from their fixed legacy
            # observations; the reviewed historical gain must reproduce exactly.
            for column, old_name in ((len(candidate_names), "anatomy"),
                                     (len(candidate_names)+1, "simple_spatial")):
                expected = float(frozen["legacy_gains"][old_name])
                if abs(float(gains[column])-expected) > 1e-10:
                    raise ValueError(f"Legacy calibration mismatch for {held_rec}/{old_name}")
            gains[len(candidate_names)+2] = float(weights @ y)  # Includes negative means.
            gains[len(candidate_names)+3] = 0.0
            held_x = raw_predictions[held]
            held_y = np.asarray([float(observations[i]["response_spikes_s"]) for i in held])
            held_pred = held_x*gains[None, :]
            legacy_fields = ("anatomy", "simple_spatial", "constant", "zero")
            for local, row_index in enumerate(held):
                old = old_lookup[_key(observations[row_index])]
                for offset, field in enumerate(legacy_fields):
                    error = abs(float(held_pred[local, len(candidate_names)+offset])-
                                float(old[field]))
                    if error > 1e-10:
                        raise ValueError(f"Historical held prediction changed: {field} {error}")
            cells = defaultdict(list)
            for local, i in enumerate(held):
                row = observations[i]
                cells[(int(row["speed_deg_s"]), int(row["direction"]),
                       int(row["center_bin"]))].append(local)
            cell_prediction = np.stack([held_pred[local].mean(axis=0)
                                        for _, local in sorted(cells.items())])
            cell_target = np.asarray([held_y[local].mean()
                                      for _, local in sorted(cells.items())])
            rmse = np.sqrt(np.mean((cell_prediction-cell_target[:, None])**2, axis=0))
            for j, name in enumerate(names):
                fold_rows.append({"condition": condition, "type": kind, "recording": held_rec,
                    "predictor": name, "gain": float(gains[j]), "degenerate": bool(xx[j] == 0),
                    "train_trial_cells": len(train), "train_recordings": n_records,
                    "held_trial_cells": len(held), "scored_cells": len(cells),
                    "rmse_spikes_s": float(rmse[j])})
                score_rows.append(fold_rows[-1])
            held_keys.extend(held_signatures)
            held_targets.extend(held_y.tolist())
            held_values.extend(held_pred.tolist())
    summary = []
    keys = sorted({(r["condition"], r["type"], r["predictor"]) for r in score_rows})
    for condition, kind, name in keys:
        rows = [r for r in score_rows if
                (r["condition"], r["type"], r["predictor"]) == (condition, kind, name)]
        summary.append({"condition": condition, "type": kind, "predictor": name,
            "recordings": len(rows),
            "mean_recording_rmse_spikes_s": float(np.mean([r["rmse_spikes_s"] for r in rows])),
            "mean_gain": float(np.mean([r["gain"] for r in rows]))})
    prediction_array = np.asarray(held_values, dtype=np.float64)
    target_array = np.asarray(held_targets, dtype=np.float64)
    # Fold order repeats each held trial-cell once (one outer recording per key).
    if len(set(held_keys)) != len(held_keys):
        raise ValueError("A held trial-cell appears in multiple outer folds")
    return score_rows, summary, prediction_array, target_array, held_keys


def _self_checks(response: LC10aVisualResponse, renderer: RetinalRenderer) -> dict:
    """Prefix, zeros, constant input, and whole-versus-chunked arithmetic checks."""
    dt = 0.0015000000000000568
    rng = np.random.default_rng(20261006)
    samples = np.zeros((129, renderer.width_px), dtype=np.float64)
    samples[12:39] = rng.random((27, renderer.width_px))
    samples[52:91] = rng.random((39, renderer.width_px))
    whole = _motion_profile(samples, dt)
    decay = math.exp(-dt/0.020)
    delayed = np.zeros(renderer.width_px, dtype=np.float64)
    direct = np.zeros_like(samples)
    previous = np.zeros(renderer.width_px, dtype=np.float64)
    for n, current in enumerate(samples):
        delayed = decay*delayed+(1.0-decay)*previous
        pairs = delayed[:-1]*current[1:]-delayed[1:]*current[:-1]
        direct[n,0],direct[n,-1]=pairs[0],pairs[-1]
        direct[n,1:-1]=(pairs[:-1]+pairs[1:])*0.5
        previous=current
    recurrence_error=float(np.max(np.abs(whole-direct)))
    changed=samples.copy(); changed[64:]=rng.random(changed[64:].shape)
    prefix_error=float(np.max(np.abs(_motion_profile(changed,dt)[:64]-whole[:64])))
    # Chunk boundaries retain prior-frame state through this explicit recurrence.
    state=np.zeros(renderer.width_px); prev=np.zeros(renderer.width_px)
    chunked=np.zeros_like(samples)
    for start,stop in ((0,43),(43,87),(87,len(samples))):
        for n in range(start,stop):
            state=decay*state+(1.0-decay)*prev
            current=samples[n]
            pairs=state[:-1]*current[1:]-state[1:]*current[:-1]
            chunked[n,0],chunked[n,-1]=pairs[0],pairs[-1]
            chunked[n,1:-1]=(pairs[:-1]+pairs[1:])*0.5
            prev=current
    chunk_error=float(np.max(np.abs(chunked-whole)))
    feature=rng.random((129,len(response.body_ids)))
    activity=causal_envelope(feature,dt)
    chunked_activity=np.zeros_like(activity)
    for start,stop in ((0,43),(43,87),(87,len(feature))):
        # The causal kernel is finite. Include all available preceding input,
        # then retain only the requested output interval.
        history_start=max(0,start-int(math.ceil(3.0/dt))-1)
        local=causal_envelope(feature[history_start:stop],dt)
        chunked_activity[start:stop]=local[start-history_start:]
    causal_chunk_error=float(np.max(np.abs(activity-chunked_activity)))
    changed_feature=feature.copy();changed_feature[64:]=rng.random(changed_feature[64:].shape)
    feature_prefix_error=float(np.max(np.abs(
        causal_envelope(changed_feature,dt)[:64]-activity[:64])))
    vertical=_vertical_coverage(renderer,60.)
    zero=np.zeros((4,renderer.width_px))
    blank=_separable_features(response,zero,zero,vertical,"primary")
    constant=np.ones_like(zero)
    constant_features=_separable_features(response,constant,np.zeros_like(constant),
                                          vertical,"primary")
    const_motion=_motion_profile(np.tile(constant[:1],(32,1)),dt)
    if (recurrence_error>1e-12 or prefix_error>1e-12 or chunk_error>1e-12 or
            causal_chunk_error>1e-12 or feature_prefix_error>1e-12):
        raise AssertionError("Prefix or chunked motion recurrence check failed")
    if np.any(blank) or np.any(const_motion):
        raise AssertionError("Zero/constant input motion check failed")
    if not np.isfinite(constant_features).all():
        raise AssertionError("Constant input produced nonfinite spatial drive")
    return {"future_prefix_change_max_abs_error":prefix_error,
        "causal_feature_future_prefix_change_max_abs_error":feature_prefix_error,
        "whole_vs_explicit_recurrence_max_abs_error":recurrence_error,
        "whole_vs_chunked_recurrence_max_abs_error":chunk_error,
        "causal_envelope_one_pass_vs_chunked_max_abs_error":causal_chunk_error,
        "zero_input_features_exactly_zero":True,
        "constant_input_motion_exactly_zero":True,
        "constant_input_features_finite":True}


def _score_summary(rows: list[dict], candidate_names: list[str]) -> tuple[list[dict], dict]:
    summary=[]
    groups=sorted({(r["condition"],r["type"],r["predictor"]) for r in rows})
    for condition,kind,name in groups:
        current=[r for r in rows if (r["condition"],r["type"],r["predictor"])==(condition,kind,name)]
        summary.append({"condition":condition,"type":kind,"predictor":name,
            "recordings":len(current),
            "mean_recording_rmse_spikes_s":float(np.mean([r["rmse_spikes_s"] for r in current])),
            "mean_gain":float(np.mean([r["gain"] for r in current])),
            "gain_min":float(min(r["gain"] for r in current)),
            "gain_max":float(max(r["gain"] for r in current))})
    lookup={(r["condition"],r["type"],r["predictor"]):r["mean_recording_rmse_spikes_s"]
            for r in summary}
    gates={}
    for kind in ("AOTU019","AOTU025"):
        primary=[r for r in rows if r["condition"]=="P1" and r["type"]==kind]
        by_rec={(r["recording"],r["predictor"]):r["rmse_spikes_s"] for r in primary}
        intact="primary:intact"; spatial="primary:matched_spatial"
        legacy="legacy_intact"
        recs=sorted({r["recording"] for r in primary})
        legacy_mean=lookup["P1",kind,legacy]
        intact_mean=lookup["P1",kind,intact]
        spatial_mean=lookup["P1",kind,spatial]
        shuffle_wins=sum(lookup["P1",kind,f"primary:shuffle_{i:02}"]>intact_mean
                         for i in range(32))
        win_count=sum(by_rec[rec,intact]<by_rec[rec,legacy] for rec in recs)
        legacy_reduction=1.0-intact_mean/legacy_mean if legacy_mean else None
        spatial_reduction=1.0-intact_mean/spatial_mean if spatial_mean else None
        gates[kind]={"recordings":len(recs),"legacy_mean_rmse":legacy_mean,
            "intact_mean_rmse":intact_mean,"legacy_rmse_reduction_fraction":legacy_reduction,
            "legacy_recording_wins":win_count,
            "required_legacy_recording_wins":15 if kind=="AOTU019" else 14,
            "matched_spatial_mean_rmse":spatial_mean,
            "spatial_rmse_reduction_fraction":spatial_reduction,
            "shuffle_strict_wins":shuffle_wins,"required_shuffle_wins":30,
            "legacy_gate_pass":bool(legacy_reduction is not None and legacy_reduction>=0.05
                and win_count>= (15 if kind=="AOTU019" else 14)),
            "wiring_gate_pass":bool(spatial_reduction is not None and spatial_reduction>=0.01
                and shuffle_wins>=30)}
        gates[kind]["primary_gate_pass"]=gates[kind]["legacy_gate_pass"] and gates[kind]["wiring_gate_pass"]
    return summary,gates


def _residual_groups(held_keys: list[tuple], held_predictions: np.ndarray,
                     held_targets: np.ndarray, predictor_names: list[str]) -> list[dict]:
    selected=("primary:intact","primary:matched_spatial","legacy_intact","legacy_simple")
    columns={name:predictor_names.index(name) for name in selected}
    groups=defaultdict(list)
    for i,key in enumerate(held_keys):
        condition,kind,_rec,_trial,speed,direction,_center=key
        groups[(condition,kind,speed,direction)].append(i)
    rows=[]
    for (condition,kind,speed,direction),indexes in sorted(groups.items()):
        y=held_targets[indexes]
        for name,column in columns.items():
            error=held_predictions[indexes,column]-y
            rows.append({"condition":condition,"type":kind,"speed_deg_s":speed,
                "direction":direction,"predictor":name,"held_trial_cells":len(indexes),
                "mean_residual_spikes_s":float(np.mean(error)),
                "rmse_spikes_s":float(np.sqrt(np.mean(error*error))),
                "negative_measured_evoked_cells":int(np.sum(y<0))})
    return rows


def _plot_primary(path: Path, observations: list[dict], held_keys: list[tuple],
                  held_predictions: np.ndarray, predictor_names: list[str],
                  held_targets: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    groups=defaultdict(lambda:defaultdict(list))
    predicted={name:predictor_names.index(name) for name in
        ("primary:intact","primary:matched_spatial","legacy_intact","legacy_simple")}
    for i,key in enumerate(held_keys):
        condition,kind,recording,_trial,speed,direction,center=key
        if condition!="P1": continue
        groups[(kind,direction,speed,center)][recording].append(i)
    fig,axes=plt.subplots(4,2,figsize=(13,14),constrained_layout=True)
    for row,(kind,direction) in enumerate(((k,d) for k in ("AOTU019","AOTU025") for d in (-1,1))):
        for col,speed in enumerate((25,75)):
            ax=axes[row,col]
            keys=sorted(k for k in groups if k[:3]==(kind,direction,speed))
            x=[]; observed=[]; sem=[]; traces={n:[] for n in predicted}
            for key in keys:
                recording_values=defaultdict(list)
                target_values=defaultdict(list)
                for rec,indexes in groups[key].items():
                    for i in indexes:
                        recording_values[rec].append(held_predictions[i])
                        target_values[rec].append(held_targets[i])
                recs=sorted(recording_values)
                if len(recs)<3: continue
                record_y=[float(np.mean(target_values[rec])) for rec in recs]
                x.append(key[3]*11.25)
                observed.append(float(np.mean(record_y)))
                sem.append(float(np.std(record_y,ddof=1)/math.sqrt(len(record_y))))
                for name,column in predicted.items():
                    traces[name].append(float(np.mean([np.mean(
                        [held_predictions[i,column] for i in groups[key][rec]]) for rec in recs])))
            if x:
                ax.errorbar(x,observed,yerr=sem,color="#222222",marker="o",markersize=3,
                            capsize=2,label="Measured")
                colors={"primary:intact":"#0072B2","primary:matched_spatial":"#D55E00",
                        "legacy_intact":"#009E73","legacy_simple":"#888888"}
                labels={"primary:intact":"New intact wiring","primary:matched_spatial":"New matched spatial",
                        "legacy_intact":"Legacy connectome input","legacy_simple":"Legacy spatial"}
                for name in predicted:
                    ax.plot(x,traces[name],color=colors[name],label=labels[name],linewidth=1.4)
            ax.axhline(0,color="gray",lw=.5);ax.grid(alpha=.15)
            ax.set(title=f"P1 {kind} | direction {direction:+d} | {speed} deg/s",
                   xlabel="Recorded center bin (degrees)",ylabel="Predicted/measured evoked spikes/s")
    axes[0,0].legend(fontsize=8)
    fig.suptitle("Frozen image-response benchmark | P1 held recordings\n"
                 "Recording-weighted curves; exploratory reused archive holdouts")
    fig.savefig(path,dpi=150,metadata={"Software":"Fly Creature frozen recorded-AOTU benchmark"})
    plt.close(fig)


def _run_review(output_dir: Path, data_dir: Path) -> Path:
    review=ROOT/"tools/review_lc10a_benchmark.py"
    report=output_dir/"preflight_review.json"
    subprocess.run([sys.executable,str(review),"--data-dir",str(data_dir),
                    "--output",str(report)],cwd=ROOT,check=True)
    result=json.loads(report.read_text(encoding="utf-8"))
    if result.get("status")!="pass":
        raise RuntimeError("Frozen benchmark preflight did not pass")
    return report


def run(data_dir: Path=ROOT/"outputs/research/aotu-recordings",
        output_dir: Path=OUTPUT_DIR, *, skip_review: bool=False) -> dict:
    started=time.monotonic()
    output_dir.mkdir(parents=True,exist_ok=True)
    cache_dir=output_dir/"recording-checkpoints"
    cache_dir.mkdir(parents=True,exist_ok=True)
    witness_dir=output_dir/"sensor-witnesses"
    witness_dir.mkdir(parents=True,exist_ok=True)
    contract=json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    protocol=json.loads((ROOT/"docs/evidence/lc10a_benchmark_protocol_v1.json").read_text(encoding="utf-8"))
    if sha(CONTRACT_PATH)!=protocol["contract_sha256"] or sha(PROTOCOL_PATH)!=protocol["protocol_sha256"]:
        raise ValueError("Frozen contract/protocol hashes changed")
    review_path=_run_review(output_dir,data_dir) if not skip_review else output_dir/"preflight_review.json"
    if not review_path.exists():
        raise ValueError("--skip-review requires a saved passing preflight report")
    review=json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status")!="pass":
        raise ValueError("Saved benchmark preflight does not pass")
    if review.get("raw_target_max_error",math.inf)>1e-12 or review.get("legacy_prediction_max_error",math.inf)>1e-10:
        raise ValueError("Independent historical target/legacy reconstruction did not pass")
    projection=ActivityProjection.from_packaged_data()
    control_names,control_matrices,control_report=_load_controls(contract,projection)
    response=LC10aVisualResponse(projection=projection)
    renderer=RetinalRenderer()
    self_checks=_self_checks(response,renderer)
    parity=_canonical_parity(data_dir,renderer,response)
    from .pursuit_motion_diagnostic import model as build_response_model
    response_model=build_response_model(projection)
    lookups={kind:(*response_model.lookups[kind],float(response_model.peaks[kind]))
             for kind in ARCHIVES}
    if lookups["AOTU019"][2]!=PEAKS["AOTU019"] or lookups["AOTU025"][2]!=PEAKS["AOTU025"]:
        raise ValueError("Response model changed the fixed lookup peak")
    observations=_read_csv(OBSERVATION_PATH)
    historical_folds=_read_csv(FOLD_PATH)
    if len(observations)!=35484 or len(historical_folds)!=34554:
        raise ValueError("Historical population artifact counts changed")
    obs_index={_key(row):i for i,row in enumerate(observations)}
    if len(obs_index)!=len(observations):
        raise ValueError("Duplicate historical observation signature")
    candidate_names=[]; config_specs=[]
    for label,ablation in CONFIGURATIONS:
        names,matrices=_config_predictors(control_names,control_matrices,label,ablation)
        config_specs.append((label,ablation,names,matrices))
        candidate_names.extend(names)
    if len(candidate_names)!=345 or len(set(candidate_names))!=345:
        raise AssertionError("Frozen 345 predictor budget/order changed")
    source_digest=sha(Path(__file__))
    predictions=np.full((len(observations),len(candidate_names)),np.nan,dtype=np.float64)
    predictor_index={name:i for i,name in enumerate(candidate_names)}
    representation={}; replay_checks=[]; record_logs=[]; witness_data={}
    complete_recordings=[]; replay_trial_count=0; quiet_pulse_count=0
    rebuilt_trial_cells=0
    witness_seen=set()
    specs_by_label={label:(ablation,names,matrices)
                    for label,ablation,names,matrices in config_specs}
    vertical_full=_vertical_coverage(renderer,60.0)
    vertical_half=_vertical_coverage(renderer,30.0)
    for condition,archives in (("NoP1",ARCHIVES),("P1",P1_ARCHIVES)):
        for kind,(filename,expected_md5) in archives.items():
            path=data_dir/filename
            with path.open("rb") as stream:
                archive_md5=hashlib.file_digest(stream,"md5").hexdigest()
            if archive_md5!=expected_md5:
                raise ValueError(f"Archive checksum mismatch: {filename}")
            with zipfile.ZipFile(path) as archive:
                for member in sorted(n for n in archive.namelist() if n.endswith("_int.mat")):
                    identity=kind+"/"+Path(member).stem.removesuffix("_int")
                    if identity==DUPLICATE: continue
                    payload=archive.read(member)
                    member_sha=hashlib.sha256(payload).hexdigest()
                    native,dt,data=read_recording(payload)
                    elapsed=native-native[0]
                    grid_error=float(np.max(np.abs(elapsed-np.arange(len(native))*dt),initial=0.0))
                    if grid_error>1e-9: raise ValueError(f"Native grid fails frozen tolerance: {identity}")
                    pulses,rejected=extract(native,dt,data,identity,kind,"canonical")
                    quiet=[p for p in pulses if p["state"]=="quiescent"]
                    if not quiet: raise ValueError(f"No quiet pulses for {identity}")
                    grouped=defaultdict(list)
                    for pulse in quiet:
                        key=(condition,kind,identity,int(pulse["trial"]),int(pulse["speed_deg_s"]),
                             int(pulse["direction"]),int(round(pulse["center_deg"]/11.25)))
                        grouped[key].append(pulse)
                    target_error=max((abs(float(np.mean([p["evoked_spikes_s"] for p in ps]))-
                        float(observations[obs_index[key]]["response_spikes_s"]))
                        for key,ps in grouped.items() if key in obs_index),default=0.0)
                    if target_error>1e-12 or len(grouped)!=sum(key in obs_index for key in grouped):
                        raise ValueError(f"Recorded quiet-pulse target coverage changed: {identity}")
                    checkpoint=cache_dir/(hashlib.sha256(identity.encode()).hexdigest()[:20]+".npz")
                    valid_cache=False
                    if checkpoint.exists():
                        with np.load(checkpoint,allow_pickle=False) as saved:
                            valid_cache=(str(saved["source_sha"])==source_digest and
                                str(saved["member_sha"])==member_sha and
                                np.array_equal(saved["names"],np.asarray(candidate_names)) and
                                np.array_equal(saved["keys"],np.asarray([json.dumps(k,separators=(",",":"))
                                    for k in sorted(grouped)])) and
                                saved["predictions"].shape==(len(grouped),len(candidate_names)) and
                                np.isfinite(saved["predictions"]).all())
                            if valid_cache:
                                for row,key in enumerate(sorted(grouped)):
                                    predictions[obs_index[key]]=saved["predictions"][row]
                                cached_rep=json.loads(str(saved["representation_json"]))
                                cached_trials=json.loads(str(saved["trials_json"]))
                                _merge_representation(representation,cached_rep)
                                replay_checks.extend(cached_trials)
                                witness_seen.update((r["condition"],r["type"]) for r in cached_trials
                                    if "canonical_activity_sha256" in r)
                                for witness in cached_trials:
                                    if "canonical_activity_sha256" in witness:
                                        group=(witness["condition"],witness["type"])
                                        witness_path=witness_dir/(group[0]+"_"+group[1]+".npz")
                                        if not witness_path.exists():
                                            raise ValueError("Completed checkpoint lacks its sensory witness")
                                        witness_data[group]=witness_path
                    if not valid_cache:
                        local_values=np.full((len(grouped),len(candidate_names)),np.nan,dtype=np.float64)
                        local_keys=sorted(grouped)
                        local_index={key:i for i,key in enumerate(local_keys)}
                        pulses_by_trial=defaultdict(list)
                        for pulse in quiet: pulses_by_trial[int(pulse["trial"])].append(pulse)
                        local_representation={}; local_trials=[]
                        for trial_index,trial_pulses in sorted(pulses_by_trial.items()):
                            position=data["int_panelps"][:,trial_index]
                            def consume(label,state,vertical,scale,ablation,
                                        components=None,activities=None):
                                names=specs_by_label[label][1]
                                matrices=specs_by_label[label][2]
                                if activities is not None:
                                    canonical,mirrored=activities
                                    info={"grid_error_s":state["grid_error_s"],
                                        "finite_samples":state["finite_samples"]}
                                elif components is None:
                                    canonical,mirrored,info=_activity_from_state(state,dt,response,
                                        vertical,ablation,scale=scale)
                                else:
                                    canonical,mirrored=_activity_pair_from_components(
                                        response,components,vertical,ablation,scale,dt)
                                    info={"grid_error_s":state["grid_error_s"],
                                        "finite_samples":state["finite_samples"]}
                                if label=="primary" and (condition,kind) not in witness_seen:
                                    local_trials.append({"condition":condition,"type":kind,
                                        "recording":identity,"trial":trial_index,"native_samples":len(position),
                                        "finite_samples":int(np.isfinite(position).sum()),
                                        "canonical_activity_sha256":hashlib.sha256(
                                            np.asarray(canonical,dtype="<f8").tobytes()).hexdigest(),
                                        "mirror_activity_sha256":hashlib.sha256(
                                            np.asarray(mirrored,dtype="<f8").tobytes()).hexdigest()})
                                    witness_path=witness_dir/(condition+"_"+kind+".npz")
                                    np.savez_compressed(witness_path,
                                        source_sha=np.asarray(source_digest),
                                        member_sha=np.asarray(member_sha),
                                        canonical=canonical,mirror=mirrored)
                                    witness_data[(condition,kind)]=witness_path
                                    witness_seen.add((condition,kind))
                                filtered,stats=_predict_config(canonical,mirrored,matrices,projection,
                                    kind,names,lookups,dt)
                                for stat in stats:
                                    stat.update({"condition":condition,"type":kind,"recording":identity,
                                                 "trial":trial_index,"configuration":label})
                                _merge_representation(local_representation,stats)
                                if len(filtered)==0:
                                    raise ValueError(f"Empty filtered output: {identity}/{label}")
                                per_cell=defaultdict(list)
                                for pulse in trial_pulses:
                                    margin=int(pulse["margin"])
                                    start=int(pulse["start_sample"])
                                    stop=start+len(pulse["position"])-2*margin
                                    base_lo=start-margin
                                    mask=(pulse["time"]>=-.250)&(pulse["time"]<=-.100)
                                    baseline=base_lo+np.flatnonzero(mask)
                                    if len(baseline)==0 or stop>len(filtered):
                                        raise ValueError("Pulse baseline or target interval invalid")
                                    value=filtered[start:stop].mean(axis=0)-filtered[baseline].mean(axis=0)
                                    key=(condition,kind,identity,trial_index,int(pulse["speed_deg_s"]),
                                         int(pulse["direction"]),int(round(pulse["center_deg"]/11.25)))
                                    per_cell[key].append(value)
                                for key,values in per_cell.items():
                                    idx=local_index[key]
                                    for j,name in enumerate(names):
                                        local_values[idx,predictor_index[name]]=float(
                                            np.mean([value[j] for value in values]))
                                del canonical,mirrored,filtered
                            primary_state=_movie_state(position,elapsed,dt,renderer,11.25,1.0)
                            primary_components=(
                                _horizontal_components(response,primary_state["dark"],
                                                       primary_state["motion"]),
                                _horizontal_components(response,primary_state["mirror_dark"],
                                                       primary_state["mirror_motion"]))
                            base_work=[
                                ("primary","primary",vertical_full,1.0),
                                ("contrast_half","primary",vertical_full,0.5),
                                ("no_surround","no_surround",vertical_full,1.0),
                                ("direction_neutral","direction_neutral",vertical_full,1.0),
                                ("no_static","no_static",vertical_full,1.0),
                                ("vertical_mean","vertical_mean",vertical_full,1.0),
                                ("instantaneous","instantaneous",vertical_full,1.0),
                                ("height_half","primary",vertical_half,1.0)]
                            for batch_start in range(0,len(base_work),4):
                                batch=base_work[batch_start:batch_start+4]
                                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                                    futures={pool.submit(_activity_pair_from_components,
                                        response,primary_components,vertical,ablation,scale,dt):
                                        (label,ablation,vertical,scale)
                                        for label,ablation,vertical,scale in batch}
                                    for future in as_completed(futures):
                                        label,ablation,vertical,scale=futures.pop(future)
                                        activities=future.result()
                                        consume(label,primary_state,vertical,scale,ablation,
                                                activities=activities)
                                        del activities,future
                            del primary_state,primary_components
                            for label,width in (("width_half",5.625),("width_double",22.5)):
                                state=_movie_state(position,elapsed,dt,renderer,width,1.0)
                                components=(
                                    _horizontal_components(response,state["dark"],state["motion"]),
                                    _horizontal_components(response,state["mirror_dark"],
                                                           state["mirror_motion"]))
                                consume(label,state,vertical_full,1.0,"primary",components=components)
                                del state,components
                            local_trials.append({"condition":condition,"type":kind,"recording":identity,
                                "trial":trial_index,"native_samples":len(position),
                                "finite_samples":int(np.isfinite(position).sum()),
                                "grid_error_s":grid_error,"configurations":len(config_specs)})
                        if not np.isfinite(local_values).all():
                            raise ValueError(f"Checkpoint contains missing predictions for {identity}")
                        for i,key in enumerate(local_keys):
                            predictions[obs_index[key]]=local_values[i]
                        np.savez_compressed(checkpoint,source_sha=np.asarray(source_digest),
                            member_sha=np.asarray(member_sha),names=np.asarray(candidate_names),
                            keys=np.asarray([json.dumps(k,separators=(",",":")) for k in local_keys]),
                            predictions=local_values,
                            representation_json=np.asarray(json.dumps(
                                _checkpoint_representation(local_representation),separators=(",",":"))),
                            trials_json=np.asarray(json.dumps(local_trials,separators=(",",":"))))
                        _merge_representation(representation,
                            _checkpoint_representation(local_representation))
                        replay_checks.extend(local_trials)
                    complete_recordings.append(identity)
                    record_logs.append({"condition":condition,"type":kind,"recording":identity,
                        "archive_md5":archive_md5,"member_sha256":member_sha,
                        "native_samples_per_trial":len(native),"trials":data["int_panelps"].shape[1],
                        "replayed_quiet_trials":len({int(p["trial"]) for p in quiet}),
                        "quiet_pulses":len(quiet),"trial_cells":len(grouped),
                        "target_rebuild_max_abs_error":target_error,"rejected":dict(rejected),
                        "checkpoint_reused":valid_cache})
                    quiet_pulse_count+=len(quiet)
                    rebuilt_trial_cells+=len(grouped)
                    replay_trial_count+=len({int(p["trial"]) for p in quiet})
                    print(f"{condition} {identity}: {'reused' if valid_cache else 'replayed'} "
                          f"{len({int(p['trial']) for p in quiet})} full trials",flush=True)
                    progress={"completed_recordings":complete_recordings,
                        "quiet_pulses":quiet_pulse_count,"replay_trials":replay_trial_count,
                        "predictor_count":len(candidate_names),"source_sha256":source_digest}
                    (output_dir/"progress.json").write_text(json.dumps(progress,indent=2)+"\n",
                        encoding="utf-8",newline="\n")
    native_frames=sum(int(r["native_samples_per_trial"])*int(r["replayed_quiet_trials"])
                      for r in record_logs)
    if (len(complete_recordings)!=69 or quiet_pulse_count!=35484 or
            rebuilt_trial_cells!=35484 or replay_trial_count!=sum(
            int(r["replayed_quiet_trials"]) for r in record_logs) or
            native_frames!=76786718):
        raise ValueError(f"Recording/trial coverage differs from contract: recordings={len(complete_recordings)}, "
                         f"pulses={quiet_pulse_count}, trial_cells={rebuilt_trial_cells}, "
                         f"native_frames={native_frames}")
    if not np.isfinite(predictions).all():
        missing=np.argwhere(~np.isfinite(predictions))
        raise ValueError(f"Some observation/predictor entries are missing: {missing[:8].tolist()}")
    if sha(Path(__file__))!=source_digest:
        raise ValueError("Runner source changed during the frozen scoring run")
    expected_witnesses={(condition,kind) for condition in ("NoP1","P1")
                        for kind in ("AOTU019","AOTU025")}
    if set(witness_data)!=expected_witnesses:
        raise ValueError(f"Independent replay witnesses incomplete: {sorted(witness_data)}")
    witness_manifest=[]
    for group in sorted(expected_witnesses):
        witness_path=witness_data[group]
        if not witness_path.exists():
            raise ValueError(f"Missing saved sensory witness: {group}")
        metadata=next(r for r in replay_checks if
            (r.get("condition"),r.get("type"))==group and "canonical_activity_sha256" in r)
        witness_manifest.append({**metadata,
            "witness_archive":str(witness_path.relative_to(output_dir)).replace("\\","/")})
    legacy=np.asarray([[float(r["anatomy_x"]),float(r["simple_spatial_x"]),1.0,0.0]
                       for r in observations],dtype=np.float64)
    all_names=candidate_names+["legacy_intact","legacy_simple","constant","zero"]
    all_raw=np.concatenate((predictions,legacy),axis=1)
    scores,summary,held_values,held_targets,held_keys=_calibrate_and_score(
        all_raw,observations,candidate_names,contract["folds"],historical_folds)
    summary,gates=_score_summary(scores,candidate_names)
    residuals=_residual_groups(held_keys,held_values,held_targets,all_names)
    _write_csv(output_dir/"recording_scores.csv",scores)
    _write_csv(output_dir/"configuration_summary.csv",summary)
    _write_csv(output_dir/"held_residuals_by_direction_speed.csv",residuals)
    representation_rows=_representation_rows(representation)
    _write_csv(output_dir/"representation.csv",representation_rows)
    np.savez_compressed(output_dir/"trial_cell_predictors.npz",
        predictions=predictions,keys=np.asarray([json.dumps(_key(r),separators=(",",":"))
            for r in observations]),predictor_names=np.asarray(candidate_names),
        targets=np.asarray([float(r["response_spikes_s"]) for r in observations]))
    np.savez_compressed(output_dir/"held_predictions.npz",
        predictions=held_values,keys=np.asarray([json.dumps(k,separators=(",",":"))
            for k in held_keys]),predictor_names=np.asarray(all_names),targets=held_targets)
    _plot_primary(output_dir/"p1_primary_curves.png",observations,held_keys,held_values,
                  all_names,held_targets)
    report={"status":"complete","protocol":"docs/lc10a_response_benchmark_protocol.md",
        "protocol_sha256":sha(PROTOCOL_PATH),"contract_sha256":sha(CONTRACT_PATH),
        "runner_sha256":source_digest,"preflight_review":str(review_path),
        "preflight_status":review["status"],"source_lookup_rebuild_max_error":
            review["legacy_prediction_max_error"],
        "counts":{"recordings":len(record_logs),"quiet_pulses_rebuilt":quiet_pulse_count,
            "observations":len(observations),"scored_trial_cells":len(held_keys),
            "native_full_trials":replay_trial_count,"native_frames":native_frames,
            "new_predictors":len(candidate_names),"total_predictors":len(all_names)},
        "control_matrices":control_report,"pre_score_checks":{"historical_preflight":True,
            "separable_public_2d_parity":parity,"numerical_self_checks":self_checks,
            "target_max_abs_error":max((r["target_rebuild_max_abs_error"] for r in record_logs),default=0.0),
            "all_prediction_cells_finite":True,"all_primary_representations_pass":True},
        "representation":{"note":"Rows cover every candidate, native movie, output column and scored full trial.",
            "rows":len(representation_rows),"summaries":representation_rows},
        "scores":{"recording_count":len(record_logs),"primary_gates":gates,
            "configuration_scores":summary,"direction_speed_residuals":residuals,
            "negative_evoked_scored_cells":int(np.sum(held_targets<0))},
        "recordings":record_logs,"independent_replay_witnesses":witness_manifest,
        "claim_boundary":{"connectome_wiring_advantage_claimed":False,
            "interactive_controller_promotion":False,
            "interpretation":"Exploratory reused recording holdouts. The simulated image-response rule is an engineered hypothesis, not measured LC10a firing or validated fly behavior."},
        "runtime_seconds":time.monotonic()-started}
    (output_dir/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True,
        allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",type=Path,default=ROOT/"outputs/research/aotu-recordings")
    parser.add_argument("--output-dir",type=Path,default=OUTPUT_DIR)
    parser.add_argument("--skip-review",action="store_true",
        help="Reuse this output directory's current passing preflight_review.json")
    args=parser.parse_args()
    result=run(args.data_dir,args.output_dir,skip_review=args.skip_review)
    print(json.dumps({"status":result["status"],"counts":result["counts"],
        "primary_gates":result["scores"]["primary_gates"],
        "runtime_seconds":result["runtime_seconds"]},indent=2),flush=True)


if __name__=="__main__":
    main()

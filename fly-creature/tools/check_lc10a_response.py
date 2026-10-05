"""Independent arithmetic and contract checks for the LC10a response probes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import zipfile

import numpy as np
from scipy.integrate import quad

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from fly_creature.lc10a_response import (  # noqa: E402
    ABLATIONS,
    ENVELOPE_HORIZON_S,
    ENVELOPE_KAPPA_S,
    ENVELOPE_SIGMA_PER_S,
    ENVELOPE_BETA_PER_S,
    ENVELOPE_ALPHA_S,
    LC10aVisualResponse,
    RetinalMotionFrontEnd,
    causal_envelope,
    temporal_interval_weights,
    temporal_kernel_unnormalized,
)
from fly_creature.pursuit_activity import ActivityProjection  # noqa: E402
from fly_creature.retina import RetinalRenderer  # noqa: E402
from run_lc10a_response_probes import load_probes, sha256  # noqa: E402


MANIFEST_PATH = ROOT / "docs/evidence/lc10a_response_design_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/research/lc10a-response-v1"


def _independent_kernel(lag_s: float) -> float:
    def sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))
    return (sigmoid(ENVELOPE_SIGMA_PER_S * (ENVELOPE_KAPPA_S - lag_s)) *
            sigmoid(ENVELOPE_BETA_PER_S * (lag_s + ENVELOPE_ALPHA_S)))


def _direct_visual_drive(image: np.ndarray, motion: np.ndarray,
                         center_abs_deg: float, side: str) -> float:
    """Slow 2D weighted-sum reference, independently written from the design."""
    height, width = image.shape
    pitch = 1.875
    x = (np.arange(width, dtype=np.float64) + 0.5 - width / 2) * pitch
    y = (height / 2 - np.arange(height, dtype=np.float64) - 0.5) * pitch
    sign = 1.0 if side == "R" else -1.0
    center = sign * center_abs_deg
    aperture = np.clip(0.5 + sign * x / 15.0, 0.0, 1.0)
    static = np.abs(image - 1.0)
    direction = sign * motion
    preferred = np.maximum(direction, 0.0) + 0.5 * np.maximum(-direction, 0.0)
    outputs = []
    for y_center in y:
        g_center = np.exp(-0.5 * ((x[None, :] - center) / 7.5) ** 2
                          -0.5 * ((y[:, None] - y_center) / 7.5) ** 2)
        g_surround = np.exp(-0.5 * ((x[None, :] - center) / 22.5) ** 2
                            -0.5 * ((y[:, None] - y_center) / 22.5) ** 2)
        raw_center = g_center * aperture[None, :]
        raw_surround = g_surround * aperture[None, :]
        k_center = raw_center / raw_center.sum(dtype=np.float64)
        k_surround = raw_surround / raw_surround.sum(dtype=np.float64)
        static_dog = max(0.0, float(np.sum(k_center * static) -
                                    np.sum(k_surround * static)))
        motion_dog = max(0.0, float(np.sum(k_center * preferred) -
                                    np.sum(k_surround * preferred)))
        outputs.append(0.25 * static_dog + 0.75 * motion_dog)
    return max(outputs)


def _check_identity_and_report(output_dir: Path, manifest: dict) -> dict:
    protected = {}
    for relative, expected in manifest["protected_sha256"].items():
        actual = sha256(ROOT / relative)
        protected[relative] = actual == expected
        if actual != expected:
            raise AssertionError(f"Frozen input changed: {relative}")
    report_path = output_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["response_module_sha256"] != sha256(ROOT / "src/fly_creature/lc10a_response.py"):
        raise AssertionError("Report does not identify the current response implementation")
    if report["runner_sha256"] != sha256(TOOLS / "run_lc10a_response_probes.py"):
        raise AssertionError("Report does not identify the current probe runner")
    summary = list(csv.DictReader((output_dir / "probe_summary.csv").open(
        encoding="utf-8", newline="")))
    if len(summary) != 68 or report["probe_count"] != 68:
        raise AssertionError("The primary probe run must retain exactly 68 rows")
    if report["cell_count"] != 275 or report["mapped_centers"] != 164 or report["fallback_centers"] != 111:
        raise AssertionError("LC10a map counts/order changed")
    if report["physiology_benchmark_started"] or report["godot_or_production_changed"]:
        raise AssertionError("Probe stage crossed a frozen implementation boundary")
    projection = ActivityProjection.from_packaged_data()
    if not np.array_equal(projection.body_ids, np.sort(projection.body_ids)):
        raise AssertionError("LC10a body IDs are not in ascending order")
    trace_path = output_dir / report["trace_archive"]
    if sha256(trace_path) != report["trace_archive_sha256"]:
        raise AssertionError("Trace archive hash disagrees with the response report")
    with zipfile.ZipFile(trace_path) as archive:
        names = archive.namelist()
        if len(names) != 68:
            raise AssertionError("Expected one activity trace for each frozen probe")
        traces = {}
        for name in names:
            values = np.load(archive.open(name), allow_pickle=False)
            if values.shape != (3000, 275) or not np.all(np.isfinite(values)):
                raise AssertionError(f"Invalid full response trace: {name}")
            if np.min(values) < -1e-12 or np.max(values) > 1.0 + 1e-10:
                raise AssertionError(f"Response outside hypothesized [0,1] range: {name}")
            traces[Path(name).stem] = values
        null_max = max(float(np.max(traces[name])) for name in
                       ("absent_R", "absent_L", "zero_contrast_R", "zero_contrast_L"))
        if null_max > manifest["tolerances"]["null_and_uniform_motion_atol"]:
            raise AssertionError(f"Null probes generated activity: {null_max}")
        polarity_error = float(np.max(np.abs(
            traces["contrast_-1_R"] - traces["contrast_1_R"])))
        if polarity_error > manifest["tolerances"]["mirror_and_chunk_atol"]:
            raise AssertionError(f"Bright/dark static polarity differs: {polarity_error}")
    return {"frozen_hashes_checked": len(protected), "probe_rows": len(summary),
            "trace_shapes": [3000, 275], "null_probe_max_activity": null_max,
            "bright_dark_trace_max_abs_error": polarity_error,
            "cell_identity_matches_packaged_projection": True}


def _check_envelope(manifest: dict) -> dict:
    normalizer, normalizer_error = quad(_independent_kernel, 0.0,
                                         ENVELOPE_HORIZON_S, epsabs=1e-14,
                                         epsrel=1e-13, limit=100)
    intervals = {}
    for dt in (0.002, 0.0015):
        weights = temporal_interval_weights(dt)
        if abs(float(np.sum(weights)) - 1.0) > manifest["tolerances"]["envelope_mass_error"]:
            raise AssertionError(f"Envelope bins do not sum to one for dt={dt}")
        selected = sorted(set((0, 1, 17, int(round(.371 / dt)),
                               len(weights) // 2, len(weights) - 1)))
        interval_errors = []
        for index in selected:
            lo = index * dt
            hi = min((index + 1) * dt, ENVELOPE_HORIZON_S)
            direct, _ = quad(_independent_kernel, lo, hi, epsabs=1e-15,
                             epsrel=1e-12, limit=100)
            interval_errors.append(abs(weights[index] - direct / normalizer))
        intervals[f"{dt:g}"] = {"bin_count": int(weights.size),
                                 "mass": float(np.sum(weights)),
                                 "max_sampled_bin_error": max(interval_errors)}
    dt = 0.002
    feature = np.zeros((301, 1), dtype=np.float64)
    feature[:50, 0] = 1.0
    response = causal_envelope(feature, dt)
    sample = 250  # t=0.5 s; the past pulse is [0,0.1) s.
    direct, _ = quad(_independent_kernel, 0.4, 0.5, epsabs=1e-14,
                     epsrel=1e-13, limit=100)
    expected = direct / normalizer
    pulse_error = abs(float(response[sample, 0]) - expected)
    if pulse_error > manifest["tolerances"]["known_held_pulse_quadrature_error"]:
        raise AssertionError(f"Held-pulse quadrature mismatch: {pulse_error}")
    future_a = np.zeros((300, 3), dtype=np.float64)
    future_b = future_a.copy()
    future_a[:100] = np.linspace(0.0, 1.0, 100)[:, None]
    future_b[:100] = future_a[:100]
    future_b[100:] = 0.9
    left = causal_envelope(future_a, dt)
    right = causal_envelope(future_b, dt)
    causal_error = float(np.max(np.abs(left[:100] - right[:100])))
    if causal_error > manifest["tolerances"]["mirror_and_chunk_atol"]:
        raise AssertionError("Future feature values altered a shared causal prefix")
    return {"independent_continuous_normalizer": normalizer,
            "normalizer_quad_error": normalizer_error,
            "interval_weights": intervals,
            "held_pulse_expected": expected,
            "held_pulse_observed": float(response[sample, 0]),
            "held_pulse_abs_error": pulse_error,
            "future_prefix_max_abs_error": causal_error,
            "sample_zero_response": float(response[0, 0])}


def _check_spatial_arithmetic(manifest: dict) -> dict:
    model = LC10aVisualResponse()
    rng = np.random.default_rng(918273)
    image = rng.uniform(0.0, 2.0, size=(32, 176))
    motion = rng.uniform(-0.18, 0.18, size=(32, 176))
    actual, _, _ = model.spatial_features(np.abs(image - 1.0), motion)
    indexes = (0, 137, 274)
    errors = {}
    for index in indexes:
        side = str(model.sides[index])
        expected = _direct_visual_drive(image, motion, float(model.centers_deg[index]), side)
        errors[str(int(model.body_ids[index]))] = abs(float(actual[0, index]) - expected)
    max_error = max(errors.values())
    tolerance = (manifest["tolerances"]["direct_pooling_atol"] +
                 manifest["tolerances"]["direct_pooling_rtol"] * 1.0)
    if max_error > tolerance:
        raise AssertionError(f"Optimized and direct spatial pooling differ by {max_error}")
    flat = np.full((1, 32, 176), 0.37, dtype=np.float64)
    no_motion = np.zeros_like(flat)
    uniform, _, _ = model.spatial_features(flat, no_motion)
    uniform_residual = float(np.max(uniform))
    if uniform_residual > manifest["tolerances"]["null_and_uniform_motion_atol"]:
        raise AssertionError("Uniform contrast generated a center-surround residual")
    return {"sampled_body_ids": [int(model.body_ids[i]) for i in indexes],
            "direct_pooling_abs_errors": errors,
            "max_direct_pooling_abs_error": max_error,
            "uniform_image_max_drive": uniform_residual,
            "kernel_horizontal_sum_error": max(
                float(np.max(np.abs(model.center_x.sum(axis=1) - 1.0))),
                float(np.max(np.abs(model.surround_x.sum(axis=1) - 1.0)))),
            "pre_normalization_center_mass_min_max": [
                float(model.center_mass.min()), float(model.center_mass.max())],
            "pre_normalization_surround_mass_min_max": [
                float(model.surround_mass.min()), float(model.surround_mass.max())]}


def _check_motion_mirror_and_chunking(manifest: dict) -> dict:
    rng = np.random.default_rng(751)
    original = RetinalMotionFrontEnd()
    reflected = RetinalMotionFrontEnd()
    mirror_error = 0.0
    for index in range(12):
        image = rng.uniform(0.2, 1.8, size=(32, 176))
        _, motion = original.step(image, index * 0.002)
        _, mirror_motion = reflected.step(image[:, ::-1], index * 0.002)
        mirror_error = max(mirror_error,
                           float(np.max(np.abs(mirror_motion + motion[:, ::-1]))))
    if mirror_error > manifest["tolerances"]["mirror_and_chunk_atol"]:
        raise AssertionError(f"Mirrored motion detector did not reverse: {mirror_error}")

    probes = load_probes(ROOT / "docs/evidence/lc10a_sensor_probes_v1.csv")
    probe = next(row for row in probes if row["probe_id"] == "dot10_dir1_unstimulated_R")
    renderer = RetinalRenderer()
    short_model = LC10aVisualResponse()
    short_eight = short_model.simulate_movie(probe, renderer, duration_s=0.24,
                                             dt_s=0.002, block_frames=8)
    short_thirtytwo = short_model.simulate_movie(probe, renderer, duration_s=0.24,
                                                 dt_s=0.002, block_frames=32)
    chunk_error = max(float(np.max(np.abs(short_eight.features - short_thirtytwo.features))),
                      float(np.max(np.abs(short_eight.activity - short_thirtytwo.activity))))
    if chunk_error > manifest["tolerances"]["mirror_and_chunk_atol"]:
        raise AssertionError(f"Frame chunking changed the response: {chunk_error}")

    right_probe = dict(probe, probe_id="virtual_right", center_azimuth_deg="60",
                       azimuth_velocity_deg_s="75", onset_s="0.1",
                       visible_duration_s="0.8", width_deg="10", height_deg="10")
    left_probe = dict(right_probe, probe_id="virtual_left", center_azimuth_deg="-60",
                      azimuth_velocity_deg_s="-75")
    right = LC10aVisualResponse.virtual_unit(60.0, "R").simulate_movie(
        right_probe, renderer, duration_s=1.2, dt_s=0.002)
    left = LC10aVisualResponse.virtual_unit(60.0, "L").simulate_movie(
        left_probe, renderer, duration_s=1.2, dt_s=0.002)
    virtual_mirror_error = float(np.max(np.abs(right.activity - left.activity)))
    if virtual_mirror_error > manifest["tolerances"]["mirror_and_chunk_atol"]:
        raise AssertionError(f"Virtual mirrored image responses differ: {virtual_mirror_error}")
    return {"random_image_motion_mirror_max_abs_error": mirror_error,
            "virtual_unit_response_mirror_max_abs_error": virtual_mirror_error,
            "chunk_8_vs_32_max_abs_error": chunk_error,
            "causal_prefix_checked": True,
            "retinal_boundary_wrap": False}


def _check_irregular_step(manifest: dict) -> dict:
    """Compare the stateful irregular-timestamp path to independent quadrature."""
    rows = load_probes(ROOT / "docs/evidence/lc10a_sensor_probes_v1.csv")
    probe = next(row for row in rows if row["probe_id"] == "dot10_dir1_unstimulated_R")
    renderer = RetinalRenderer()
    model = LC10aVisualResponse()
    times = (0.0, 0.003, 0.011, 0.024, 0.051)
    gains = (1.0, 1.7, 0.8, 2.0, 0.5)
    features = []
    observed = []
    for time_s, gain in zip(times, gains):
        # Renderer time moves the finite target; the response API receives only
        # the image and the deliberately irregular timestamp.
        image = renderer.render_linear(probe, 1.0 + time_s)
        feature, activity = model.step(image, time_s, state_gain=gain)
        features.append(feature)
        observed.append(activity)
    normalizer, _ = quad(_independent_kernel, 0.0, ENVELOPE_HORIZON_S,
                         epsabs=1e-14, epsrel=1e-13, limit=100)
    errors = []
    for n in range(1, len(times)):
        expected = np.zeros_like(features[n])
        for k in range(n):
            lag_lo = max(0.0, times[n] - times[k + 1])
            lag_hi = min(ENVELOPE_HORIZON_S, times[n] - times[k])
            if lag_hi > lag_lo:
                area, _ = quad(_independent_kernel, lag_lo, lag_hi,
                               epsabs=1e-14, epsrel=1e-12, limit=100)
                expected += features[k] * (area / normalizer)
        expected *= gains[n]
        errors.append(float(np.max(np.abs(observed[n] - expected))))
    maximum = max(errors, default=0.0)
    if maximum > manifest["tolerances"]["direct_pooling_atol"]:
        raise AssertionError(f"Irregular-time integration mismatch: {maximum}")
    return {"timestamps_s": list(times), "current_gains": list(gains),
            "max_independent_quadrature_abs_error": maximum,
            "sample_count": len(times), "past_held_intervals_only": True}


class ExactRectangleRenderer:
    """Analytic pixel-area rectangle coverage, independent of supersampling."""

    def __init__(self):
        self.base = RetinalRenderer(oversample=8)
        self.width_px = 176
        self.height_px = 32
        self.pitch = 1.875
        self.az_min = -165.0
        self.el_min = -30.0
        self.azimuth = ((np.arange(self.width_px) + 0.5 - self.width_px / 2) * self.pitch)
        self.elevation = ((self.height_px / 2 - np.arange(self.height_px) - 0.5)
                          * self.pitch)

    def render_linear(self, probe: dict, time_s: float) -> np.ndarray:
        image = self.base._background(probe, time_s)
        if not RetinalRenderer._flag(probe["target_present"]):
            return image
        onset = float(probe["onset_s"])
        end = onset + float(probe["visible_duration_s"])
        if not onset <= time_s < end:
            return image
        if probe["shape"] != "rectangle":
            raise ValueError("Exact rectangle reference applies only to rectangle probes")
        width, height = float(probe["width_deg"]), float(probe["height_deg"])
        cx = float(probe["center_azimuth_deg"]) + float(
            probe["azimuth_velocity_deg_s"]) * (time_s - onset - (end - onset) / 2)
        cy = float(probe["center_elevation_deg"])
        left, right = cx - width / 2, cx + width / 2
        bottom, top = cy - height / 2, cy + height / 2
        pixel_left = self.azimuth - self.pitch / 2
        pixel_right = self.azimuth + self.pitch / 2
        pixel_bottom = self.elevation - self.pitch / 2
        pixel_top = self.elevation + self.pitch / 2
        x_overlap = np.maximum(0.0, np.minimum(pixel_right, right) - np.maximum(pixel_left, left))
        y_overlap = np.maximum(0.0, np.minimum(pixel_top, top) - np.maximum(pixel_bottom, bottom))
        coverage = np.outer(y_overlap, x_overlap) / (self.pitch * self.pitch)
        target_luminance = 1.0 + float(probe["weber_contrast"])
        return image * (1.0 - coverage) + target_luminance * coverage


def _mirror_probe(probe: dict[str, str], eye: str, phase_offset: float) -> dict[str, str]:
    value = dict(probe)
    original_sign = 1.0 if probe["eye"] == "R" else -1.0
    target_sign = 1.0 if eye == "R" else -1.0
    mirror_sign = target_sign / original_sign
    for key in ("center_azimuth_deg", "azimuth_velocity_deg_s",
                "surround_velocity_deg_s", "surround_phase_deg"):
        value[key] = str(mirror_sign * float(probe[key]))
    value["center_azimuth_deg"] = str(float(value["center_azimuth_deg"]) +
                                      target_sign * phase_offset)
    value["eye"] = eye
    value["probe_id"] = f"{probe['probe_id']}_{eye}_phase{phase_offset:g}"
    return value


def _check_raster(manifest: dict, output_dir: Path) -> dict:
    probes = load_probes(ROOT / "docs/evidence/lc10a_sensor_probes_v1.csv")
    by_id = {row["probe_id"]: row for row in probes}
    config = manifest["raster_checks"]
    offsets = config["horizontal_phase_offsets_deg"]
    oversamples = config["oversamples_per_axis"]
    rows = []
    start = time.perf_counter()
    for probe_id in config["probe_ids"]:
        source = by_id[probe_id]
        for eye in ("R", "L"):
            for offset in offsets:
                probe = _mirror_probe(source, eye, float(offset))
                center_abs = abs(float(probe["center_azimuth_deg"]))
                responses: dict[int, float] = {}
                for oversample in oversamples:
                    virtual = LC10aVisualResponse.virtual_unit(center_abs, eye)
                    result = virtual.simulate_movie(
                        probe, RetinalRenderer(oversample=oversample),
                        duration_s=6.0, dt_s=0.002, block_frames=32)
                    responses[oversample] = float(np.sum(result.activity, dtype=np.float64) * 0.002)
                reference = responses[32]
                for oversample in (8, 16):
                    error = abs(responses[oversample] - reference) / max(
                        abs(reference), config["relative_denominator_floor"])
                    rows.append({"probe_id": probe_id, "eye": eye,
                                 "phase_offset_deg": float(offset),
                                 "oversample": oversample,
                                 "reference_oversample": 32,
                                 "integral": responses[oversample],
                                 "reference_integral": reference,
                                 "relative_error": error,
                                 "reference_type": "subpixel_32"})
                if source["shape"] == "rectangle":
                    exact = LC10aVisualResponse.virtual_unit(center_abs, eye).simulate_movie(
                        probe, ExactRectangleRenderer(), duration_s=6.0,
                        dt_s=0.002, block_frames=32)
                    exact_integral = float(np.sum(exact.activity, dtype=np.float64) * 0.002)
                    error = abs(responses[8] - exact_integral) / max(
                        abs(exact_integral), config["relative_denominator_floor"])
                    rows.append({"probe_id": probe_id, "eye": eye,
                                 "phase_offset_deg": float(offset),
                                 "oversample": 8, "reference_oversample": "exact_rectangle",
                                 "integral": responses[8],
                                 "reference_integral": exact_integral,
                                 "relative_error": error,
                                 "reference_type": "exact_rectangle"})
    output_path = output_dir / "raster_convergence.csv"
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    max_error = max(float(row["relative_error"]) for row in rows)
    # Direction-preference sign must not flip across raster resolutions.
    pos = by_id["dot10_dir1_unstimulated_R"]
    neg = by_id["dot10_dir-1_unstimulated_R"]
    direction_rows = []
    for oversample in oversamples:
        values = []
        for source in (pos, neg):
            probe = _mirror_probe(source, "R", 0.0)
            center_abs = abs(float(probe["center_azimuth_deg"]))
            result = LC10aVisualResponse.virtual_unit(center_abs, "R").simulate_movie(
                probe, RetinalRenderer(oversample=oversample), duration_s=6.0,
                dt_s=0.002, block_frames=32)
            values.append(float(np.sum(result.activity, dtype=np.float64) * 0.002))
        difference = values[0] - values[1]
        direction_rows.append({"oversample": oversample, "progressive_integral": values[0],
                               "regressive_integral": values[1],
                               "progressive_minus_regressive": difference,
                               "sign": int(np.sign(difference))})
    signs = {int(row["sign"]) for row in direction_rows if row["sign"] != 0}
    sign_reversal = len(signs) > 1
    tolerance = config["integrated_virtual_response_relative_error_max"]
    if max_error > tolerance:
        raise AssertionError(f"Raster convergence exceeded {tolerance:.1%}: {max_error:.3%}")
    if config["direction_preference_sign_reversal_allowed"] is False and sign_reversal:
        raise AssertionError("Raster resolution reversed direction preference")
    return {"rows": len(rows), "max_relative_error": max_error,
            "threshold": tolerance, "direction_resolution_results": direction_rows,
            "direction_sign_reversal": sign_reversal,
            "elapsed_s": time.perf_counter() - start,
            "csv": output_path.name, "csv_sha256": sha256(output_path)}


def run(output_dir: Path, *, raster: bool = True) -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    identity = _check_identity_and_report(output_dir, manifest)
    envelope = _check_envelope(manifest)
    spatial = _check_spatial_arithmetic(manifest)
    motion = _check_motion_mirror_and_chunking(manifest)
    irregular = _check_irregular_step(manifest)
    probe_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    aux = probe_report["auxiliary_and_numerical_checks"]
    if not aux["absent_equals_zero_contrast_frames"]:
        raise AssertionError("Absent and zero-contrast stimulus frames differ")
    if not aux["invisible_target_metadata_does_not_change_frames"]:
        raise AssertionError("Invisible target metadata altered retinal frames")
    if aux["whole_panel_flash_motion_max"] > manifest["tolerances"]["null_and_uniform_motion_atol"]:
        raise AssertionError("Uniform whole-field flash triggered image motion")
    if aux["stationary_object_motion_max"] > manifest["tolerances"]["null_and_uniform_motion_atol"]:
        raise AssertionError("Stationary object triggered sustained image motion")
    if aux["uniform_local_motion_max_drive"] > manifest["tolerances"]["null_and_uniform_motion_atol"]:
        raise AssertionError("Uniform local motion created center-surround drive")
    if aux["explicit_gain_two_max_abs_error"] > 1e-12 or aux["label_swap_max_abs_error"] > 1e-12:
        raise AssertionError("Gain or label software check failed")
    if (aux["first_sample_response_max"] > 1e-12 or
            aux["reset_clears_history_max"] > 1e-12 or
            aux["first_sample_drive_max"] <= 0 or
            aux["second_sample_response_max"] <= 0 or
            aux["post_reset_second_sample_max"] <= 0):
        raise AssertionError("First-sample/reset history invariant failed")
    checks = {"identity_and_artifact_integrity": identity,
              "independent_envelope_arithmetic": envelope,
              "independent_spatial_pooling": spatial,
              "motion_mirror_chunking": motion,
              "irregular_timestamp_integration": irregular,
              "auxiliary_controls": aux,
              "raster_convergence": _check_raster(manifest, output_dir) if raster else "skipped"}
    result = {"status": "pass", "checks": checks,
              "claim_limit": "software and numerical checks only; no physiological score or Godot promotion",
              "checker_sha256": sha256(Path(__file__))}
    path = output_dir / "check_report.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-raster", action="store_true",
                        help="skip the slower render-resolution convergence matrix")
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir, raster=not args.skip_raster), indent=2,
                     sort_keys=True))


if __name__ == "__main__":
    main()

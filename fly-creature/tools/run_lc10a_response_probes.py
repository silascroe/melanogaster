"""Run the frozen LC10a image-response rule on the 68 offline probes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fly_creature.lc10a_response import (  # noqa: E402
    LC10aVisualResponse,
    causal_envelope,
    temporal_interval_weights,
)
from fly_creature.retina import RetinalRenderer  # noqa: E402


DEFAULT_MATRIX = ROOT / "docs/evidence/lc10a_sensor_probes_v1.csv"
DEFAULT_MANIFEST = ROOT / "docs/evidence/lc10a_response_design_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/research/lc10a-response-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_probes(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 68 or len({row["probe_id"] for row in rows}) != len(rows):
        raise ValueError("Frozen probe matrix must have 68 unique rows")
    if any(abs(float(row["dt_s"]) - 0.002) > 1e-12 for row in rows):
        raise ValueError("The frozen response probe stage requires 2 ms probes")
    return rows


def float_summary(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {"mean": 0.0, "max": 0.0, "integral": 0.0}
    return {
        "mean": float(np.mean(values, dtype=np.float64)),
        "max": float(np.max(values)),
        "integral": float(np.sum(values, dtype=np.float64) * 0.002),
    }


def group_activity(activity: np.ndarray, model: LC10aVisualResponse) -> dict[str, float]:
    result: dict[str, float] = {}
    for side in ("L", "R"):
        for provenance in ("mapped", "fallback"):
            indexes = np.flatnonzero((model.sides == side) &
                                     (model.angle_provenance == provenance))
            result[f"{side}_{provenance}_mean"] = float(
                np.mean(activity[:, indexes], dtype=np.float64)) if indexes.size else 0.0
    return result


def write_trace(archive: zipfile.ZipFile, name: str, values: np.ndarray) -> None:
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(values, dtype=np.float64), allow_pickle=False)
    info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, buffer.getvalue(), compress_type=zipfile.ZIP_DEFLATED,
                     compresslevel=6)


def summarize_probe(probe: dict[str, str], result, model: LC10aVisualResponse) -> dict:
    activity = result.activity
    visible_end = float(probe["onset_s"]) + float(probe["visible_duration_s"])
    tail = result.times_s >= 3.0
    visible = ((result.times_s >= float(probe["onset_s"])) &
               (result.times_s < visible_end))
    peak_frame = int(np.argmax(np.mean(activity, axis=1)))
    return {
        "probe_id": probe["probe_id"],
        "family": probe["family"],
        "eye": probe["eye"],
        "target_present": probe["target_present"],
        "shape": probe["shape"],
        "width_deg": float(probe["width_deg"]),
        "height_deg": float(probe["height_deg"]),
        "center_azimuth_deg": float(probe["center_azimuth_deg"]),
        "center_elevation_deg": float(probe["center_elevation_deg"]),
        "azimuth_velocity_deg_s": float(probe["azimuth_velocity_deg_s"]),
        "weber_contrast": float(probe["weber_contrast"]),
        "surround": probe["surround"],
        "surround_velocity_deg_s": float(probe["surround_velocity_deg_s"]),
        "state_label_ignored_by_response": probe["state"],
        "frames": int(activity.shape[0]),
        "dt_s": 0.002,
        "max_feature": float(np.max(result.features)),
        "mean_feature": float(np.mean(result.features, dtype=np.float64)),
        "max_activity": float(np.max(activity)),
        "mean_activity": float(np.mean(activity, dtype=np.float64)),
        "total_integral": float(np.sum(activity, dtype=np.float64) * 0.002),
        "visible_mean_activity": float(np.mean(activity[visible], dtype=np.float64))
        if np.any(visible) else 0.0,
        "tail_max_activity_3_6s": float(np.max(activity[tail])) if np.any(tail) else 0.0,
        "population_peak_time_s": float(result.times_s[peak_frame]),
        "mean_winning_row": float(np.mean(result.winning_rows, dtype=np.float64)),
        **group_activity(activity, model),
    }


def make_absent(probe: dict[str, str]) -> dict[str, str]:
    absent = dict(probe)
    absent["target_present"] = "False"
    absent["probe_id"] = f"{probe['probe_id']}_target_absent"
    return absent


def _flash_probe(contrast: float, eye: str) -> dict[str, str]:
    return {
        "probe_id": f"whole_panel_flash_{'bright' if contrast > 0 else 'dark'}_{eye}",
        "family": "auxiliary_flash", "eye": eye, "target_present": "True",
        "shape": "rectangle", "width_deg": "330", "height_deg": "60",
        "center_azimuth_deg": "0", "center_elevation_deg": "0",
        "azimuth_velocity_deg_s": "0", "weber_contrast": str(contrast),
        "surround": "uniform", "surround_velocity_deg_s": "0",
        "surround_period_deg": "0", "surround_phase_deg": "0",
        "surround_weber_amplitude": "0", "state": "unspecified",
        "onset_s": "1", "visible_duration_s": "0.4", "dt_s": "0.002",
    }


class PausedDiscRenderer:
    """Piecewise-constant-motion auxiliary stimulus, with a uniform surround."""

    def __init__(self, eye: str, oversample: int = 8):
        self.base = RetinalRenderer(oversample=oversample)
        sign = 1.0 if eye == "R" else -1.0
        self.segments = ((1.0, 1.4, 30.0 * sign, 75.0 * sign),
                         (1.4, 1.9, 60.0 * sign, 0.0),
                         (1.9, 2.3, 60.0 * sign, 75.0 * sign))
        self.eye = eye

    def render_linear(self, probe: dict[str, str], time_s: float) -> np.ndarray:
        image = np.ones((32, 176), dtype=np.float64)
        for start, end, start_x, velocity in self.segments:
            if start <= time_s < end:
                row = dict(probe)
                row.update(target_present="True", shape="disc", width_deg="10",
                           height_deg="10", center_azimuth_deg=str(
                               start_x + velocity * (end - start) / 2),
                           center_elevation_deg="0", azimuth_velocity_deg_s=str(velocity),
                           weber_contrast="-1", onset_s=str(start),
                           visible_duration_s=str(end - start), surround="uniform")
                return self.base.render_linear(row, time_s)
        return image


def _auxiliary_checks(model: LC10aVisualResponse, probes: list[dict[str, str]],
                      renderer: RetinalRenderer, dt_s: float) -> dict:
    by_id = {probe["probe_id"]: probe for probe in probes}
    checks: dict[str, object] = {}

    absent = by_id["absent_R"]
    invisible_variants = dict(absent)
    invisible_variants.update(center_azimuth_deg="-130", center_elevation_deg="29",
                              width_deg="91", height_deg="43",
                              azimuth_velocity_deg_s="-120", weber_contrast="0.91",
                              onset_s="4.2", visible_duration_s="1.2")
    sample_times = (0.0, 1.1, 5.998)
    invisible_equal = all(np.array_equal(renderer.render_linear(absent, t),
                                         renderer.render_linear(invisible_variants, t))
                          for t in sample_times)
    zero = by_id["zero_contrast_R"]
    zero_equal = all(np.array_equal(renderer.render_linear(absent, t),
                                    renderer.render_linear(zero, t)) for t in sample_times)
    checks["absent_equals_zero_contrast_frames"] = zero_equal
    checks["invisible_target_metadata_does_not_change_frames"] = invisible_equal

    # Explicit gain and label checks reuse a single computed movie: the gain is
    # applied after recalled history, and the P1 label is not a neural input.
    gain_probe = by_id["dot25_dir1_unstimulated_R"]
    base_result = model.simulate_movie(gain_probe, renderer, duration_s=6.0,
                                       dt_s=dt_s, state_gain=1.0)
    gain_two = causal_envelope(base_result.features, dt_s, state_gain=2.0)
    checks["explicit_gain_two_max_abs_error"] = float(
        np.max(np.abs(gain_two - 2.0 * base_result.activity)))
    stimulated_label = dict(gain_probe, state="P1_stimulated")
    label_result = model.simulate_movie(stimulated_label, renderer, duration_s=6.0,
                                        dt_s=dt_s, state_gain=1.0)
    checks["label_swap_max_abs_error"] = float(
        np.max(np.abs(label_result.activity - base_result.activity)))

    # A spatially uniform whole-field flash changes contrast but cannot create
    # adjacent-pixel correlation. Test both polarities and both mirrors.
    flash_motion_max = 0.0
    flash_responses: list[dict] = []
    for eye in ("R", "L"):
        for contrast in (-1.0, 1.0):
            probe = _flash_probe(contrast, eye)
            frontend = model.frontend.__class__()
            motion_max = 0.0
            static_max = 0.0
            for index in range(3000):
                t = index * dt_s
                image = renderer.render_linear(probe, t)
                static, motion = frontend.step(image, t)
                motion_max = max(motion_max, float(np.max(np.abs(motion))))
                static_max = max(static_max, float(np.max(static)))
            flash_motion_max = max(flash_motion_max, motion_max)
            flash_responses.append({"probe_id": probe["probe_id"],
                                    "max_static_contrast": static_max,
                                    "max_motion": motion_max})
    checks["whole_panel_flash_motion_max"] = flash_motion_max
    checks["whole_panel_flashes"] = flash_responses

    stationary_probe = by_id["stationary_object_R"]
    stationary_frontend = model.frontend.__class__()
    stationary_motion_max = 0.0
    for index in range(3000):
        t = index * dt_s
        _, motion = stationary_frontend.step(renderer.render_linear(stationary_probe, t), t)
        stationary_motion_max = max(stationary_motion_max,
                                    float(np.max(np.abs(motion))))
    checks["stationary_object_motion_max"] = stationary_motion_max
    uniform_motion = np.full((1, 32, 176), 0.25, dtype=np.float64)
    uniform_contrast = np.zeros_like(uniform_motion)
    uniform_motion_drive = model.spatial_features(uniform_contrast, uniform_motion)[0]
    checks["uniform_local_motion_max_drive"] = float(np.max(uniform_motion_drive))

    # Independent-trial reset smoke check on the public online step path.
    online = LC10aVisualResponse()
    online.reset()
    first = renderer.render_linear(gain_probe, 1.4)
    second = renderer.render_linear(gain_probe, 1.402)
    first_drive, r0 = online.step(first, 0.0)
    _, r1 = online.step(second, dt_s)
    online.reset()
    _, reset_r0 = online.step(second, 0.0)
    reset_then_next = online.step(first, dt_s)[1]
    checks["first_sample_response_max"] = float(np.max(np.abs(r0)))
    checks["first_sample_drive_max"] = float(np.max(first_drive))
    checks["reset_clears_history_max"] = float(np.max(np.abs(reset_r0)))
    checks["second_sample_response_max"] = float(np.max(np.abs(r1)))
    checks["post_reset_second_sample_max"] = float(np.max(np.abs(reset_then_next)))

    # Auxiliary pause and isolated-rest trajectories are software probes only.
    aux_summaries = []
    for eye in ("R", "L"):
        paused = PausedDiscRenderer(eye)
        paused_probe = {"probe_id": f"paused_disc_{eye}", "family": "auxiliary_pause",
                        "eye": eye, "onset_s": "1", "visible_duration_s": "1.3"}
        pause_result = model.simulate_movie(paused_probe, paused, duration_s=6.0,
                                            dt_s=dt_s)
        isolated = dict(gain_probe)
        isolated.update(probe_id=f"isolated_disc_{eye}", eye=eye,
                        target_present="True", shape="disc", width_deg="10",
                        height_deg="10", center_azimuth_deg="60" if eye == "R" else "-60",
                        center_elevation_deg="0", azimuth_velocity_deg_s="75" if eye == "R" else "-75",
                        weber_contrast="-1", surround="uniform", onset_s="6",
                        visible_duration_s="0.8", state="unspecified")
        isolated_result = model.simulate_movie(isolated, renderer, duration_s=10.0,
                                               dt_s=dt_s)
        aux_summaries.extend((
            {"probe_id": f"paused_disc_{eye}", "duration_s": 6.0,
             "max_feature": float(np.max(pause_result.features)),
             "integrated_activity": float(np.sum(pause_result.activity) * dt_s)},
            {"probe_id": f"isolated_disc_{eye}", "duration_s": 10.0,
             "max_feature": float(np.max(isolated_result.features)),
             "integrated_activity": float(np.sum(isolated_result.activity) * dt_s)},
        ))
    checks["auxiliary_movies"] = aux_summaries

    weights_2ms = temporal_interval_weights(0.002)
    weights_15ms = temporal_interval_weights(0.0015)
    checks["envelope_discrete_mass_2ms"] = float(np.sum(weights_2ms))
    checks["envelope_discrete_mass_1_5ms"] = float(np.sum(weights_15ms))
    return checks


def run(matrix: Path, output_dir: Path, *, block_frames: int = 32) -> dict:
    probes = load_probes(matrix)
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    if manifest["probe_stage"]["existing_matrix_rows"] != len(probes):
        raise ValueError("Frozen manifest and probe matrix row counts differ")
    dt_s = float(manifest["probe_stage"]["dt_s"])
    duration_s = float(manifest["probe_stage"]["extended_duration_s"])
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = RetinalRenderer(oversample=8)
    model = LC10aVisualResponse()
    summary_rows: list[dict] = []
    absent_rows: list[dict] = []
    trace_path = output_dir / "activity_traces.npz"
    with zipfile.ZipFile(trace_path, mode="w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as trace_archive:
        for index, probe in enumerate(probes, start=1):
            result = model.simulate_movie(probe, renderer, duration_s=duration_s,
                                          dt_s=dt_s, block_frames=block_frames)
            summary_rows.append(summarize_probe(probe, result, model))
            write_trace(trace_archive, probe["probe_id"], result.activity)
            if probe["family"] == "surround":
                absent_probe = make_absent(probe)
                absent_result = model.simulate_movie(absent_probe, renderer,
                                                     duration_s=duration_s, dt_s=dt_s,
                                                     block_frames=block_frames)
                total = np.sum(result.activity, axis=0) * dt_s
                background = np.sum(absent_result.activity, axis=0) * dt_s
                absent_rows.append({
                    "probe_id": probe["probe_id"], "eye": probe["eye"],
                    "surround_velocity_deg_s": float(probe["surround_velocity_deg_s"]),
                    "target_integral_sum_cells": float(np.sum(total)),
                    "absent_background_integral_sum_cells": float(np.sum(background)),
                    "signed_target_minus_absent_sum_cells": float(np.sum(total - background)),
                    "signed_difference_min_per_cell": float(np.min(total - background)),
                    "signed_difference_max_per_cell": float(np.max(total - background)),
                })
            if index % 10 == 0 or index == len(probes):
                print(f"Completed {index}/{len(probes)} frozen probes", flush=True)

    checks = _auxiliary_checks(model, probes, renderer, dt_s)
    summary_path = output_dir / "probe_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary_rows)
    absent_path = output_dir / "surround_absent_contrasts.csv"
    with absent_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(absent_rows[0]),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(absent_rows)

    report = {
        "status": "completed frozen image-to-LC10a probe stage; no physiology fit performed",
        "design": "docs/lc10a_response_design.md",
        "probe_matrix": matrix.resolve().relative_to(ROOT).as_posix(),
        "probe_matrix_sha256": sha256(matrix),
        "design_manifest_sha256": sha256(DEFAULT_MANIFEST),
        "response_module_sha256": sha256(ROOT / "src/fly_creature/lc10a_response.py"),
        "renderer_sha256": sha256(ROOT / "src/fly_creature/retina.py"),
        "runner_sha256": sha256(Path(__file__)),
        "probe_count": len(probes),
        "duration_s": duration_s,
        "dt_s": dt_s,
        "frames_per_probe": int(round(duration_s / dt_s)),
        "block_frames": block_frames,
        "cell_count": len(model.body_ids),
        "mapped_centers": int(np.count_nonzero(model.angle_provenance == "mapped")),
        "fallback_centers": int(np.count_nonzero(model.angle_provenance == "fallback")),
        "source_identity": "existing sorted LC10a IDs and unchanged selected MaleCNS contacts",
        "activity_units": "dimensionless hypothesized drive; not voltage or spikes",
        "trace_archive": trace_path.name,
        "trace_archive_sha256": sha256(trace_path),
        "summary_csv": summary_path.name,
        "summary_csv_sha256": sha256(summary_path),
        "surround_absent_csv": absent_path.name,
        "surround_absent_csv_sha256": sha256(absent_path),
        "auxiliary_and_numerical_checks": checks,
        "physiology_benchmark_started": False,
        "godot_or_production_changed": False,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--block-frames", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(run(args.matrix, args.output_dir,
                         block_frames=args.block_frames), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

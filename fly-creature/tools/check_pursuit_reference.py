"""Compare the offline Python reference with unchanged author-core Octave runs.

Run from fly-creature with PYTHONPATH=src. Octave trace files and licensed
source data remain in ignored outputs; this writes only a compact summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from fly_creature.pursuit_reference import (
    ReferenceConfig,
    load_response_fields,
    simulate_step,
    static_steering,
)


TOLERANCE = 1e-6


def _maximum_difference(actual: np.ndarray, expected_file: Path) -> float:
    expected = np.loadtxt(expected_file, delimiter=",")
    if actual.shape != expected.shape:
        raise ValueError(f"Shape mismatch in {expected_file}: {actual.shape} vs {expected.shape}")
    difference = float(np.max(np.abs(actual - expected)))
    if not np.isfinite(difference) or difference > TOLERANCE:
        raise ValueError(f"Reference mismatch in {expected_file}: {difference}")
    return difference


def _continuous_settle_seconds(position: np.ndarray, timebase: np.ndarray,
                               held_samples: int, *, tolerance: float = 2.0,
                               duration_s: float = 1.0) -> list[float | None]:
    """Onset of first continuous within-band interval after target release."""
    minimum_samples = int(np.ceil(duration_s / (timebase[1] - timebase[0])))
    results: list[float | None] = []
    for run in position:
        inside = np.abs(run) <= tolerance
        onset = next((start for start in range(held_samples, len(run) - minimum_samples + 1)
                      if np.all(inside[start:start + minimum_samples])), None)
        results.append(None if onset is None else float(timebase[onset] - timebase[held_samples - 1]))
    return results


def _source_settle_seconds(position: np.ndarray, timebase: np.ndarray,
                           held_samples: int, *, tolerance: float = 2.0,
                           duration_s: float = 1.0) -> float | None:
    """Recreate the author's helper, including its cumulative-visit behavior."""
    minimum_samples = int(np.ceil(duration_s / (timebase[1] - timebase[0])))
    times = []
    for run in position:
        inside_indices = np.flatnonzero(np.abs(run) <= tolerance)
        if not len(inside_indices):
            continue
        consecutive = np.concatenate(([True], np.diff(inside_indices) == 1))
        counts = np.cumsum(consecutive)
        counts[~consecutive] = 0
        matches = np.flatnonzero(counts >= minimum_samples)
        if len(matches):
            times.append(timebase[inside_indices[matches[0]]])
    return (float(np.mean(times) - timebase[held_samples - 1]) if times else None)


def _case(fields, trace_dir: Path, label: str, count: int,
          noise: np.ndarray | None) -> dict:
    results = {}
    for mode in (0, 1, 2):
        config = ReferenceConfig(number_of_runs=count, direction_mode=mode)
        run = simulate_step(fields, config, movement_noise_deg=noise)
        prefix = trace_dir / f"mode{mode}_"
        errors = {
            "azimuth_deg": _maximum_difference(run["azimuth_deg"],
                                                Path(str(prefix) + "positions.csv")),
            "reported_turn_deg_s": _maximum_difference(run["reported_turn_deg_s"],
                                                         Path(str(prefix) + "velocity.csv")),
        }
        if label == "zero_noise":
            errors["time_s"] = _maximum_difference(run["time_s"],
                                                    Path(str(prefix) + "time.csv"))
        for channel in range(6):
            errors[f"channel_{channel + 1}"] = _maximum_difference(
                run["aotu_channels"][:, :, channel],
                Path(str(prefix) + f"channel{channel + 1}.csv"),
            )
        after_release = run["azimuth_deg"][:, config.initial_held_samples:]
        continuous = _continuous_settle_seconds(run["azimuth_deg"], run["time_s"],
                                                config.initial_held_samples)
        source_settle = _source_settle_seconds(
            run["azimuth_deg"], run["time_s"], config.initial_held_samples
        )
        octave_settle = float(np.loadtxt(Path(str(prefix) + "source_settle.csv"), delimiter=","))
        if source_settle is None:
            if not np.isnan(octave_settle):
                raise ValueError(f"Source settling mismatch in {prefix}: expected NaN")
        elif not np.isfinite(octave_settle) or abs(source_settle - octave_settle) > TOLERANCE:
            raise ValueError(f"Source settling mismatch in {prefix}: {source_settle}, {octave_settle}")
        results[str(mode)] = {
            "maximum_absolute_errors": errors,
            "mean_absolute_azimuth_deg_after_release": float(np.abs(after_release).mean()),
            "mean_absolute_final_azimuth_deg": float(np.abs(after_release[:, -1]).mean()),
            "fraction_within_two_deg_after_release": float((np.abs(after_release) <= 2).mean()),
            "source_helper_settle_s_after_release": source_settle,
            "continuous_stay_onset_s_after_release_per_run": continuous,
            "continuous_stay_successes": sum(value is not None for value in continuous),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path,
                        default=Path("outputs/research/CollieWilson"))
    parser.add_argument("--trace-root", type=Path,
                        default=Path("outputs/research/verification"))
    parser.add_argument("--output", type=Path,
                        default=Path("docs/evidence/pursuit_reference_comparison_v1.json"))
    args = parser.parse_args()
    source_manifest = json.loads(Path("docs/evidence/pursuit_reference_source_v1.json").read_text())
    table_path = args.source_root / "Modeling_Code/Pursuit_RFs.csv"
    table_hash = hashlib.sha256(table_path.read_bytes()).hexdigest()
    if table_hash != source_manifest["sha256"]["Modeling_Code/Pursuit_RFs.csv"]:
        raise ValueError("Author response table differs from the pinned revision")
    fields = load_response_fields(table_path)
    static_error = _maximum_difference(static_steering(fields),
                                       args.trace_root / "octave/static_drive.csv")
    noise = np.loadtxt(args.trace_root / "octave_noise/shared_noise.csv", delimiter=",")
    report = {
        "source_commit": source_manifest["commit"],
        "comparison_runtime": "GNU Octave 11.3.0 with external compatibility shims",
        "scope": "author core model; zero noise and shared nonzero noise with identity lowpass shim",
        "author_matlab_lowpass_reproduced": False,
        "static_max_absolute_error": static_error,
        "tolerance": TOLERANCE,
        "zero_noise": _case(fields, args.trace_root / "octave", "zero_noise", 2, None),
        "shared_noise_unfiltered": _case(fields, args.trace_root / "octave_noise",
                                         "shared_noise_unfiltered", 8, noise),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Compared all 3 conditions in both cases; wrote {args.output}")


if __name__ == "__main__":
    main()

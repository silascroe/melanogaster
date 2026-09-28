"""Offline population-level pursuit reference for the Collie/Wilson protocol.

This is an independently written numerical implementation for comparing with
the authors' pinned MATLAB source. It does not instantiate MaleCNS neurons or
change the playable creature. Response tables must be supplied explicitly;
the authors' licensed CSV is not included with this package.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path

import numpy as np


GRID = np.arange(-180, 181, dtype=np.float64)
OTHER_CONTRALATERAL = {"AOTU002_a", "AOTU002_c"}


@dataclass(frozen=True)
class ResponseFields:
    other_right: np.ndarray
    aotu019_right: np.ndarray
    aotu025_right: np.ndarray


@dataclass(frozen=True)
class ReferenceConfig:
    sample_rate_hz: int = 100
    duration_s: int = 16
    initial_held_samples: int = 100
    initial_azimuth_deg: float = 120.0
    number_of_runs: int = 2
    steering_gain: float = 0.65
    aotu019_delay_ms: int = 450
    other_delay_ms: int = 450
    aotu019_nonpreferred: float = 0.66
    aotu025_nonpreferred: float = 1.0
    d_na02_min: float = -2.25
    d_na02_max: float = 4.0
    direction_mode: int = 0
    include_other: bool = False


def load_response_fields(csv_path: str | Path) -> ResponseFields:
    """Load the supplied author table; mirror the two contralateral columns."""
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(GRID) or not rows:
        raise ValueError("Expected the authors' 361-row response table")
    angles = np.asarray([float(row["rPos_deg"]) for row in rows])
    if not np.array_equal(angles, GRID):
        raise ValueError("Response table azimuth must be -180..180 in 1-degree steps")
    columns = set(rows[0]) - {"rPos_deg", "AOTU019", "AOTU025"}
    if not columns:
        raise ValueError("Response table is missing minor AOTU columns")
    other = np.zeros(len(GRID), dtype=np.float64)
    for name in sorted(columns):
        values = np.asarray([float(row[name]) for row in rows], dtype=np.float64)
        other += values[::-1] if name in OTHER_CONTRALATERAL else values
    a019 = np.asarray([float(row["AOTU019"]) for row in rows], dtype=np.float64)
    a025 = np.asarray([float(row["AOTU025"]) for row in rows], dtype=np.float64)
    if any(not np.all(np.isfinite(a)) for a in (other, a019, a025)):
        raise ValueError("Response table contains nonfinite values")
    return ResponseFields(other, a019, a025)


def _rescale(values: np.ndarray, low: float, high: float) -> np.ndarray:
    minimum, maximum = float(np.min(values)), float(np.max(values))
    if maximum == minimum:
        raise ValueError("Constant lookup range cannot be rescaled")
    return low + (values - minimum) * (high - low) / (maximum - minimum)


def _elu_lookup(maximum: float) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, maximum if maximum else 1.0, 1000)
    u = _rescale(x, -1.0, 1.0)
    activated = np.where(u >= 0.0, u, np.expm1(u))
    return x, _rescale(activated, 0.0, 1.0)


def _adjusted_elu_lookup(x: np.ndarray, alpha: float, shift: float) -> np.ndarray:
    u = _rescale(x, -1.0, 1.0)
    activated = np.where(u >= shift, u - shift, alpha * np.expm1(u - shift))
    return _rescale(activated, 0.0, 1.0)


def _nearest_lookup(grid: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Nearest interpolation on an equally spaced MATLAB linspace grid."""
    step = (grid[-1] - grid[0]) / (len(grid) - 1)
    coordinate = (np.asarray(query) - grid[0]) / step
    if np.any(coordinate < -1e-12) or np.any(coordinate > len(grid) - 1 + 1e-12):
        raise ValueError("Lookup input outside source grid")
    indices = np.floor(np.clip(coordinate, 0, len(grid) - 1) + 0.5).astype(np.int64)
    return values[indices]


def _wrap_to_180(angle: np.ndarray) -> np.ndarray:
    wrapped = (angle + 180.0) % 360.0 - 180.0
    return np.where((wrapped == -180.0) & (angle > 0.0), 180.0, wrapped)


def static_steering(fields: ResponseFields, *, alpha: float = 1.0) -> np.ndarray:
    """Source's stationary spatial response, including its minor AOTU sum."""
    a019r = fields.aotu019_right
    a025r = fields.aotu025_right
    otherr = fields.other_right
    right_input = a025r - a019r[::-1] + otherr
    left_input = a025r[::-1] - a019r + otherr[::-1]
    grid = np.linspace(-2.25, 4.0, 1000)
    output = _adjusted_elu_lookup(grid, alpha, -0.25)
    return _nearest_lookup(grid, output, right_input) - _nearest_lookup(grid, output, left_input)


def simulate_step(
    fields: ResponseFields,
    config: ReferenceConfig = ReferenceConfig(),
    *,
    movement_noise_deg: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Run the source's retinal-position feedback loop on explicit input noise.

    The zero-noise path is the deterministic parity case. Supplying a noise
    matrix permits comparison with MATLAB-generated perturbations while the
    source-specific low-pass random generator remains outside this function.
    """
    if config.direction_mode not in (0, 1, 2):
        raise ValueError("Direction mode must be 0, 1, or 2")
    if config.number_of_runs < 1 or config.sample_rate_hz < 1:
        raise ValueError("Run count and sample rate must be positive")
    n_time = round(config.duration_s * config.sample_rate_hz)
    if not 1 <= config.initial_held_samples < n_time:
        raise ValueError("Initial hold must be within simulation duration")
    shape = (config.number_of_runs, n_time)
    noise = np.zeros(shape) if movement_noise_deg is None else np.asarray(movement_noise_deg)
    if noise.shape != shape or not np.all(np.isfinite(noise)):
        raise ValueError("Movement noise must be finite with one value per run and step")

    positions = np.zeros(shape, dtype=np.float64)
    sides = np.where(np.arange(config.number_of_runs) % 2 == 0, 1.0, -1.0)
    positions[:, : config.initial_held_samples] = config.initial_azimuth_deg * sides[:, None]
    channels = np.zeros((*shape, 6), dtype=np.float64)
    d_na02_right = np.zeros(shape, dtype=np.float64)
    d_na02_left = np.zeros(shape, dtype=np.float64)
    turn_per_step = np.zeros(shape, dtype=np.float64)

    a019r = np.abs(fields.aotu019_right)
    a025r = np.abs(fields.aotu025_right)
    otherr = np.abs(fields.other_right) if config.include_other else np.zeros(len(GRID))
    a019_grid, a019_out = _elu_lookup(float(a019r.max()))
    a025_grid, a025_out = _elu_lookup(float(a025r.max()))
    dna_grid = np.linspace(config.d_na02_min, config.d_na02_max, 1000)
    delay019 = round(config.aotu019_delay_ms / 1000 * config.sample_rate_hz)
    delay_other = round(config.other_delay_ms / 1000 * config.sample_rate_hz)
    penalty019 = config.aotu019_nonpreferred if config.direction_mode == 1 else (
        config.aotu025_nonpreferred if config.direction_mode == 2 else 1.0
    )
    penalty025 = config.aotu025_nonpreferred if config.direction_mode == 1 else (
        config.aotu019_nonpreferred if config.direction_mode == 2 else 1.0
    )

    for t in range(config.initial_held_samples, n_time):
        read019 = max(t - delay019, 0)
        read_other = max(t - delay_other, 0)
        az019 = _wrap_to_180(np.sign(positions[:, read019]) * np.floor(
            np.abs(positions[:, read019]) + 0.5
        )).astype(np.int64) + 180
        az_other = _wrap_to_180(np.sign(positions[:, read_other]) * np.floor(
            np.abs(positions[:, read_other]) + 0.5
        )).astype(np.int64) + 180
        motion019 = (positions[:, read019] - positions[:, read019 - 1]
                     if read019 > 0 else np.zeros(config.number_of_runs))
        motion_other = (positions[:, read_other] - positions[:, read_other - 1]
                        if read_other > 0 else np.zeros(config.number_of_runs))

        right019 = _nearest_lookup(a019_grid, a019_out,
                                  a019r[az019] * np.where(motion019 < 0, penalty019, 1.0))
        left019 = _nearest_lookup(a019_grid, a019_out,
                                 a019r[::-1][az019] * np.where(motion019 > 0, penalty019, 1.0))
        right025 = _nearest_lookup(a025_grid, a025_out,
                                  a025r[az_other] * np.where(motion_other < 0, penalty025, 1.0))
        left025 = _nearest_lookup(a025_grid, a025_out,
                                 a025r[::-1][az_other] * np.where(motion_other > 0, penalty025, 1.0))
        other_right = otherr[az_other]
        other_left = otherr[::-1][az_other]
        channels[:, t, :] = np.stack(
            (right019, left019, right025, left025, other_right, other_left), axis=1
        )

        input_right = right025 - left019 + other_right
        input_left = left025 - right019 + other_left
        d_na02_right[:, t] = _nearest_lookup(dna_grid, dna_grid, input_right)
        d_na02_left[:, t] = _nearest_lookup(dna_grid, dna_grid, input_left)
        turn_per_step[:, t] = config.steering_gain * (d_na02_right[:, t] - d_na02_left[:, t])
        positions[:, t] = _wrap_to_180(positions[:, t - 1] - turn_per_step[:, t] + noise[:, t])

        if (t + 1) % (20 * config.sample_rate_hz) == 0:
            raise ValueError("Source's 20-second random jumps require a supplied jump sequence")

    return {
        "time_s": np.linspace(0.0, config.duration_s, n_time),
        "azimuth_deg": positions,
        "aotu_channels": channels,
        "d_na02_right": d_na02_right,
        "d_na02_left": d_na02_left,
        "turn_per_step_deg": turn_per_step,
        "reported_turn_deg_s": turn_per_step / (2.0 / config.sample_rate_hz),
    }

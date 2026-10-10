"""Frozen offline LC10a image-response hypothesis.

This component translates retinal luminance movies into dimensionless activity
for the existing 275-cell LC10a selection. It is a research implementation,
not
a measured LC10a firing model and not part of the playable controller.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json
import math
from pathlib import Path
from typing import Mapping

import numpy as np

from .pursuit_activity import ActivityProjection


WIDTH_PX = 176
HEIGHT_PX = 32
PIXEL_PITCH_DEG = 1.875
REFERENCE_LUMINANCE = 1.0
SUPPORTED_LUMINANCE = (0.0, 2.0)
MOTION_TAU_S = 0.020
CENTER_SIGMA_DEG = 7.5
SURROUND_SIGMA_DEG = 22.5
APERTURE_OVERLAP_DEG = 15.0
STATIC_COEFFICIENT = 0.25
MOTION_COEFFICIENT = 0.75
REGRESSIVE_WEIGHT = 0.5
ENVELOPE_HORIZON_S = 3.0
ENVELOPE_SIGMA_PER_S = 5.5273
ENVELOPE_KAPPA_S = 0.84962
ENVELOPE_BETA_PER_S = 15.5884
ENVELOPE_ALPHA_S = -0.1859

ABLATIONS = ("primary", "no_surround", "direction_neutral", "no_static",
             "vertical_mean", "instantaneous")


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-value))


def temporal_kernel_unnormalized(lag_s: np.ndarray | float) -> np.ndarray:
    """Pinned source-inspired envelope shape before unit-area normalization."""
    lag = np.asarray(lag_s, dtype=np.float64)
    return (_sigmoid(ENVELOPE_SIGMA_PER_S * (ENVELOPE_KAPPA_S - lag)) *
            _sigmoid(ENVELOPE_BETA_PER_S * (lag + ENVELOPE_ALPHA_S)))


@lru_cache(maxsize=16)
def temporal_interval_weights(dt_s: float) -> np.ndarray:
    """Unit-mass integrals of K over successive held-input lag intervals."""
    dt = float(dt_s)
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("dt_s must be finite and positive")
    count = int(math.ceil(ENVELOPE_HORIZON_S / dt))
    # Gauss-Legendre integrates this smooth, source-derived envelope well below
    # the frozen 1e-12 mass tolerance, including a final partial interval.
    nodes, weights = np.polynomial.legendre.leggauss(12)
    lo = np.arange(count, dtype=np.float64) * dt
    hi = np.minimum(lo + dt, ENVELOPE_HORIZON_S)
    mid = (lo + hi) * 0.5
    half = (hi - lo) * 0.5
    sample = mid[:, None] + half[:, None] * nodes[None, :]
    raw = half * (temporal_kernel_unnormalized(sample) @ weights)
    mass = float(np.sum(raw, dtype=np.float64))
    if not math.isfinite(mass) or mass <= 0:
        raise FloatingPointError("Temporal envelope has invalid unit mass")
    result = raw / mass
    result.setflags(write=False)
    return result


def causal_envelope(features: np.ndarray, dt_s: float, *,
                    state_gain: float | np.ndarray = 1.0,
                    instantaneous: bool = False) -> np.ndarray:
    """Apply the frozen past-held-interval envelope to one uniform-rate movie.

    ``features[n]`` starts its held interval at ``n*dt``. Consequently the
    output at sample n uses only intervals ending at or before n, with an empty
    history at sample zero. FFT is only the convolution algorithm; its output
    indices are shifted to preserve that one-sample causal convention.
    """
    values = np.asarray(features, dtype=np.float64)
    if values.ndim != 2 or not np.all(np.isfinite(values)):
        raise ValueError("features must be a finite time-by-cell matrix")
    if not math.isfinite(float(dt_s)) or float(dt_s) <= 0:
        raise ValueError("dt_s must be finite and positive")
    gains = np.asarray(state_gain, dtype=np.float64)
    if gains.ndim == 0:
        gains = np.full(values.shape[0], float(gains), dtype=np.float64)
    if (gains.shape != (values.shape[0],) or not np.all(np.isfinite(gains))
            or np.any(gains < 0)):
        raise ValueError("state_gain must be a finite nonnegative scalar or time vector")
    if instantaneous:
        return values * gains[:, None]
    if values.shape[0] == 0:
        return values.copy()
    kernel = temporal_interval_weights(float(dt_s))
    full_length = values.shape[0] + kernel.size - 1
    fft_length = 1 << (full_length - 1).bit_length()
    feature_fft = np.fft.rfft(values, n=fft_length, axis=0)
    kernel_fft = np.fft.rfft(kernel, n=fft_length)
    convolution = np.fft.irfft(feature_fft * kernel_fft[:, None],
                               n=fft_length, axis=0)[:values.shape[0]]
    recalled = np.zeros_like(values)
    if values.shape[0] > 1:
        recalled[1:] = convolution[:-1]
    # Round-off in FFT can create tiny negative values for a nonnegative
    # mathematical convolution. Anything larger indicates an implementation
    # error and is not silently clipped.
    minimum = float(np.min(recalled, initial=0.0))
    if minimum < -1e-11:
        raise FloatingPointError(f"Causal envelope produced negative activity: {minimum}")
    recalled[recalled < 0] = 0.0
    return recalled * gains[:, None]


class RetinalMotionFrontEnd:
    """Causal ON/OFF correlation detector using the previous held image."""

    def __init__(self, tau_s: float = MOTION_TAU_S):
        if not math.isfinite(tau_s) or tau_s <= 0:
            raise ValueError("tau_s must be finite and positive")
        self.tau_s = float(tau_s)
        self.reset()

    def reset(self) -> None:
        self.previous_on: np.ndarray | None = None
        self.previous_off: np.ndarray | None = None
        self.delayed_on: np.ndarray | None = None
        self.delayed_off: np.ndarray | None = None
        self.previous_time_s: float | None = None

    @staticmethod
    def _validate_image(image: np.ndarray) -> np.ndarray:
        value = np.asarray(image, dtype=np.float64)
        if value.shape != (HEIGHT_PX, WIDTH_PX):
            raise ValueError(f"Expected a {HEIGHT_PX}x{WIDTH_PX} retinal image")
        if (not np.all(np.isfinite(value)) or value.min() < SUPPORTED_LUMINANCE[0]
                or value.max() > SUPPORTED_LUMINANCE[1]):
            raise ValueError("Image must be finite linear luminance in [0,2]")
        return value

    def step(self, image: np.ndarray, time_s: float) -> tuple[np.ndarray, np.ndarray]:
        """Return abs contrast and signed horizontal motion for one image."""
        frame = self._validate_image(image)
        now = float(time_s)
        if not math.isfinite(now) or now < 0:
            raise ValueError("time_s must be finite and nonnegative")
        contrast = frame - REFERENCE_LUMINANCE
        on = np.maximum(contrast, 0.0)
        off = np.maximum(-contrast, 0.0)
        motion = np.zeros_like(frame)
        if self.previous_time_s is not None:
            dt = now - self.previous_time_s
            if not math.isfinite(dt) or dt <= 0:
                raise ValueError("Frame timestamps must be strictly increasing")
            assert self.previous_on is not None and self.previous_off is not None
            assert self.delayed_on is not None and self.delayed_off is not None
            decay = math.exp(-dt / self.tau_s)
            self.delayed_on = decay * self.delayed_on + (1.0 - decay) * self.previous_on
            self.delayed_off = decay * self.delayed_off + (1.0 - decay) * self.previous_off
            pairs = (
                self.delayed_on[:, :-1] * on[:, 1:] - self.delayed_on[:, 1:] * on[:, :-1]
                + self.delayed_off[:, :-1] * off[:, 1:]
                - self.delayed_off[:, 1:] * off[:, :-1]
            )
            motion[:, 0] = pairs[:, 0]
            motion[:, -1] = pairs[:, -1]
            if WIDTH_PX > 2:
                motion[:, 1:-1] = (pairs[:, :-1] + pairs[:, 1:]) * 0.5
        else:
            self.delayed_on = np.zeros_like(on)
            self.delayed_off = np.zeros_like(off)
        self.previous_on = on
        self.previous_off = off
        self.previous_time_s = now
        return np.abs(contrast), motion


@dataclass(frozen=True)
class LC10aMovieResult:
    body_ids: np.ndarray
    sides: np.ndarray
    angle_provenance: np.ndarray
    times_s: np.ndarray
    features: np.ndarray
    activity: np.ndarray
    winning_rows: np.ndarray


class LC10aVisualResponse:
    """Frozen image-to-LC10a hypothesis over the existing circuit selection."""

    def __init__(self, *, projection: ActivityProjection | None = None,
                 map_path: Path | None = None, width_px: int = WIDTH_PX,
                 height_px: int = HEIGHT_PX,
                 pixel_pitch_deg: float = PIXEL_PITCH_DEG):
        if width_px != WIDTH_PX or height_px != HEIGHT_PX:
            raise ValueError("The frozen LC10a response is defined on the 176x32 panel")
        if not math.isfinite(pixel_pitch_deg) or pixel_pitch_deg <= 0:
            raise ValueError("pixel_pitch_deg must be finite and positive")
        self.projection = projection or ActivityProjection.from_packaged_data()
        data_root = files("fly_creature").joinpath("data")
        visual_map_path = map_path or Path(str(data_root.joinpath(
            "lc10a_registered_eyemap_hypothesis_v3.json")))
        visual_map = json.loads(Path(visual_map_path).read_text(encoding="utf-8"))
        rows = sorted(visual_map["cells"], key=lambda row: int(row["body_id"]))
        ids = np.asarray([int(row["body_id"]) for row in rows], dtype=np.int64)
        if not np.array_equal(ids, self.projection.body_ids):
            raise ValueError("Eye map body IDs do not match the selected projection")
        self.body_ids = ids
        self.sides = np.asarray([row["side"] for row in rows])
        self.centers_deg = np.asarray([row["preferred_abs_bearing_deg"] for row in rows],
                                      dtype=np.float64)
        self.angle_provenance = np.asarray([
            "mapped" if row["angle_source"] == "upstream registered columns" else "fallback"
            for row in rows
        ])
        if len(ids) != 275 or set(self.angle_provenance) != {"mapped", "fallback"}:
            raise ValueError("The frozen map must contain 275 mapped/fallback LC10a cells")
        self.pixel_pitch_deg = float(pixel_pitch_deg)
        self._prepare_weights()
        self.reset()

    @classmethod
    def virtual_unit(cls, center_abs_deg: float, side: str) -> "LC10aVisualResponse":
        """Construct one explicit synthetic unit for map-independent checks."""
        center = float(center_abs_deg)
        if not math.isfinite(center) or not 0 <= center <= 180 or side not in ("L", "R"):
            raise ValueError("Virtual unit requires |center| in [0,180] and side L/R")
        value = object.__new__(cls)
        value.projection = None
        value.body_ids = np.asarray([-1], dtype=np.int64)
        value.sides = np.asarray([side])
        value.centers_deg = np.asarray([center], dtype=np.float64)
        value.angle_provenance = np.asarray(["virtual"])
        value.pixel_pitch_deg = PIXEL_PITCH_DEG
        value._prepare_weights()
        value.reset()
        return value

    def _prepare_weights(self) -> None:
        width_px, height_px = WIDTH_PX, HEIGHT_PX
        self._signs = np.where(self.sides == "R", 1.0, -1.0)
        self.azimuth = ((np.arange(width_px, dtype=np.float64) + 0.5 - width_px / 2)
                        * self.pixel_pitch_deg)
        self.elevation = ((height_px / 2 - np.arange(height_px, dtype=np.float64) - 0.5)
                          * self.pixel_pitch_deg)
        signed_centers = self._signs * self.centers_deg
        aperture = np.clip(0.5 + self._signs[:, None] *
                           self.azimuth[None, :] / APERTURE_OVERLAP_DEG, 0.0, 1.0)
        self.center_mass_x, self.center_x = self._horizontal_weights(
            signed_centers, CENTER_SIGMA_DEG, aperture)
        self.surround_mass_x, self.surround_x = self._horizontal_weights(
            signed_centers, SURROUND_SIGMA_DEG, aperture)
        self.center_y = self._vertical_weights(CENTER_SIGMA_DEG)
        self.surround_y = self._vertical_weights(SURROUND_SIGMA_DEG)
        self.center_mass = (self.center_mass_x[:, None] *
                            self._vertical_mass(CENTER_SIGMA_DEG)[None, :])
        self.surround_mass = (self.surround_mass_x[:, None] *
                              self._vertical_mass(SURROUND_SIGMA_DEG)[None, :])

    def reset(self) -> None:
        self.frontend = RetinalMotionFrontEnd()
        self._feature_history: list[np.ndarray] = []
        self._time_history: list[float] = []

    def _horizontal_weights(self, centers: np.ndarray, sigma: float,
                            aperture: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raw = np.exp(-0.5 * ((self.azimuth[None, :] - centers[:, None]) / sigma) ** 2)
        raw *= aperture
        mass = raw.sum(axis=1, dtype=np.float64)
        if np.any(mass <= 0):
            raise ValueError("A spatial kernel has no support on the retinal panel")
        return mass, raw / mass[:, None]

    def _vertical_weights(self, sigma: float) -> np.ndarray:
        delta = self.elevation[:, None] - self.elevation[None, :]
        raw = np.exp(-0.5 * (delta / sigma) ** 2)
        return raw / raw.sum(axis=1, keepdims=True)

    def _vertical_mass(self, sigma: float) -> np.ndarray:
        delta = self.elevation[:, None] - self.elevation[None, :]
        return np.exp(-0.5 * (delta / sigma) ** 2).sum(axis=1, dtype=np.float64)

    @staticmethod
    def _pool_batch(images: np.ndarray, horizontal: np.ndarray,
                    vertical: np.ndarray) -> np.ndarray:
        count = images.shape[0]
        cells = horizontal.shape[0]
        row_cells = (images.reshape(count * HEIGHT_PX, WIDTH_PX) @ horizontal.T
                     ).reshape(count, HEIGHT_PX, cells)
        return np.einsum("yr,brn->byn", vertical, row_cells, optimize=True)

    @staticmethod
    def _motion_for_side(motion: np.ndarray, side_sign: float,
                         direction_neutral: bool) -> np.ndarray:
        if direction_neutral:
            return np.abs(motion) * MOTION_COEFFICIENT
        preferred = side_sign * motion
        return np.maximum(preferred, 0.0) + REGRESSIVE_WEIGHT * np.maximum(-preferred, 0.0)

    def spatial_features(self, contrast_images: np.ndarray, motion_images: np.ndarray,
                         *, ablation: str = "primary") -> tuple[np.ndarray, np.ndarray,
                                                                  dict[str, np.ndarray]]:
        """Compute per-cell instantaneous spatial drive for one frame or batch."""
        if ablation not in ABLATIONS:
            raise ValueError(f"Unknown ablation: {ablation}")
        contrast = np.asarray(contrast_images, dtype=np.float64)
        motion = np.asarray(motion_images, dtype=np.float64)
        if contrast.ndim == 2:
            contrast = contrast[None, ...]
        if motion.ndim == 2:
            motion = motion[None, ...]
        if contrast.shape != motion.shape or contrast.shape[1:] != (HEIGHT_PX, WIDTH_PX):
            raise ValueError("Contrast and motion batches must be matching retinal images")
        count = contrast.shape[0]
        features = np.zeros((count, len(self.body_ids)), dtype=np.float64)
        winners = np.zeros((count, len(self.body_ids)), dtype=np.int16)
        details: dict[str, np.ndarray] = {}
        directions_neutral = ablation == "direction_neutral"
        surround_weight = 0.0 if ablation == "no_surround" else 1.0
        static_weight = 0.0 if ablation == "no_static" else STATIC_COEFFICIENT
        motion_weight = MOTION_COEFFICIENT
        if ablation == "direction_neutral":
            motion_weight = 1.0
        for side, sign in (("L", -1.0), ("R", 1.0)):
            indexes = np.flatnonzero(self.sides == side)
            static_center = self._pool_batch(contrast, self.center_x[indexes], self.center_y)
            static_surround = self._pool_batch(contrast, self.surround_x[indexes],
                                               self.surround_y)
            side_motion = self._motion_for_side(motion, sign, directions_neutral)
            motion_center = self._pool_batch(side_motion, self.center_x[indexes], self.center_y)
            motion_surround = self._pool_batch(side_motion, self.surround_x[indexes],
                                               self.surround_y)
            static_dog = static_center - surround_weight * static_surround
            motion_dog = motion_center - surround_weight * motion_surround
            static_dog = np.maximum(static_dog, 0.0)
            motion_dog = np.maximum(motion_dog, 0.0)
            combined = static_weight * static_dog + motion_weight * motion_dog
            if ablation == "vertical_mean":
                side_features = np.mean(combined, axis=1, dtype=np.float64)
                side_winners = np.argmax(combined, axis=1).astype(np.int16)
            else:
                side_winners = np.argmax(combined, axis=1).astype(np.int16)
                side_features = np.max(combined, axis=1)
            features[:, indexes] = side_features
            winners[:, indexes] = side_winners
            if count == 1:
                details[f"{side}_static_dog"] = static_dog[0]
                details[f"{side}_motion_dog"] = motion_dog[0]
                details[f"{side}_center_minus_surround_static"] = (
                    static_center[0] - surround_weight * static_surround[0])
                details[f"{side}_center_minus_surround_motion"] = (
                    motion_center[0] - surround_weight * motion_surround[0])
        if np.any(features < -1e-12) or np.any(features > 1.0 + 1e-10):
            raise FloatingPointError("Instantaneous LC10a drive escaped the frozen [0,1] bound")
        if np.any(features < 0):
            features = np.maximum(features, 0.0)
        return features, winners, details

    def step(self, image: np.ndarray, time_s: float, state_gain: float = 1.0,
             *, ablation: str = "primary") -> tuple[np.ndarray, np.ndarray]:
        """Advance one frame and return (instantaneous drive, recalled activity)."""
        gain = float(state_gain)
        if not math.isfinite(gain) or gain < 0:
            raise ValueError("state_gain must be finite and nonnegative")
        static, motion = self.frontend.step(image, time_s)
        feature, winner, _ = self.spatial_features(static, motion, ablation=ablation)
        feature = feature[0]
        now = float(time_s)
        self._feature_history.append(feature.copy())
        self._time_history.append(now)
        if ablation == "instantaneous":
            return feature, gain * feature
        if len(self._time_history) < 2:
            return feature, np.zeros_like(feature)
        # Integrate each actual past held interval against the continuous kernel.
        current = self._time_history[-1]
        activity = np.zeros_like(feature)
        for index in range(len(self._feature_history) - 1):
            left_time = self._time_history[index]
            right_time = self._time_history[index + 1]
            lag_lo = max(0.0, current - right_time)
            lag_hi = min(ENVELOPE_HORIZON_S, current - left_time)
            if lag_hi > lag_lo:
                activity += self._feature_history[index] * _integrate_kernel(lag_lo, lag_hi)
        return feature, gain * activity

    def simulate_movie(self, probe: Mapping, renderer, *, duration_s: float = 6.0,
                       dt_s: float = 0.002, block_frames: int = 32,
                       state_gain: float = 1.0,
                       ablation: str = "primary") -> LC10aMovieResult:
        """Render a declared movie, stream image history, and compute responses."""
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("duration_s must be finite and positive")
        if not math.isfinite(dt_s) or dt_s <= 0:
            raise ValueError("dt_s must be finite and positive")
        if block_frames <= 0:
            raise ValueError("block_frames must be positive")
        frame_count_float = duration_s / dt_s
        frame_count = int(round(frame_count_float))
        if not math.isclose(frame_count_float, frame_count, rel_tol=0, abs_tol=1e-9):
            raise ValueError("duration_s must be an integer number of dt_s intervals")
        times = np.arange(frame_count, dtype=np.float64) * dt_s
        all_features = np.empty((frame_count, len(self.body_ids)), dtype=np.float64)
        all_winners = np.empty((frame_count, len(self.body_ids)), dtype=np.int16)
        frontend = RetinalMotionFrontEnd()
        for start in range(0, frame_count, block_frames):
            stop = min(frame_count, start + block_frames)
            contrast = np.empty((stop - start, HEIGHT_PX, WIDTH_PX), dtype=np.float64)
            motion = np.empty_like(contrast)
            for offset, frame_index in enumerate(range(start, stop)):
                image = renderer.render_linear(probe, float(times[frame_index]))
                contrast[offset], motion[offset] = frontend.step(image, float(times[frame_index]))
            block_features, block_winners, _ = self.spatial_features(
                contrast, motion, ablation=ablation)
            all_features[start:stop] = block_features
            all_winners[start:stop] = block_winners
        if np.ndim(state_gain) == 0:
            gains = float(state_gain)
        else:
            gains = np.asarray(state_gain, dtype=np.float64)
        activity = causal_envelope(all_features, dt_s, state_gain=gains,
                                   instantaneous=ablation == "instantaneous")
        return LC10aMovieResult(self.body_ids.copy(), self.sides.copy(),
                                self.angle_provenance.copy(), times, all_features,
                                activity, all_winners)


def _integrate_kernel(lo_s: float, hi_s: float) -> float:
    """High-order interval integral used by the stateful irregular-time step."""
    nodes, weights = np.polynomial.legendre.leggauss(12)
    mid = 0.5 * (lo_s + hi_s)
    half = 0.5 * (hi_s - lo_s)
    values = temporal_kernel_unnormalized(mid + half * nodes)
    # Normalize using the exact same continuous domain as the construction.
    norm = _kernel_normalizer()
    return float(half * np.dot(weights, values) / norm)


@lru_cache(maxsize=1)
def _kernel_normalizer() -> float:
    nodes, weights = np.polynomial.legendre.leggauss(48)
    half = ENVELOPE_HORIZON_S / 2.0
    values = temporal_kernel_unnormalized(half + half * nodes)
    return float(half * np.dot(weights, values))

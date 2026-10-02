"""Finite angular stimulus renderer; produces images, never neural responses."""
from __future__ import annotations

import math
import struct
import zlib
from typing import Mapping

import numpy as np


class RetinalRenderer:
    """Render a single contract probe as linear-luminance retinal frames."""

    def __init__(self, *, width_px: int = 176, height_px: int = 32,
                 pixel_pitch_deg: float = 1.875, oversample: int = 8):
        if width_px <= 0 or height_px <= 0 or pixel_pitch_deg <= 0 or oversample < 2:
            raise ValueError("Retinal grid dimensions and oversampling must be positive")
        if not all(math.isfinite(x) for x in (pixel_pitch_deg,)):
            raise ValueError("Pixel pitch must be finite")
        self.width_px, self.height_px = width_px, height_px
        self.pitch, self.oversample = float(pixel_pitch_deg), int(oversample)
        self.azimuth = ((np.arange(width_px, dtype=np.float64) + .5 - width_px/2)
                        * self.pitch)
        self.elevation = ((height_px/2 - np.arange(height_px, dtype=np.float64) - .5)
                          * self.pitch)
        self.az_min, self.el_min = -width_px*self.pitch/2, -height_px*self.pitch/2

    def _background(self, probe: Mapping, time_s: float) -> np.ndarray:
        image = np.full((self.height_px, self.width_px), 1., dtype=np.float64)
        if probe["surround"] == "uniform":
            return image
        if probe["surround"] != "square_grating":
            raise ValueError(f"Unsupported surround: {probe['surround']}")
        period = float(probe["surround_period_deg"])
        amplitude = float(probe["surround_weber_amplitude"])
        phase = float(probe["surround_phase_deg"])
        velocity = float(probe["surround_velocity_deg_s"])
        if period <= 0 or amplitude < 0 or not all(math.isfinite(v) for v in
                (period, amplitude, phase, velocity)):
            raise ValueError("Invalid square-grating parameters")
        coordinate = self.azimuth[None, :] - velocity*time_s - phase
        cycles = np.cos(2*math.pi*coordinate/period)
        image[:] = 1. + amplitude*np.where(cycles >= 0, 1., -1.)
        return image

    @staticmethod
    def _flag(value) -> bool:
        if isinstance(value,str):
            normalized=value.strip().lower()
            if normalized in ("true","1","yes"):return True
            if normalized in ("false","0","no"):return False
            raise ValueError(f"Invalid Boolean stimulus field: {value}")
        return bool(value)

    def _coverage(self, probe: Mapping, time_s: float):
        """Return clipped target bbox and fractional coverage per pixel."""
        if not self._flag(probe["target_present"]) or not (
                float(probe["onset_s"]) <= time_s <
                float(probe["onset_s"])+float(probe["visible_duration_s"])):
            return None
        width, height = float(probe["width_deg"]), float(probe["height_deg"])
        az = float(probe["center_azimuth_deg"])+float(probe["azimuth_velocity_deg_s"])*(
            time_s-float(probe["onset_s"])-float(probe["visible_duration_s"])/2)
        el = float(probe["center_elevation_deg"])
        if not all(math.isfinite(v) for v in (width,height,az,el)) or min(width,height) <= 0:
            raise ValueError("Target geometry must be finite and positive")
        if probe["shape"] not in ("rectangle", "disc"):
            raise ValueError(f"Unsupported target shape: {probe['shape']}")
        if probe["shape"] == "disc" and not math.isclose(width,height):
            raise ValueError("Disc probes require equal angular width and height")
        x0 = max(0, math.floor((az-width/2-self.az_min)/self.pitch))
        x1 = min(self.width_px, math.ceil((az+width/2-self.az_min)/self.pitch))
        el_max = -self.el_min
        y0 = max(0, math.floor((el_max-(el+height/2))/self.pitch))
        y1 = min(self.height_px, math.ceil((el_max-(el-height/2))/self.pitch))
        if x0 >= x1 or y0 >= y1:
            return None
        sub = self.oversample
        xs = self.az_min+(np.arange(x0*sub,(x1)*sub)+.5)*self.pitch/sub
        ys = self.el_min+(self.height_px*sub-1-(np.arange(y0*sub,y1*sub))+.5)*self.pitch/sub
        xx, yy = np.meshgrid(xs,ys)
        if probe["shape"] == "disc":
            inside = ((xx-az)/(width/2))**2+((yy-el)/(height/2))**2 <= 1.
        else:
            inside = (np.abs(xx-az) <= width/2) & (np.abs(yy-el) <= height/2)
        coverage = inside.reshape(y1-y0,sub,x1-x0,sub).mean(axis=(1,3))
        return (y0,y1,x0,x1),coverage,az,el

    def render_linear(self, probe: Mapping, time_s: float) -> np.ndarray:
        """Render a frame in normalized linear luminance (background is 1)."""
        if not math.isfinite(time_s) or time_s < 0:
            raise ValueError("Frame time must be a finite nonnegative number")
        background = self._background(probe,time_s)
        result = background.copy()
        geometry = self._coverage(probe,time_s)
        if geometry is None:
            return result
        bbox,coverage,_,_ = geometry
        y0,y1,x0,x1 = bbox
        contrast = float(probe["weber_contrast"])
        if not math.isfinite(contrast) or contrast < -1:
            raise ValueError("Target Weber contrast must be finite and >= -1")
        target_luminance = 1.+contrast
        roi = result[y0:y1,x0:x1]
        result[y0:y1,x0:x1] = roi*(1.-coverage)+target_luminance*coverage
        return result

    def render_gray8(self, probe: Mapping, time_s: float) -> np.ndarray:
        """Convert linear luminance to a fixed 0..2 normalized PNG grayscale."""
        return np.rint(np.clip(self.render_linear(probe,time_s),0.,2.)*127.5).astype(np.uint8)


def write_gray_png(path, image: np.ndarray) -> None:
    """Write an 8-bit grayscale PNG without a plotting or imaging dependency."""
    pixels = np.asarray(image,dtype=np.uint8)
    if pixels.ndim != 2 or min(pixels.shape) <= 0:
        raise ValueError("PNG input must be a nonempty two-dimensional image")
    height,width = pixels.shape
    raw = b"".join(b"\0"+pixels[y].tobytes() for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind+data
        return struct.pack(">I",len(data))+body+struct.pack(">I",zlib.crc32(body)&0xffffffff)

    payload = (b"\x89PNG\r\n\x1a\n"+
               chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,0,0,0,0))+
               chunk(b"IDAT",zlib.compress(raw,9))+chunk(b"IEND",b""))
    path.write_bytes(payload)

"""Fractal noise utilities shared across terrain and starfield generation."""
from __future__ import annotations

import numpy as np


def box_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    """Fast box blur using cumulative sums. Works on 2D float arrays."""
    padded = np.pad(arr, radius + 1, mode='edge')
    cs = np.cumsum(np.cumsum(padded, axis=0), axis=1)
    d = 2 * radius + 1
    rows, cols = arr.shape
    result = (
        cs[d:d + rows, d:d + cols]
        - cs[:rows, d:d + cols]
        - cs[d:d + rows, :cols]
        + cs[:rows, :cols]
    ) / (d * d)
    return result


def fractal_noise(
    np_rng: np.random.RandomState, w: int, h: int,
    octaves: int = 3, base_radius: int = 8,
) -> np.ndarray:
    """Generate a smooth fractal noise field in [0, 1] using layered box blur."""
    result = np.zeros((w, h), dtype=np.float64)
    amplitude = 1.0
    total_amp = 0.0
    for i in range(octaves):
        raw = np_rng.uniform(0.0, 1.0, size=(w, h))
        radius = max(base_radius >> i, 1)
        smoothed = box_blur(raw, radius)
        result += smoothed * amplitude
        total_amp += amplitude
        amplitude *= 0.5
    result /= total_amp
    rmin, rmax = result.min(), result.max()
    if rmax > rmin:
        result = (result - rmin) / (rmax - rmin)
    return result

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


def coord_fractal_noise(
    seed: int, xs: np.ndarray, ys: np.ndarray,
    octaves: int = 3, base_period: int = 16,
) -> np.ndarray:
    """Coordinate-based fractal value noise. Deterministic per (seed, x, y).

    Returns a (len(xs), len(ys)) array in [0, 1].  Any two callers using the
    same seed and overlapping coordinate ranges will get identical values in
    the overlap — regardless of the total region size.
    """
    gx_base = xs.reshape(-1, 1).astype(np.float64)
    gy_base = ys.reshape(1, -1).astype(np.float64)
    result = np.zeros((len(xs), len(ys)), dtype=np.float64)
    amplitude = 1.0
    total_amp = 0.0

    for i in range(octaves):
        period = max(base_period >> i, 1)
        freq = 1.0 / period
        gx = gx_base * freq
        gy = gy_base * freq

        x0 = np.floor(gx).astype(np.int64)
        y0 = np.floor(gy).astype(np.int64)

        fx = gx - x0
        fy = gy - y0
        # Smoothstep interpolation
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)

        octave_seed = np.int64(seed + i * 1000003)

        def _hash(gxi: np.ndarray, gyi: np.ndarray) -> np.ndarray:
            h = (gxi * np.int64(374761393) + gyi * np.int64(668265263) + octave_seed)
            h = (h ^ (h >> np.int64(13))) * np.int64(2654435761)
            h = h ^ (h >> np.int64(16))
            return (h & np.int64(0xFFFFFF)).astype(np.float64) / 0xFFFFFF

        n00 = _hash(x0, y0)
        n10 = _hash(x0 + 1, y0)
        n01 = _hash(x0, y0 + 1)
        n11 = _hash(x0 + 1, y0 + 1)

        nx0 = n00 * (1 - fx) + n10 * fx
        nx1 = n01 * (1 - fx) + n11 * fx
        result += (nx0 * (1 - fy) + nx1 * fy) * amplitude
        total_amp += amplitude
        amplitude *= 0.5

    result /= total_amp
    # Normalize to [0, 1]
    rmin, rmax = result.min(), result.max()
    if rmax > rmin:
        result = (result - rmin) / (rmax - rmin)
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

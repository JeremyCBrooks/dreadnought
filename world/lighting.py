"""Light source definitions and light map computation."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Tuple, List

import numpy as np


LIGHT_SPILL_RADIUS = 3


HAZARD_LIGHT_COLOR: Tuple[int, int, int] = (200, 40, 20)


@dataclass
class LightSource:
    x: int
    y: int
    radius: int
    color: Tuple[int, int, int]
    intensity: float = 1.0
    flicker: bool = False
    base_color: Tuple[int, int, int] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.base_color is None:
            self.base_color = self.color


def compute_light_map(
    width: int,
    height: int,
    tiles: np.ndarray,
    light_sources: List[LightSource],
) -> np.ndarray:
    """Compute an RGB light intensity map (float32, shape width x height x 3).

    Each light source propagates through transparent tiles using FOV,
    with smooth falloff based on distance.
    """
    import tcod.map

    light_map = np.zeros((width, height, 3), dtype=np.float32)
    if not light_sources:
        return light_map

    transparency = tiles["transparent"]

    now = time.time()

    for ls in light_sources:
        if not (0 <= ls.x < width and 0 <= ls.y < height):
            continue
        # Extend FOV radius so light can spill a few tiles through windows/doors
        fov_radius = ls.radius + LIGHT_SPILL_RADIUS
        fov = tcod.map.compute_fov(transparency, (ls.x, ls.y), fov_radius)

        # Clamp to bounding box around the light source
        x0 = max(0, ls.x - fov_radius)
        x1 = min(width, ls.x + fov_radius + 1)
        y0 = max(0, ls.y - fov_radius)
        y1 = min(height, ls.y + fov_radius + 1)

        # Euclidean distance from source (only within bounding box)
        ix = np.arange(x0, x1)[:, np.newaxis]
        iy = np.arange(y0, y1)[np.newaxis, :]
        dist = np.sqrt((ix - ls.x) ** 2 + (iy - ls.y) ** 2)

        # Linear falloff over the extended radius for smooth spill
        falloff = np.maximum(0.0, 1.0 - dist / fov_radius)

        # Apply flicker: time-based intensity modulation using overlapping sine waves
        effective_intensity = ls.intensity
        if ls.flicker:
            # Use position as a unique phase offset so lights flicker independently
            phase = ls.x * 7.3 + ls.y * 13.1
            # Pseudo-random hash component: quantize time to create
            # abrupt jumps between intensity levels
            t_slot = int(now * 6 + phase)
            hash_val = ((t_slot * 2654435761) & 0xFFFFFFFF) / 0xFFFFFFFF  # 0-1
            # Sine waves for smooth oscillation between the jumps
            wave = (
                math.sin(now * 7.1 + phase) * 0.4
                + math.sin(now * 17.3 + phase * 1.3) * 0.3
            )
            # Blend hash noise and wave; bias toward off
            combined = hash_val * 0.6 + (0.5 + wave) * 0.4  # 0-1 range
            # Sharp threshold: light is mostly off or mostly on
            if combined < 0.45:
                effective_intensity = ls.intensity * combined * 0.3
            else:
                effective_intensity = ls.intensity * min(1.0, combined * 1.2)

        # Mask to FOV-reachable tiles only
        fov_slice = fov[x0:x1, y0:y1]
        contribution = falloff * fov_slice * effective_intensity

        # Apply normalized color (only to the subregion)
        light_map[x0:x1, y0:y1, 0] += contribution * (ls.color[0] / 255.0)
        light_map[x0:x1, y0:y1, 1] += contribution * (ls.color[1] / 255.0)
        light_map[x0:x1, y0:y1, 2] += contribution * (ls.color[2] / 255.0)

    np.clip(light_map, 0, 1, out=light_map)
    return light_map

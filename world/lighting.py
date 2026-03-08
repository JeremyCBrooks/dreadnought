"""Light source definitions and light map computation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, List

import numpy as np


LIGHT_SPILL_RADIUS = 3


@dataclass
class LightSource:
    x: int
    y: int
    radius: int
    color: Tuple[int, int, int]
    intensity: float = 1.0


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

        # Mask to FOV-reachable tiles only
        fov_slice = fov[x0:x1, y0:y1]
        contribution = falloff * fov_slice * ls.intensity

        # Apply normalized color (only to the subregion)
        light_map[x0:x1, y0:y1, 0] += contribution * (ls.color[0] / 255.0)
        light_map[x0:x1, y0:y1, 1] += contribution * (ls.color[1] / 255.0)
        light_map[x0:x1, y0:y1, 2] += contribution * (ls.color[2] / 255.0)

    np.clip(light_map, 0, 1, out=light_map)
    return light_map

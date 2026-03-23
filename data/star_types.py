"""Star type definitions for the strategic layer."""

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StarType:
    name: str
    radius: int
    core_color: tuple[int, int, int]
    mid_color: tuple[int, int, int]
    edge_color: tuple[int, int, int]
    corona_color: tuple[int, int, int]
    corona_width: int
    surface_chars: str
    weight: float
    render_hint: str = ""  # "pulsar", "black_hole", or "" for normal


STAR_TYPES: dict[str, StarType] = {
    "red_dwarf": StarType(
        name="red dwarf",
        radius=4,
        core_color=(255, 180, 120),
        mid_color=(255, 100, 50),
        edge_color=(200, 60, 30),
        corona_color=(120, 30, 10),
        corona_width=3,
        surface_chars="~*+.",
        weight=30,
    ),
    "yellow_dwarf": StarType(
        name="yellow dwarf",
        radius=6,
        core_color=(255, 255, 220),
        mid_color=(255, 230, 140),
        edge_color=(255, 200, 80),
        corona_color=(200, 160, 40),
        corona_width=4,
        surface_chars="~*+.o",
        weight=20,
    ),
    "orange_giant": StarType(
        name="orange giant",
        radius=9,
        core_color=(255, 220, 160),
        mid_color=(255, 170, 80),
        edge_color=(230, 120, 40),
        corona_color=(160, 80, 20),
        corona_width=5,
        surface_chars="~*+.oO",
        weight=6,
    ),
    "red_giant": StarType(
        name="red giant",
        radius=11,
        core_color=(255, 160, 100),
        mid_color=(220, 80, 40),
        edge_color=(180, 50, 20),
        corona_color=(100, 20, 5),
        corona_width=6,
        surface_chars="~*+.oO#",
        weight=4,
    ),
    "yellow_white_dwarf": StarType(
        name="yellow-white dwarf",
        radius=7,
        core_color=(255, 255, 240),
        mid_color=(255, 240, 190),
        edge_color=(250, 220, 140),
        corona_color=(210, 190, 80),
        corona_width=4,
        surface_chars="~*+.o",
        weight=12,
    ),
    "white_star": StarType(
        name="white star",
        radius=8,
        core_color=(255, 255, 255),
        mid_color=(240, 245, 255),
        edge_color=(220, 230, 250),
        corona_color=(170, 185, 220),
        corona_width=5,
        surface_chars="~*+.ox",
        weight=7,
    ),
    "blue_giant": StarType(
        name="blue giant",
        radius=8,
        core_color=(220, 230, 255),
        mid_color=(140, 180, 255),
        edge_color=(80, 130, 255),
        corona_color=(40, 60, 180),
        corona_width=5,
        surface_chars="~*+.x",
        weight=4,
    ),
    "white_dwarf": StarType(
        name="white dwarf",
        radius=3,
        core_color=(255, 255, 255),
        mid_color=(230, 235, 255),
        edge_color=(200, 210, 240),
        corona_color=(140, 150, 200),
        corona_width=4,
        surface_chars="*+.",
        weight=8,
    ),
    "neutron_star": StarType(
        name="neutron star",
        radius=2,
        core_color=(200, 220, 255),
        mid_color=(150, 180, 255),
        edge_color=(100, 140, 255),
        corona_color=(60, 80, 200),
        corona_width=7,
        surface_chars="*+x",
        weight=3,
    ),
    "brown_dwarf": StarType(
        name="brown dwarf",
        radius=3,
        core_color=(160, 90, 60),
        mid_color=(120, 60, 35),
        edge_color=(80, 40, 20),
        corona_color=(40, 20, 10),
        corona_width=2,
        surface_chars="~.:",
        weight=8,
    ),
    "blue_supergiant": StarType(
        name="blue supergiant",
        radius=12,
        core_color=(230, 240, 255),
        mid_color=(160, 200, 255),
        edge_color=(100, 150, 255),
        corona_color=(50, 80, 200),
        corona_width=7,
        surface_chars="~*+.xO",
        weight=2,
    ),
    "red_supergiant": StarType(
        name="red supergiant",
        radius=15,
        core_color=(255, 140, 80),
        mid_color=(200, 60, 25),
        edge_color=(150, 35, 10),
        corona_color=(80, 15, 5),
        corona_width=8,
        surface_chars="~*+.oO#@",
        weight=2,
    ),
    "yellow_giant": StarType(
        name="yellow giant",
        radius=9,
        core_color=(255, 250, 200),
        mid_color=(255, 220, 120),
        edge_color=(240, 180, 60),
        corona_color=(180, 130, 30),
        corona_width=5,
        surface_chars="~*+.oO",
        weight=5,
    ),
    "wolf_rayet": StarType(
        name="Wolf-Rayet",
        radius=5,
        core_color=(200, 220, 255),
        mid_color=(160, 140, 255),
        edge_color=(130, 80, 220),
        corona_color=(80, 40, 160),
        corona_width=8,
        surface_chars="~*+x!",
        weight=2,
    ),
    "pulsar": StarType(
        name="pulsar",
        radius=2,
        core_color=(220, 240, 255),
        mid_color=(160, 200, 255),
        edge_color=(100, 150, 255),
        corona_color=(50, 70, 180),
        corona_width=6,
        surface_chars="*+x",
        weight=3,
        render_hint="pulsar",
    ),
    "black_hole": StarType(
        name="black hole",
        radius=4,
        core_color=(0, 0, 0),
        mid_color=(5, 5, 10),
        edge_color=(10, 10, 20),
        corona_color=(60, 40, 15),
        corona_width=6,
        surface_chars=".",
        weight=2,
        render_hint="black_hole",
    ),
    "supermassive_black_hole": StarType(
        name="supermassive black hole",
        radius=8,
        core_color=(0, 0, 0),
        mid_color=(5, 5, 10),
        edge_color=(10, 10, 20),
        corona_color=(60, 40, 15),
        corona_width=8,
        surface_chars=".",
        weight=1,
        render_hint="black_hole",
    ),
}

_KEYS = tuple(STAR_TYPES.keys())
_WEIGHTS = tuple(STAR_TYPES[k].weight for k in _KEYS)


def pick_star_type(rng: random.Random) -> str:
    """Select a random star type key using weighted random choice."""
    return rng.choices(_KEYS, weights=_WEIGHTS, k=1)[0]

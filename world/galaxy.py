"""Minimal galaxy, star system, and location classes for the strategic layer."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from data.db import system_words, location_types, location_words
from data.star_types import pick_star_type


_LOW_GRAVITY_TYPES = frozenset({"asteroid", "derelict"})


class Location:
    def __init__(self, name: str, loc_type: str, environment: Optional[dict] = None) -> None:
        self.name = name
        self.loc_type = loc_type
        env = environment or {}
        if "low_gravity" in env and loc_type not in _LOW_GRAVITY_TYPES:
            env.pop("low_gravity")
        self.environment = env
        self.scanned = False
        self.visited = False


class StarSystem:
    def __init__(self, name: str, locations: Optional[List[Location]] = None, depth: int = 0,
                 star_type: str = "yellow_dwarf", gx: int = 0, gy: int = 0) -> None:
        self.name = name
        self.locations: List[Location] = locations or []
        self.depth = depth
        self.star_type = star_type
        self.gx = gx
        self.gy = gy
        self.connections: Dict[str, int] = {}


def _direction(ax: int, ay: int, bx: int, by: int) -> tuple[int, int]:
    """Snap relative direction from (ax,ay) to (bx,by) to one of 8 cardinal/diagonal."""
    dx = bx - ax
    dy = by - ay
    return ((dx > 0) - (dx < 0), (dy > 0) - (dy < 0))


def _euclidean(ax: int, ay: int, bx: int, by: int) -> float:
    return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)


def _build_graph(positions: list[tuple[int, int]], rng: random.Random,
                 max_extra: int = 3) -> list[tuple[int, int, float]]:
    """Build a connected sparse graph over grid positions.

    Returns list of (i, j, distance) edges.
    Uses MST (Prim's) + a few extra short edges.
    """
    n = len(positions)
    if n <= 1:
        return []

    # Prim's MST
    in_tree = [False] * n
    in_tree[0] = True
    edges: list[tuple[int, int, float]] = []

    # All candidate edges sorted by distance
    all_edges: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            d = _euclidean(*positions[i], *positions[j])
            all_edges.append((d, i, j))
    all_edges.sort()

    # Build MST
    tree_count = 1
    while tree_count < n:
        for d, i, j in all_edges:
            if in_tree[i] != in_tree[j]:
                edges.append((i, j, d))
                in_tree[i] = in_tree[j] = True
                tree_count += 1
                break

    # Track which directions are used per node
    used_dirs: list[set[tuple[int, int]]] = [set() for _ in range(n)]
    for i, j, d in edges:
        dir_ij = _direction(*positions[i], *positions[j])
        dir_ji = _direction(*positions[j], *positions[i])
        used_dirs[i].add(dir_ij)
        used_dirs[j].add(dir_ji)

    # Add extra short edges (skip MST edges, check direction conflicts)
    mst_set = {(min(i, j), max(i, j)) for i, j, _ in edges}
    candidates = [(d, i, j) for d, i, j in all_edges
                  if (min(i, j), max(i, j)) not in mst_set]
    rng.shuffle(candidates)  # randomize among similar-length edges
    candidates.sort(key=lambda e: e[0])  # re-sort by distance, stable

    added = 0
    for d, i, j in candidates:
        if added >= max_extra:
            break
        dir_ij = _direction(*positions[i], *positions[j])
        dir_ji = _direction(*positions[j], *positions[i])
        if dir_ij in used_dirs[i] or dir_ji in used_dirs[j]:
            continue
        edges.append((i, j, d))
        used_dirs[i].add(dir_ij)
        used_dirs[j].add(dir_ji)
        added += 1

    return edges


def _unique_location_name(rng: random.Random, type_words: dict,
                          used: set[str], max_attempts: int = 50) -> str:
    """Generate a location name that isn't already in *used*, then register it."""
    for _ in range(max_attempts):
        adj = rng.choice(type_words["adjectives"])
        noun = rng.choice(type_words["nouns"])
        fmt = rng.randint(0, 2)
        if fmt == 0:
            name = f"{adj} {noun}"
        elif fmt == 1:
            name = noun
        else:
            name = f"{noun} {rng.randint(2, 999)}"
        if name not in used:
            used.add(name)
            return name
    # Fallback: append a number to guarantee uniqueness
    base = f"{adj} {noun}"
    n = 2
    while f"{base} {n}" in used:
        n += 1
    name = f"{base} {n}"
    used.add(name)
    return name


class Galaxy:
    def __init__(self, seed: Optional[int] = None, num_systems: int = 10) -> None:
        rng = random.Random(seed)
        self.systems: Dict[str, StarSystem] = {}

        sw = system_words()
        loc_types = location_types()
        words = location_words()

        # Generate guaranteed-unique system names
        used_names: set[str] = set()
        primaries = rng.sample(sw["primaries"], min(num_systems, len(sw["primaries"])))
        chosen: list[str] = []
        for p in primaries:
            for _ in range(50):
                roll = rng.randint(0, 2)
                if roll == 0:
                    name = f"{p} {rng.choice(sw['suffixes'])}"
                elif roll == 1:
                    name = f"{p}-{rng.randint(1, 999)}"
                else:
                    name = p
                if name not in used_names:
                    break
            else:
                # Fallback: bare primary is unique since primaries are sampled
                # without replacement; append number if even that collides.
                name = p
                n = 2
                while name in used_names:
                    name = f"{p}-{n}"
                    n += 1
            used_names.add(name)
            chosen.append(name)

        # Place systems on a grid (unique positions)
        grid_w, grid_h = 7, 5
        all_cells = [(x, y) for x in range(grid_w) for y in range(grid_h)]
        rng.shuffle(all_cells)
        positions = all_cells[:num_systems]

        # Build systems
        for i, name in enumerate(chosen):
            gx, gy = positions[i]
            locations: List[Location] = []
            for _ in range(rng.randint(2, 4)):
                lt = rng.choice(loc_types)
                type_words = words[lt]
                loc_name = _unique_location_name(rng, type_words, used_names)
                env = {"vacuum": 1} if lt in ("derelict", "asteroid") else {}
                if lt in ("asteroid", "derelict") and rng.random() < 0.7:
                    env["low_gravity"] = 1
                locations.append(Location(loc_name, lt, environment=env or None))
            self.systems[name] = StarSystem(name, locations, depth=0,
                                           star_type=pick_star_type(rng),
                                           gx=gx, gy=gy)

        # Build graph edges
        edges = _build_graph(positions, rng, max_extra=3)
        base_fuel = 30
        fuel_per_dist = 15
        for i, j, dist in edges:
            a, b = chosen[i], chosen[j]
            fuel = max(base_fuel, int(dist * fuel_per_dist))
            self.systems[a].connections[b] = fuel
            self.systems[b].connections[a] = fuel

        # Assign depth via BFS from home (first system)
        self.current_system: str = chosen[0]
        self.home_system: str = chosen[0]
        self._assign_depths()

    def _assign_depths(self) -> None:
        distances: Dict[str, int] = {self.home_system: 0}
        queue = [self.home_system]
        while queue:
            name = queue.pop(0)
            for neighbor in self.systems[name].connections:
                if neighbor not in distances:
                    distances[neighbor] = distances[name] + 1
                    queue.append(neighbor)
        for name, sys in self.systems.items():
            sys.depth = distances.get(name, 0)

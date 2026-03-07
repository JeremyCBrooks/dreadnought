"""Procedural on-demand galaxy with star systems and locations."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional

from data.db import system_words, location_types, location_words
from data.star_types import pick_star_type


_LOW_GRAVITY_TYPES = frozenset({"asteroid", "derelict"})

# 8 cardinal/diagonal direction vectors
_DIRECTIONS = [
    (0, -1), (0, 1), (-1, 0), (1, 0),
    (-1, -1), (1, -1), (-1, 1), (1, 1),
]

# Weighted distribution for total desired connections: index=count, value=weight
_CONNECTION_WEIGHTS = [(1, 5), (2, 30), (3, 40), (4, 20), (5, 5)]


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
    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        self.systems: Dict[str, StarSystem] = {}
        self._used_names: set[str] = set()
        self._occupied_positions: Dict[tuple[int, int], str] = {}
        self._generated_frontiers: set[str] = set()
        self._unexplored_frontier: set[str] = set()

        # Cache data tables
        self._sw = system_words()
        self._loc_types = location_types()
        self._loc_words = location_words()

        # Generate home system at (0, 0)
        home = self._generate_system(0, 0)
        self.home_system: str = home.name
        self.current_system: str = home.name

        # Expand home frontier so player has somewhere to go
        self._expand_frontier(home.name, min_exits=2)
        self._assign_depths()

    def _system_seed(self, gx: int, gy: int) -> int:
        """Deterministic seed for a grid position."""
        return (self.seed * 2654435761 + gx * 40503 + gy * 65537) & 0xFFFFFFFF

    def _generate_system(self, gx: int, gy: int) -> StarSystem:
        """Create a system at (gx, gy) with name, star type, locations. No connections."""
        base_seed = self._system_seed(gx, gy)
        prop_seed = base_seed ^ 0xA5A5A5A5
        rng = random.Random(prop_seed)

        # Generate unique name
        name = self._generate_system_name(rng)

        # Generate locations
        locations: List[Location] = []
        for _ in range(rng.randint(2, 4)):
            lt = rng.choice(self._loc_types)
            type_words = self._loc_words[lt]
            loc_name = _unique_location_name(rng, type_words, self._used_names)
            env = {"vacuum": 1} if lt in ("derelict", "asteroid") else {}
            if lt in ("asteroid", "derelict") and rng.random() < 0.7:
                env["low_gravity"] = 1
            locations.append(Location(loc_name, lt, environment=env or None))

        system = StarSystem(name, locations, depth=0,
                           star_type=pick_star_type(rng), gx=gx, gy=gy)
        self.systems[name] = system
        self._occupied_positions[(gx, gy)] = name
        return system

    def _generate_system_name(self, rng: random.Random) -> str:
        """Generate a unique system name using the given RNG."""
        sw = self._sw
        for _ in range(100):
            primary = rng.choice(sw["primaries"])
            roll = rng.randint(0, 2)
            if roll == 0:
                name = f"{primary} {rng.choice(sw['suffixes'])}"
            elif roll == 1:
                name = f"{primary}-{rng.randint(1, 999)}"
            else:
                name = primary
            if name not in self._used_names:
                self._used_names.add(name)
                return name
        # Fallback with counter
        base = rng.choice(sw["primaries"])
        n = 2
        name = base
        while name in self._used_names:
            name = f"{base}-{n}"
            n += 1
        self._used_names.add(name)
        return name

    def _used_directions(self, system_name: str) -> set[tuple[int, int]]:
        """Return set of directions already used by connections of a system."""
        sys = self.systems[system_name]
        dirs: set[tuple[int, int]] = set()
        for neighbor_name in sys.connections:
            nb = self.systems[neighbor_name]
            dirs.add(_direction(sys.gx, sys.gy, nb.gx, nb.gy))
        return dirs

    def _expand_frontier(self, system_name: str, min_exits: int = 0) -> bool:
        """Generate new connected systems branching from the given system.

        Returns True if the graph was modified (new systems or connections).
        """
        if system_name in self._generated_frontiers:
            return False
        self._generated_frontiers.add(system_name)
        self._unexplored_frontier.discard(system_name)

        sys = self.systems[system_name]
        base_seed = self._system_seed(sys.gx, sys.gy)
        frontier_seed = base_seed ^ 0x5A5A5A5A
        rng = random.Random(frontier_seed)

        # Roll total desired connections
        population, weights = zip(*_CONNECTION_WEIGHTS)
        desired_total = rng.choices(population, weights=weights, k=1)[0]
        desired_total = max(desired_total, min_exits)

        existing_count = len(sys.connections)
        new_exits = max(0, desired_total - existing_count)

        used_dirs = self._used_directions(system_name)
        available_dirs = [d for d in _DIRECTIONS if d not in used_dirs]
        rng.shuffle(available_dirs)

        base_fuel = 30
        fuel_per_dist = 15

        for d in available_dirs:
            if new_exits <= 0:
                break

            # Try 1-2 cell distances in this direction
            for scale in [1, 2]:
                tx = sys.gx + d[0] * scale
                ty = sys.gy + d[1] * scale
                target_pos = (tx, ty)

                if target_pos in self._occupied_positions:
                    # Existing system - try to connect as cycle
                    existing_name = self._occupied_positions[target_pos]
                    existing_sys = self.systems[existing_name]
                    reverse_dir = _direction(tx, ty, sys.gx, sys.gy)
                    reverse_used = self._used_directions(existing_name)
                    if reverse_dir not in reverse_used and rng.random() < 0.20:
                        dist = _euclidean(sys.gx, sys.gy, tx, ty)
                        fuel = max(base_fuel, int(dist * fuel_per_dist))
                        sys.connections[existing_name] = fuel
                        existing_sys.connections[system_name] = fuel
                        new_exits -= 1
                        used_dirs.add(d)
                        break
                else:
                    # Empty position - generate new system
                    new_sys = self._generate_system(tx, ty)
                    self._unexplored_frontier.add(new_sys.name)
                    dist = _euclidean(sys.gx, sys.gy, tx, ty)
                    fuel = max(base_fuel, int(dist * fuel_per_dist))
                    sys.connections[new_sys.name] = fuel
                    new_sys.connections[system_name] = fuel
                    new_exits -= 1
                    used_dirs.add(d)
                    break

        return len(sys.connections) > existing_count

    def arrive_at(self, system_name: str) -> None:
        """Called when the player arrives at a system. Expands its frontier."""
        changed = self._expand_frontier(system_name)
        if not self._unexplored_frontier:
            # Graph would close — force at least one new exit from this system
            self._generated_frontiers.discard(system_name)
            changed = self._expand_frontier(
                system_name, min_exits=len(self.systems[system_name].connections) + 1
            ) or changed
        if changed:
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

"""Minimal galaxy, star system, and location classes for the strategic layer."""
from __future__ import annotations

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
                 star_type: str = "yellow_dwarf") -> None:
        self.name = name
        self.locations: List[Location] = locations or []
        self.depth = depth
        self.star_type = star_type
        self.connections: Dict[str, int] = {}


class Galaxy:
    def __init__(self, seed: Optional[int] = None, num_systems: int = 3) -> None:
        rng = random.Random(seed)
        self.systems: Dict[str, StarSystem] = {}

        sw = system_words()
        loc_types = location_types()
        words = location_words()

        primaries = rng.sample(sw["primaries"], min(num_systems, len(sw["primaries"])))
        chosen = []
        for p in primaries:
            roll = rng.randint(0, 2)
            if roll == 0:
                name = f"{p} {rng.choice(sw['suffixes'])}"
            elif roll == 1:
                name = f"{p}-{rng.randint(1, 999)}"
            else:
                name = p
            chosen.append(name)

        for i, name in enumerate(chosen):
            locations: List[Location] = []
            for _ in range(rng.randint(2, 4)):
                lt = rng.choice(loc_types)
                type_words = words[lt]
                adj = rng.choice(type_words["adjectives"])
                noun = rng.choice(type_words["nouns"])
                fmt = rng.randint(0, 2)
                if fmt == 0:
                    loc_name = f"{adj} {noun}"
                elif fmt == 1:
                    loc_name = noun
                else:
                    loc_name = f"{noun} {rng.randint(2, 999)}"
                env = {"vacuum": 1} if lt in ("derelict", "asteroid") else {}
                if lt in ("asteroid", "derelict") and rng.random() < 0.7:
                    env["low_gravity"] = 1
                locations.append(Location(loc_name, lt, environment=env or None))
            self.systems[name] = StarSystem(name, locations, depth=i,
                                               star_type=pick_star_type(rng))

        for i in range(len(chosen) - 1):
            fuel = 30 + i * 15
            a, b = chosen[i], chosen[i + 1]
            self.systems[a].connections[b] = fuel
            self.systems[b].connections[a] = fuel

        self.current_system: str = chosen[0]
        self.home_system: str = chosen[0]

"""Ship: player's vessel with fuel, cargo, and scanner quality."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.entity import Entity
    from world.game_map import GameMap


class Ship:
    """The player's ship - persists across tactical sessions."""

    @staticmethod
    def _max_nav_units() -> int:
        import debug

        return debug.MAX_NAV_UNITS if debug.MAX_NAV_UNITS is not None else 6

    @property
    def max_nav_units(self) -> int:
        return Ship._max_nav_units()

    def __init__(
        self,
        fuel: int = 5,
        max_fuel: int = 10,
        scanner_quality: int = 1,
        hull: int = 10,
        max_hull: int = 10,
    ) -> None:
        self.fuel = fuel
        self.max_fuel = max_fuel
        self.cargo: list[Entity] = []
        self.scanner_quality = scanner_quality
        self.nav_units: int = 0
        self.hull = hull
        self.max_hull = max_hull
        self.game_map: GameMap | None = None
        self.rooms: list | None = None
        self.exit_pos: tuple[int, int] | None = None
        # Where the ship's own interior sits on ``game_map``: non-zero only
        # while an interdiction has swapped in a composite map.
        self.interior_offset: tuple[int, int] = (0, 0)
        # Entities the interior was generated with, in generation order.
        self.furnishings: list[Entity] = []

    def generate_interior(self, seed: int) -> None:
        """(Re)build the ship interior from *seed* and record its furnishings."""
        from world.dungeon_gen import generate_player_ship

        self.game_map, self.rooms, self.exit_pos = generate_player_ship(seed=seed)
        self.furnishings = list(self.game_map.entities)

    def consumed_furnishing_indices(self) -> list[int]:
        """Indices of generated furnishings the player has used up (searched lockers etc.)."""
        if self.game_map is None:
            return []
        from game.helpers import missing_entity_indices

        return missing_entity_indices(self.furnishings, self.game_map)

    def remove_furnishings(self, indices: list[int]) -> None:
        """Take already-consumed furnishings back off a freshly generated interior."""
        from game.helpers import remove_entities_at_indices

        remove_entities_at_indices(self.furnishings, indices, self.game_map)

    def add_cargo(self, item: Entity) -> None:
        """Add an item to the cargo hold."""
        self.cargo.append(item)

    def remove_cargo(self, item: Entity) -> bool:
        """Remove an item from cargo. Returns True if found and removed."""
        try:
            self.cargo.remove(item)
        except ValueError:
            return False
        return True

    def add_fuel(self, amount: int) -> int:
        """Add fuel, clamped at max_fuel. Returns the amount actually added."""
        added = min(amount, self.max_fuel - self.fuel)
        self.fuel += added
        return added

    def consume_fuel(self, cost: int) -> bool:
        """Deduct fuel if sufficient. Returns True if successful, False if insufficient."""
        if self.fuel < cost:
            return False
        self.fuel -= cost
        return True

    def damage_hull(self, amount: int = 1, rng: Any = random, near: tuple[int, int] | None = None) -> None:
        """Reduce hull by *amount*, clamped at 0, opening one breach per point lost.

        Breaches open in the outer hull closest to *near* (ship coordinates),
        or wherever *rng* picks when no point is given. A ship without an
        interior only loses the number.
        """
        lost = min(amount, self.hull)
        self.hull -= lost
        if self.game_map is not None:
            self._open_hull_breaches(lost, rng, near)

    def _open_hull_breaches(self, count: int, rng: Any, near: tuple[int, int] | None = None) -> None:
        from world.dungeon_gen import player_ship_breach_candidates

        candidates = player_ship_breach_candidates(self.game_map)
        count = min(count, len(candidates))
        if count <= 0:
            return
        if near is None:
            chosen = rng.sample(candidates, count)
        else:
            ox, oy = self.interior_offset
            nx, ny = near[0] + ox, near[1] + oy
            chosen = sorted(candidates, key=lambda pos: ((pos[0] - nx) ** 2 + (pos[1] - ny) ** 2, pos))[:count]
        for x, y in chosen:
            self.game_map.open_hull_breach(x, y)

    def hull_breach_positions(self) -> list[tuple[int, int]]:
        """Open breaches in the ship's own coordinates, wherever its interior currently sits."""
        if self.game_map is None:
            return []
        ox, oy = self.interior_offset
        return [(x - ox, y - oy) for x, y in self.game_map.hull_breaches]

    def restore_hull_breaches(self, positions: list[tuple[int, int]]) -> None:
        """Re-open saved breaches (ship coordinates) on a freshly generated interior."""
        ox, oy = self.interior_offset
        for x, y in positions:
            self.game_map.open_hull_breach(x + ox, y + oy)

    def match_breaches_to_hull(self, rng: Any) -> None:
        """Open breaches until every missing hull point has one (saves that predate breaches)."""
        if self.game_map is None:
            return
        missing = self.max_hull - self.hull - len(self.game_map.hull_breaches)
        self._open_hull_breaches(missing, rng)

    def seal_hull_breach(self, x: int, y: int) -> bool:
        """Patch the breach at (x, y) on the current map, restoring one hull point. False if none is there."""
        if self.game_map is None or (x, y) not in self.game_map.hull_breaches:
            return False
        from world.dungeon_gen import player_ship_hull_tile

        self.game_map.seal_hull_breach(x, y, player_ship_hull_tile())
        self.repair_hull(1)
        return True

    def repair_hull(self, amount: int) -> int:
        """Repair hull, clamped at max_hull. Returns the amount actually repaired."""
        repaired = min(amount, self.max_hull - self.hull)
        self.hull += repaired
        return repaired

    def add_nav_unit(self) -> bool:
        """Increment nav_units by 1 if below max. Returns True if added."""
        if self.nav_units >= self.max_nav_units:
            return False
        self.nav_units += 1
        return True

    def materialize_cargo(self, game_map: GameMap, rooms: list | None) -> None:
        """Place items from cargo onto the ship floor, then clear cargo.

        Items are dropped near the cargo-hold room centre.  Falls back to
        ``rooms[0]`` when no room is labelled ``"cargo"``.  Returns early
        without placing anything when *rooms* is empty or None.
        """
        if not rooms:
            return

        from game.helpers import find_drop_tile

        # Pick the cargo-hold room, falling back to the first room.
        room = next((r for r in rooms if r.label == "cargo"), rooms[0])
        cx, cy = room.center

        placed = 0
        for item in self.cargo:
            tile = find_drop_tile(game_map, cx, cy)
            if tile is None:
                # 3x3 neighbourhood is full - scan the entire map for space.
                tile = next(
                    (
                        (x, y)
                        for x in range(game_map.width)
                        for y in range(game_map.height)
                        if game_map.is_walkable(x, y) and not game_map.get_items_at(x, y)
                    ),
                    None,
                )
            if tile is None:
                # No space at all - leave remaining items in cargo.
                break
            item.x, item.y = tile
            game_map.entities.append(item)
            placed += 1

        del self.cargo[:placed]
        game_map.invalidate_entity_index()

    @staticmethod
    def floor_items(game_map: GameMap) -> list[Entity]:
        """Items lying on *game_map* that a ship exit would sweep into cargo."""
        return [e for e in game_map.entities if e.item is not None]

    def collect_floor_items(self, game_map: GameMap) -> None:
        """Sweep floor items from *game_map* into cargo and remove them from the map."""
        floor_items = self.floor_items(game_map)
        for item in floor_items:
            self.cargo.append(item)
            game_map.entities.remove(item)
        if floor_items:
            game_map.invalidate_entity_index()

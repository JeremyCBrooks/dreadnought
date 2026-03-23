"""Entity and component definitions -- standalone, no game-logic imports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from game.loadout import Loadout


class Fighter:
    """Combat stats component."""

    __slots__ = ("hp", "max_hp", "defense", "power", "base_power")

    def __init__(self, hp: int, max_hp: int, defense: int, power: int) -> None:
        self.hp = hp
        self.max_hp = max_hp
        self.defense = defense
        self.power = power
        self.base_power = power

    def __repr__(self) -> str:
        return f"Fighter({self.hp}/{self.max_hp} def={self.defense} pow={self.power})"


PLAYER_MAX_INVENTORY = 10


class Entity:
    """Generic game object: player, enemy, item, interactable, etc."""

    __slots__ = (
        "x",
        "y",
        "char",
        "color",
        "name",
        "blocks_movement",
        "fighter",
        "ai",
        "item",
        "interactable",
        "organic",
        "gore_color",
        "max_inventory",
        "inventory",
        "loadout",
        "drifting",
        "drift_direction",
        "decompression_moves",
        "decompression_direction",
        "move_cooldown",
        "ai_config",
        "ai_state",
        "ai_target",
        "ai_wander_goal",
        "ai_turns_since_seen",
        "ai_stuck_turns",
        "ai_energy",
        "stolen_loot",
    )

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        char: str = "?",
        color: tuple[int, int, int] = (255, 255, 255),
        name: str = "<unnamed>",
        blocks_movement: bool = True,
        fighter: Fighter | None = None,
        ai: Any = None,
        item: dict | None = None,
        interactable: dict | None = None,
        organic: bool = True,
        gore_color: tuple[int, int, int] | None = None,
        max_inventory: int | None = None,
    ) -> None:
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.name = name
        self.blocks_movement = blocks_movement
        self.fighter = fighter
        self.ai = ai
        self.item = item
        self.interactable = interactable  # {kind, hazard?: {type, severity, damage, equipment_damage}, loot?, scanned?}
        self.organic = organic
        self.gore_color = gore_color
        self.max_inventory = max_inventory
        self.inventory: list[Entity] = []
        self.loadout: Loadout | None = None
        self.drifting: bool = False
        self.drift_direction: tuple[int, int] = (0, 0)
        self.decompression_moves: int = 0
        self.decompression_direction: tuple[int, int] = (0, 0)
        self.move_cooldown: int = 0
        self.ai_config: dict = {}
        self.ai_state: str = "wandering"
        self.ai_target: tuple[int, int] | None = None
        self.ai_wander_goal: tuple[int, int] | None = None
        self.ai_turns_since_seen: int = 0
        self.ai_stuck_turns: int = 0
        self.ai_energy: int = 0
        self.stolen_loot: list[Entity] = []

    def can_carry(self) -> bool:
        """Return True if inventory has room (or is unlimited).

        Equipped items are kept in inventory, so no separate loadout count needed.
        """
        if self.max_inventory is None:
            return True
        return len(self.inventory) < self.max_inventory

    def __repr__(self) -> str:
        return f"Entity({self.name!r} @{self.x},{self.y} '{self.char}')"

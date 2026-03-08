"""Entity and component definitions -- standalone, no game-logic imports."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple, TYPE_CHECKING

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


PLAYER_MAX_INVENTORY = 10


class Entity:
    """Generic game object: player, enemy, item, interactable, etc."""

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        char: str = "?",
        color: Tuple[int, int, int] = (255, 255, 255),
        name: str = "<unnamed>",
        blocks_movement: bool = True,
        fighter: Optional[Fighter] = None,
        ai: Any = None,
        item: Optional[dict] = None,
        interactable: Optional[dict] = None,
        organic: bool = True,
        max_inventory: Optional[int] = None,
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
        self.max_inventory = max_inventory
        self.inventory: List[Entity] = []
        self.loadout: Optional[Loadout] = None
        self.drifting: bool = False
        self.drift_direction: Tuple[int, int] = (0, 0)
        self.decompression_moves: int = 0
        self.decompression_direction: Tuple[int, int] = (0, 0)
        self.move_cooldown: int = 0
        self.ai_config: dict = {}
        self.ai_state: str = "wandering"
        self.ai_target: Optional[Tuple[int, int]] = None
        self.ai_wander_goal: Optional[Tuple[int, int]] = None
        self.ai_turns_since_seen: int = 0
        self.ai_stuck_turns: int = 0
        self.ai_energy: int = 0

    def can_carry(self) -> bool:
        """Return True if inventory has room (or is unlimited).

        Equipped items are kept in inventory, so no separate loadout count needed.
        """
        if self.max_inventory is None:
            return True
        return len(self.inventory) < self.max_inventory

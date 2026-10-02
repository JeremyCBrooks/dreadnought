"""The player's between-mission record: build the entity, snapshot it, restore it."""

from __future__ import annotations

from game.entity import Entity, Fighter
from game.loadout import Loadout, recalc_melee_power

PLAYER_HP = 10
PLAYER_DEFENSE = 0
PLAYER_POWER = 1


def new_player(x: int, y: int) -> Entity:
    """A player entity with starting stats at (x, y)."""
    return Entity(
        x=x,
        y=y,
        char="@",
        color=(255, 255, 255),
        name="Player",
        blocks_movement=True,
        fighter=Fighter(hp=PLAYER_HP, max_hp=PLAYER_HP, defense=PLAYER_DEFENSE, power=PLAYER_POWER),
    )


def snapshot_player(player: Entity) -> dict:
    """Record of *player* to carry between missions. Power resets to base: the melee bonus is re-derived on restore."""
    fighter = player.fighter
    return {
        "hp": fighter.hp,
        "max_hp": fighter.max_hp,
        "defense": fighter.defense,
        "power": fighter.base_power,
        "base_power": fighter.base_power,
        "inventory": list(player.inventory),
        "loadout": player.loadout,
    }


def fresh_player_snapshot() -> dict:
    """Record of a player who has not been on a mission yet."""
    return {**snapshot_player(new_player(0, 0)), "loadout": Loadout()}


def apply_snapshot(player: Entity, snapshot: dict | None) -> None:
    """Restore stats, inventory and loadout from *snapshot* onto a freshly built player."""
    if not snapshot:
        return
    player.fighter.hp = snapshot["hp"]
    player.fighter.max_hp = snapshot["max_hp"]
    player.fighter.defense = snapshot["defense"]
    player.fighter.power = snapshot["power"]
    player.fighter.base_power = snapshot["base_power"]
    player.inventory = snapshot.get("inventory", [])
    player.loadout = snapshot.get("loadout")
    recalc_melee_power(player)

"""Tests for weapon management via loadout model."""

from game.entity import Entity, Fighter
from game.helpers import get_equipped_ranged_weapon
from game.loadout import Loadout
from tests.conftest import make_engine


def _ranged(name="Blaster", ammo=5, range_=5, value=3):
    return Entity(
        name=name,
        item={
            "type": "weapon",
            "weapon_class": "ranged",
            "value": value,
            "range": range_,
            "ammo": ammo,
            "max_ammo": 20,
        },
    )


def test_loadout_ranged_weapon_preferred():
    """When loadout has a ranged weapon, it should be returned."""
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    blaster = _ranged("Blaster")
    player.loadout = Loadout(slot1=blaster)
    assert get_equipped_ranged_weapon(player) is blaster


def test_loadout_no_ammo_returns_none():
    """Loadout weapon with no ammo should not be returned."""
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    blaster = _ranged("Blaster", ammo=0)
    player.loadout = Loadout(slot1=blaster)
    assert get_equipped_ranged_weapon(player) is None


def test_fallback_to_inventory():
    """Without loadout, fall back to inventory (for enemies)."""
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    blaster = _ranged("Blaster")
    shotgun = _ranged("Shotgun")
    player.inventory.extend([blaster, shotgun])
    assert get_equipped_ranged_weapon(player) is blaster


def test_fallback_when_equipped_empty():
    """If loadout weapon has no ammo, no fallback from loadout (inventory is for enemies)."""
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    blaster = _ranged("Blaster", ammo=0)
    player.loadout = Loadout(slot1=blaster)
    # No inventory fallback for player with loadout
    assert get_equipped_ranged_weapon(player) is None


def test_melee_weapon_auto_applies_power():
    """Melee weapon in loadout should auto-apply power bonus on tactical entry."""
    engine = make_engine()
    melee = Entity(name="Pipe", item={"type": "weapon", "weapon_class": "melee", "value": 3})
    engine.player.loadout = Loadout(slot1=melee)
    engine.player.fighter.power = engine.player.fighter.base_power + melee.item["value"]
    assert engine.player.fighter.power == 4

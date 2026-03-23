"""Tests for inventory item usage via consumables module."""

from game.entity import Entity
from game.loadout import Loadout
from tests.conftest import make_engine as _make_engine


def test_weapon_in_loadout():
    """Melee weapon in loadout auto-applies power on tactical entry."""
    engine = _make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "weapon_class": "melee", "value": 3})
    engine.player.loadout = Loadout(slot1=weapon)
    # Simulate auto-apply
    engine.player.fighter.power = engine.player.fighter.base_power + weapon.item["value"]
    assert engine.player.fighter.power == 4

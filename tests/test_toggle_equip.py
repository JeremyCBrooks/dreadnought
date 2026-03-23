"""Tests for the shared toggle_equip function."""

from game.entity import Entity, Fighter
from game.loadout import Loadout, toggle_equip
from tests.conftest import (
    MockEngine,
    make_arena,
    make_heal_item,
    make_melee_weapon,
    make_scanner,
    make_weapon,
)


def _setup():
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout()
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    return engine, player


class TestToggleEquip:
    def test_equip_weapon(self):
        engine, player = _setup()
        wpn = make_weapon()
        player.inventory.append(wpn)
        toggle_equip(engine, player, wpn)
        assert player.loadout.has_item(wpn)
        assert any("Equipped" in m[0] for m in engine.message_log.messages)

    def test_unequip_weapon(self):
        engine, player = _setup()
        wpn = make_weapon()
        player.inventory.append(wpn)
        player.loadout.equip(wpn)
        toggle_equip(engine, player, wpn)
        assert not player.loadout.has_item(wpn)
        assert any("Unequipped" in m[0] for m in engine.message_log.messages)

    def test_equip_scanner(self):
        engine, player = _setup()
        scanner = make_scanner()
        player.inventory.append(scanner)
        toggle_equip(engine, player, scanner)
        assert player.loadout.has_item(scanner)

    def test_equip_when_full_shows_warning(self):
        engine, player = _setup()
        w1 = make_weapon(name="Gun1")
        w2 = make_weapon(name="Gun2")
        w3 = make_weapon(name="Gun3")
        player.loadout.equip(w1)
        player.loadout.equip(w2)
        toggle_equip(engine, player, w3)
        assert not player.loadout.has_item(w3)
        assert any("full" in m[0].lower() for m in engine.message_log.messages)

    def test_non_equippable_item_ignored(self):
        engine, player = _setup()
        heal = make_heal_item()
        player.inventory.append(heal)
        toggle_equip(engine, player, heal)
        assert not player.loadout.has_item(heal)
        assert len(engine.message_log.messages) == 0

    def test_melee_weapon_recalculates_power(self):
        engine, player = _setup()
        wpn = make_melee_weapon(value=5)
        player.inventory.append(wpn)
        toggle_equip(engine, player, wpn)
        assert player.fighter.power == player.fighter.base_power + 5

    def test_unequip_melee_resets_power(self):
        engine, player = _setup()
        wpn = make_melee_weapon(value=5)
        player.inventory.append(wpn)
        player.loadout.equip(wpn)
        player.fighter.power = player.fighter.base_power + 5
        toggle_equip(engine, player, wpn)
        assert player.fighter.power == player.fighter.base_power

    def test_equip_without_fighter_skips_recalc(self):
        """CargoState uses a proxy entity without fighter."""
        engine, player = _setup()
        proxy = Entity()
        proxy.loadout = Loadout()
        wpn = make_weapon()
        toggle_equip(engine, proxy, wpn)
        assert proxy.loadout.has_item(wpn)

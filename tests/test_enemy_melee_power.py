"""Tests for AI melee power recalculation (Phase 2)."""
from game.entity import Entity, Fighter
from game.helpers import recalc_melee_power_ai
from tests.conftest import make_creature, make_melee_weapon


class TestRecalcMeleePowerAI:
    def test_weapon_boosts_power(self):
        enemy = make_creature(power=2)
        weapon = make_melee_weapon(value=3)
        enemy.inventory.append(weapon)
        recalc_melee_power_ai(enemy)
        assert enemy.fighter.power == 2 + 3

    def test_no_weapon_keeps_base_power(self):
        enemy = make_creature(power=2)
        recalc_melee_power_ai(enemy)
        assert enemy.fighter.power == 2

    def test_damaged_weapon_skipped(self):
        enemy = make_creature(power=2)
        weapon = make_melee_weapon(value=3)
        weapon.item["damaged"] = True
        enemy.inventory.append(weapon)
        recalc_melee_power_ai(enemy)
        assert enemy.fighter.power == 2

    def test_multiple_weapons_uses_highest(self):
        enemy = make_creature(power=1)
        w1 = make_melee_weapon(name="Pipe", value=2)
        w2 = make_melee_weapon(name="Baton", value=5)
        enemy.inventory.extend([w1, w2])
        recalc_melee_power_ai(enemy)
        assert enemy.fighter.power == 1 + 5

    def test_ranged_weapon_ignored(self):
        from tests.conftest import make_weapon
        enemy = make_creature(power=2)
        ranged = make_weapon(name="Blaster", weapon_class="ranged", value=4)
        enemy.inventory.append(ranged)
        recalc_melee_power_ai(enemy)
        assert enemy.fighter.power == 2

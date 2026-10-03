"""A destroyed Sentry Turret sometimes leaves its gun behind: the best blaster in the game, found nowhere else."""

from __future__ import annotations

import random

from data.enemies import enemy_by_name
from data.items import ITEMS, all_loot, item_by_name
from game.actions import MeleeAction
from game.entity import Entity, Fighter
from game.factories import build_enemy
from tests.conftest import MockEngine, make_arena

SALVAGE = "Sentry Blaster"


def _destroy_turret(seed: int) -> list[Entity]:
    """Build a turret from *seed*, destroy it, and return what it left on the floor."""
    game_map = make_arena(12, 12)
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 50))
    turret = build_enemy(enemy_by_name("Sentry Turret"), 6, 5, random.Random(seed))
    game_map.entities.extend([player, turret])
    MeleeAction(turret).perform(MockEngine(game_map, player), player)
    return [e for e in game_map.entities if e.item is not None]


class TestSentryBlaster:
    def test_outclasses_the_low_power_blaster(self):
        salvage, common = item_by_name(SALVAGE), item_by_name("Low-power Blaster")
        assert salvage.type == "weapon" and salvage.weapon_class == "ranged"
        assert salvage.value > common.value
        assert salvage.range > common.range
        assert salvage.max_ammo >= common.max_ammo

    def test_is_found_nowhere_but_on_turrets(self):
        assert SALVAGE not in {i.name for i in ITEMS}
        assert SALVAGE not in {d["name"] for d in all_loot()}
        carriers = [c for c in (enemy_by_name(n) for n in ("Sentry Turret",)) if SALVAGE in dict(c.loot_table)]
        assert carriers


class TestTurretDrops:
    def test_some_turrets_drop_one_and_some_do_not(self):
        drops = sum(any(e.name == SALVAGE for e in _destroy_turret(seed)) for seed in range(60))
        assert 10 <= drops <= 40, f"{drops} of 60 turrets dropped a {SALVAGE}"

    def test_the_dropped_blaster_is_a_working_player_weapon(self):
        blaster = next(e for seed in range(60) for e in _destroy_turret(seed) if e.name == SALVAGE)
        assert blaster.item["weapon_class"] == "ranged"
        assert blaster.item["ammo"] == blaster.item["max_ammo"] > 0
        assert not blaster.item.get("natural")

    def test_the_turret_s_own_gun_still_never_drops(self):
        for seed in range(30):
            assert not [e for e in _destroy_turret(seed) if e.name == "Turret Blaster"]

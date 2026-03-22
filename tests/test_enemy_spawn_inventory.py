"""Tests for enemy spawn integration with inventory (Phase 3)."""
import random

from game.entity import Entity, Fighter
from game.ai import CreatureAI
from game.helpers import recalc_melee_power_ai, get_equipped_ranged_weapon
from data.enemies import ENEMIES, EnemyDef, build_enemy_inventory
from tests.conftest import make_melee_weapon, make_weapon


def _enemy_by_name(name: str) -> EnemyDef:
    for e in ENEMIES:
        if e.name == name:
            return e
    raise ValueError(f"No enemy named {name!r}")


def _spawn_like_dungeon(defn: EnemyDef, rng: random.Random) -> Entity:
    """Simulate what dungeon_gen._spawn_enemies does."""
    entity = Entity(
        x=3, y=3, char=defn.char, color=defn.color, name=defn.name,
        blocks_movement=True,
        fighter=Fighter(hp=defn.hp, max_hp=defn.hp,
                        defense=defn.defense, power=defn.power),
        ai=CreatureAI(),
        organic=defn.organic,
        gore_color=defn.gore_color,
    )
    entity.inventory = build_enemy_inventory(defn, rng)
    entity.max_inventory = defn.max_inventory
    recalc_melee_power_ai(entity)
    return entity


class TestSpawnIntegration:
    def test_pirate_with_melee_weapon_has_boosted_power(self):
        pirate_def = _enemy_by_name("Pirate")
        # Find a seed that gives a melee weapon
        for seed in range(200):
            rng = random.Random(seed)
            entity = _spawn_like_dungeon(pirate_def, rng)
            melee_items = [
                e for e in entity.inventory
                if e.item and e.item.get("weapon_class") == "melee"
            ]
            if melee_items:
                best_val = max(e.item["value"] for e in melee_items)
                assert entity.fighter.power == pirate_def.power + best_val
                return
        raise AssertionError("Could not find a seed producing a melee weapon")

    def test_spawned_enemy_with_ranged_weapon(self):
        pirate_def = _enemy_by_name("Pirate")
        for seed in range(200):
            rng = random.Random(seed)
            entity = _spawn_like_dungeon(pirate_def, rng)
            ranged = get_equipped_ranged_weapon(entity)
            if ranged:
                assert ranged.item["weapon_class"] == "ranged"
                assert ranged.item.get("ammo", 0) > 0
                return
        raise AssertionError("Could not find a seed producing a ranged weapon")

    def test_rat_has_empty_inventory(self):
        rat_def = _enemy_by_name("Rat")
        entity = _spawn_like_dungeon(rat_def, random.Random(0))
        assert entity.inventory == []
        assert entity.fighter.power == rat_def.power

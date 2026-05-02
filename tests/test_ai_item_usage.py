"""Tests for AI consumable usage (Phase 5)."""

from game.entity import Entity, Fighter
from tests.conftest import (
    DEFAULT_AI_CONFIG,
    MockEngine,
    force_rng,
    make_arena,
    make_creature,
    make_heal_item,
    make_melee_weapon,
)


def _make_engine_with_enemy(
    enemy_x=3, enemy_y=3, enemy_hp=10, enemy_max_hp=10, organic=True, ai_state="hunting", power=1
):
    gm = make_arena(20, 20)
    player = Entity(x=15, y=15, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    enemy = make_creature(
        x=enemy_x,
        y=enemy_y,
        hp=enemy_hp,
        power=power,
        ai_state=ai_state,
        organic=organic,
        ai_config={**DEFAULT_AI_CONFIG, "flee_threshold": 0.0},
    )
    enemy.fighter.max_hp = enemy_max_hp
    gm.entities.append(enemy)
    return engine, enemy


class TestTryUseItem:
    def test_organic_enemy_heals_when_low(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=3, enemy_max_hp=10)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        # Force RNG to allow healing (< 0.4)
        force_rng(engine, 0.1)
        used = ai._try_use_item(enemy, engine)
        assert used is True
        assert enemy.fighter.hp == 8  # 3 + 5
        assert medkit not in enemy.inventory

    def test_organic_enemy_no_heal_at_full_hp(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=10, enemy_max_hp=10)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        force_rng(engine, 0.1)
        used = ai._try_use_item(enemy, engine)
        assert used is False
        assert medkit in enemy.inventory

    def test_nonorganic_enemy_never_heals(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=3, enemy_max_hp=10, organic=False)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        force_rng(engine, 0.1)
        used = ai._try_use_item(enemy, engine)
        assert used is False
        assert enemy.fighter.hp == 3

    def test_mechanical_enemy_repairs_damaged_weapon(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=5, enemy_max_hp=10, organic=False)
        weapon = make_melee_weapon(value=3)
        weapon.item["damaged"] = True
        weapon.item["durability"] = 0
        weapon.item["max_durability"] = 5
        repair_kit = Entity(
            char="#",
            color=(180, 140, 80),
            name="Repair Kit",
            blocks_movement=False,
            item={"type": "repair", "value": 5},
        )
        enemy.inventory.extend([weapon, repair_kit])

        ai = enemy.ai
        force_rng(engine, 0.1)
        used = ai._try_use_item(enemy, engine)
        assert used is True
        assert not weapon.item.get("damaged")
        assert weapon.item["durability"] == weapon.item["max_durability"]
        assert repair_kit not in enemy.inventory

    def test_item_removed_after_use(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=3, enemy_max_hp=10)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        force_rng(engine, 0.1)
        ai._try_use_item(enemy, engine)
        assert medkit not in enemy.inventory

    def test_rng_gate_prevents_use(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=3, enemy_max_hp=10)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        # RNG returns 0.9 > 0.4, so should not use
        force_rng(engine, 0.9)
        used = ai._try_use_item(enemy, engine)
        assert used is False
        assert medkit in enemy.inventory
        assert enemy.fighter.hp == 3

    def test_message_logged_on_heal(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=3, enemy_max_hp=10)
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        force_rng(engine, 0.1)
        ai._try_use_item(enemy, engine)
        messages = [text for text, _ in engine.message_log._messages]
        assert any("heals" in m.lower() or "uses" in m.lower() for m in messages)

    def test_heal_does_not_exceed_max_hp(self):
        engine, enemy = _make_engine_with_enemy(enemy_hp=4, enemy_max_hp=10)
        medkit = make_heal_item(value=20)
        enemy.inventory.append(medkit)

        ai = enemy.ai
        force_rng(engine, 0.1)
        ai._try_use_item(enemy, engine)
        assert enemy.fighter.hp == 10  # capped at max


class TestAIItemUsageInStates:
    def test_hunting_uses_item_consumes_turn(self):
        """When hunting and item is used, no movement/attack happens."""
        engine, enemy = _make_engine_with_enemy(
            enemy_hp=3,
            enemy_max_hp=10,
            ai_state="hunting",
        )
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)
        old_x, old_y = enemy.x, enemy.y

        force_rng(engine, 0.1)
        enemy.ai.perform(enemy, engine)
        # Enemy healed instead of moving
        assert enemy.fighter.hp == 8
        assert enemy.x == old_x and enemy.y == old_y

    def test_wandering_uses_item(self):
        engine, enemy = _make_engine_with_enemy(
            enemy_hp=3,
            enemy_max_hp=10,
            ai_state="wandering",
        )
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        force_rng(engine, 0.1)
        enemy.ai.perform(enemy, engine)
        assert enemy.fighter.hp == 8

    def test_fleeing_uses_item(self):
        engine, enemy = _make_engine_with_enemy(
            enemy_hp=3,
            enemy_max_hp=10,
            ai_state="fleeing",
        )
        medkit = make_heal_item(value=5)
        enemy.inventory.append(medkit)

        force_rng(engine, 0.1)
        enemy.ai.perform(enemy, engine)
        assert enemy.fighter.hp == 8

"""Tests for enemy loot tables and inventory building (Phase 1)."""

import random

from data.enemies import EnemyDef, build_enemy_inventory, enemy_by_name
from data.items import item_by_name


class TestLootTableFields:
    def test_rat_has_empty_loot_table(self):
        rat = enemy_by_name("Rat")
        assert rat.loot_table == ()

    def test_pirate_has_loot_table(self):
        pirate = enemy_by_name("Pirate")
        assert len(pirate.loot_table) > 0
        names = [name for name, _ in pirate.loot_table]
        assert "Med-kit" in names

    def test_bot_has_repair_kit(self):
        bot = enemy_by_name("Bot")
        names = [name for name, _ in bot.loot_table]
        assert "Repair Kit" in names

    def test_mech_pirate_has_loot(self):
        mp = enemy_by_name("Mech Pirate")
        assert len(mp.loot_table) > 0

    def test_security_drone_has_loot(self):
        sd = enemy_by_name("Security Drone")
        names = [name for name, _ in sd.loot_table]
        assert "Repair Kit" in names


class TestItemByName:
    def test_known_item(self):
        defn = item_by_name("Med-kit")
        assert defn.name == "Med-kit"
        assert defn.type == "heal"

    def test_unknown_item_raises(self):
        import pytest

        with pytest.raises(KeyError):
            item_by_name("Nonexistent Gizmo")


class TestBuildEnemyInventory:
    def test_rat_empty_inventory(self):
        rat = enemy_by_name("Rat")
        rng = random.Random(42)
        inv = build_enemy_inventory(rat, rng)
        assert inv == []

    def test_pirate_deterministic_with_seed(self):
        pirate = enemy_by_name("Pirate")
        rng1 = random.Random(12345)
        inv1 = build_enemy_inventory(pirate, rng1)
        rng2 = random.Random(12345)
        inv2 = build_enemy_inventory(pirate, rng2)
        assert [e.name for e in inv1] == [e.name for e in inv2]

    def test_max_inventory_cap(self):
        """Even with a generous loot table and favorable RNG, cap is respected."""
        # Use a pirate (max_inventory=3) with a seed that gives many items
        pirate = enemy_by_name("Pirate")
        # Try many seeds to find one that would give >3 items without cap
        for seed in range(1000):
            rng = random.Random(seed)
            inv = build_enemy_inventory(pirate, rng)
            assert len(inv) <= pirate.max_inventory

    def test_items_have_correct_item_dicts(self):
        pirate = enemy_by_name("Pirate")
        # Use seed that produces at least one item
        for seed in range(100):
            rng = random.Random(seed)
            inv = build_enemy_inventory(pirate, rng)
            if inv:
                break
        assert len(inv) > 0, "Could not find a seed producing items"
        for item_ent in inv:
            assert item_ent.item is not None
            assert "type" in item_ent.item
            assert "value" in item_ent.item
            assert not item_ent.blocks_movement

    def test_items_are_entity_instances(self):
        from game.entity import Entity

        pirate = enemy_by_name("Pirate")
        for seed in range(100):
            rng = random.Random(seed)
            inv = build_enemy_inventory(pirate, rng)
            if inv:
                break
        for item_ent in inv:
            assert isinstance(item_ent, Entity)

    def test_empty_inventory_chance(self):
        """A meaningful fraction of enemies with loot tables should get nothing.

        The 25% forced-empty chance combines with natural roll failures,
        so the overall empty rate will be higher than 25%.
        """
        pirate = enemy_by_name("Pirate")
        empty_count = 0
        trials = 1000
        for seed in range(trials):
            rng = random.Random(seed)
            inv = build_enemy_inventory(pirate, rng)
            if not inv:
                empty_count += 1
        # 25% forced-empty + natural roll failures → expect roughly 35-60%
        ratio = empty_count / trials
        assert 0.30 < ratio < 0.65, f"Empty ratio {ratio:.2%} outside expected range"

    def test_forced_empty_chance_exists(self):
        """Even with 100% drop rates, 25% of enemies carry nothing."""
        # Create a fake enemy def with guaranteed drops
        guaranteed = EnemyDef(
            char="x",
            color=(255, 0, 0),
            name="Test",
            hp=5,
            defense=0,
            power=1,
            organic=True,
            gore_color=(0, 0, 0),
            ai_initial_state="wandering",
            aggro_distance=8,
            sleep_aggro_distance=3,
            can_open_doors=False,
            flee_threshold=0.0,
            memory_turns=15,
            vision_radius=8,
            move_speed=4,
            loot_table=(("Med-kit", 1.0),),  # 100% drop rate
        )
        empty_count = 0
        trials = 1000
        for seed in range(trials):
            rng = random.Random(seed)
            inv = build_enemy_inventory(guaranteed, rng)
            if not inv:
                empty_count += 1
        ratio = empty_count / trials
        assert 0.18 < ratio < 0.32, f"Forced-empty ratio {ratio:.2%} should be ~25%"

    def test_ranged_weapon_has_ammo(self):
        """Ranged weapons in enemy inventory should have ammo."""
        pirate = enemy_by_name("Pirate")
        for seed in range(200):
            rng = random.Random(seed)
            inv = build_enemy_inventory(pirate, rng)
            for item_ent in inv:
                if item_ent.item and item_ent.item.get("weapon_class") == "ranged":
                    assert item_ent.item.get("ammo", 0) > 0
                    assert item_ent.item.get("max_ammo", 0) > 0
                    return
        raise AssertionError("Could not find a seed producing a ranged weapon")

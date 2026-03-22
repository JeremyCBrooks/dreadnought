"""Tests for enemy item drops on death (Phase 4)."""
from game.entity import Entity, Fighter
from game.helpers import find_drop_tile, drop_all_inventory
from tests.conftest import make_arena, make_creature, make_heal_item, make_melee_weapon, MockEngine


class TestFindDropTile:
    def test_empty_tile_returns_same_pos(self):
        gm = make_arena()
        tile = find_drop_tile(gm, 5, 5)
        assert tile == (5, 5)

    def test_occupied_tile_returns_adjacent(self):
        gm = make_arena()
        # Place an item at (5,5)
        item = make_heal_item()
        item.x, item.y = 5, 5
        gm.entities.append(item)
        tile = find_drop_tile(gm, 5, 5)
        assert tile is not None
        assert tile != (5, 5)
        # Must be adjacent
        dx = abs(tile[0] - 5)
        dy = abs(tile[1] - 5)
        assert dx <= 1 and dy <= 1

    def test_all_tiles_full_returns_none(self):
        gm = make_arena(3, 3)
        # Only (1,1) is floor, fill it
        item = make_heal_item()
        item.x, item.y = 1, 1
        gm.entities.append(item)
        assert find_drop_tile(gm, 1, 1) is None


class TestDropAllInventory:
    def test_single_item_dropped(self):
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        enemy = make_creature(x=3, y=3)
        item = make_heal_item()
        enemy.inventory.append(item)
        gm.entities.append(enemy)

        drop_all_inventory(enemy, gm)
        assert len(enemy.inventory) == 0
        assert item in gm.entities
        assert item.x == 3 and item.y == 3

    def test_multiple_items_dropped(self):
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)

        enemy = make_creature(x=3, y=3)
        items = [make_heal_item(), make_melee_weapon(), make_heal_item()]
        enemy.inventory.extend(items)
        gm.entities.append(enemy)

        drop_all_inventory(enemy, gm)
        assert len(enemy.inventory) == 0
        for it in items:
            assert it in gm.entities

    def test_empty_inventory_no_crash(self):
        gm = make_arena()
        enemy = make_creature(x=3, y=3)
        gm.entities.append(enemy)
        drop_all_inventory(enemy, gm)  # should not raise

    def test_no_space_items_lost(self):
        gm = make_arena(3, 3)  # only (1,1) is walkable floor
        enemy = make_creature(x=1, y=1)
        gm.entities.append(enemy)
        items = [make_heal_item(), make_heal_item()]
        enemy.inventory.extend(items)

        drop_all_inventory(enemy, gm)
        # First item gets placed at (1,1), second has no space
        placed = [e for e in gm.entities if e.item and e.item.get("type") == "heal"]
        assert len(placed) == 1

    def test_dropped_items_are_valid_pickups(self):
        gm = make_arena()
        enemy = make_creature(x=3, y=3)
        item = make_melee_weapon()
        enemy.inventory.append(item)
        gm.entities.append(enemy)

        drop_all_inventory(enemy, gm)
        assert not item.blocks_movement
        assert item.item is not None


class TestDeathDropsIntegration:
    def test_kill_enemy_drops_items(self):
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 5))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        enemy = make_creature(x=4, y=5, hp=1, power=0)
        item = make_heal_item()
        enemy.inventory.append(item)
        gm.entities.append(enemy)

        from game.actions import MeleeAction
        MeleeAction(enemy).perform(engine, player)

        # Enemy should be dead and removed
        assert enemy not in gm.entities
        # Item should be on the map
        assert item in gm.entities

    def test_dropped_ranged_weapon_preserves_ammo(self):
        """A ranged weapon fired by an enemy should drop with depleted ammo."""
        gm = make_arena(20, 20)
        player = Entity(x=10, y=10, name="Player", fighter=Fighter(50, 50, 0, 1))
        gm.entities.append(player)
        engine = MockEngine(gm, player)
        # Make all tiles visible for ranged attack LOS check
        gm.visible[:] = True

        enemy = make_creature(x=8, y=10, hp=1, power=0)
        from tests.conftest import make_weapon
        blaster = make_weapon(name="Blaster", weapon_class="ranged", value=2,
                              ammo=5, max_ammo=5, range_=5)
        enemy.inventory.append(blaster)
        gm.entities.append(enemy)

        # Enemy fires at player
        from game.actions import RangedAction
        RangedAction(player).perform(engine, enemy)
        assert blaster.item["ammo"] == 4  # 1 shot fired

        # Fire again
        RangedAction(player).perform(engine, enemy)
        assert blaster.item["ammo"] == 3

        # Now kill the enemy — weapon should drop with ammo=3
        from game.actions import MeleeAction
        enemy.fighter.hp = 1
        player.fighter.power = 99
        MeleeAction(enemy).perform(engine, player)

        assert enemy not in gm.entities
        assert blaster in gm.entities
        assert blaster.item["ammo"] == 3  # preserved from when enemy had it

    def test_dropped_damaged_weapon_stays_damaged(self):
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 5))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        enemy = make_creature(x=4, y=5, hp=1, power=0)
        weapon = make_melee_weapon(value=3)
        weapon.item["damaged"] = True
        weapon.item["durability"] = 0
        enemy.inventory.append(weapon)
        gm.entities.append(enemy)

        from game.actions import MeleeAction
        MeleeAction(enemy).perform(engine, player)

        assert weapon in gm.entities
        assert weapon.item["damaged"] is True
        assert weapon.item["durability"] == 0

    def test_kill_enemy_no_items_no_crash(self):
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 5))
        gm.entities.append(player)
        engine = MockEngine(gm, player)

        enemy = make_creature(x=4, y=5, hp=1, power=0)
        gm.entities.append(enemy)

        from game.actions import MeleeAction
        MeleeAction(enemy).perform(engine, player)
        assert enemy not in gm.entities

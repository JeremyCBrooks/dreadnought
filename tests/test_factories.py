"""One place builds item and enemy entities from their data definitions."""

import random

from data.enemies import enemy_by_name
from data.items import item_by_name, scanner_by_name
from game.actions import PickupAction
from game.factories import build_enemy, build_enemy_inventory, build_item_entity
from tests.conftest import enter_ship, make_engine, new_game


def test_a_built_item_can_be_picked_up_and_used_as_what_it_is():
    engine = make_engine()
    engine.player.max_inventory = 10
    engine.game_map.entities.append(build_item_entity(item_by_name("Med-kit"), 5, 5))

    assert PickupAction().perform(engine, engine.player) == 1
    assert [(i.name, i.item) for i in engine.player.inventory] == [("Med-kit", {"type": "heal", "value": 5})]


def test_scanner_uses_come_from_the_given_rng_not_the_global_one():
    def eight_scanners(global_seed: int) -> list[int]:
        random.seed(global_seed)
        rng = random.Random(5)
        return [build_item_entity(scanner_by_name("Basic Scanner"), rng=rng).item["uses"] for _ in range(8)]

    assert eight_scanners(1) == eight_scanners(2)


def test_enemy_starts_in_the_state_and_body_its_definition_names():
    drone = build_enemy(enemy_by_name("Security Drone"), 0, 0, random.Random(1))
    rat = build_enemy(enemy_by_name("Rat"), 0, 0, random.Random(1))

    assert (drone.ai_state, drone.organic) == ("sleeping", False)
    assert (rat.ai_state, rat.organic) == ("wandering", True)


def test_enemy_melee_power_includes_its_best_weapon():
    defn = enemy_by_name("Pirate")
    for seed in range(200):
        enemy = build_enemy(defn, 0, 0, random.Random(seed))
        bonus = max(
            (i.item["value"] for i in enemy.inventory if i.item.get("weapon_class") == "melee"),
            default=0,
        )
        assert enemy.fighter.power == defn.power + bonus


def test_build_enemy_draws_exactly_what_the_inventory_roll_draws():
    defn = enemy_by_name("Pirate")
    via_factory, via_inventory = random.Random(9), random.Random(9)

    build_enemy(defn, 0, 0, via_factory)
    build_enemy_inventory(defn, via_inventory)

    assert via_factory.random() == via_inventory.random()


def test_a_debug_starting_item_on_the_ship_floor_can_be_picked_up():
    import debug

    debug.START_INVENTORY = [("item", "Med-kit")]
    engine, _ = new_game()
    engine.ship.cargo = debug.build_debug_inventory()
    enter_ship(engine)
    medkit = next(e for e in engine.game_map.entities if e.name == "Med-kit")
    engine.player.x, engine.player.y = medkit.x, medkit.y
    engine.game_map.invalidate_entity_index()

    assert PickupAction().perform(engine, engine.player) == 1
    assert medkit in engine.player.inventory

"""Hull Patches are applied by hand, next to the breach, one charge per hole."""

from __future__ import annotations

import tcod.event

from data.items import build_item_data, item_by_name
from engine.game_state import Engine
from game.consumables import charges_left, use_consumable
from game.entity import Entity
from game.loadout import Loadout
from game.salvage import unload_mission_salvage
from game.ship import Ship
from tests.conftest import FakeEvent, make_arena, make_engine, new_game
from ui.inventory_state import InventoryState
from world import tile_types

BREACH = (1, 5)


def _patch() -> Entity:
    definition = item_by_name("Hull Patch")
    return Entity(name=definition.name, blocks_movement=False, item=build_item_data(definition))


def _aboard_holed_ship(player_at: tuple[int, int], breaches: tuple[tuple[int, int], ...] = (BREACH,)) -> Engine:
    """The player aboard a one-room ship: (0, y) is space, (1, y) is hull, floor from x=2."""
    engine = make_engine()
    game_map = make_arena(12, 10)
    for y in range(10):
        game_map.tiles[0, y] = tile_types.space
        game_map.tiles[1, y] = tile_types.wall
    game_map.has_space = True
    engine.player.x, engine.player.y = player_at
    game_map.entities.append(engine.player)
    engine.game_map = game_map
    engine.player.loadout = Loadout()

    engine.ship = Ship()
    engine.ship.game_map = game_map
    for x, y in breaches:
        engine.ship.hull -= 1
        game_map.open_hull_breach(x, y)
    return engine


def _use(engine: Engine, patch: Entity) -> bool:
    if patch not in engine.player.inventory:
        engine.player.inventory.append(patch)
    return use_consumable(engine, engine.player, patch)


def _last_message(engine: Engine) -> str:
    return engine.message_log.messages[-1][0]


def _is_breach(engine: Engine, pos: tuple[int, int]) -> bool:
    return int(engine.game_map.tiles[pos]["tile_id"]) == int(tile_types.hull_breach["tile_id"])


# ---- The item ----


def test_a_hull_patch_carries_three_charges():
    assert charges_left(_patch()) == 3


def test_other_consumables_have_no_charge_count():
    assert charges_left(Entity(name="Med-kit", item={"type": "heal", "value": 5})) is None


# ---- Sealing ----


def test_patching_beside_a_breach_seals_it_and_restores_one_hull_point():
    engine = _aboard_holed_ship(player_at=(2, 5))
    patch = _patch()

    used = _use(engine, patch)

    assert used is True
    assert not _is_breach(engine, BREACH)
    assert engine.game_map.hull_breaches == []
    assert engine.ship.hull == 10


def test_a_patch_spends_one_charge_per_breach_and_stays_in_the_inventory():
    engine = _aboard_holed_ship(player_at=(2, 5))
    patch = _patch()

    _use(engine, patch)

    assert charges_left(patch) == 2
    assert patch in engine.player.inventory


def test_the_last_charge_uses_the_patch_up():
    engine = _aboard_holed_ship(player_at=(2, 5), breaches=((1, 4), (1, 5), (1, 6)))
    patch = _patch()

    for _ in range(3):
        _use(engine, patch)

    assert engine.game_map.hull_breaches == []
    assert engine.ship.hull == 10
    assert patch not in engine.player.inventory


def test_one_use_seals_only_the_nearest_breach():
    engine = _aboard_holed_ship(player_at=(2, 5), breaches=((1, 3), (1, 5)))

    _use(engine, _patch())

    assert engine.game_map.hull_breaches == [(1, 3)]
    assert engine.ship.hull == 9


def test_a_breach_two_tiles_away_is_within_reach():
    engine = _aboard_holed_ship(player_at=(3, 5))

    assert _use(engine, _patch()) is True
    assert engine.game_map.hull_breaches == []


# ---- When it does nothing ----


def test_a_breach_three_tiles_away_is_out_of_reach():
    engine = _aboard_holed_ship(player_at=(4, 5))
    patch = _patch()

    used = _use(engine, patch)

    assert used is False
    assert engine.game_map.hull_breaches == [BREACH]
    assert engine.ship.hull == 9
    assert charges_left(patch) == 3
    assert "reach" in _last_message(engine)


def test_a_breach_behind_a_bulkhead_cannot_be_patched():
    engine = _aboard_holed_ship(player_at=(3, 5))
    engine.game_map.tiles[2, 5] = tile_types.wall
    patch = _patch()

    used = _use(engine, patch)

    assert used is False
    assert engine.game_map.hull_breaches == [BREACH]
    assert charges_left(patch) == 3


def test_a_breach_someone_is_standing_in_cannot_be_sealed_over_them():
    engine = _aboard_holed_ship(player_at=BREACH)
    patch = _patch()

    used = _use(engine, patch)

    assert used is False
    assert engine.game_map.hull_breaches == [BREACH]
    assert charges_left(patch) == 3


def test_patching_a_sound_hull_wastes_nothing():
    engine = _aboard_holed_ship(player_at=(2, 5), breaches=())
    patch = _patch()

    used = _use(engine, patch)

    assert used is False
    assert charges_left(patch) == 3
    assert _last_message(engine) == "No breaches to seal."


def test_a_patch_only_works_aboard_your_own_ship():
    engine = _aboard_holed_ship(player_at=(2, 5))
    engine.ship.game_map = make_arena()  # the player is on some derelict, not their ship
    patch = _patch()

    used = _use(engine, patch)

    assert used is False
    assert engine.game_map.hull_breaches == [BREACH]
    assert charges_left(patch) == 3
    assert "own ship" in _last_message(engine)


# ---- No longer applied automatically ----


def test_returning_from_a_mission_leaves_hull_patches_in_the_inventory():
    engine, _ = new_game()
    engine.ship.hull = 4
    patch = _patch()
    inventory = [patch]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.hull == 4
    assert inventory == [patch]
    assert charges_left(patch) == 3


# ---- From the inventory screen ----


def test_using_a_patch_from_the_inventory_screen_seals_the_breach():
    engine = _aboard_holed_ship(player_at=(2, 5))
    engine.player.inventory.append(_patch())
    state = InventoryState()

    state.ev_key(engine, FakeEvent(tcod.event.KeySym.E))

    assert engine.game_map.hull_breaches == []
    assert engine.ship.hull == 10


def test_the_inventory_screen_shows_the_charges_left():
    from unittest.mock import MagicMock

    engine = _aboard_holed_ship(player_at=(2, 5))
    engine.player.inventory.append(_patch())
    console = MagicMock()

    InventoryState().on_render(console, engine)

    printed = [c.kwargs["string"] for c in console.print.call_args_list]
    assert any("Hull Patch (3)" in line for line in printed)


# ---- The whole loop on a real ship ----


def test_break_away_then_board_and_patch_the_hull_back_up():
    import random

    from game.interdiction import BREAK_AWAY_HULL_DAMAGE, Interdiction, start_interdiction
    from tests.conftest import enter_ship

    engine, strategic = new_game(seed=42)
    here = engine.galaxy.systems[engine.galaxy.current_system]
    for seed in range(200):
        engine.ship.generate_interior(engine.galaxy.seed)
        here.interdiction = Interdiction()
        start_interdiction(here.interdiction, engine.ship, rng=random.Random(seed))
        if here.interdiction.started:
            break
    engine.ship.fuel = engine.ship.max_fuel

    strategic.break_away(engine, next(iter(here.connections)))
    enter_ship(engine)
    patch = _patch()
    for bx, by in list(engine.game_map.hull_breaches):
        # Stand on the deck just inside each hole.
        engine.player.x, engine.player.y = next(
            (bx + dx, by + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if engine.game_map.is_walkable(bx + dx, by + dy)
            and int(engine.game_map.tiles[bx + dx, by + dy]["tile_id"]) != int(tile_types.space["tile_id"])
        )
        engine.game_map.invalidate_entity_index()
        assert _use(engine, patch) is True

    assert engine.game_map.hull_breaches == []
    assert engine.ship.hull == engine.ship.max_hull
    assert charges_left(patch) == 3 - BREAK_AWAY_HULL_DAMAGE

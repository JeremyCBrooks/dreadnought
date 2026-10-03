"""Fixes for the game-breaking and playability issues found in the full-project review."""

from __future__ import annotations

import random

import pytest

from data.enemies import enemy_by_name
from game.entity import Entity, Fighter
from game.factories import build_enemy, build_item_entity
from tests.conftest import MockEngine, enter_mission, make_arena, new_game
from world import tile_types

NAV_UNIT = {"char": "⌂", "color": (0, 255, 200), "name": "Navigation Unit", "type": "nav_unit", "value": 1}
MEDKIT = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}


def _item(definition: dict) -> Entity:
    return build_item_entity(definition)


def _arena(w: int = 20, h: int = 12):
    gm = make_arena(w, h)
    player = Entity(x=2, y=2, name="Player", fighter=Fighter(20, 20, 0, 1))
    gm.entities.append(player)
    return MockEngine(gm, player), player


def _carrying(engine, species: str, x: int, y: int, *items: Entity) -> Entity:
    creature = build_enemy(enemy_by_name(species), x, y, random.Random(0))
    creature.inventory = list(items)
    engine.game_map.entities.append(creature)
    return creature


def _on_floor(engine, name: str) -> list[Entity]:
    return [e for e in engine.game_map.entities if e.item is not None and e.name == name]


# ---------------------------------------------------------------------------
# 1. Every nav-unit derelict really holds its Navigation Unit
# ---------------------------------------------------------------------------


def _holds_nav_unit(game_map) -> bool:
    for e in game_map.entities:
        loot = (e.interactable or {}).get("loot") or {}
        if loot.get("type") == "nav_unit" or (e.item and e.item.get("type") == "nav_unit"):
            return True
    return False


@pytest.mark.parametrize("seed", [4, 7, 8, 51, 57, 86, 113, 124])
def test_cramped_bridges_still_hold_the_nav_unit(seed):
    from world.dungeon_gen import generate_dungeon

    game_map, _, _ = generate_dungeon(width=120, height=42, seed=seed, loc_type="derelict", has_nav_unit=True)
    assert _holds_nav_unit(game_map)


def test_every_nav_unit_derelict_holds_one():
    from world.dungeon_gen import generate_dungeon

    missing = [
        seed
        for seed in range(1, 201)
        if not _holds_nav_unit(
            generate_dungeon(width=120, height=42, seed=seed, loc_type="derelict", has_nav_unit=True)[0]
        )
    ]
    assert missing == []


def test_derelicts_without_one_stay_without():
    from world.dungeon_gen import generate_dungeon

    for seed in range(1, 21):
        assert not _holds_nav_unit(generate_dungeon(width=120, height=42, seed=seed, loc_type="derelict")[0])


# ---------------------------------------------------------------------------
# 2. What a creature carries outlives it, however it dies
# ---------------------------------------------------------------------------


class TestBelongingsOutliveTheirCarrier:
    def test_suffocating_drops_everything(self):
        from game.environment import apply_environment_tick_entity

        engine, _ = _arena()
        engine.environment = {"gas": 1}
        thief = _carrying(engine, "Pirate", 8, 6, _item(NAV_UNIT), _item(MEDKIT))
        thief.fighter.hp = 1
        apply_environment_tick_entity(engine, thief)
        assert thief not in engine.game_map.entities
        assert _on_floor(engine, "Navigation Unit") and _on_floor(engine, "Med-kit")

    def test_crushed_by_decompression_drops_everything(self):
        from game.turn import _process_decompression

        engine, _ = _arena()
        thief = _carrying(engine, "Pirate", 8, 6, _item(NAV_UNIT))
        thief.fighter.hp = 0
        _process_decompression(engine)
        assert thief not in engine.game_map.entities
        assert _on_floor(engine, "Navigation Unit")

    def test_mission_items_lost_to_space_are_washed_back_aboard(self):
        from game.turn import lose_to_space

        engine, _ = _arena()
        gm = engine.game_map
        gm.tiles[15:, :] = tile_types.space
        thief = _carrying(engine, "Pirate", 18, 6, _item(NAV_UNIT))
        lose_to_space(engine, thief)
        (unit,) = _on_floor(engine, "Navigation Unit")
        assert gm.is_walkable(unit.x, unit.y)

    def test_a_built_in_weapon_still_dies_with_its_owner(self):
        from game.environment import apply_environment_tick_entity

        engine, _ = _arena()
        engine.environment = {"gas": 1}
        turret = build_enemy(enemy_by_name("Sentry Turret"), 8, 6, random.Random(0))
        turret.organic = True  # make it mortal to gas for the test
        turret.fighter.hp = 1
        engine.game_map.entities.append(turret)
        apply_environment_tick_entity(engine, turret)
        assert not _on_floor(engine, "Turret Blaster")


class TestRespawningKeepsWhatMatters:
    def test_a_stolen_or_mission_item_is_left_behind(self):
        from world.dungeon_gen import respawn_creatures

        engine, player = _arena()
        gm = engine.game_map
        stolen = _item(MEDKIT)
        thief = _carrying(engine, "Pirate", 8, 6, _item(NAV_UNIT), stolen)
        thief.stolen_loot = [stolen]
        rooms = [type("R", (), {"x1": 1, "y1": 1, "x2": 18, "y2": 10, "center": (9, 5), "label": "x"})()] * 2
        respawn_creatures(gm, rooms, max_enemies=0, seed=1)
        assert thief not in gm.entities
        assert _on_floor(engine, "Navigation Unit")
        assert stolen in gm.entities

    def test_a_creature_s_own_kit_is_not_farmed(self):
        from world.dungeon_gen import respawn_creatures

        engine, _ = _arena()
        gm = engine.game_map
        _carrying(engine, "Pirate", 8, 6, _item(MEDKIT))
        rooms = [type("R", (), {"x1": 1, "y1": 1, "x2": 18, "y2": 10, "center": (9, 5), "label": "x"})()] * 2
        respawn_creatures(gm, rooms, max_enemies=0, seed=1)
        assert not _on_floor(engine, "Med-kit")


# ---------------------------------------------------------------------------
# 3. A new run after a game over starts clean
# ---------------------------------------------------------------------------


def test_a_new_run_does_not_inherit_the_last_one():
    from ui.game_over_state import GameOverState
    from ui.title_state import TitleState

    engine, _ = new_game(1)
    enter_mission(engine, "colony")
    engine.player.inventory.append(_item(MEDKIT))
    engine.player.fighter.hp = 1
    over = GameOverState(title="MISSION ABANDONED")
    engine.push_state(over)
    over._fade_start = 0.0
    from tests.conftest import FakeEvent

    over.ev_key(engine, FakeEvent(next(iter(__import__("engine.keys", fromlist=["x"]).confirm_keys()))))
    assert isinstance(engine.current_state, TitleState)
    assert engine.saved_player is None
    assert engine.mission_loadout == []
    assert engine.ship is None and engine.galaxy is None


# ---------------------------------------------------------------------------
# 4. Items moved to your pack at the helm are not lost at the briefing
# ---------------------------------------------------------------------------


class TestPackingAtTheHelm:
    def _helm_transfer(self, engine, item: Entity):
        from ui.cargo_state import CargoState

        engine.ship.cargo = [item]
        cargo = CargoState()
        cargo._transfer(engine)
        return cargo

    def test_packed_items_survive_the_briefing_and_reach_the_mission(self):
        from ui.briefing_state import BriefingState
        from ui.tactical_state import TacticalState

        engine, _ = new_game(1)
        assert engine.saved_player is None
        kit = _item(MEDKIT)
        self._helm_transfer(engine, kit)
        assert kit not in engine.ship.cargo
        location = next(loc for s in engine.galaxy.systems.values() for loc in s.locations)
        briefing = BriefingState(location=location, depth=0)
        engine.push_state(briefing)
        engine.pop_state()
        engine.push_state(TacticalState(location=location, depth=0))
        assert kit in engine.player.inventory

    def test_items_packed_during_a_briefing_you_back_out_of_go_back_to_cargo(self):
        from ui.briefing_state import BriefingState
        from ui.cargo_state import CargoState

        engine, _ = new_game(1)
        location = next(loc for s in engine.galaxy.systems.values() for loc in s.locations)
        engine.push_state(BriefingState(location=location, depth=0))
        kit = _item(MEDKIT)
        engine.ship.cargo = [kit]
        CargoState(during_briefing=True)._transfer(engine)
        assert engine.mission_loadout == [kit]
        engine.pop_state()  # back out to the helm
        engine.push_state(BriefingState(location=location, depth=0))
        assert kit in engine.ship.cargo
        assert engine.mission_loadout == []


# ---------------------------------------------------------------------------
# 5. Inventory actions cost a turn on a mission
# ---------------------------------------------------------------------------


class TestInventoryTakesTime:
    def _open(self, *items: Entity):
        from ui.inventory_state import InventoryState

        engine, _ = new_game(1)
        enter_mission(engine, "colony")
        engine.player.inventory[:] = list(items)
        inventory = InventoryState()
        engine.push_state(inventory)
        return engine, inventory

    def test_using_a_med_kit_lets_the_world_move(self):
        engine, inventory = self._open(_item(MEDKIT))
        engine.player.fighter.hp = 3
        turn = engine.turn_counter
        inventory._activate(engine)
        assert engine.player.fighter.hp > 3
        assert engine.turn_counter == turn + 1

    def test_a_failed_use_takes_no_time(self):
        engine, inventory = self._open(_item(MEDKIT))
        turn = engine.turn_counter
        inventory._activate(engine)  # already at full health
        assert engine.turn_counter == turn

    def test_equipping_takes_a_turn(self):
        pipe = _item(
            {"char": "/", "color": (1, 1, 1), "name": "Bent Pipe", "type": "weapon", "value": 2}
            | {"weapon_class": "melee", "durability": 5, "max_durability": 5}
        )
        engine, inventory = self._open(pipe)
        if engine.player.loadout and engine.player.loadout.has_item(pipe):
            engine.player.loadout.unequip(pipe)
        turn = engine.turn_counter
        inventory._activate(engine)
        assert engine.player.loadout.has_item(pipe)
        assert engine.turn_counter == turn + 1

    def test_dropping_takes_a_turn(self):
        engine, inventory = self._open(_item(MEDKIT))
        turn = engine.turn_counter
        inventory._drop(engine)
        assert engine.turn_counter == turn + 1

    def test_at_the_helm_time_stands_still(self):
        from ui.inventory_state import InventoryState

        engine, _ = new_game(1)
        engine.saved_player = None
        inventory = InventoryState()
        assert not inventory._spend_turn(engine)


# ---------------------------------------------------------------------------
# 6. A reload does not restock places you have already looted
# ---------------------------------------------------------------------------


class TestLootedPlacesStayLooted:
    def _loot_and_reload(self, loc_type: str):
        from web.save_load import _galaxy_from_dict, _galaxy_to_dict

        engine, _ = new_game(1)
        state = enter_mission(engine, loc_type)
        location = state.location
        gm = engine.game_map
        furnishing = next(e for e in gm.entities if e.interactable and e.fighter is None)
        spot = (furnishing.x, furnishing.y)
        gm.entities.remove(furnishing)
        engine.pop_state()
        loaded = _galaxy_from_dict(_galaxy_to_dict(engine.galaxy))
        reloaded = next(loc for s in loaded.systems.values() for loc in s.locations if loc.name == location.name)
        engine.galaxy = loaded
        engine.area_cache.clear()
        from ui.tactical_state import TacticalState

        engine.push_state(TacticalState(location=reloaded, depth=state.depth))
        return engine, spot, furnishing

    def test_a_searched_furnishing_stays_searched(self):
        engine, spot, furnishing = self._loot_and_reload("derelict")
        assert not [
            e
            for e in engine.game_map.entities
            if e.interactable and (e.x, e.y) == spot and e.name == furnishing.name and e.fighter is None
        ]

    def test_an_extracted_core_stays_extracted(self):
        from web.save_load import _galaxy_from_dict, _galaxy_to_dict

        engine, _ = new_game(1)
        state = enter_mission(engine, "derelict")
        gm = engine.game_map
        core = int(tile_types.reactor_core["tile_id"])
        xs, ys = (gm.tiles["tile_id"] == core).nonzero()
        assert len(xs)
        gm.tiles[int(xs[0]), int(ys[0])] = tile_types.floor
        engine.pop_state()
        loaded = _galaxy_from_dict(_galaxy_to_dict(engine.galaxy))
        location = next(loc for s in loaded.systems.values() for loc in s.locations if loc.name == state.location.name)
        engine.area_cache.clear()
        from ui.tactical_state import TacticalState

        engine.push_state(TacticalState(location=location, depth=state.depth))
        assert not (engine.game_map.tiles["tile_id"] == core).any()


# ---------------------------------------------------------------------------
# 7. The Dreadnought's system stops being "unexplored" once you've been
# ---------------------------------------------------------------------------


def test_the_dreadnought_costs_normal_fuel_once_visited():
    from world.galaxy import Galaxy

    galaxy = Galaxy(seed=4)
    name = galaxy.spawn_dreadnought()
    assert galaxy.travel_cost(name) == 2
    galaxy.arrive_at(name)
    assert galaxy.travel_cost(name) == 1


# ---------------------------------------------------------------------------
# 8. One place decides why a shot can't be fired
# ---------------------------------------------------------------------------


class TestRangedWeaponProblem:
    def test_reports_no_weapon(self):
        from game.helpers import ranged_weapon_problem

        engine, player = _arena()
        assert ranged_weapon_problem(player) == "No ranged weapon equipped."

    def test_reports_an_empty_weapon(self):
        from game.helpers import ranged_weapon_problem

        engine, player = _arena()
        blaster = _item(
            {"char": "}", "color": (1, 1, 1), "name": "Blaster", "type": "weapon", "value": 3}
            | {"weapon_class": "ranged", "range": 5, "ammo": 0, "max_ammo": 5}
        )
        player.inventory.append(blaster)
        assert ranged_weapon_problem(player) == "Out of ammo!"

    def test_reports_nothing_when_ready(self):
        from game.helpers import ranged_weapon_problem

        engine, player = _arena()
        player.inventory.append(
            _item(
                {"char": "}", "color": (1, 1, 1), "name": "Blaster", "type": "weapon", "value": 3}
                | {"weapon_class": "ranged", "range": 5, "ammo": 3, "max_ammo": 5}
            )
        )
        assert ranged_weapon_problem(player) is None

    def test_the_action_reports_the_same_reason(self):
        from game.actions import RangedAction

        engine, player = _arena()
        target = _carrying(engine, "Rat", 5, 2)
        assert RangedAction(target).perform(engine, player) == 0
        assert engine.message_log.messages[-1][0] == "No ranged weapon equipped."

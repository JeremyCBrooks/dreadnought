"""Life aboard and life after: stowaways, the ship's cat, and wrecks that don't stay empty."""

from __future__ import annotations

import random

import pytest

from data.enemies import COMMUNITIES, MISCHIEF, enemy_by_name
from data.names import WRECK_LOC_TYPE
from game.entity import Entity
from game.factories import build_enemy, build_item_entity
from game.shipboard import adopt_companions, life_between_jumps, settle_ship_life, take_on_stowaways, welcome_aboard
from tests.conftest import enter_ship, new_game


class _Always:
    """An rng whose every roll succeeds; everything else is a seeded stream."""

    def __init__(self, value: float = 0.0) -> None:
        self._value = value
        self._real = random.Random(0)

    def random(self) -> float:
        return self._value

    def __getattr__(self, name):
        return getattr(self._real, name)


def _game():
    engine, strategic = new_game(1)
    engine.ship.max_fuel = engine.ship.fuel = 50
    return engine, strategic


def _mission_map(engine, *species: str):
    """A bare map holding the player and the given creatures beside them."""
    from tests.conftest import make_arena

    game_map = make_arena(20, 12)
    player = Entity(x=5, y=5, name="Player")
    game_map.entities.append(player)
    engine.player = player
    for i, name in enumerate(species):
        game_map.entities.append(build_enemy(enemy_by_name(name), 6 + i, 5, random.Random(i)))
    return game_map


def _messages(engine) -> str:
    return " ".join(text for text, *_ in engine.message_log.messages)


class TestStowawayData:
    def test_vermin_stow_away(self):
        assert enemy_by_name("Rat").stowaway.mischief == "eat_cargo"
        assert enemy_by_name("Hull Mite").stowaway.mischief == "chew_hull"

    def test_mischief_is_known(self):
        from data.enemies import ENEMIES

        for creature in ENEMIES:
            if creature.stowaway:
                assert creature.stowaway.mischief in MISCHIEF
                assert 0 < creature.stowaway.chance <= 1

    def test_the_cat_hunts_vermin(self):
        cat = enemy_by_name("Ship's Cat")
        assert {"Rat", "Hull Mite"} <= set(cat.hunts)
        assert cat.adoptable


class TestTakingOnStowaways:
    def test_vermin_can_slip_aboard(self):
        engine, _ = _game()
        take_on_stowaways(engine, _mission_map(engine, "Rat"), _Always(0.0))
        assert engine.ship.stowaways == ["Rat"]
        assert "cargo hold" in _messages(engine)

    def test_lucky_rolls_keep_them_off(self):
        engine, _ = _game()
        take_on_stowaways(engine, _mission_map(engine, "Rat"), _Always(0.99))
        assert engine.ship.stowaways == []

    def test_only_vermin_stow_away(self):
        engine, _ = _game()
        take_on_stowaways(engine, _mission_map(engine, "Pirate", "Glowmoth"), _Always(0.0))
        assert engine.ship.stowaways == []

    def test_one_stowaway_per_trip_at_most(self):
        engine, _ = _game()
        take_on_stowaways(engine, _mission_map(engine, "Rat", "Rat", "Hull Mite"), _Always(0.0))
        assert len(engine.ship.stowaways) == 1


class TestMischief:
    def test_mites_chew_the_hull(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Hull Mite"]
        hull = engine.ship.hull
        assert life_between_jumps(engine, random.Random(0)) == 1
        engine.ship.damage_hull(1, rng=random.Random(0))  # the caller applies the damage
        assert engine.ship.hull == hull - 1

    def test_rats_eat_supplies_but_not_the_mission(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Rat"]
        medkit = build_item_entity({"char": "!", "color": (1, 1, 1), "name": "Med-kit", "type": "heal", "value": 5})
        nav = Entity(name="Nav Unit", item={"type": "nav_unit", "value": 1})
        engine.ship.cargo = [medkit, nav]
        life_between_jumps(engine, random.Random(0))
        assert engine.ship.cargo == [nav]
        assert "Med-kit" in _messages(engine)

    def test_nothing_aboard_nothing_happens(self):
        engine, _ = _game()
        assert life_between_jumps(engine, random.Random(0)) == 0

    def test_the_cat_catches_them_first(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Rat"]
        engine.ship.crew = ["Ship's Cat"]
        medkit = build_item_entity({"char": "!", "color": (1, 1, 1), "name": "Med-kit", "type": "heal", "value": 5})
        engine.ship.cargo = [medkit]
        life_between_jumps(engine, random.Random(0))
        assert engine.ship.stowaways == []
        assert engine.ship.cargo == [medkit]
        assert "catches" in _messages(engine)


class TestAdoption:
    def test_a_cat_at_your_heels_comes_aboard(self):
        engine, _ = _game()
        game_map = _mission_map(engine, "Ship's Cat")
        adopt_companions(engine, game_map)
        assert engine.ship.crew == ["Ship's Cat"]
        assert not [e for e in game_map.entities if e.ai]

    def test_a_distant_cat_stays(self):
        engine, _ = _game()
        game_map = _mission_map(engine)
        game_map.entities.append(build_enemy(enemy_by_name("Ship's Cat"), 15, 9, random.Random(0)))
        adopt_companions(engine, game_map)
        assert engine.ship.crew == []

    def test_a_cat_you_hurt_will_not_follow(self):
        engine, _ = _game()
        game_map = _mission_map(engine, "Ship's Cat")
        next(e for e in game_map.entities if e.ai).ai_config["wronged"] = True
        adopt_companions(engine, game_map)
        assert engine.ship.crew == []

    def test_one_cat_is_enough(self):
        engine, _ = _game()
        engine.ship.crew = ["Ship's Cat"]
        adopt_companions(engine, _mission_map(engine, "Ship's Cat"))
        assert engine.ship.crew == ["Ship's Cat"]


class TestLifeAboard:
    def test_stowaways_are_waiting_when_you_board(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Rat", "Hull Mite"]
        enter_ship(engine)
        aboard = {e.ai_config.get("species") for e in engine.game_map.entities if e.ai}
        assert {"Rat", "Hull Mite"} <= aboard
        assert engine.ship.stowaways == []

    def test_your_cat_greets_you(self):
        engine, _ = _game()
        engine.ship.crew = ["Ship's Cat"]
        enter_ship(engine)
        cats = [e for e in engine.game_map.entities if e.ai and e.ai_config.get("species") == "Ship's Cat"]
        assert len(cats) == 1
        from game.helpers import chebyshev

        assert chebyshev(cats[0].x, cats[0].y, engine.player.x, engine.player.y) <= 3

    def test_survivors_go_back_into_hiding_and_the_dead_stay_dead(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Rat", "Rat"]
        engine.ship.crew = ["Ship's Cat"]
        enter_ship(engine)
        rats = [e for e in engine.game_map.entities if e.ai and e.ai_config.get("species") == "Rat"]
        rats[0].fighter.hp = 0
        engine.game_map.entities.remove(rats[0])
        engine.pop_state()
        assert engine.ship.stowaways == ["Rat"]
        assert engine.ship.crew == ["Ship's Cat"]

    def test_settling_clears_the_ship_map(self):
        engine, _ = _game()
        engine.ship.stowaways = ["Rat"]
        welcome_aboard(engine, engine.ship.game_map)
        settle_ship_life(engine, engine.ship.game_map)
        assert not [e for e in engine.ship.game_map.entities if e.ai]

    def test_stowaways_and_crew_survive_a_save(self):
        from web.save_load import _ship_from_dict, _ship_to_dict

        engine, _ = _game()
        engine.ship.stowaways = ["Hull Mite"]
        engine.ship.crew = ["Ship's Cat"]
        loaded = _ship_from_dict(_ship_to_dict(engine.ship))
        assert (loaded.stowaways, loaded.crew) == (["Hull Mite"], ["Ship's Cat"])


class TestWiring:
    def test_leaving_a_mission_can_bring_vermin_home(self):
        from tests.conftest import enter_mission

        engine, _ = _game()
        enter_mission(engine, "colony")
        player = engine.player
        rat = build_enemy(enemy_by_name("Rat"), player.x, player.y, random.Random(0))
        rat.ai_config["stowaway"]["chance"] = 1.0
        engine.game_map.entities.append(rat)
        engine.pop_state()
        assert engine.ship.stowaways == ["Rat"]

    def test_jumping_lets_them_loose(self):
        from tests.conftest import FakeEvent, key_for
        from ui.strategic_state import _direction

        engine, strategic = _game()
        engine.ship.stowaways = ["Hull Mite"]
        hull = engine.ship.hull
        galaxy = engine.galaxy
        here = galaxy.systems[galaxy.current_system]
        dest = next(iter(here.connections))
        strategic.focus = "navigation"
        strategic.ev_key(engine, FakeEvent(key_for(_direction(here, galaxy.systems[dest]))))
        assert engine.ship.hull == hull - 1
        assert "chew" in _messages(engine)


# ---------------------------------------------------------------------------
# Wrecks that don't stay empty
# ---------------------------------------------------------------------------


class TestWreckColonisation:
    def _wreck(self):
        from game.wreck import WreckRecord
        from world.galaxy import Location

        location = Location("Raider 500", WRECK_LOC_TYPE, system_name="Somewhere")
        location.visited = True
        location.wreck = WreckRecord(ship_seed=7)
        return location

    def test_wrecks_have_settlers_in_waiting(self):
        communities = COMMUNITIES[WRECK_LOC_TYPE]
        assert len(communities) >= 2
        assert all(c.report.strip() for c in communities)

    def test_a_fresh_wreck_is_empty(self):
        from game.creatures import community_of

        assert community_of(self._wreck()) is None

    def test_time_brings_settlers(self):
        from game.creatures import community_of
        from game.shipboard import colonise_wrecks

        location = self._wreck()
        galaxy = type("G", (), {"systems": {"Somewhere": type("S", (), {"locations": [location]})()}})()
        colonise_wrecks(galaxy, _Always(0.0))
        assert location.wreck.community in {c.name for c in COMMUNITIES[WRECK_LOC_TYPE]}
        assert community_of(location).name == location.wreck.community

    def test_settlers_stay_settled(self):
        from game.shipboard import colonise_wrecks

        location = self._wreck()
        location.wreck.community = "Glowmoth roost"
        galaxy = type("G", (), {"systems": {"Somewhere": type("S", (), {"locations": [location]})()}})()
        colonise_wrecks(galaxy, _Always(0.0))
        assert location.wreck.community == "Glowmoth roost"

    def test_settlers_live_aboard_the_same_ship(self):
        import numpy as np

        from ui.tactical_state import TacticalState
        from world.boarding_ship import generate_pirate_ship

        engine, _ = _game()
        location = self._wreck()
        location.wreck.community = "Mite colony"
        members = set(next(c for c in COMMUNITIES[WRECK_LOC_TYPE] if c.name == "Mite colony").members)
        engine.push_state(TacticalState(location=location, depth=3))
        species = {e.ai_config.get("species") for e in engine.game_map.entities if e.ai}
        assert species and species <= members
        pristine, _, _ = generate_pirate_ship(7)
        assert np.array_equal(engine.game_map.tiles["tile_id"], pristine.tiles["tile_id"])

    def test_the_community_is_saved_with_the_wreck(self):
        from web.save_load import _wreck_from_dict, _wreck_to_dict

        location = self._wreck()
        location.wreck.community = "Scavenger camp"
        assert _wreck_from_dict(_wreck_to_dict(location.wreck)).community == "Scavenger camp"

    @pytest.mark.parametrize("jumps", [30])
    def test_jumping_around_eventually_settles_a_wreck(self, jumps):
        from tests.conftest import FakeEvent, key_for
        from ui.strategic_state import _direction

        engine, strategic = _game()
        location = self._wreck()
        galaxy = engine.galaxy
        galaxy.systems[galaxy.current_system].locations.append(location)
        strategic.focus = "navigation"
        for _ in range(jumps):
            here = galaxy.systems[galaxy.current_system]
            dest = next(iter(here.connections))
            engine.ship.fuel = engine.ship.max_fuel
            strategic.ev_key(engine, FakeEvent(key_for(_direction(here, galaxy.systems[dest]))))
            if location.wreck.community:
                break
        assert location.wreck.community


def test_the_jump_count_survives_a_save():
    from web.save_load import _galaxy_from_dict, _galaxy_to_dict
    from world.galaxy import Galaxy

    galaxy = Galaxy(seed=2)
    galaxy.jumps = 7
    assert _galaxy_from_dict(_galaxy_to_dict(galaxy)).jumps == 7

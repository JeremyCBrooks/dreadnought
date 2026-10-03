"""Creatures come in communities that make sense together, and some places are simply peaceful."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from data.enemies import BOARDING, COMMUNITIES, TEMPERAMENTS, enemy_by_name, pick_community
from world.dungeon_gen import generate_dungeon, respawn_creatures
from world.loc_profiles import PROFILES

LOCATION_TYPES = tuple(PROFILES)
_ALL = [(loc_type, c) for loc_type, communities in COMMUNITIES.items() for c in communities]


def _hostile(name: str) -> bool:
    return TEMPERAMENTS[enemy_by_name(name).temperament].attacks_on_sight


def _species(game_map) -> set[str]:
    return {e.ai_config.get("species") for e in game_map.entities if e.ai is not None}


def _community(loc_type: str, name: str):
    return next(c for c in COMMUNITIES[loc_type] if c.name == name)


def test_every_location_type_has_communities():
    assert set(COMMUNITIES) == {*LOCATION_TYPES, BOARDING}


@pytest.mark.parametrize(("loc_type", "community"), _ALL, ids=[f"{lt}:{c.name}" for lt, c in _ALL])
class TestEveryCommunity:
    def test_members_are_real_creatures(self, loc_type, community):
        assert community.members
        for name in community.members:
            enemy_by_name(name)

    def test_has_a_briefing_report(self, loc_type, community):
        assert loc_type == BOARDING or community.report.strip()

    def test_weight_is_positive(self, loc_type, community):
        assert community.weight > 0


@pytest.mark.parametrize("loc_type", LOCATION_TYPES)
def test_every_location_type_can_be_peaceful(loc_type):
    assert [c for c in COMMUNITIES[loc_type] if c.peaceful]


@pytest.mark.parametrize("loc_type", LOCATION_TYPES)
def test_every_location_type_can_be_dangerous(loc_type):
    assert [c for c in COMMUNITIES[loc_type] if not c.peaceful]


def test_peaceful_means_nothing_attacks_on_sight():
    for _, community in _ALL:
        assert community.peaceful == (not any(_hostile(name) for name in community.members))


@pytest.mark.parametrize("loc_type", ["starbase", "colony"])
def test_settled_places_are_often_peaceful(loc_type):
    communities = COMMUNITIES[loc_type]
    peaceful = sum(c.weight for c in communities if c.peaceful)
    assert peaceful / sum(c.weight for c in communities) >= 0.25


class TestPickCommunity:
    def test_a_place_is_always_the_same_kind_of_place(self):
        assert pick_community("starbase", "Steadfast Platform") == pick_community("starbase", "Steadfast Platform")

    def test_places_differ(self):
        names = {pick_community("starbase", f"Station {i}").name for i in range(60)}
        assert len(names) >= 3

    def test_some_stations_are_peaceful_and_some_are_not(self):
        picks = [pick_community("starbase", f"Station {i}") for i in range(60)]
        assert any(c.peaceful for c in picks) and not all(c.peaceful for c in picks)

    def test_peace_can_be_ruled_out(self):
        for i in range(60):
            assert not pick_community("derelict", f"Hulk {i}", allow_peaceful=False).peaceful

    def test_unknown_location_types_have_none(self):
        assert pick_community("wreck", "Raider 590") is None


class TestSpawningByCommunity:
    def test_only_the_community_spawns(self):
        members = set(_community("starbase", "Security lockdown").members)
        for seed in range(1, 21):
            game_map, _, _ = generate_dungeon(
                seed=seed, loc_type="starbase", depth=5, max_enemies=3, community="Security lockdown"
            )
            assert _species(game_map) <= members

    def test_a_peaceful_place_has_no_hostiles(self):
        peaceful = next(c for c in COMMUNITIES["colony"] if c.peaceful)
        for seed in range(1, 21):
            game_map, _, _ = generate_dungeon(
                seed=seed, loc_type="colony", depth=5, max_enemies=3, community=peaceful.name
            )
            assert not [name for name in _species(game_map) if _hostile(name)]

    @pytest.mark.parametrize("loc_type", LOCATION_TYPES)
    def test_left_to_itself_a_map_still_holds_one_coherent_community(self, loc_type):
        member_sets = [set(c.members) for c in COMMUNITIES[loc_type]]
        for seed in range(1, 31):
            game_map, _, _ = generate_dungeon(seed=seed, loc_type=loc_type, depth=5, max_enemies=3)
            species = _species(game_map)
            assert any(species <= members for members in member_sets), f"seed {seed}: mixed {species}"

    def test_respawning_keeps_the_community(self):
        members = set(_community("derelict", "Pirate hideout").members)
        game_map, rooms, _ = generate_dungeon(seed=3, loc_type="derelict", community="Pirate hideout")
        for seed in range(10):
            respawn_creatures(
                game_map, rooms, max_enemies=3, seed=seed, loc_type="derelict", depth=5, community="Pirate hideout"
            )
            assert _species(game_map) <= members


class TestMissions:
    def _location(self, name: str, loc_type: str = "starbase", **extra):
        return SimpleNamespace(
            name=name, loc_type=loc_type, environment=None, has_nav_unit=False, system_name="", **extra
        )

    def test_location_community_is_the_one_picked_for_its_name(self):
        from game.creatures import community_of

        location = self._location("Steadfast Platform")
        assert community_of(location) == pick_community("starbase", "Steadfast Platform")

    def test_the_dreadnought_is_never_peaceful(self):
        from game.creatures import community_of

        for i in range(40):
            assert not community_of(self._location(f"Dread {i}", "derelict", is_dreadnought=True)).peaceful

    def test_the_briefing_relays_the_report(self):
        import numpy as np

        from tests.conftest import make_engine
        from ui.briefing_state import BriefingState

        location = self._location("Steadfast Platform")
        engine = make_engine()
        engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT = 160, 50
        printed = []
        console = SimpleNamespace(rgb=np.zeros((160, 50), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")]))
        console.print = lambda *, x, y, string, fg=(255, 255, 255): printed.append(string)
        console.draw_rect = lambda *a, **kw: None
        BriefingState(location=location, depth=0).on_render(console, engine)
        report = pick_community("starbase", "Steadfast Platform").report
        assert report.split()[0] in " ".join(printed)


class TestThreatLevel:
    def test_depth_alone_does_not_make_a_peaceful_place_dangerous(self):
        from ui.briefing_state import _threat_level

        assert _threat_level(None, depth=4, hostiles=False) == "LOW"
        assert _threat_level(None, depth=4) == "HIGH"

    def test_hazards_still_count_where_nobody_is_hostile(self):
        from ui.briefing_state import _threat_level

        assert _threat_level({"vacuum": 1, "radiation": 2}, depth=4, hostiles=False) == "MODERATE"


class TestCaps:
    @pytest.mark.parametrize(
        ("loc_type", "community", "species"),
        [
            ("starbase", "Skeleton crew", "Custodian"),
            ("starbase", "Skeleton crew", "Ship's Cat"),
            ("derelict", "Infested hulk", "Scrap Mimic"),
        ],
    )
    def test_a_place_holds_no_more_than_its_share(self, loc_type, community, species):
        cap = enemy_by_name(species).max_per_place
        assert cap is not None
        for seed in range(1, 31):
            game_map, _, _ = generate_dungeon(seed=seed, loc_type=loc_type, depth=5, max_enemies=3, community=community)
            count = sum(1 for e in game_map.entities if e.ai is not None and e.ai_config.get("species") == species)
            assert count <= cap, f"seed {seed}: {count} x {species}"

    def test_a_boarding_crew_brings_one_breacher_at_most(self):
        import random

        from game.interdiction import _spawn_pirates_in_room
        from world import tile_types
        from world.dungeon_gen.rooms import RectRoom
        from world.game_map import GameMap

        game_map = GameMap(20, 20, fill_tile=tile_types.floor)
        for seed in range(40):
            crew = _spawn_pirates_in_room(RectRoom(1, 1, 12, 12), game_map, random.Random(seed), 4)
            assert sum(1 for p in crew if p.name == "Breacher") <= 1

    def test_caps_are_positive(self):
        from data.enemies import ENEMIES

        for creature in ENEMIES:
            assert creature.max_per_place is None or creature.max_per_place >= 1

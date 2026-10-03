"""New creature traits: Shade (unseen in the dark), Brood Mother (spawns), Demolition Drone (detonates),
Acid Slime (splits), Hull Leech (lives in space), Rival Scavenger (loots)."""

from __future__ import annotations

import random

import numpy as np

from data.enemies import COMMUNITIES, enemy_by_name
from game.actions import MeleeAction
from game.creatures import is_hidden, is_target
from game.entity import Entity, Fighter
from game.factories import build_enemy, build_item_entity
from game.helpers import chebyshev
from tests.conftest import MockEngine, make_arena
from world import tile_types


def _arena(w: int = 24, h: int = 16, player_at: tuple[int, int] = (2, 2), hp: int = 60, lit: bool = True):
    gm = make_arena(w, h)
    gm.visible[:] = True
    gm.explored[:] = True
    gm.fully_lit = lit
    player = Entity(x=player_at[0], y=player_at[1], name="Player", fighter=Fighter(hp, hp, 0, 1))
    gm.entities.append(player)
    return MockEngine(gm, player), player


def _spawn(engine, species: str, x: int, y: int) -> Entity:
    creature = build_enemy(enemy_by_name(species), x, y, random.Random(0))
    engine.game_map.entities.append(creature)
    return creature


def _run(engine, creature, turns: int) -> None:
    for _ in range(turns):
        if creature.fighter.hp <= 0 or creature not in engine.game_map.entities:
            return
        engine.game_map.clear_fov_cache()
        engine.game_map.invalidate_entity_index()
        creature.ai.perform(creature, engine)
        engine.turn_counter += 1


def _of(engine, species: str) -> list[Entity]:
    return [e for e in engine.game_map.entities if e.ai and e.ai_config.get("species") == species]


def _members(loc_type: str, community: str) -> tuple[str, ...]:
    return next(c for c in COMMUNITIES[loc_type] if c.name == community).members


def _messages(engine) -> str:
    return " ".join(text for text, *_ in engine.message_log.messages)


# ---------------------------------------------------------------------------
# Shade
# ---------------------------------------------------------------------------


class TestShade:
    def test_lives_in_infested_hulks(self):
        assert "Shade" in _members("derelict", "Infested hulk")

    def test_cannot_be_seen_in_the_dark(self):
        engine, _ = _arena(lit=False)
        shade = _spawn(engine, "Shade", 12, 8)
        _run(engine, shade, 1)
        assert is_hidden(shade)
        assert not is_target(shade)

    def test_is_seen_in_the_light(self):
        engine, _ = _arena(lit=True)
        shade = _spawn(engine, "Shade", 12, 8)
        _run(engine, shade, 1)
        assert not is_hidden(shade)

    def test_a_glowmoth_gives_it_away(self):
        engine, _ = _arena(lit=False)
        shade = _spawn(engine, "Shade", 12, 8)
        _spawn(engine, "Glowmoth", 13, 8)
        engine.game_map.invalidate_lights()
        _run(engine, shade, 1)
        assert not is_hidden(shade)

    def test_is_felt_when_it_is_beside_you(self):
        engine, player = _arena(lit=False)
        shade = _spawn(engine, "Shade", 3, 2)
        _run(engine, shade, 1)
        assert not is_hidden(shade)

    def test_hidden_shades_are_not_drawn_or_listed(self):
        from game.scanner import build_nearby_entries

        engine, _ = _arena(lit=False)
        shade = _spawn(engine, "Shade", 12, 8)
        _run(engine, shade, 1)
        assert not [e for e in build_nearby_entries(engine) if (e.x, e.y) == (12, 8)]
        assert "Shade" not in " ".join(text for text, _ in engine.game_map.describe_at(12, 8))
        console = _render(engine)
        assert console.rgb["ch"][12, 8] != ord(shade.char)


def _render(engine):
    import tcod.console

    console = tcod.console.Console(engine.game_map.width, engine.game_map.height, order="F")
    engine.game_map.render(console, 0, 0, 0, 0, engine.game_map.width, engine.game_map.height)
    return console


class TestCarriedLightIsDrawn:
    def test_a_glowmoth_lights_a_room_with_no_lamps(self):
        engine, _ = _arena(lit=False)
        before = _render(engine).rgb["bg"][10, 8].astype(int).sum()
        _spawn(engine, "Glowmoth", 10, 8)
        after = _render(engine).rgb["bg"][10, 8].astype(int).sum()
        assert after > before


# ---------------------------------------------------------------------------
# Brood Mother
# ---------------------------------------------------------------------------


class TestBroodMother:
    def test_lives_deep_in_infested_hulks_alone(self):
        mother = enemy_by_name("Brood Mother")
        assert "Brood Mother" in _members("derelict", "Infested hulk")
        assert mother.max_per_place == 1 and mother.min_depth >= 2
        assert mother.move_speed == 0

    def test_spawns_mites_while_awake(self):
        engine, _ = _arena(player_at=(4, 8))
        mother = _spawn(engine, "Brood Mother", 10, 8)
        _run(engine, mother, 12)
        assert len(_of(engine, "Hull Mite")) >= 2
        assert "Brood Mother" in _messages(engine)

    def test_her_brood_is_capped(self):
        engine, _ = _arena(player_at=(4, 8))
        mother = _spawn(engine, "Brood Mother", 10, 8)
        _run(engine, mother, 80)
        assert len(_of(engine, "Hull Mite")) <= mother.ai_config["spawns"]["max"]

    def test_a_sleeping_mother_lays_nothing(self):
        engine, _ = _arena(player_at=(2, 2))
        engine.game_map.tiles[6, :] = tile_types.wall
        mother = _spawn(engine, "Brood Mother", 14, 8)
        _run(engine, mother, 12)
        assert _of(engine, "Hull Mite") == []

    def test_her_young_come_out_hunting(self):
        engine, _ = _arena(player_at=(4, 8))
        mother = _spawn(engine, "Brood Mother", 10, 8)
        _run(engine, mother, 12)
        assert all(mite.ai_state == "hunting" for mite in _of(engine, "Hull Mite"))


# ---------------------------------------------------------------------------
# Demolition Drone
# ---------------------------------------------------------------------------


class TestDemolitionDrone:
    def test_runs_with_rogue_systems(self):
        assert "Demolition Drone" in _members("derelict", "Rogue systems")

    def test_blows_itself_up_beside_you(self):
        engine, player = _arena()
        drone = _spawn(engine, "Demolition Drone", 6, 2)
        _run(engine, drone, 6)
        assert drone not in engine.game_map.entities
        assert player.fighter.hp <= player.fighter.max_hp - 3
        assert "detonates" in _messages(engine)

    def test_shot_down_at_range_it_hurts_nobody(self):
        engine, player = _arena()
        drone = _spawn(engine, "Demolition Drone", 12, 8)
        drone.fighter.hp = 1
        player.fighter.power = 50
        from game.actions import _apply_damage_and_death

        _apply_damage_and_death(engine, player, drone, 50)
        assert player.fighter.hp == player.fighter.max_hp


# ---------------------------------------------------------------------------
# Acid Slime
# ---------------------------------------------------------------------------


class TestAcidSlime:
    def test_oozes_through_overrun_colonies(self):
        assert "Acid Slime" in _members("colony", "Overrun")

    def test_splits_in_two_when_hit(self):
        engine, player = _arena()
        slime = _spawn(engine, "Acid Slime", 3, 2)
        hp = slime.fighter.hp
        MeleeAction(slime).perform(engine, player)
        slimes = _of(engine, "Acid Slime")
        assert len(slimes) == 2
        assert sum(s.fighter.hp for s in slimes) == hp - 1
        assert all(chebyshev(s.x, s.y, 3, 2) <= 1 for s in slimes)
        assert "splits" in _messages(engine)

    def test_a_scrap_too_small_does_not_split(self):
        engine, player = _arena()
        slime = _spawn(engine, "Acid Slime", 3, 2)
        slime.fighter.hp = 2
        MeleeAction(slime).perform(engine, player)
        assert len(_of(engine, "Acid Slime")) == 1

    def test_splitting_has_a_limit(self):
        engine, player = _arena(w=30, h=20, player_at=(15, 10))
        slime = _spawn(engine, "Acid Slime", 16, 10)
        slime.fighter.hp = slime.fighter.max_hp = 200
        for _ in range(40):
            for target in list(_of(engine, "Acid Slime")):
                if target.fighter.hp > 0 and target in engine.game_map.entities:
                    MeleeAction(target).perform(engine, player)
        assert len(_of(engine, "Acid Slime")) <= enemy_by_name("Acid Slime").max_per_place


# ---------------------------------------------------------------------------
# Hull Leech
# ---------------------------------------------------------------------------


def _ship_in_space():
    """A 3-wide corridor of floor, walled, inside open space: (engine, player)."""
    gm = make_arena(30, 15)
    gm.tiles[:, :] = tile_types.space
    gm.tiles[5:25, 5:10] = tile_types.wall
    gm.tiles[6:24, 6:9] = tile_types.floor
    gm.has_space = True
    gm.visible[:] = True
    player = Entity(x=10, y=7, name="Player", fighter=Fighter(40, 40, 0, 1))
    gm.entities.append(player)
    return MockEngine(gm, player), player


class TestHullLeech:
    def test_clings_to_infested_hulks(self):
        assert "Hull Leech" in _members("derelict", "Infested hulk")

    def test_never_leaves_space(self):
        engine, _ = _ship_in_space()
        leech = _spawn(engine, "Hull Leech", 15, 3)
        space = int(tile_types.space["tile_id"])
        for _ in range(20):
            _run(engine, leech, 1)
            assert int(engine.game_map.tiles["tile_id"][leech.x, leech.y]) == space

    def test_attacks_a_player_out_on_the_hull(self):
        engine, player = _ship_in_space()
        player.x, player.y = 15, 4  # floating just outside
        leech = _spawn(engine, "Hull Leech", 18, 3)
        _run(engine, leech, 8)
        assert player.fighter.hp < player.fighter.max_hp

    def test_cannot_reach_a_player_inside(self):
        engine, player = _ship_in_space()
        leech = _spawn(engine, "Hull Leech", 10, 3)
        _run(engine, leech, 15)
        assert player.fighter.hp == player.fighter.max_hp

    def test_spawns_out_in_space(self):
        from world.dungeon_gen import generate_dungeon

        space = int(tile_types.space["tile_id"])
        seen = 0
        for seed in range(1, 40):
            game_map, _, _ = generate_dungeon(seed=seed, loc_type="derelict", depth=5, community="Infested hulk")
            for leech in [e for e in game_map.entities if e.ai and e.ai_config.get("species") == "Hull Leech"]:
                seen += 1
                assert int(game_map.tiles["tile_id"][leech.x, leech.y]) == space
        assert seen


# ---------------------------------------------------------------------------
# Rival Scavenger
# ---------------------------------------------------------------------------


def _crate(engine, x: int, y: int, loot: bool = True) -> Entity:
    loot_dict = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    crate = Entity(
        x=x,
        y=y,
        char="=",
        name="Crate",
        blocks_movement=False,
        interactable={"kind": "crate", "hazard": None, "loot": loot_dict if loot else None},
    )
    engine.game_map.entities.append(crate)
    return crate


class TestRivalScavenger:
    def test_works_the_quiet_wrecks_and_stations(self):
        assert "Rival Scavenger" in _members("derelict", "Silent wreck")
        assert "Rival Scavenger" in _members("starbase", "Skeleton crew")

    def test_is_a_person_who_minds_their_own_business(self):
        scavenger = enemy_by_name("Rival Scavenger")
        assert scavenger.char == "@"
        assert scavenger.temperament == "territorial"

    def test_empties_crates_before_you_can(self):
        engine, player = _arena()
        scavenger = _spawn(engine, "Rival Scavenger", 14, 8)
        crate = _crate(engine, 18, 8)
        _run(engine, scavenger, 25)
        assert crate not in engine.game_map.entities
        assert any(item.name == "Med-kit" for item in scavenger.inventory)

    def test_picks_up_loose_items(self):
        engine, _ = _arena()
        scavenger = _spawn(engine, "Rival Scavenger", 14, 8)
        item = build_item_entity({"char": "#", "color": (1, 1, 1), "name": "Repair Kit", "type": "repair", "value": 5})
        item.x, item.y = 18, 10
        engine.game_map.entities.append(item)
        _run(engine, scavenger, 25)
        assert item in scavenger.inventory

    def test_rob_them_and_you_get_it_all_back(self):
        engine, player = _arena()
        scavenger = _spawn(engine, "Rival Scavenger", 3, 2)
        _crate(engine, 4, 2)
        _run(engine, scavenger, 3)
        scavenger.fighter.hp = 1
        player.fighter.power = 50
        MeleeAction(scavenger).perform(engine, player)
        assert [e for e in engine.game_map.entities if e.item and e.name == "Med-kit"]

    def test_leaves_you_alone_while_you_leave_them_alone(self):
        engine, player = _arena()
        _run(engine, _spawn(engine, "Rival Scavenger", 3, 2), 12)
        assert player.fighter.hp == player.fighter.max_hp


def test_only_people_share_the_player_s_glyph():
    from data.enemies import ENEMIES

    people = {"Colonist", "Rival Scavenger", "Hermit"}
    assert {c.name for c in ENEMIES if c.char == "@"} <= people
    assert np  # numpy kept for render assertions above

"""More of the menagerie: Warden, Echo Flitter, Rust Beetle, Bloat Grazer, Pirate Captain, and colonists who
look after their own."""

from __future__ import annotations

import random

import pytest

from data.enemies import COMMUNITIES, TEMPERAMENTS, enemy_by_name
from game.actions import MeleeAction
from game.entity import Entity, Fighter
from game.factories import build_enemy
from tests.conftest import MockEngine, make_arena


def _arena(w: int = 24, h: int = 16, player_at: tuple[int, int] = (2, 2), hp: int = 40):
    gm = make_arena(w, h)
    gm.visible[:] = True
    player = Entity(x=player_at[0], y=player_at[1], name="Player", fighter=Fighter(hp, hp, 0, 1))
    gm.entities.append(player)
    return MockEngine(gm, player), player


def _spawn(engine, species: str, x: int, y: int) -> Entity:
    creature = build_enemy(enemy_by_name(species), x, y, random.Random(0))
    engine.game_map.entities.append(creature)
    return creature


def _members(loc_type: str, community: str) -> tuple[str, ...]:
    return next(c for c in COMMUNITIES[loc_type] if c.name == community).members


@pytest.mark.parametrize(
    ("species", "loc_type", "community"),
    [
        ("Warden", "starbase", "Security lockdown"),
        ("Echo Flitter", "asteroid", "Quiet rock"),
        ("Rust Beetle", "derelict", "Infested hulk"),
        ("Bloat Grazer", "colony", "Holdouts"),
        ("Pirate Captain", "derelict", "Pirate hideout"),
        ("Pirate Captain", "starbase", "Raided"),
        ("Pirate Captain", "asteroid", "Pirate den"),
    ],
)
def test_lives_with_its_community(species, loc_type, community):
    assert species in _members(loc_type, community)


class TestWarden:
    def test_is_the_heavy_machine_of_a_lockdown(self):
        warden = enemy_by_name("Warden")
        assert not warden.organic
        assert warden.hp >= 10 and warden.defense >= 3
        assert warden.natural_weapon == "Stun Cannon"
        assert warden.min_depth >= 2
        assert warden.max_per_place == 1


class TestEchoFlitter:
    def test_is_a_harmless_flock(self):
        flitter = enemy_by_name("Echo Flitter")
        assert flitter.temperament == "skittish"
        assert flitter.group[0] >= 3


class TestRustBeetle:
    def test_is_tough_but_weak(self):
        beetle = enemy_by_name("Rust Beetle")
        assert beetle.defense >= 3 and beetle.power <= 1
        assert TEMPERAMENTS[beetle.temperament].attacks_on_sight


class TestPirateCaptain:
    def test_is_a_rare_boss_with_a_shotgun(self):
        captain = enemy_by_name("Pirate Captain")
        assert captain.max_per_place == 1
        assert captain.hp >= 10
        assert ("Shotgun", 1.0) in captain.loot_table or "Shotgun" in dict(captain.loot_table)
        assert captain.min_depth >= 1


class TestBloatGrazer:
    def test_is_docile_livestock(self):
        grazer = enemy_by_name("Bloat Grazer")
        assert grazer.temperament == "docile"
        assert "Med-kit" in dict(grazer.loot_table)


class TestColonistsDefendTheirOwn:
    def test_harming_livestock_turns_watching_colonists_hostile(self):
        engine, player = _arena()
        grazer = _spawn(engine, "Bloat Grazer", 3, 2)
        grazer.fighter.hp = grazer.fighter.max_hp = 30
        colonist = _spawn(engine, "Colonist", 8, 6)
        MeleeAction(grazer).perform(engine, player)
        assert colonist.ai_config["temperament"] == "hostile"
        assert colonist.ai_state == "hunting"

    def test_killing_a_colonist_alarms_the_others(self):
        engine, player = _arena()
        victim = _spawn(engine, "Colonist", 3, 2)
        witness = _spawn(engine, "Colonist", 9, 5)
        victim.fighter.hp = 1
        player.fighter.power = 50
        MeleeAction(victim).perform(engine, player)
        assert witness.ai_state == "hunting"

    def test_colonists_who_cannot_see_it_stay_calm(self):
        engine, player = _arena()
        engine.game_map.tiles[12, :] = engine.game_map.tiles[0, 0]  # a wall between them
        grazer = _spawn(engine, "Bloat Grazer", 3, 2)
        grazer.fighter.hp = grazer.fighter.max_hp = 30
        colonist = _spawn(engine, "Colonist", 18, 6)
        MeleeAction(grazer).perform(engine, player)
        assert colonist.ai_config["temperament"] == "territorial"

    def test_strangers_do_not_care(self):
        engine, player = _arena()
        rat = _spawn(engine, "Rat", 3, 2)
        rat.fighter.hp = rat.fighter.max_hp = 30
        colonist = _spawn(engine, "Colonist", 8, 6)
        MeleeAction(rat).perform(engine, player)
        assert colonist.ai_config["temperament"] == "territorial"

    def test_the_alarm_is_raised_aloud(self):
        engine, player = _arena()
        grazer = _spawn(engine, "Bloat Grazer", 3, 2)
        grazer.fighter.hp = grazer.fighter.max_hp = 30
        _spawn(engine, "Colonist", 8, 6)
        MeleeAction(grazer).perform(engine, player)
        assert any("Colonist" in text for text, *_ in engine.message_log.messages)

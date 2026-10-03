"""Creatures behave as their data says: temperaments, built-in weapons, immunities, death throes, glow,
disguises and chores."""

from __future__ import annotations

import random

from data.enemies import enemy_by_name
from game.actions import BumpAction, InteractAction, MeleeAction
from game.creatures import is_disguised
from game.entity import Entity, Fighter
from game.factories import build_enemy, build_item_entity
from game.helpers import chebyshev
from game.turn import advance_turn
from tests.conftest import MockEngine, make_arena
from world import tile_types


def _arena(w: int = 24, h: int = 16, player_at: tuple[int, int] = (2, 2), hp: int = 30):
    gm = make_arena(w, h)
    gm.visible[:] = True
    gm.explored[:] = True
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


def _messages(engine) -> str:
    return " ".join(text for text, *_ in engine.message_log.messages)


# ---------------------------------------------------------------------------
# Temperaments
# ---------------------------------------------------------------------------


class TestHostile:
    def test_attacks_the_player_on_sight(self):
        engine, player = _arena()
        _run(engine, _spawn(engine, "Rat", 3, 2), turns=4)
        assert player.fighter.hp < player.fighter.max_hp


class TestTerritorial:
    def test_leaves_a_peaceful_player_alone(self):
        engine, player = _arena()
        colonist = _spawn(engine, "Colonist", 3, 2)
        _run(engine, colonist, turns=10)
        assert player.fighter.hp == player.fighter.max_hp
        assert colonist.ai_state != "hunting"

    def test_fights_back_once_struck(self):
        engine, player = _arena()
        colonist = _spawn(engine, "Colonist", 3, 2)
        colonist.fighter.hp = colonist.fighter.max_hp = 30
        MeleeAction(colonist).perform(engine, player)
        assert colonist.ai_config["temperament"] == "hostile"
        assert colonist.ai_state == "hunting"
        _run(engine, colonist, turns=4)
        assert player.fighter.hp < player.fighter.max_hp

    def test_a_ranged_shot_provokes_it_too(self):
        from game.actions import RangedAction

        engine, player = _arena()
        colonist = _spawn(engine, "Colonist", 6, 2)
        colonist.fighter.hp = colonist.fighter.max_hp = 30
        blaster = build_item_entity(
            {"char": "}", "color": (1, 1, 1), "name": "Blaster", "type": "weapon", "value": 1}
            | {"weapon_class": "ranged", "range": 8, "ammo": 3, "max_ammo": 3}
        )
        player.inventory.append(blaster)
        RangedAction(colonist).perform(engine, player)
        assert colonist.ai_state == "hunting"


class TestSkittish:
    def test_flees_from_an_approaching_player(self):
        engine, player = _arena(player_at=(6, 7))
        grazer = _spawn(engine, "Lithovore", 9, 7)
        before = chebyshev(player.x, player.y, grazer.x, grazer.y)
        _run(engine, grazer, turns=8)
        assert grazer.ai_state == "fleeing"
        assert chebyshev(player.x, player.y, grazer.x, grazer.y) > before

    def test_never_bites_even_when_cornered(self):
        engine, player = _arena(w=5, h=5, player_at=(2, 2))
        grazer = _spawn(engine, "Lithovore", 1, 1)
        _run(engine, grazer, turns=10)
        assert player.fighter.hp == player.fighter.max_hp


class TestDocile:
    def test_ignores_the_player(self):
        engine, player = _arena()
        drifter = _spawn(engine, "Spore Drifter", 3, 2)
        _run(engine, drifter, turns=10)
        assert player.fighter.hp == player.fighter.max_hp
        assert drifter.ai_state == "wandering"

    def test_turns_skittish_when_hurt(self):
        engine, player = _arena()
        moth = _spawn(engine, "Glowmoth", 3, 2)
        moth.fighter.hp = moth.fighter.max_hp = 30
        MeleeAction(moth).perform(engine, player)
        assert moth.ai_config["temperament"] == "skittish"
        assert moth.ai_state == "fleeing"


class TestFriendly:
    def test_follows_the_player(self):
        engine, player = _arena(player_at=(2, 7))
        cat = _spawn(engine, "Ship's Cat", 14, 7)
        _run(engine, cat, turns=12)
        assert chebyshev(player.x, player.y, cat.x, cat.y) <= 2

    def test_never_attacks(self):
        engine, player = _arena()
        cat = _spawn(engine, "Ship's Cat", 3, 2)
        _run(engine, cat, turns=10)
        assert player.fighter.hp == player.fighter.max_hp

    def test_bumping_it_swaps_places_instead_of_attacking(self):
        engine, player = _arena()
        cat = _spawn(engine, "Ship's Cat", 3, 2)
        BumpAction(1, 0).perform(engine, player)
        assert (player.x, player.y) == (3, 2)
        assert (cat.x, cat.y) == (2, 2)
        assert cat.fighter.hp == cat.fighter.max_hp

    def test_turns_wary_when_hurt(self):
        engine, player = _arena()
        cat = _spawn(engine, "Ship's Cat", 3, 2)
        cat.fighter.hp = cat.fighter.max_hp = 30
        MeleeAction(cat).perform(engine, player)
        assert cat.ai_config["temperament"] == "skittish"


class TestProvokingAHostile:
    def test_wakes_a_sleeper(self):
        engine, player = _arena()
        drone = _spawn(engine, "Security Drone", 12, 12)
        drone.fighter.hp = drone.fighter.max_hp = 30
        assert drone.ai_state == "sleeping"
        MeleeAction(drone).perform(engine, player)
        assert drone.ai_state == "hunting"


# ---------------------------------------------------------------------------
# Built-in weapons and immobility
# ---------------------------------------------------------------------------


class TestSentryTurret:
    def test_never_moves(self):
        engine, player = _arena(player_at=(2, 7))
        turret = _spawn(engine, "Sentry Turret", 12, 7)
        _run(engine, turret, turns=12)
        assert (turret.x, turret.y) == (12, 7)

    def test_shoots_a_player_in_range(self):
        engine, player = _arena(player_at=(7, 7))
        turret = _spawn(engine, "Sentry Turret", 12, 7)
        _run(engine, turret, turns=3)
        assert player.fighter.hp < player.fighter.max_hp

    def test_never_runs_out_of_ammo(self):
        engine, player = _arena(player_at=(7, 7), hp=200)
        turret = _spawn(engine, "Sentry Turret", 12, 7)
        _run(engine, turret, turns=10)
        hp_after_ten = player.fighter.hp
        _run(engine, turret, turns=5)
        assert player.fighter.hp < hp_after_ten

    def test_is_harmless_beyond_its_range(self):
        engine, player = _arena(w=30, player_at=(2, 7))
        _run(engine, _spawn(engine, "Sentry Turret", 20, 7), turns=6)
        assert player.fighter.hp == player.fighter.max_hp

    def test_leaves_no_gun_behind(self):
        engine, player = _arena()
        turret = _spawn(engine, "Sentry Turret", 3, 2)
        turret.fighter.hp = 1
        player.fighter.power = 50
        MeleeAction(turret).perform(engine, player)
        assert turret not in engine.game_map.entities
        assert not [e for e in engine.game_map.entities if e.item and e.item.get("natural")]


class TestAcidSpitter:
    def test_spits_from_a_distance(self):
        engine, player = _arena(player_at=(5, 7))
        _run(engine, _spawn(engine, "Acid Spitter", 8, 7), turns=3)
        assert player.fighter.hp < player.fighter.max_hp
        assert "Acid Spit" in _messages(engine) or "shoots" in _messages(engine)


# ---------------------------------------------------------------------------
# Hazard immunities
# ---------------------------------------------------------------------------


def _environment_ticks(engine, creature, turns: int) -> None:
    from game.environment import apply_environment_tick_entity

    for _ in range(turns):
        if creature in engine.game_map.entities:
            apply_environment_tick_entity(engine, creature)


class TestImmunities:
    def test_vent_lurker_breathes_gas(self):
        engine, _ = _arena()
        engine.environment = {"gas": 1}
        lurker = _spawn(engine, "Vent Lurker", 10, 10)
        _environment_ticks(engine, lurker, 6)
        assert lurker.fighter.hp == lurker.fighter.max_hp

    def test_rats_do_not(self):
        engine, _ = _arena()
        engine.environment = {"gas": 1}
        rat = _spawn(engine, "Rat", 10, 10)
        _environment_ticks(engine, rat, 3)
        assert rat.fighter.hp < rat.fighter.max_hp or rat not in engine.game_map.entities

    def test_hull_mites_live_in_vacuum(self):
        engine, _ = _arena()
        engine.environment = {"vacuum": 1}
        engine.game_map.hazard_overlays["vacuum"] = engine.game_map.tiles["walkable"].copy()
        engine.game_map._hazards_dirty = False
        mite = _spawn(engine, "Hull Mite", 10, 10)
        _environment_ticks(engine, mite, 6)
        assert mite in engine.game_map.entities


# ---------------------------------------------------------------------------
# Death throes
# ---------------------------------------------------------------------------


def _kill(engine, player, creature) -> None:
    creature.fighter.hp = 1
    player.fighter.power = 50
    MeleeAction(creature).perform(engine, player)


class TestDeathEffects:
    def test_spore_drifter_bursts_on_whoever_is_next_to_it(self):
        engine, player = _arena()
        _kill(engine, player, _spawn(engine, "Spore Drifter", 3, 2))
        assert player.fighter.hp < player.fighter.max_hp
        assert "bursts in a cloud of spores" in _messages(engine)

    def test_a_drifter_shot_from_afar_hurts_nobody(self):
        engine, player = _arena()
        drifter = _spawn(engine, "Spore Drifter", 8, 8)
        drifter.fighter.hp = 0
        from game.actions import _apply_damage_and_death

        _apply_damage_and_death(engine, player, drifter, 0)
        assert player.fighter.hp == player.fighter.max_hp

    def test_breacher_charge_hits_everything_beside_it(self):
        engine, player = _arena()
        breacher = _spawn(engine, "Breacher", 3, 2)
        rat = _spawn(engine, "Rat", 4, 2)
        _kill(engine, player, breacher)
        assert player.fighter.hp <= player.fighter.max_hp - 3
        assert rat not in engine.game_map.entities
        assert "demolition charge detonates" in _messages(engine)

    def test_plain_creatures_just_die(self):
        engine, player = _arena()
        _kill(engine, player, _spawn(engine, "Rat", 3, 2))
        assert player.fighter.hp == player.fighter.max_hp


# ---------------------------------------------------------------------------
# Glow
# ---------------------------------------------------------------------------


class TestGlowmoth:
    def _dark_arena(self):
        engine, player = _arena(player_at=(1, 1))
        engine.game_map.fully_lit = False
        return engine, player

    def test_lights_up_the_dark_around_it(self):
        engine, _ = self._dark_arena()
        dark = engine.game_map.get_light_map()[10, 8].sum()
        _spawn(engine, "Glowmoth", 10, 8)
        assert engine.game_map.get_light_map()[10, 8].sum() > dark

    def test_its_light_moves_with_it(self):
        engine, _ = self._dark_arena()
        moth = _spawn(engine, "Glowmoth", 4, 8)
        engine.game_map.get_light_map()
        moth.x = 18
        light = engine.game_map.get_light_map()
        assert light[18, 8].sum() > light[4, 8].sum()

    def test_a_dead_moth_goes_dark(self):
        engine, player = self._dark_arena()
        moth = _spawn(engine, "Glowmoth", 10, 8)
        _kill(engine, player, moth)
        assert engine.game_map.get_light_map()[10, 8].sum() == 0


# ---------------------------------------------------------------------------
# Disguise
# ---------------------------------------------------------------------------


class TestScrapMimic:
    def test_passes_for_a_crate(self):
        engine, _ = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 10, 8)
        assert (mimic.char, mimic.name) == ("=", "Crate")
        assert mimic.interactable
        assert is_disguised(mimic)

    def test_reads_as_a_crate_on_the_hud_and_in_look_mode(self):
        from game.scanner import build_nearby_entries

        engine, _ = _arena()
        _spawn(engine, "Scrap Mimic", 4, 2)
        (entry,) = [e for e in build_nearby_entries(engine) if e.x == 4]
        assert entry.category == "container"
        assert "[e] to interact" in " ".join(text for text, _ in engine.game_map.describe_at(4, 2))

    def test_waits_until_someone_comes_close(self):
        engine, _ = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 12, 8)
        _run(engine, mimic, turns=8)
        assert (mimic.x, mimic.y) == (12, 8)
        assert is_disguised(mimic)

    def test_reaching_inside_springs_the_ambush(self):
        engine, player = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 3, 2)
        InteractAction(1, 0).perform(engine, player)
        assert not is_disguised(mimic)
        assert mimic.name == "Scrap Mimic"
        assert mimic.ai_state == "hunting"
        assert player.fighter.hp < player.fighter.max_hp
        assert "Crate was a Scrap Mimic" in _messages(engine)

    def test_lunges_at_a_player_who_stands_beside_it(self):
        engine, player = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 3, 2)
        _run(engine, mimic, turns=1)
        assert not is_disguised(mimic)
        assert player.fighter.hp < player.fighter.max_hp

    def test_striking_it_gives_it_away(self):
        engine, player = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 3, 2)
        mimic.fighter.hp = mimic.fighter.max_hp = 30
        BumpAction(1, 0).perform(engine, player)
        assert not is_disguised(mimic)
        assert mimic.ai_state == "hunting"

    def test_a_scan_finds_the_heartbeat(self):
        from game.scanner import perform_area_scan

        engine, player = _arena()
        mimic = _spawn(engine, "Scrap Mimic", 9, 2)
        scanner = build_item_entity(
            {"char": "]", "color": (1, 1, 1), "name": "Scanner", "type": "scanner", "value": 1}
            | {"scanner_tier": 2, "range": 10, "uses": 3}
        )
        results = perform_area_scan(engine, player, scanner=scanner)
        assert not is_disguised(mimic)
        assert any(entry.category == "creature" for entry in results.entries)
        assert player.fighter.hp == player.fighter.max_hp

    def test_is_not_offered_as_a_ranged_target_while_disguised(self):
        from game.creatures import is_target

        engine, _ = _arena()
        assert not is_target(_spawn(engine, "Scrap Mimic", 9, 2))
        assert is_target(_spawn(engine, "Rat", 9, 4))

    def test_disguise_survives_a_save(self):
        from web.save_load import _entity_from_dict, _entity_to_dict

        engine, _ = _arena()
        restored = _entity_from_dict(_entity_to_dict(_spawn(engine, "Scrap Mimic", 9, 2)))
        assert is_disguised(restored)
        assert restored.name == "Crate"
        assert restored.ai_state == "lurking"


# ---------------------------------------------------------------------------
# Chores
# ---------------------------------------------------------------------------


class TestCustodian:
    def test_welds_a_neighbouring_breach_shut(self):
        engine, _ = _arena()
        gm = engine.game_map
        gm.open_hull_breach(10, 0)
        custodian = _spawn(engine, "Custodian", 10, 1)
        _run(engine, custodian, turns=2)
        assert (10, 0) not in gm.hull_breaches
        assert int(gm.tiles["tile_id"][10, 0]) != int(tile_types.hull_breach["tile_id"])
        assert not gm.tiles["walkable"][10, 0]

    def test_closes_a_door_left_open(self):
        engine, _ = _arena()
        gm = engine.game_map
        gm.tiles[10, 9] = tile_types.door_open
        custodian = _spawn(engine, "Custodian", 10, 8)
        _run(engine, custodian, turns=2)
        assert int(gm.tiles["tile_id"][10, 9]) == int(tile_types.door_closed["tile_id"])

    def test_leaves_a_door_someone_is_standing_in(self):
        engine, player = _arena(player_at=(10, 9))
        gm = engine.game_map
        gm.tiles[10, 9] = tile_types.door_open
        custodian = _spawn(engine, "Custodian", 10, 8)
        _run(engine, custodian, turns=3)
        assert int(gm.tiles["tile_id"][10, 9]) == int(tile_types.door_open["tile_id"])

    def test_works_around_a_peaceful_player(self):
        engine, player = _arena()
        _run(engine, _spawn(engine, "Custodian", 3, 2), turns=10)
        assert player.fighter.hp == player.fighter.max_hp


# ---------------------------------------------------------------------------
# Look mode
# ---------------------------------------------------------------------------


def test_look_mode_describes_the_creature():
    engine, _ = _arena()
    _spawn(engine, "Lithovore", 6, 6)
    text = " ".join(line for line, _ in engine.game_map.describe_at(6, 6))
    assert "cracks ice for its oxygen" in text


def test_harmless_creatures_are_marked_apart_on_the_hud():
    from game.scanner import build_nearby_entries

    engine, _ = _arena()
    _spawn(engine, "Rat", 6, 2)
    _spawn(engine, "Glowmoth", 2, 6)
    categories = {entry.x: entry.category for entry in build_nearby_entries(engine)}
    assert categories[6] == "creature"
    assert categories[2] == "neutral"


def test_a_full_turn_runs_the_menagerie_without_error():
    engine, player = _arena(w=30, h=20, hp=500)
    for i, species in enumerate(
        ["Rat", "Sentry Turret", "Scrap Mimic", "Custodian", "Glowmoth", "Lithovore", "Ship's Cat", "Spore Drifter"]
    ):
        _spawn(engine, species, 4 + 3 * i, 10)
    for _ in range(15):
        advance_turn(engine)
    assert player.fighter.hp > 0

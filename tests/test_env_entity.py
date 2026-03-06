"""Tests for apply_environment_tick_entity and related edge cases."""
import pytest

from tests.conftest import make_arena, make_creature, MockEngine
from game.entity import Entity, Fighter
from game.environment import apply_environment_tick_entity
from game.suit import Suit


def _env_engine(env, creature_organic=True):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    creature = make_creature(x=3, y=3, hp=5, organic=creature_organic)
    gm.entities.append(creature)
    engine = MockEngine(gm, player, environment=env)
    return engine, creature


class TestEnvironmentEntityDamage:
    def test_vacuum_damages_organic_enemy(self):
        engine, creature = _env_engine({"vacuum": 1})
        # Set up vacuum overlay on creature's tile
        import numpy as np
        overlay = np.full((10, 10), fill_value=True, order="F")
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before - 1

    def test_vacuum_does_not_damage_non_organic(self):
        engine, creature = _env_engine({"vacuum": 1}, creature_organic=False)
        import numpy as np
        overlay = np.full((10, 10), fill_value=True, order="F")
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before

    def test_entity_killed_by_environment_removed(self):
        engine, creature = _env_engine({"vacuum": 1})
        creature.fighter.hp = 1
        import numpy as np
        overlay = np.full((10, 10), fill_value=True, order="F")
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        apply_environment_tick_entity(engine, creature)
        assert creature not in engine.game_map.entities

    def test_entity_not_on_hazard_tile_unaffected(self):
        engine, creature = _env_engine({"vacuum": 1})
        import numpy as np
        overlay = np.full((10, 10), fill_value=False, order="F")
        engine.game_map.hazard_overlays["vacuum"] = overlay
        engine.game_map._hazards_dirty = False
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before

    def test_no_environment_no_damage(self):
        engine, creature = _env_engine(None)
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before

    def test_player_is_skipped(self):
        engine, creature = _env_engine({"vacuum": 1})
        hp_before = engine.player.fighter.hp
        apply_environment_tick_entity(engine, engine.player)
        assert engine.player.fighter.hp == hp_before

    def test_low_gravity_does_not_damage(self):
        engine, creature = _env_engine({"low_gravity": 1})
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before

    def test_spatial_hazard_without_overlay_no_damage(self):
        """Vacuum is a spatial hazard; no overlay means no effect."""
        engine, creature = _env_engine({"vacuum": 1})
        engine.game_map._hazards_dirty = False
        # No overlay set — spatial hazard should not fall back to global
        hp_before = creature.fighter.hp
        apply_environment_tick_entity(engine, creature)
        assert creature.fighter.hp == hp_before

    def test_dead_entity_ignored(self):
        engine, creature = _env_engine({"vacuum": 1})
        creature.fighter.hp = 0
        apply_environment_tick_entity(engine, creature)
        # Should return without doing anything
        assert creature.fighter.hp == 0

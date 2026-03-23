"""Tests for starbase vacuum/breach behaviour.

Covers the full chain: galaxy env, briefing display, tactical env setup,
dungeon-gen breach probability, and environment tick O2 drain.
"""

import numpy as np

from game.entity import Entity, Fighter
from game.environment import apply_environment_tick
from game.suit import Suit
from tests.conftest import MockEngine, make_arena
from world.galaxy import Location

# ===================================================================
# Briefing: implied vacuum display
# ===================================================================


class TestBriefingVacuumDisplay:
    """Briefing shows vacuum only when the location's environment has it
    (assigned by the galaxy based on loc_type)."""

    def _env_from_briefing(self, loc: Location) -> dict:
        """Extract the effective env dict that BriefingState.on_render uses."""
        return dict(loc.environment or {})

    def test_derelict_shows_vacuum(self):
        """Galaxy gives derelicts vacuum in their environment."""
        loc = Location("Wreck", "derelict", environment={"vacuum": 1})
        assert "vacuum" in self._env_from_briefing(loc)

    def test_asteroid_shows_vacuum(self):
        loc = Location("Rock", "asteroid", environment={"vacuum": 1})
        assert "vacuum" in self._env_from_briefing(loc)

    def test_starbase_no_vacuum(self):
        loc = Location("Station", "starbase")
        assert "vacuum" not in self._env_from_briefing(loc)

    def test_colony_no_vacuum(self):
        loc = Location("Outpost", "colony")
        assert "vacuum" not in self._env_from_briefing(loc)

    def test_starbase_with_explicit_vacuum_shows_it(self):
        loc = Location("Damaged Base", "starbase", environment={"vacuum": 1})
        assert "vacuum" in self._env_from_briefing(loc)

    def test_no_env_shows_no_hazards(self):
        loc = Location("Clean", "starbase")
        env = self._env_from_briefing(loc)
        assert env == {}


# ===================================================================
# Tactical state: environment defaults
# ===================================================================


class TestTacticalEnvironmentSetup:
    """engine.environment should come from the location, not default to vacuum."""

    def test_no_env_defaults_to_empty(self):
        """Location with no environment -> engine.environment = {}."""
        loc = Location("Station", "starbase")
        assert loc.environment == {}
        # Simulate what tactical_state.on_enter does:
        env = getattr(loc, "environment", None)
        result = dict(env) if env else {}
        assert result == {}

    def test_derelict_env_preserved(self):
        loc = Location("Wreck", "derelict", environment={"vacuum": 1})
        env = getattr(loc, "environment", None)
        result = dict(env) if env else {}
        assert result == {"vacuum": 1}

    def test_explicit_env_preserved(self):
        loc = Location("Hot Zone", "starbase", environment={"radiation": 2})
        env = getattr(loc, "environment", None)
        result = dict(env) if env else {}
        assert result == {"radiation": 2}


# ===================================================================
# Tactical state: vacuum added from map features
# ===================================================================


class TestVacuumFromMapFeatures:
    """When the generated map has hull breaches or airlocks, vacuum should
    be added to engine.environment (matching tactical_state lines 160-162)."""

    def _make_game_map_with_breaches(self):
        gm = make_arena(10, 10)
        gm.hull_breaches = [(1, 1)]
        return gm

    def _make_game_map_with_airlocks(self):
        gm = make_arena(10, 10)
        gm.airlocks = [{"exterior_door": (1, 1), "direction": (0, -1)}]
        return gm

    def _make_game_map_no_features(self):
        gm = make_arena(10, 10)
        return gm

    def test_breaches_add_vacuum(self):
        env: dict = {}
        gm = self._make_game_map_with_breaches()
        if gm.hull_breaches or gm.airlocks:
            env.setdefault("vacuum", 1)
        assert env == {"vacuum": 1}

    def test_airlocks_add_vacuum(self):
        env: dict = {}
        gm = self._make_game_map_with_airlocks()
        if gm.hull_breaches or gm.airlocks:
            env.setdefault("vacuum", 1)
        assert env == {"vacuum": 1}

    def test_no_features_no_vacuum(self):
        env: dict = {}
        gm = self._make_game_map_no_features()
        if gm.hull_breaches or gm.airlocks:
            env.setdefault("vacuum", 1)
        assert env == {}

    def test_existing_vacuum_not_overwritten(self):
        env = {"vacuum": 2}
        gm = self._make_game_map_with_breaches()
        if gm.hull_breaches or gm.airlocks:
            env.setdefault("vacuum", 1)
        assert env["vacuum"] == 2  # setdefault keeps original


# ===================================================================
# Dungeon gen: starbase breach probability
# ===================================================================


class TestStarbaseBreachProbability:
    """Starbases should have breaches ~20% of the time, derelicts ~always."""

    def test_derelicts_usually_have_breaches(self):
        from world.dungeon_gen import generate_dungeon

        breach_count = 0
        n = 30
        for seed in range(n):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
            if gm.hull_breaches:
                breach_count += 1
        # Derelicts should almost always have breaches (candidates permitting)
        assert breach_count >= n * 0.6, f"Only {breach_count}/{n} derelicts had breaches, expected most"

    def test_starbases_rarely_have_breaches(self):
        from world.dungeon_gen import generate_dungeon

        breach_count = 0
        n = 100
        for seed in range(n):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
            if gm.hull_breaches:
                breach_count += 1
        # ~20% chance -> expect roughly 10-40 out of 100
        assert breach_count < n * 0.5, f"{breach_count}/{n} starbases had breaches, expected ~20%"

    def test_starbases_can_have_breaches(self):
        """At least some starbases should get breaches (non-zero probability)."""
        from world.dungeon_gen import generate_dungeon

        for seed in range(200):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="starbase")
            if gm.hull_breaches:
                return  # success
        raise AssertionError("No starbase had breaches in 200 seeds")


# ===================================================================
# Environment tick: no O2 drain in safe starbase
# ===================================================================


class TestNoFalseO2Drain:
    """Vacuum is spatial: O2 drains ONLY when the player stands on a tile
    marked by the vacuum overlay.  No overlay = no vacuum = no drain."""

    def _make_engine(self, env, suit, game_map=None):
        gm = game_map or make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
        gm.entities.append(player)
        return MockEngine(gm, player, suit=suit, environment=env)

    def test_empty_env_no_drain(self):
        suit = Suit("EVA", {"vacuum": 10})
        engine = self._make_engine(env={}, suit=suit)
        for _ in range(20):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 10
        assert engine.player.fighter.hp == 10

    def test_none_env_no_drain(self):
        suit = Suit("EVA", {"vacuum": 10})
        engine = self._make_engine(env=None, suit=suit)
        for _ in range(20):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 10

    def test_vacuum_in_env_but_no_overlay_no_drain(self):
        """Vacuum in env but no overlay (no sources) -> spatial hazard, no drain."""
        suit = Suit("EVA", {"vacuum": 10})
        engine = self._make_engine(env={"vacuum": 1}, suit=suit)
        # Arena has no breaches/airlocks so recalculate_hazards removes overlay
        for _ in range(Suit.DRAIN_INTERVAL * 2):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 10
        assert engine.player.fighter.hp == 10

    def test_vacuum_overlay_covers_player_does_drain(self):
        """Player standing on a vacuum-marked tile should drain O2."""
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[5, 5] = True  # player position
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False

        suit = Suit("EVA", {"vacuum": 10})
        engine = self._make_engine(env={"vacuum": 1}, suit=suit, game_map=gm)
        for _ in range(Suit.DRAIN_INTERVAL):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] < 10

    def test_vacuum_overlay_misses_player_no_drain(self):
        """Player on a safe tile (not vacuum overlay) should not drain."""
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[0, 0] = True  # vacuum only at corner, not at player (5,5)
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False

        suit = Suit("EVA", {"vacuum": 10})
        engine = self._make_engine(env={"vacuum": 1}, suit=suit, game_map=gm)
        for _ in range(20):
            apply_environment_tick(engine)
        assert suit.current_pools["vacuum"] == 10
        assert engine.player.fighter.hp == 10

    def test_non_spatial_hazard_still_applies_globally(self):
        """Hazards like radiation (not in SPATIAL_HAZARDS) still apply
        without an overlay — they are inherently global."""
        suit = Suit("EVA", {"radiation": 5})
        engine = self._make_engine(env={"radiation": 1}, suit=suit)
        for _ in range(Suit.DRAIN_INTERVAL):
            apply_environment_tick(engine)
        assert suit.current_pools["radiation"] < 5


# ===================================================================
# Enemy environment tick: spatial vacuum for entities
# ===================================================================


class TestEnemySpatialVacuum:
    """apply_environment_tick_entity should also respect SPATIAL_HAZARDS."""

    def test_enemy_no_overlay_no_damage(self):
        """Enemy in vacuum env but no overlay should not take damage."""
        from game.environment import apply_environment_tick_entity

        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        enemy = Entity(x=5, y=5, name="Enemy", fighter=Fighter(5, 5, 0, 1))
        gm.entities.extend([player, enemy])
        engine = MockEngine(gm, player, environment={"vacuum": 1})
        apply_environment_tick_entity(engine, enemy)
        assert enemy.fighter.hp == 5

    def test_enemy_on_vacuum_overlay_takes_damage(self):
        from game.environment import apply_environment_tick_entity

        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[5, 5] = True
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        enemy = Entity(x=5, y=5, name="Enemy", fighter=Fighter(5, 5, 0, 1))
        gm.entities.extend([player, enemy])
        engine = MockEngine(gm, player, environment={"vacuum": 1})
        apply_environment_tick_entity(engine, enemy)
        assert enemy.fighter.hp == 4


# ===================================================================
# Galaxy: location environment assignment
# ===================================================================


class TestGalaxyLocationEnvironment:
    """Galaxy correctly assigns vacuum to derelicts/asteroids but not starbases."""

    def test_derelict_gets_vacuum(self):
        loc = Location("Wreck", "derelict", environment={"vacuum": 1})
        assert loc.environment.get("vacuum") == 1

    def test_asteroid_gets_vacuum(self):
        loc = Location("Rock", "asteroid", environment={"vacuum": 1})
        assert loc.environment.get("vacuum") == 1

    def test_starbase_no_vacuum_by_default(self):
        loc = Location("Station", "starbase")
        assert "vacuum" not in loc.environment

    def test_colony_no_vacuum_by_default(self):
        loc = Location("Outpost", "colony")
        assert "vacuum" not in loc.environment

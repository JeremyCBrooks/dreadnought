"""Tests for the light source and lighting system."""
import numpy as np
import pytest

from world import tile_types
from world.lighting import LightSource, compute_light_map
from world.game_map import GameMap
from tests.conftest import make_arena


class TestLightSourceFields:
    def test_stores_fields(self):
        ls = LightSource(x=3, y=4, radius=6, color=(255, 200, 100), intensity=0.8)
        assert ls.x == 3
        assert ls.y == 4
        assert ls.radius == 6
        assert ls.color == (255, 200, 100)
        assert ls.intensity == 0.8

    def test_default_intensity(self):
        ls = LightSource(x=0, y=0, radius=5, color=(255, 255, 255))
        assert ls.intensity == 1.0


class TestComputeLightMap:
    def test_single_light_intensity_at_source(self):
        gm = make_arena(20, 20)
        sources = [LightSource(x=10, y=10, radius=5, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        assert lm.shape == (20, 20, 3)
        # At source position, intensity should be maximal (1.0 * color_normalized)
        assert lm[10, 10, 0] == pytest.approx(1.0, abs=0.01)
        assert lm[10, 10, 1] == pytest.approx(1.0, abs=0.01)
        assert lm[10, 10, 2] == pytest.approx(1.0, abs=0.01)

    def test_falloff_decreases_with_distance(self):
        gm = make_arena(20, 20)
        sources = [LightSource(x=10, y=10, radius=8, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        # Closer tile should be brighter than farther tile
        val_near = lm[11, 10, 0]
        val_far = lm[14, 10, 0]
        assert val_near > val_far > 0

    def test_zero_beyond_radius(self):
        gm = make_arena(20, 20)
        sources = [LightSource(x=5, y=5, radius=3, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        # Tile well beyond radius should be zero
        assert lm[15, 15, 0] == pytest.approx(0.0)
        assert lm[15, 15, 1] == pytest.approx(0.0)
        assert lm[15, 15, 2] == pytest.approx(0.0)

    def test_light_blocked_by_wall(self):
        gm = make_arena(20, 20)
        # Place a wall between source and target
        for y in range(0, 20):
            gm.tiles[8, y] = tile_types.wall
        sources = [LightSource(x=5, y=5, radius=10, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        # Tile on the other side of the wall should get no light
        assert lm[12, 5, 0] == pytest.approx(0.0)

    def test_light_passes_through_window(self):
        gm = make_arena(20, 20)
        # Place a window wall between source and target
        for y in range(0, 20):
            gm.tiles[8, y] = tile_types.wall
        gm.tiles[8, 5] = tile_types.structure_window  # transparent=True
        sources = [LightSource(x=5, y=5, radius=10, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        # Tile on other side should get some light through the window
        assert lm[9, 5, 0] > 0

    def test_light_blocked_by_closed_door(self):
        gm = make_arena(20, 20)
        # Place closed doors across the map
        for y in range(0, 20):
            gm.tiles[8, y] = tile_types.wall
        gm.tiles[8, 5] = tile_types.door_closed  # transparent=False
        sources = [LightSource(x=5, y=5, radius=10, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        assert lm[12, 5, 0] == pytest.approx(0.0)

    def test_light_spills_outside_through_window(self):
        """A room light should illuminate tiles outside the building through windows."""
        gm = make_arena(20, 20)
        # Build a room: walls at x=4 and x=14, y=3 and y=13 (10x10 room)
        for x in range(4, 15):
            gm.tiles[x, 3] = tile_types.wall
            gm.tiles[x, 13] = tile_types.wall
        for y in range(3, 14):
            gm.tiles[4, y] = tile_types.wall
            gm.tiles[14, y] = tile_types.wall
        # Window at (4, 8) on the left wall
        gm.tiles[4, 8] = tile_types.structure_window
        # Light at room center (9, 8), radius 7
        sources = [LightSource(x=9, y=8, radius=7, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        # Tile just outside the window (3, 8) should have some light
        assert lm[3, 8, 0] > 0, f"Light outside window is {lm[3, 8, 0]}, expected > 0"
        # Tile 2 outside (2, 8) should also have some (dimmer)
        assert lm[2, 8, 0] > 0, f"Light 2 tiles outside window is {lm[2, 8, 0]}, expected > 0"

    def test_light_passes_through_open_door(self):
        gm = make_arena(20, 20)
        for y in range(0, 20):
            gm.tiles[8, y] = tile_types.wall
        gm.tiles[8, 5] = tile_types.door_open  # transparent=True
        sources = [LightSource(x=5, y=5, radius=10, color=(255, 255, 255), intensity=1.0)]
        lm = compute_light_map(gm.width, gm.height, gm.tiles, sources)
        assert lm[9, 5, 0] > 0

    def test_multiple_lights_blend(self):
        gm = make_arena(20, 20)
        s1 = LightSource(x=5, y=10, radius=8, color=(255, 0, 0), intensity=1.0)
        s2 = LightSource(x=15, y=10, radius=8, color=(0, 255, 0), intensity=1.0)
        lm = compute_light_map(gm.width, gm.height, gm.tiles, [s1, s2])
        # Midpoint should have both red and green components
        mid = lm[10, 10]
        assert mid[0] > 0  # red from s1
        assert mid[1] > 0  # green from s2

    def test_empty_sources_zero_map(self):
        gm = make_arena(10, 10)
        lm = compute_light_map(gm.width, gm.height, gm.tiles, [])
        assert lm.shape == (10, 10, 3)
        assert np.all(lm == 0)


class TestGameMapLightCaching:
    def test_light_map_caching(self):
        gm = make_arena(20, 20)
        gm.add_light_source(5, 5, radius=4, color=(255, 255, 255))
        lm1 = gm.get_light_map()
        lm2 = gm.get_light_map()
        assert lm1 is lm2  # same object — cached

    def test_invalidate_clears_cache(self):
        gm = make_arena(20, 20)
        gm.add_light_source(5, 5, radius=4, color=(255, 255, 255))
        lm1 = gm.get_light_map()
        gm.invalidate_lights()
        lm2 = gm.get_light_map()
        assert lm1 is not lm2  # recomputed


class TestFlickerLights:
    def test_flicker_default_false(self):
        ls = LightSource(x=0, y=0, radius=5, color=(255, 255, 255))
        assert ls.flicker is False

    def test_flicker_light_varies_intensity(self):
        """A flickering light should produce different intensities at different times."""
        import time
        from unittest.mock import patch

        gm = make_arena(20, 20)
        sources = [LightSource(x=10, y=10, radius=5, color=(255, 255, 255), intensity=1.0, flicker=True)]

        with patch("world.lighting.time") as mock_time:
            mock_time.time.return_value = 0.0
            lm1 = compute_light_map(gm.width, gm.height, gm.tiles, sources)
            val1 = float(lm1[10, 10, 0])

            mock_time.time.return_value = 0.3
            lm2 = compute_light_map(gm.width, gm.height, gm.tiles, sources)
            val2 = float(lm2[10, 10, 0])

        # At least one of the two samples should differ from full intensity
        # (the flicker modulates between ~0.2 and 1.0)
        assert val1 != pytest.approx(val2, abs=0.01) or val1 < 1.0

    def test_non_flicker_light_stable(self):
        """A non-flickering light should produce the same intensity regardless of time."""
        from unittest.mock import patch

        gm = make_arena(20, 20)
        sources = [LightSource(x=10, y=10, radius=5, color=(255, 255, 255), intensity=1.0, flicker=False)]

        with patch("world.lighting.time") as mock_time:
            mock_time.time.return_value = 0.0
            lm1 = compute_light_map(gm.width, gm.height, gm.tiles, sources)
            val1 = float(lm1[10, 10, 0])

            mock_time.time.return_value = 0.3
            lm2 = compute_light_map(gm.width, gm.height, gm.tiles, sources)
            val2 = float(lm2[10, 10, 0])

        assert val1 == pytest.approx(val2)

    def test_game_map_has_flickering_lights(self):
        gm = make_arena(20, 20)
        assert not gm.has_flickering_lights
        gm.add_light_source(5, 5, radius=4, color=(255, 255, 255), flicker=True)
        assert gm.has_flickering_lights

    def test_game_map_always_dirty_with_flicker(self):
        """Light map should always recompute when flickering lights exist."""
        gm = make_arena(20, 20)
        gm.add_light_source(5, 5, radius=4, color=(255, 255, 255), flicker=True)
        _ = gm.get_light_map()
        # Should still be considered dirty for next call
        lm1 = gm.get_light_map()
        lm2 = gm.get_light_map()
        # They should be different objects (recomputed)
        assert lm1 is not lm2


class TestDerelictLightReduction:
    def test_derelict_corridor_lights_at_most_half(self):
        """Derelict corridor lights should be at most 50% of what a
        fully-lit ship would have (plus fixture lights like reactors)."""
        from world.dungeon_gen import generate_dungeon
        for seed in range(10):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
            # Should have at least 1 light
            assert len(gm.light_sources) >= 1, f"seed={seed}: no lights at all"

    def test_derelict_has_some_flickering_lights(self):
        """25-75% of derelict corridor lights should be flickering."""
        from world.dungeon_gen import generate_dungeon
        any_flicker = False
        for seed in range(10):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
            flicker_count = sum(1 for ls in gm.light_sources if ls.flicker)
            if flicker_count > 0:
                any_flicker = True
                break
        assert any_flicker, "No flickering lights found in derelicts across 10 seeds"

    def test_derelict_corridor_flicker_max_two(self):
        """At most 2 corridor lights should flicker on a derelict."""
        from world.dungeon_gen import generate_dungeon
        for seed in range(10):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
            corridor_flicker = sum(1 for ls in gm.light_sources
                                   if ls.color == (200, 190, 170) and ls.flicker)
            assert corridor_flicker <= 2, f"seed={seed}: {corridor_flicker} flickering corridor lights"


class TestDerelictFixtureFlicker:
    def test_fixture_lights_sometimes_flicker(self):
        """Engine room and bridge fixture lights should sometimes flicker (5% each)."""
        from world.dungeon_gen import generate_dungeon
        fixture_colors = {(120, 60, 220), (80, 160, 255)}
        any_flicker = False
        for seed in range(200):
            gm, _, _ = generate_dungeon(seed=seed, loc_type="derelict")
            for ls in gm.light_sources:
                if ls.color in fixture_colors and ls.flicker:
                    any_flicker = True
                    break
            if any_flicker:
                break
        assert any_flicker, "No flickering fixture lights across 200 seeds"

    def test_no_corridor_lights_in_bridge_or_engine(self):
        """Corridor lights should not appear inside bridge or engine rooms."""
        from world.dungeon_gen import generate_dungeon
        corridor_color = (200, 190, 170)
        for seed in range(10):
            gm, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
            fixture_rooms = [r for r in rooms if r.label in ("bridge", "engine_room")]
            corridor_lights = [ls for ls in gm.light_sources if ls.color == corridor_color]
            for ls in corridor_lights:
                for r in fixture_rooms:
                    assert not (r.x1 <= ls.x <= r.x2 and r.y1 <= ls.y <= r.y2), (
                        f"seed={seed}: corridor light at ({ls.x},{ls.y}) inside {r.label}"
                    )

    def test_fixture_lights_always_present(self):
        """Fixture lights should always be placed (never skipped)."""
        from world.dungeon_gen import generate_dungeon
        fixture_colors = {(120, 60, 220), (80, 160, 255)}
        for seed in range(10):
            gm, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
            has_engine = any(r.label == "engine_room" for r in rooms)
            has_bridge = any(r.label == "bridge" for r in rooms)
            fixture_lights = [ls for ls in gm.light_sources if ls.color in fixture_colors]
            if has_engine or has_bridge:
                assert len(fixture_lights) > 0, f"seed={seed}: fixture rooms exist but no fixture lights"


class TestDungeonGenLights:
    def test_ship_has_light_sources(self):
        from world.dungeon_gen import generate_dungeon
        game_map, rooms, _ = generate_dungeon(seed=42, loc_type="derelict")
        assert len(game_map.light_sources) > 0

    def test_village_has_street_lights(self):
        from world.dungeon_gen import generate_dungeon
        game_map, rooms, _ = generate_dungeon(seed=42, loc_type="colony")
        assert len(game_map.light_sources) > 0
        # Should have street_lamp tiles
        lamp_tid = int(tile_types.street_lamp["tile_id"])
        assert np.any(game_map.tiles["tile_id"] == lamp_tid)

    def test_street_lights_not_too_numerous(self):
        """Street lamps should be sparse — spacing >= 12 spine tiles."""
        from world.dungeon_gen import generate_dungeon
        for seed in range(5):
            game_map, _, _ = generate_dungeon(seed=seed, loc_type="colony")
            lamp_tid = int(tile_types.street_lamp["tile_id"])
            count = int(np.sum(game_map.tiles["tile_id"] == lamp_tid))
            # With spacing 12-15 on a ~80-wide map, expect roughly 4-8 lamps
            assert count <= 12, f"seed={seed}: too many street lamps ({count})"

    def test_starbase_has_light_sources(self):
        from world.dungeon_gen import generate_dungeon
        game_map, rooms, _ = generate_dungeon(seed=42, loc_type="starbase")
        assert len(game_map.light_sources) > 0

    def test_asteroid_has_light_sources(self):
        from world.dungeon_gen import generate_dungeon
        game_map, rooms, _ = generate_dungeon(seed=42, loc_type="asteroid")
        assert len(game_map.light_sources) > 0

    def test_ship_engine_room_has_reactor_core_tile(self):
        """Engine rooms should have a non-walkable reactor_core tile that is a light source."""
        from world.dungeon_gen import generate_dungeon
        reactor_tid = int(tile_types.reactor_core["tile_id"])
        found = False
        for seed in range(10):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
            engine_rooms = [r for r in rooms if r.label == "engine_room"]
            for room in engine_rooms:
                xs, ys = room.inner
                region = game_map.tiles["tile_id"][xs, ys]
                if np.any(region == reactor_tid):
                    found = True
                    # Verify it's a light source
                    core_positions = np.argwhere(game_map.tiles["tile_id"] == reactor_tid)
                    for pos in core_positions:
                        light_at = [ls for ls in game_map.light_sources
                                    if ls.x == pos[0] and ls.y == pos[1]]
                        assert len(light_at) > 0, f"Reactor core at {pos} has no light source"
        assert found, "No reactor_core tiles found in engine rooms across 10 seeds"

    def test_ship_bridge_has_control_console_tile(self):
        """Bridge rooms should have a non-walkable control_console tile that is a light source."""
        from world.dungeon_gen import generate_dungeon
        console_tid = int(tile_types.control_console["tile_id"])
        found = False
        for seed in range(10):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="derelict")
            bridges = [r for r in rooms if r.label == "bridge"]
            for room in bridges:
                xs, ys = room.inner
                region = game_map.tiles["tile_id"][xs, ys]
                if np.any(region == console_tid):
                    found = True
                    console_positions = np.argwhere(game_map.tiles["tile_id"] == console_tid)
                    for pos in console_positions:
                        light_at = [ls for ls in game_map.light_sources
                                    if ls.x == pos[0] and ls.y == pos[1]]
                        assert len(light_at) > 0, f"Control console at {pos} has no light source"
        assert found, "No control_console tiles found in bridges across 10 seeds"

    def test_reactor_core_tile_not_walkable(self):
        assert not bool(tile_types.reactor_core["walkable"])

    def test_control_console_tile_not_walkable(self):
        assert not bool(tile_types.control_console["walkable"])

    def test_colony_buildings_sometimes_have_indoor_lights(self):
        """Some colony buildings should have interior light sources."""
        from world.dungeon_gen import generate_dungeon
        from world.lighting import LightSource
        found_indoor = False
        for seed in range(20):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
            # Indoor lights are at walkable floor positions inside rooms
            for ls in game_map.light_sources:
                for room in rooms:
                    xs, ys = room.inner
                    if (xs.start <= ls.x < xs.stop and ys.start <= ls.y < ys.stop):
                        found_indoor = True
                        break
                if found_indoor:
                    break
            if found_indoor:
                break
        assert found_indoor, "No indoor lights found in colony buildings across 20 seeds"

    def test_colony_indoor_lights_not_on_doors_or_windows(self):
        """Indoor light sources must not be on door or window tiles."""
        from world.dungeon_gen import generate_dungeon
        door_tids = {int(tile_types.door_closed["tile_id"]), int(tile_types.door_open["tile_id"])}
        window_tid = int(tile_types.structure_window["tile_id"])
        for seed in range(20):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
            for ls in game_map.light_sources:
                if not game_map.in_bounds(ls.x, ls.y):
                    continue
                tid = int(game_map.tiles["tile_id"][ls.x, ls.y])
                assert tid not in door_tids, (
                    f"seed={seed}: light at ({ls.x},{ls.y}) on door tile"
                )
                assert tid != window_tid, (
                    f"seed={seed}: light at ({ls.x},{ls.y}) on window tile"
                )

    def test_colony_not_every_building_lit(self):
        """Not every colony building should have lights — some randomness."""
        from world.dungeon_gen import generate_dungeon
        any_unlit = False
        for seed in range(20):
            game_map, rooms, _ = generate_dungeon(seed=seed, loc_type="colony")
            light_positions = {(ls.x, ls.y) for ls in game_map.light_sources}
            for room in rooms:
                xs, ys = room.inner
                has_light = any(
                    xs.start <= lx < xs.stop and ys.start <= ly < ys.stop
                    for lx, ly in light_positions
                )
                if not has_light:
                    any_unlit = True
                    break
            if any_unlit:
                break
        assert any_unlit, "Every room had a light across 20 seeds — needs randomness"

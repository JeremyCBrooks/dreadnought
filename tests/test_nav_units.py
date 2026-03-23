"""Tests for navigation unit collection and installation."""

from game.entity import Entity
from game.ship import Ship
from tests.conftest import make_engine
from world.galaxy import Galaxy, Location

# ---- Galaxy assignment tests ----


class TestLocationHasNavUnit:
    def test_default_false(self):
        loc = Location("Test", "derelict")
        assert loc.has_nav_unit is False

    def test_home_system_never_has_nav_unit(self):
        """Ring 0 (home) should never contain a nav unit."""
        galaxy = Galaxy(seed=42)
        home = galaxy.systems[galaxy.home_system]
        for loc in home.locations:
            assert loc.has_nav_unit is False

    def test_at_most_one_nav_unit_per_ring(self):
        """Each ring (1-6) should have at most one nav unit."""
        galaxy = Galaxy(seed=42)
        # Expand enough systems to populate rings
        for _ in range(20):
            for name in list(galaxy.systems):
                galaxy._expand_frontier(name)

        ring_counts: dict[int, int] = {}
        for sys in galaxy.systems.values():
            ring = abs(sys.gx) + abs(sys.gy)
            for loc in sys.locations:
                if loc.has_nav_unit:
                    ring_counts[ring] = ring_counts.get(ring, 0) + 1

        for ring, count in ring_counts.items():
            assert count <= 1, f"Ring {ring} has {count} nav units"
            assert 1 <= ring <= 6, f"Nav unit found in ring {ring}"

    def test_nav_units_only_in_derelicts(self):
        """Nav units should only be assigned to derelict locations."""
        galaxy = Galaxy(seed=42)
        for _ in range(20):
            for name in list(galaxy.systems):
                galaxy._expand_frontier(name)

        for sys in galaxy.systems.values():
            for loc in sys.locations:
                if loc.has_nav_unit:
                    assert loc.loc_type == "derelict", f"{loc.name} is {loc.loc_type}, not derelict"

    def test_deterministic_assignment(self):
        """Same seed must produce same nav unit assignments."""

        def get_nav_locations(seed):
            galaxy = Galaxy(seed=seed)
            for _ in range(15):
                for name in list(galaxy.systems):
                    galaxy._expand_frontier(name)
            result = set()
            for sys in galaxy.systems.values():
                for loc in sys.locations:
                    if loc.has_nav_unit:
                        result.add(loc.name)
            return result

        a = get_nav_locations(123)
        b = get_nav_locations(123)
        assert a == b
        assert len(a) > 0  # sanity: at least one nav unit was placed


# ---- Ship counter tests ----


class TestShipNavUnits:
    def test_starts_at_zero(self):
        ship = Ship()
        assert ship.nav_units == 0


# ---- Mission exit: install nav units ----


class TestNavUnitInstallOnExit:
    def _make_nav_unit(self):
        return Entity(
            char="\u2302",
            color=(0, 255, 200),
            name="Navigation Unit",
            blocks_movement=False,
            item={"type": "nav_unit", "value": 1},
        )

    def test_nav_unit_installed_on_exit(self):
        """Nav unit items should convert to ship.nav_units on mission exit."""
        from ui.tactical_state import TacticalState

        engine = make_engine()
        engine.ship = Ship(fuel=5, max_fuel=10)
        nav = self._make_nav_unit()
        engine.player.inventory.append(nav)

        state = TacticalState.__new__(TacticalState)
        state.location = None
        state.depth = 0
        state.on_exit(engine)

        assert engine.ship.nav_units == 1
        saved_inv = engine._saved_player["inventory"]
        assert all(i.item.get("type") != "nav_unit" for i in saved_inv), "Nav unit should be removed from inventory"

    def test_multiple_nav_units_installed(self):
        """Multiple nav units should all convert."""
        from ui.tactical_state import TacticalState

        engine = make_engine()
        engine.ship = Ship(fuel=5, max_fuel=10)
        for _ in range(3):
            engine.player.inventory.append(self._make_nav_unit())

        state = TacticalState.__new__(TacticalState)
        state.location = None
        state.depth = 0
        state.on_exit(engine)

        assert engine.ship.nav_units == 3

    def test_no_ship_no_crash(self):
        """If ship is None, nav units stay in inventory without crashing."""
        from ui.tactical_state import TacticalState

        engine = make_engine()
        engine.ship = None
        nav = self._make_nav_unit()
        engine.player.inventory.append(nav)

        state = TacticalState.__new__(TacticalState)
        state.location = None
        state.depth = 0
        state.on_exit(engine)

        saved_inv = engine._saved_player["inventory"]
        assert any(i.item.get("type") == "nav_unit" for i in saved_inv)


# ---- Dungeon generation: nav unit in bridge ----


class TestNavUnitInDungeon:
    def test_has_nav_unit_parameter_accepted(self):
        """generate_dungeon should accept has_nav_unit without error."""
        from world.dungeon_gen import generate_dungeon

        game_map, rooms, exit_pos = generate_dungeon(
            width=80,
            height=50,
            seed=42,
            loc_type="derelict",
            has_nav_unit=True,
        )
        assert game_map is not None

    def test_nav_unit_placed_in_bridge(self):
        """When has_nav_unit=True, a nav unit entity should appear in the map."""
        from world.dungeon_gen import generate_dungeon

        # Try several seeds — ship gen is variable; we need one that produces a bridge
        found = False
        for seed in range(50):
            game_map, rooms, exit_pos = generate_dungeon(
                width=80,
                height=50,
                seed=seed,
                loc_type="derelict",
                has_nav_unit=True,
            )
            bridge_rooms = [r for r in rooms if r.label == "bridge"]
            if not bridge_rooms:
                continue
            nav_ents = [
                e
                for e in game_map.entities
                if e.interactable and e.interactable.get("loot") and e.interactable["loot"].get("type") == "nav_unit"
            ]
            if nav_ents:
                found = True
                break
        assert found, "No nav unit placed in bridge across 50 seeds"

    def test_no_nav_unit_when_false(self):
        """When has_nav_unit=False, no nav_unit loot should appear."""
        from world.dungeon_gen import generate_dungeon

        for seed in range(20):
            game_map, rooms, exit_pos = generate_dungeon(
                width=80,
                height=50,
                seed=seed,
                loc_type="derelict",
                has_nav_unit=False,
            )
            nav_ents = [
                e
                for e in game_map.entities
                if e.interactable and e.interactable.get("loot") and e.interactable["loot"].get("type") == "nav_unit"
            ]
            assert not nav_ents, f"Nav unit found with has_nav_unit=False (seed={seed})"

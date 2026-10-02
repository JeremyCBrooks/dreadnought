"""Tests for interdiction HUD banners (Phase 7).

Strategic view shows BEING BOARDED while interdiction is unresolved.
Tactical (ship explore) shows INTRUDERS DETECTED — N remain.
Both banners disappear after resolution.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from game.entity import Entity, Fighter
from game.interdiction import Interdiction
from game.ship import Ship
from tests.conftest import MockEngine, make_arena, make_engine
from ui.strategic_state import StrategicState


def _galaxy_with_interdiction(interdiction):
    here = SimpleNamespace(
        name="Here",
        gx=0,
        gy=0,
        locations=[],
        connections={},
        depth=0,
        star_type="yellow_dwarf",
        interdiction=interdiction,
    )
    return SimpleNamespace(
        systems={"Here": here},
        current_system="Here",
        home_system="Here",
        arrive_at=lambda name, **_: None,
        _unexplored_frontier=set(),
        travel_cost=lambda dest: 1,
        dreadnought_system=None,
        seed=1,
    )


def _strategic_engine(galaxy):
    gm = make_arena()
    player = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.ship = Ship()
    engine.galaxy = galaxy
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50
    return engine


def _capture_console_strings():
    """A console mock that records every print() call's string."""
    console = MagicMock()
    console.print_box = MagicMock()
    return console


def _printed_strings(console) -> list[str]:
    return [c.kwargs.get("string", c.args[2] if len(c.args) > 2 else "") for c in console.print.call_args_list]


# ---- Strategic banner ----


def test_strategic_banner_shown_when_interdicted():
    galaxy = _galaxy_with_interdiction(Interdiction(started=True))
    state = StrategicState(galaxy)
    engine = _strategic_engine(galaxy)
    console = _capture_console_strings()
    with patch("ui.viewport_renderer.render_viewport"):
        state.on_render(console, engine)
    strings = _printed_strings(console)
    assert any("BOARDED" in s for s in strings), f"expected BOARDED banner in strategic HUD; got {strings[:30]}"


def test_strategic_banner_hidden_when_resolved():
    galaxy = _galaxy_with_interdiction(Interdiction(started=True, resolved=True))
    state = StrategicState(galaxy)
    engine = _strategic_engine(galaxy)
    console = _capture_console_strings()
    with patch("ui.viewport_renderer.render_viewport"):
        state.on_render(console, engine)
    strings = _printed_strings(console)
    assert not any("BOARDED" in s for s in strings)


def test_strategic_banner_hidden_when_no_interdiction():
    galaxy = _galaxy_with_interdiction(None)
    state = StrategicState(galaxy)
    engine = _strategic_engine(galaxy)
    console = _capture_console_strings()
    with patch("ui.viewport_renderer.render_viewport"):
        state.on_render(console, engine)
    strings = _printed_strings(console)
    assert not any("BOARDED" in s for s in strings)


# ---- Tactical (ship explore) banner ----


def _ship_engine_with_interdiction(interdiction):
    from world.dungeon_gen import generate_player_ship

    engine = make_engine()
    ship = Ship()
    gm, rooms, exit_pos = generate_player_ship(seed=42)
    ship.game_map = gm
    ship.rooms = rooms
    ship.exit_pos = exit_pos
    engine.ship = ship
    engine.CONSOLE_WIDTH = 160
    engine.CONSOLE_HEIGHT = 50

    system = SimpleNamespace(name="TestSys", interdiction=interdiction)
    engine.galaxy = SimpleNamespace(
        systems={"TestSys": system},
        current_system="TestSys",
        seed=42,
        home_system="TestSys",
    )
    return engine


def _enter(engine):
    from ui.tactical_state import TacticalState

    state = TacticalState(explore_ship=True)
    with patch.object(engine.ship.game_map, "update_fov"):
        state.on_enter(engine)
    return state


def test_tactical_banner_shows_pirate_count():
    engine = _ship_engine_with_interdiction(Interdiction())
    state = _enter(engine)
    interdiction = engine.galaxy.systems["TestSys"].interdiction
    pirate_count = interdiction.alive_pirate_count()

    console = _capture_console_strings()
    with patch.object(engine.game_map, "render"), patch("ui.viewport_renderer.render_map_starfield"):
        state.on_render(console, engine)
    strings = _printed_strings(console)
    assert any("INTRUDERS" in s for s in strings), f"expected INTRUDERS banner in tactical HUD; got {strings[:30]}"
    # Pirate count appears in some banner string.
    assert any(str(pirate_count) in s and "INTRUDERS" in s for s in strings), (
        f"expected pirate count {pirate_count} in INTRUDERS banner"
    )


def test_tactical_banner_hidden_after_resolution():
    engine = _ship_engine_with_interdiction(Interdiction())
    state = _enter(engine)
    interdiction = engine.galaxy.systems["TestSys"].interdiction
    # Kill all pirates and resolve
    for p in interdiction.pirate_entities:
        p.fighter.hp = 0
    state._after_player_turn(engine)
    assert interdiction.resolved is True

    console = _capture_console_strings()
    with patch.object(engine.game_map, "render"), patch("ui.viewport_renderer.render_map_starfield"):
        state.on_render(console, engine)
    strings = _printed_strings(console)
    assert not any("INTRUDERS" in s for s in strings), f"banner should be gone after resolution; got {strings[:30]}"

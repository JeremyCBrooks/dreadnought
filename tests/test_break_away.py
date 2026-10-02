"""Breaking away from a hard-docked pirate ship: confirm prompt, costs, and travel."""

from __future__ import annotations

from types import SimpleNamespace

import tcod.event

from engine.game_state import Engine
from game.entity import Entity
from game.interdiction import BREAK_AWAY_HULL_DAMAGE, Interdiction
from game.ship import Ship
from tests.conftest import FakeEvent, force_rng, make_arena
from ui.break_away_state import BreakAwayState
from ui.game_over_state import GameOverState
from ui.strategic_state import StrategicState

K = tcod.event.KeySym
TRAVEL_COST = 2


def _system(name: str, gx: int, neighbour: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        gx=gx,
        gy=0,
        locations=[],
        connections={neighbour: 30},
        depth=gx,
        star_type="yellow_dwarf",
        interdiction=None,
    )


def _interdicted_game(fuel: int = 5) -> tuple[Engine, StrategicState, Interdiction]:
    """A real engine on the star map of 'Here', hard-docked, with 'There' to the east."""
    arrivals: list[tuple[str, dict]] = []
    galaxy = SimpleNamespace(
        systems={"Here": _system("Here", 0, "There"), "There": _system("There", 1, "Here")},
        current_system="Here",
        home_system="Home",
        arrive_at=lambda name, **kwargs: arrivals.append((name, kwargs)),
        travel_cost=lambda dest: TRAVEL_COST,
        dreadnought_system=None,
        seed=42,
        arrivals=arrivals,
    )
    interdiction = Interdiction(started=True)
    galaxy.systems["Here"].interdiction = interdiction

    engine = Engine()
    engine.galaxy = galaxy
    engine.ship = Ship(fuel=fuel, max_fuel=10)
    strategic = StrategicState(galaxy)
    engine.push_state(strategic)
    strategic.ev_key(engine, FakeEvent(K.TAB))  # navigation focus
    return engine, strategic, interdiction


def _cargo(name: str = "Crate", item_type: str = "heal") -> Entity:
    return Entity(name=name, blocks_movement=False, item={"type": item_type, "value": 1})


def _navigate_east(engine: Engine) -> None:
    engine.current_state.ev_key(engine, FakeEvent(K.RIGHT))


def _texts(engine: Engine) -> list[str]:
    return [text for text, _ in engine.message_log.messages]


def _prompt_text(engine: Engine) -> str:
    return " ".join(text for text, _ in engine.current_state.body(engine))


# ---- The prompt ----


def test_navigating_while_hard_docked_asks_before_doing_anything():
    engine, _, interdiction = _interdicted_game()

    _navigate_east(engine)

    assert isinstance(engine.current_state, BreakAwayState)
    assert engine.galaxy.current_system == "Here"
    assert engine.ship.fuel == 5
    assert engine.ship.hull == 10
    assert interdiction.resolved is False


def test_declining_leaves_everything_as_it_was():
    for key in (K.N, K.ESCAPE):
        engine, strategic, interdiction = _interdicted_game()
        _navigate_east(engine)

        engine.current_state.ev_key(engine, FakeEvent(key))

        assert engine.current_state is strategic
        assert engine.galaxy.current_system == "Here"
        assert engine.ship.fuel == 5
        assert engine.ship.hull == 10
        assert interdiction.resolved is False


def test_other_keys_do_not_break_away():
    engine, _, interdiction = _interdicted_game()
    _navigate_east(engine)

    consumed = engine.current_state.ev_key(engine, FakeEvent(K.RIGHT))

    assert consumed is True
    assert isinstance(engine.current_state, BreakAwayState)
    assert interdiction.resolved is False


def test_prompt_names_the_destination_and_the_hull_cost():
    engine, _, _ = _interdicted_game()
    _navigate_east(engine)

    text = _prompt_text(engine)

    assert "There" in text
    assert f"-{BREAK_AWAY_HULL_DAMAGE}" in text
    assert f"{10 - BREAK_AWAY_HULL_DAMAGE}/10" in text
    assert "destroy" not in text.lower()
    assert "Dreadnought" not in text


def test_prompt_warns_when_breaking_away_would_destroy_the_ship():
    engine, _, _ = _interdicted_game()
    engine.ship.hull = BREAK_AWAY_HULL_DAMAGE
    _navigate_east(engine)

    assert "destroy" in _prompt_text(engine).lower()


def test_prompt_warns_when_the_dreadnought_core_is_aboard():
    engine, _, _ = _interdicted_game()
    engine.ship.add_cargo(_cargo("Dreadnought Core", "dreadnought_core"))
    _navigate_east(engine)

    assert "Dreadnought" in _prompt_text(engine)


def test_prompt_draws_its_title_warning_and_both_choices_inside_the_box():
    from unittest.mock import MagicMock, patch

    engine, _, _ = _interdicted_game()
    _navigate_east(engine)
    console = MagicMock()

    with patch("ui.viewport_renderer.render_viewport"):
        engine.current_state.on_render(console, engine)

    box_x, _, box_w, _ = console.draw_rect.call_args.args
    printed = {c.kwargs["string"]: c.kwargs["x"] for c in console.print.call_args_list}
    for line in ("HARD-DOCKED", "[Y] Break away", "[N] No, stay", *(t for t, _ in engine.current_state.body(engine))):
        assert line in printed
        assert box_x < printed[line] and printed[line] + len(line) < box_x + box_w


def test_no_prompt_when_the_jump_is_unaffordable():
    engine, strategic, interdiction = _interdicted_game(fuel=TRAVEL_COST - 1)

    _navigate_east(engine)

    assert engine.current_state is strategic
    assert "Not enough fuel." in _texts(engine)
    assert interdiction.resolved is False


def test_no_prompt_once_the_interdiction_is_resolved():
    engine, strategic, interdiction = _interdicted_game()
    interdiction.resolved = True

    _navigate_east(engine)

    assert engine.current_state is strategic
    assert engine.galaxy.current_system == "There"
    assert engine.ship.hull == 10


# ---- Breaking away ----


def _break_away(engine: Engine) -> None:
    _navigate_east(engine)
    engine.current_state.ev_key(engine, FakeEvent(K.Y))


def test_breaking_away_travels_to_the_chosen_system_for_normal_fuel():
    engine, strategic, _ = _interdicted_game()

    _break_away(engine)

    assert engine.current_state is strategic
    assert engine.galaxy.current_system == "There"
    assert engine.ship.fuel == 5 - TRAVEL_COST


def test_breaking_away_damages_the_hull():
    engine, _, _ = _interdicted_game()

    _break_away(engine)

    assert engine.ship.hull == 10 - BREAK_AWAY_HULL_DAMAGE


def test_breaking_away_resolves_the_interdiction_and_restores_the_ship_map():
    engine, _, interdiction = _interdicted_game()
    original_map = make_arena()
    engine.ship.game_map = make_arena()  # stands in for the composite
    interdiction.original_ship_map = original_map

    _break_away(engine)

    assert interdiction.resolved is True
    assert engine.ship.game_map is original_map


def test_breaking_away_can_rip_a_cargo_item_loose():
    engine, _, _ = _interdicted_game()
    engine.ship.add_cargo(_cargo())
    force_rng(engine, 0.0)  # below the cargo-loss chance

    _break_away(engine)

    assert engine.ship.cargo == []
    assert any("Crate" in text for text in _texts(engine))


def test_breaking_away_can_keep_the_cargo():
    engine, _, _ = _interdicted_game()
    crate = _cargo()
    engine.ship.add_cargo(crate)
    force_rng(engine, 0.99)  # above the cargo-loss chance

    _break_away(engine)

    assert engine.ship.cargo == [crate]


def test_arrival_after_breaking_away_is_not_interdicted_again():
    engine, _, _ = _interdicted_game()
    engine.ship.add_cargo(_cargo())

    _break_away(engine)

    assert engine.galaxy.arrivals == [("There", {})]


def test_breaking_away_on_a_weak_hull_destroys_the_ship():
    engine, _, _ = _interdicted_game()
    engine.ship.hull = BREAK_AWAY_HULL_DAMAGE

    _break_away(engine)

    assert engine.ship.hull == 0
    assert isinstance(engine.current_state, GameOverState)
    assert engine.current_state.title == "SHIP DESTROYED"
    assert engine.galaxy.current_system == "Here"


def test_losing_the_dreadnought_core_ends_the_game():
    engine, _, _ = _interdicted_game()
    engine.ship.add_cargo(_cargo("Dreadnought Core", "dreadnought_core"))
    force_rng(engine, 0.0)

    _break_away(engine)

    assert isinstance(engine.current_state, GameOverState)
    assert engine.current_state.title == "THE CORE IS LOST"


# ---- Out-of-fuel drift is unchanged ----


def test_drift_at_zero_fuel_still_tears_free_without_a_prompt():
    engine, strategic, interdiction = _interdicted_game(fuel=0)

    _navigate_east(engine)

    assert engine.current_state is strategic
    assert engine.galaxy.current_system == "There"
    assert interdiction.resolved is True
    assert "The boarding craft tears free as you drift!" in _texts(engine)

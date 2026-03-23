"""Tests for BriefingState."""

from engine.game_state import Engine, State
from game.ship import Ship
from game.suit import EVA_SUIT
from ui.briefing_state import BriefingState, _threat_level, _threat_score
from world.galaxy import Location


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _make_engine():
    engine = Engine()
    engine.ship = Ship()
    engine.suit = EVA_SUIT.copy()
    return engine


def test_threat_level_low_no_hazards():
    assert _threat_level(None, depth=0) == "LOW"
    assert _threat_level({}, depth=1) == "LOW"


def test_threat_level_low_mild_hazard():
    assert _threat_level({"vacuum": 1}, depth=0) == "LOW"


def test_threat_level_moderate():
    assert _threat_level({"vacuum": 1}, depth=1) == "MODERATE"
    assert _threat_level({"radiation": 2}, depth=0) == "MODERATE"


def test_threat_level_high():
    assert _threat_level({"radiation": 2}, depth=2) == "HIGH"
    assert _threat_level({"vacuum": 1, "radiation": 2}, depth=2) == "HIGH"


def test_threat_score_sums_severity_and_depth():
    assert _threat_score(None, 0) == 0
    assert _threat_score({"vacuum": 1}, 0) == 1
    assert _threat_score({"vacuum": 1, "radiation": 2}, 1) == 4


def test_briefing_esc_pops():
    import tcod.event

    engine = _make_engine()
    engine.push_state(State())  # base state
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.ESCAPE))
    assert engine.current_state is not briefing


def test_briefing_enter_switches_to_tactical():
    import tcod.event

    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=1)
    engine.push_state(briefing)
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.RETURN))
    from ui.tactical_state import TacticalState

    assert isinstance(engine.current_state, TacticalState)


def test_briefing_suit_navigation():
    import tcod.event

    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    assert briefing._suit_index == 0
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert briefing._suit_index == 1
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.UP))
    assert briefing._suit_index == 0


def test_briefing_confirm_sets_suit():
    import tcod.event

    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.DOWN))
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.RETURN))
    assert engine.suit.name == "Hazard Suit"


def test_briefing_stores_location():
    loc = Location("Alpha Station", "starbase", environment={"radiation": 2})
    briefing = BriefingState(loc, depth=2)
    assert briefing.location is loc
    assert briefing.depth == 2


def test_briefing_c_opens_cargo():
    import tcod.event

    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.c))
    from ui.cargo_state import CargoState

    assert isinstance(engine.current_state, CargoState)


def test_briefing_on_enter_remembers_suit():
    """on_enter restores suit_index when engine already has a matching suit."""
    engine = _make_engine()
    from game.suit import HAZARD_SUIT

    engine.suit = HAZARD_SUIT.copy()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    assert briefing._suit_index == 1


def test_briefing_suit_navigation_clamps():
    """UP at 0 stays at 0; DOWN at max stays at max."""
    import tcod.event

    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    # Already at 0, pressing UP should stay at 0
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.UP))
    assert briefing._suit_index == 0
    # Move to last suit
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert briefing._suit_index == 1
    # DOWN again should stay clamped
    briefing.ev_key(engine, FakeEvent(tcod.event.KeySym.DOWN))
    assert briefing._suit_index == 1


def test_briefing_on_enter_resets_mission_loadout():
    """on_enter clears mission_loadout."""
    engine = _make_engine()
    engine.mission_loadout = ["dummy"]
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=0)
    engine.push_state(briefing)
    assert engine.mission_loadout == []

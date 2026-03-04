"""Tests for BriefingState."""
from engine.game_state import Engine, State
from game.ship import Ship
from game.suit import EVA_SUIT
from world.galaxy import Location
from ui.briefing_state import BriefingState, _threat_level, _threat_score


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _make_engine():
    engine = Engine()
    engine.ship = Ship()
    engine.suit = EVA_SUIT
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
    briefing.ev_keydown(engine, FakeEvent(tcod.event.KeySym.ESCAPE))
    assert engine.current_state is not briefing


def test_briefing_enter_switches_to_loadout():
    import tcod.event
    engine = _make_engine()
    loc = Location("Test Station", "derelict")
    briefing = BriefingState(loc, depth=1)
    engine.push_state(briefing)
    briefing.ev_keydown(engine, FakeEvent(tcod.event.KeySym.RETURN))
    from ui.loadout_state import LoadoutState
    assert isinstance(engine.current_state, LoadoutState)
    assert engine.current_state.location is loc
    assert engine.current_state.depth == 1


def test_briefing_stores_location():
    loc = Location("Alpha Station", "starbase", environment={"radiation": 2})
    briefing = BriefingState(loc, depth=2)
    assert briefing.location is loc
    assert briefing.depth == 2

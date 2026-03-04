"""Tests for ranged weapon UI enhancements in the tactical stats panel."""
from types import SimpleNamespace

from game.entity import Entity, Fighter
from game.loadout import Loadout
from tests.conftest import make_engine
from ui.tactical_state import TacticalState, CTRL_LINES


def _ranged_weapon(ammo=15, max_ammo=20, range_=5, value=3):
    return Entity(
        name="Blaster",
        item={
            "type": "weapon", "weapon_class": "ranged",
            "value": value, "range": range_, "ammo": ammo, "max_ammo": max_ammo,
        },
    )


def _mock_console():
    """Console that records all print calls."""
    calls = []

    class Console:
        def print(self, *, x, y, string, fg=(255, 255, 255)):
            calls.append({"x": x, "y": y, "string": string, "fg": fg})

    return Console(), calls


def _make_layout(stats_x=60, stats_w=20, viewport_h=50):
    return SimpleNamespace(stats_x=stats_x, stats_w=stats_w, viewport_h=viewport_h)


def _find_print(calls, substring):
    """Return first call whose string contains *substring*, or None."""
    for c in calls:
        if substring in c["string"]:
            return c
    return None


# --- Weapon / ammo display ---

def test_stats_show_equipped_ranged_weapon():
    engine = make_engine()
    engine.player.loadout = Loadout(weapon=_ranged_weapon(ammo=15, max_ammo=20))
    state = TacticalState()
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    hit = _find_print(calls, "WPN:")
    assert hit is not None
    assert "Blaster" in hit["string"]
    assert "15/20" in hit["string"]


def test_stats_no_ranged_weapon():
    engine = make_engine()
    state = TacticalState()
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    hit = _find_print(calls, "WPN:")
    assert hit is not None
    assert "--" in hit["string"]


# --- Ground text header ---

def test_targeting_header():
    engine = make_engine()
    engine.player.loadout = Loadout(weapon=_ranged_weapon())
    state = TacticalState()
    state._ranged_cursor = (7, 5)
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    hit = _find_print(calls, "TARGETING:")
    # The ground header should be "TARGETING:" (not underfoot or looking)
    headers = [c for c in calls if c["string"] == "TARGETING:"]
    assert len(headers) >= 1
    # And the color should be red-ish
    assert headers[0]["fg"] == (255, 100, 100)


def test_look_header():
    engine = make_engine()
    state = TacticalState()
    state._look_cursor = (6, 5)
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    headers = [c for c in calls if c["string"] == "LOOKING AT:"]
    assert len(headers) == 1


def test_underfoot_header():
    engine = make_engine()
    state = TacticalState()
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    headers = [c for c in calls if c["string"] == "UNDERFOOT:"]
    assert len(headers) == 1


# --- Distance / range display in controls ---

def test_targeting_distance_display():
    engine = make_engine()
    engine.player.loadout = Loadout(weapon=_ranged_weapon(range_=5))
    state = TacticalState()
    # Player at (5,5), cursor at (8,5) -> Chebyshev distance = 3
    state._ranged_cursor = (8, 5)
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    hit = _find_print(calls, "TARGETING: 3/5")
    assert hit is not None
    # In range -> green
    assert hit["fg"] == (100, 255, 100)


def test_targeting_out_of_range_color():
    engine = make_engine()
    engine.player.loadout = Loadout(weapon=_ranged_weapon(range_=2))
    state = TacticalState()
    # Player at (5,5), cursor at (8,5) -> distance = 3, range = 2 -> out of range
    state._ranged_cursor = (8, 5)
    console, calls = _mock_console()
    layout = _make_layout()
    state._render_stats(console, engine, layout)
    hit = _find_print(calls, "TARGETING: 3/2")
    assert hit is not None
    # Out of range -> red
    assert hit["fg"] == (255, 100, 100)

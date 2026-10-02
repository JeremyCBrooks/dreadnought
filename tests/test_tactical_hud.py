"""The tactical stats panel renders from a plain view object, without a TacticalState."""

import tcod.console

from engine.game_state import Engine
from tests.conftest import enter_mission, new_game
from ui.tactical_hud import HudView, render_stats
from ui.tactical_state import _layout


def _row_text(console, y: int, x0: int) -> str:
    return "".join(chr(int(ch)) for ch in console.rgb["ch"][x0:, y]).rstrip()


def _rendered(view_overrides: dict | None = None):
    engine, _ = new_game()
    state = enter_mission(engine)
    layout = _layout(engine)
    console = tcod.console.Console(Engine.CONSOLE_WIDTH, Engine.CONSOLE_HEIGHT, order="F")
    view = HudView(
        location_label="Somewhere (colony)",
        explore_ship=False,
        look_cursor=None,
        ranged_cursor=None,
        ground_lines=[("Dusty ground.", (140, 140, 160))],
    )
    for key, value in (view_overrides or {}).items():
        setattr(view, key, value)
    render_stats(console, engine, layout, view)
    return console, layout, state


def test_panel_shows_location_and_vitals():
    console, layout, _ = _rendered()
    x = layout.stats_x + 1

    assert _row_text(console, 1, x) == "Somewhere (colony)"
    assert _row_text(console, 4, x) == "HP: 10/10"
    assert _row_text(console, 6, x) == "POW: 1"


def test_panel_shows_the_ground_text_under_its_header():
    console, layout, _ = _rendered()
    x = layout.stats_x + 1
    rows = [_row_text(console, y, x) for y in range(layout.viewport_h)]

    header = rows.index("UNDERFOOT:")
    assert rows[header + 1] == "Dusty ground."


def test_look_mode_changes_the_ground_header():
    console, layout, _ = _rendered({"look_cursor": (1, 1)})
    x = layout.stats_x + 1

    assert "LOOKING AT:" in [_row_text(console, y, x) for y in range(layout.viewport_h)]

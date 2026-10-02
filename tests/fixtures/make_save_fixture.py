"""Writes save_before_refactor.json: a real save from a played game.

Run ONCE, on the code as it stands before the DRY/SOLID refactor. Never
regenerate it afterwards: its whole value is that older code wrote it.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import debug  # noqa: E402

debug.GOD_MODE = False
debug.MAX_NAV_UNITS = None
debug.START_INVENTORY = []

from tests.conftest import (  # noqa: E402
    FakeEvent,
    enter_mission,
    free_step_from,
    key_for,
    make_heal_item,
    make_melee_weapon,
    new_game,
)
from web.save_load import engine_to_dict  # noqa: E402

engine, strategic = new_game(seed=1)
engine.mission_loadout = [make_melee_weapon(), make_heal_item()]
state = enter_mission(engine)
ex, ey = state.exit_pos
dx, dy = free_step_from(engine, ex, ey)
state.ev_key(engine, FakeEvent(key_for((dx, dy))))
state.ev_key(engine, FakeEvent(key_for((-dx, -dy))))
assert engine.current_state is strategic, "the mission should have ended at the exit"
engine.saved_player["hp"] = 7

strategic.focus = "navigation"
direction = next(iter(strategic._connection_by_direction()))
strategic.ev_key(engine, FakeEvent(key_for(direction)))
assert engine.galaxy.current_system != engine.galaxy.home_system

out = Path(__file__).with_name("save_before_refactor.json")
out.write_text(json.dumps(engine_to_dict(engine), indent=1), encoding="utf-8")
print(f"wrote {out}")

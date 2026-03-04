## Dreadnought Roguelike (Vertical Slice)

Python + `python-tcod` roguelike prototype. Classic ASCII, FOV shadowcast, room-and-corridor dungeons, turn-based combat.

### Setup (uv + venv + requirements.txt)

```powershell
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

### Run the game

```powershell
.\.venv\Scripts\python.exe main.py
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

### Project structure

```
main.py                 Entry point
engine/
  game_state.py         State machine (push/pop/switch) + Engine
  message_log.py        Scrollable message log
  font.py               Tileset loading (optional custom font)
game/
  entity.py             Entity + Fighter component
  actions.py            Action classes (move, bump, melee, pickup, drop)
  ai.py                 HostileAI (chase + attack)
world/
  tile_types.py         Numpy tile dtypes (floor, wall, exit)
  game_map.py           GameMap with FOV, rendering, entity tracking
  dungeon_gen.py        Room-and-corridor procedural generation
  galaxy.py             Galaxy / StarSystem / Location (strategic layer)
ui/
  title_state.py        Title screen
  tactical_state.py     Dungeon exploration (the core gameplay)
  strategic_state.py    Star system navigation UI
  inventory_state.py    Inventory overlay
  game_over_state.py    Death / victory screen
tests/                  pytest test suite (37 tests)
```

### Controls (tactical mode)

| Key | Action |
|---|---|
| Arrows / vi keys (hjklyubn) / numpad | Move (8-directional) |
| `.` or numpad 5 | Wait |
| `g` or `,` | Pick up item |
| `x` | Look mode (cursor inspect tiles/entities) |
| `i` | Open inventory |
| `PgUp` / `PgDn` | Scroll message log |
| `Esc` | (title: quit, tactical: no-op) |

### Game flow

**Title** -- press any key --> **Strategic** (star system, pick a location) -- Enter --> **Tactical** (dungeon: explore, fight, loot) -- reach exit `>` --> back to **Strategic**.

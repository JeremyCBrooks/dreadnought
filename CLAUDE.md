# Dreadnought - Project Guide

Follow TDD, DRY and Pythonic conventions.
Use uv and .venv for python commands.
Be data driven and prefer abstractions.

## What is this?
A sci-fi roguelike built with Python and python-tcod. Vertical slice featuring dungeon exploration, turn-based combat, environmental hazards, and a strategic galaxy layer.

## Commands
- **Run**: `python main.py` (from project root, requires `.venv` activated)
- **Tests**: `pytest` or `pytest tests/`
- **Install deps**: `uv pip install -r requirements.txt`
- **Virtual env**: `.venv` managed with `uv`

## Architecture

### State machine
`Engine` owns a state stack. States are pushed/popped/switched:
```
TitleState -> StrategicState -> TacticalState (push)
                             <- TacticalState (pop)
TacticalState -> GameOverState (switch, on death)
```

### Module layout
- `engine/` - Engine (state machine + shared game state), MessageLog, font loading
- `game/` - Entity/Fighter components, Action classes, AI, Suit, hazards/environment
- `world/` - Tile types (numpy structured arrays), GameMap (FOV, rendering), dungeon generation, Galaxy
- `ui/` - State subclasses for each screen (title, strategic, tactical, inventory, game over)
- `tests/` - pytest suite with fixtures in `conftest.py`

### Entity model
Bag-of-components on a single `Entity` class. Optional fields: `fighter`, `ai`, `item` (dict), `interactable` (dict), `inventory` (list).

### Turn flow (tactical)
Player action -> environment tick -> hazard tick -> enemy AI turns -> death check

### Dungeon generation
Seeded room-and-corridor algorithm. Seed is MD5 of `"{location_name}_{depth}"`. Areas cached on `engine.area_cache` keyed by `(location_name, depth)`.

## Conventions
- Lazy-import `tcod` inside methods (not at module top level) to keep modules testable without a display
- `TYPE_CHECKING` guards for type-hint-only imports
- Colors are `Tuple[int, int, int]` RGB throughout
- Console order is `"F"` (Fortran/column-major) matching numpy tile arrays
- Actions follow the command pattern: subclass `Action`, implement `perform(engine, entity)`
- Tests use either the `engine` fixture from `conftest.py` or lightweight `MockEngine`/`FakeEngine` stubs

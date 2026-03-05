# Dreadnought - Project Guide

Follow TDD, DRY and Pythonic conventions.
When fixing bugs or implementing new features, always first write and execute tests that accurately assert how the feature should and should NOT work. Only after the correct test cases are in place should you write the implementation and/or fix.
Use uv and .venv for python commands.
Be data driven and prefer abstractions.

## What is this?
A sci-fi roguelike built with Python and python-tcod. Vertical slice featuring dungeon exploration, turn-based combat, environmental hazards, and a strategic galaxy layer.

## Commands
- **Run**: `python main.py` (from project root, requires `.venv` activated)
- **Tests**: `pytest` or `pytest tests/`
- **Install deps**: `uv pip install -r requirements.txt`
- **Virtual env**: `.venv` managed with `uv`

## Conventions
- Lazy-import `tcod` inside methods (not at module top level) to keep modules testable without a display
- `TYPE_CHECKING` guards for type-hint-only imports
- Colors are `Tuple[int, int, int]` RGB throughout
- Console order is `"F"` (Fortran/column-major) matching numpy tile arrays

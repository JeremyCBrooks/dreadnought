# Dreadnought - Project Guide

Follow TDD, DRY and Pythonic conventions.

When fixing bugs or implementing new features, always first write and execute tests that accurately assert how the feature should and should NOT work. Only after the correct test cases are in place should you write the implementation and/or fix.
Use uv and .venv for python commands. Make sure venv is active before running python.

Write clean, production-ready, idiomatic Python 3.12+ code that follows PEP 8 conventions. Use modern typing syntax, keep the code clean and readable, and ensure it passes ruff check and ruff format. The code should run in a uv-managed project using pyproject.toml.

Be data driven and prefer abstractions.

## What is this?
A sci-fi roguelike built with Python and python-tcod. Features dungeon exploration, turn-based combat, environmental hazards, and a strategic galaxy layer.

## Commands
- **Run**: `python main.py` (from project root, requires `.venv` activated)
- **Tests**: `pytest`
- **Install deps**: `uv pip install -e ".[dev]"` (requires `.venv` activated)
- **Virtual env**: `.venv` managed with `uv`

This is a Windows system with a cygwin bash shell available at `F:\software\Tools\cygwin64\bin\bash.exe`. Use Powershell or bash as needed.
`ruff` is available here: `C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe`

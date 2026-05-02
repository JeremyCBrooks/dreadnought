# Test Suite Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce suite runtime and remove low-value tests without losing real coverage.

**Architecture:** Three focused tasks — share the expensive galaxy expansion across tests via a module-scoped fixture + per-test deepcopy; remove two pairs of identical dungeon-gen crash tests; scan all test files for performative patterns and remove confirmed low-value tests.

**Tech Stack:** pytest fixtures (`scope="module"`), `copy.deepcopy`, grep

---

## File Map

| File | Action |
|---|---|
| `tests/test_dreadnought_spawn.py` | Add module-scoped fixture, replace per-test galaxy builds with fixture |
| `tests/test_dungeon_gen.py` | Remove 2 duplicate crash tests |
| All `tests/*.py` | Pattern scan, targeted removal of performative tests |

---

## Task 1: Share expanded galaxy across dreadnought spawn tests

**Problem:** `TestSpawnDreadnought` (10 tests) and `TestDreadnoughtTrigger` (2 tests) each independently call `Galaxy(seed=42)` + `_expand_all(galaxy)`. Each expansion takes ~13s. Fix: expand once per module, deepcopy for each test.

**Files:**
- Modify: `tests/test_dreadnought_spawn.py`

- [ ] **Step 1: Verify current timing**

```
cd F:\dev\gamedev\dreadnought && .venv/Scripts/pytest tests/test_dreadnought_spawn.py -v --tb=short 2>&1 | tail -20
```

Note the total time. This is the baseline to beat.

- [ ] **Step 2: Add imports at top of `tests/test_dreadnought_spawn.py`**

The current imports block starts at line 1. Add `import copy` and `import pytest` after the existing imports:

```python
"""Tests for Dreadnought spawning, core item, and victory mechanics."""

import copy

import pytest
from collections import deque

from engine.game_state import Engine
from game.entity import Entity, Fighter
from game.ship import Ship
from world.galaxy import DREADNOUGHT_LOCATION_NAME, DREADNOUGHT_SYSTEM_NAME, Galaxy
```

- [ ] **Step 3: Add the two fixtures immediately after the helpers block (before `class TestSpawnDreadnought`)**

Insert after the `_make_engine_with_galaxy` function (around line 44), before the first class:

```python
# ---------------------------------------------------------------------------
# Shared galaxy fixture — expands once per module, per-test deepcopy for isolation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _galaxy_42_template():
    """Build and fully expand Galaxy(seed=42) once. Never mutate this directly."""
    g = Galaxy(seed=42)
    _expand_all(g)
    return g


@pytest.fixture
def expanded_galaxy(_galaxy_42_template):
    """Per-test isolated copy of the pre-expanded galaxy."""
    return copy.deepcopy(_galaxy_42_template)
```

- [ ] **Step 4: Update all 9 seed-42 tests in `TestSpawnDreadnought` to use the fixture**

For each test method listed below, add `expanded_galaxy` as a parameter and replace the two-line galaxy setup with `galaxy = expanded_galaxy`.

**`test_spawn_creates_system`** — current lines 53–57:
```python
def test_spawn_creates_system(self, expanded_galaxy):
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    assert DREADNOUGHT_SYSTEM_NAME in galaxy.systems
```

**`test_spawn_single_derelict_location`** — current lines 59–66:
```python
def test_spawn_single_derelict_location(self, expanded_galaxy):
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    sys = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
    assert len(sys.locations) == 1
    loc = sys.locations[0]
    assert loc.name == DREADNOUGHT_LOCATION_NAME
    assert loc.loc_type == "derelict"
```

**`test_spawn_beyond_deepest`** — current lines 69–75:
```python
def test_spawn_beyond_deepest(self, expanded_galaxy):
    galaxy = expanded_galaxy
    max_depth = max(s.depth for s in galaxy.systems.values())
    galaxy.spawn_dreadnought()
    dread = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
    assert dread.depth >= max_depth
```

**`test_spawn_reachable`** — current lines 77–82:
```python
def test_spawn_reachable(self, expanded_galaxy):
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    reachable = _bfs_reachable(galaxy, galaxy.home_system)
    assert DREADNOUGHT_SYSTEM_NAME in reachable
```

**`test_spawn_idempotent`** — current lines 84–91:
```python
def test_spawn_idempotent(self, expanded_galaxy):
    galaxy = expanded_galaxy
    name1 = galaxy.spawn_dreadnought()
    count_before = len(galaxy.systems)
    name2 = galaxy.spawn_dreadnought()
    assert name1 == name2
    assert len(galaxy.systems) == count_before
```

**`test_spawn_not_on_existing_position`** — current lines 104–110:
```python
def test_spawn_not_on_existing_position(self, expanded_galaxy):
    galaxy = expanded_galaxy
    occupied_before = set(galaxy._occupied_positions.keys())
    galaxy.spawn_dreadnought()
    sys = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
    assert (sys.gx, sys.gy) not in occupied_before
```

**`test_spawn_connections_bidirectional`** — current lines 112–120:
```python
def test_spawn_connections_bidirectional(self, expanded_galaxy):
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    dread = galaxy.systems[DREADNOUGHT_SYSTEM_NAME]
    assert len(dread.connections) >= 1
    for parent_name in dread.connections:
        parent = galaxy.systems[parent_name]
        assert DREADNOUGHT_SYSTEM_NAME in parent.connections
```

**`test_spawn_is_dead_end`** — current lines 122–126:
```python
def test_spawn_is_dead_end(self, expanded_galaxy):
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    assert DREADNOUGHT_SYSTEM_NAME in galaxy._generated_frontiers
```

**`test_spawn_is_frontier`** — current lines 128–133:
```python
def test_spawn_is_frontier(self, expanded_galaxy):
    """Dreadnought system has travel cost 2 (unexplored frontier)."""
    galaxy = expanded_galaxy
    galaxy.spawn_dreadnought()
    assert galaxy.travel_cost(DREADNOUGHT_SYSTEM_NAME) == 2
```

**Leave `test_spawn_deterministic` unchanged.** It uses `seed=99` and must run two genuine expansions to verify determinism — it cannot use the shared fixture.

- [ ] **Step 5: Update the 2 tests in `TestDreadnoughtTrigger` to use the fixture**

Both tests (around lines 416–490) currently do `galaxy = Galaxy(seed=42); _expand_all(galaxy)`. Replace with the fixture:

**`test_reveal_on_sixth_nav_unit`:**
```python
def test_reveal_on_sixth_nav_unit(self, expanded_galaxy):
    from tests.conftest import make_arena
    from ui.tactical_state import TacticalState
    from world.galaxy import Location

    engine = Engine()
    engine.ship = Ship()
    galaxy = expanded_galaxy
    engine.galaxy = galaxy
    engine.ship.nav_units = 5  # already have 5

    loc = Location("Test", "derelict", system_name="TestSys")
    ts = TacticalState(location=loc, depth=0)

    gm = make_arena()
    nav = Entity(
        char="n",
        color=(0, 255, 200),
        name="Nav Unit",
        blocks_movement=False,
        item={"type": "nav_unit", "value": 1},
    )
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    player.inventory.append(nav)
    gm.entities.append(player)
    engine.game_map = gm
    engine.player = player

    ts.on_exit(engine)

    assert engine.ship.nav_units == 6
    assert galaxy.dreadnought_system == DREADNOUGHT_SYSTEM_NAME
```

**`test_no_reveal_before_six`:** Read the current test body in the file. Add `expanded_galaxy` as the second parameter after `self`. Replace the two lines `galaxy = Galaxy(seed=42)` and `_expand_all(galaxy)` with `galaxy = expanded_galaxy`. Do not change any other lines in the method.

- [ ] **Step 6: Run the dreadnought spawn tests and verify all pass**

```
.venv/Scripts/pytest tests/test_dreadnought_spawn.py -v --tb=short 2>&1 | tail -25
```

Expected: all tests PASS. Total time should be under 60s (was ~175s before).

- [ ] **Step 7: Run ruff**

```
C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe check tests/test_dreadnought_spawn.py
```

- [ ] **Step 8: Commit**

```bash
git add tests/test_dreadnought_spawn.py
git commit -m "perf: share expanded galaxy fixture across dreadnought spawn tests"
```

---

## Task 2: Remove duplicate dungeon-gen crash tests

**Problem:** Two pairs of tests are identical (same function call, same assertion) — the `_with_windows` versions were added to verify windows don't crash the generator but ended up duplicating the pre-existing "no crash" tests exactly.

**Files:**
- Modify: `tests/test_dungeon_gen.py`

- [ ] **Step 1: Verify the duplicates are truly identical**

Read lines 603–607 and 959–963 of `tests/test_dungeon_gen.py`. Confirm:
- `test_ship_gen_no_crash_80x45` calls `generate_dungeon(width=80, height=45, seed=seed, loc_type="derelict")` and `assert rooms`
- `test_derelict_no_crash_with_windows` calls `generate_dungeon(width=80, height=45, seed=seed, loc_type="derelict")` and `assert rooms`
- They are identical.

Read lines 765–769 and 952–956. Confirm:
- `test_colony_no_crash_200_seeds` calls `generate_dungeon(width=80, height=45, seed=seed, loc_type="colony")` and `assert rooms`
- `test_colony_no_crash_with_windows` calls `generate_dungeon(width=80, height=45, seed=seed, loc_type="colony")` and `assert rooms`
- They are identical.

If either pair has any difference, do NOT remove — stop and report DONE_WITH_CONCERNS.

- [ ] **Step 2: Remove `test_derelict_no_crash_with_windows` (lines ~959–963)**

Delete the function including its docstring and the blank line preceding it. The section to remove is:

```python
def test_derelict_no_crash_with_windows():
    """Derelict generator with windows must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(width=80, height=45, seed=seed, loc_type="derelict")
        assert rooms
```

- [ ] **Step 3: Remove `test_colony_no_crash_with_windows` (lines ~952–956)**

Delete the function including its docstring and the blank line preceding it:

```python
def test_colony_no_crash_with_windows():
    """Colony generator with windows must not crash across 200 seeds."""
    for seed in range(200):
        game_map, rooms, exit_pos = generate_dungeon(width=80, height=45, seed=seed, loc_type="colony")
        assert rooms
```

- [ ] **Step 4: Run the dungeon gen tests and verify all remaining pass**

```
.venv/Scripts/pytest tests/test_dungeon_gen.py -v --tb=short -q 2>&1 | tail -10
```

Expected: all PASS, 2 fewer tests than before.

- [ ] **Step 5: Commit**

```bash
git add tests/test_dungeon_gen.py
git commit -m "test: remove duplicate colony and derelict no-crash tests"
```

---

## Task 3: Pattern scan and removal of performative tests

**Goal:** Scan all test files for low-value patterns, read each flagged file in full depth, remove confirmed performative tests.

**Files:**
- Read-then-edit: any `tests/*.py` file that has flagged matches

### Phase A — Run the scans

- [ ] **Step 1: Scan for trivially-true assertions**

```
cd F:\dev\gamedev\dreadnought
grep -rn "assert True\b\|assert len(.*) >= 0\|assert .* == .*\bTrue\b" tests/ --include="*.py"
```

Record every match. Each is a candidate for removal.

- [ ] **Step 2: Scan for assert-is-not-None with nothing else meaningful**

```
grep -n "assert .* is not None$" tests/*.py | head -60
```

Record file:line for every match. These are worth examining in context — often fine, but sometimes the only assertion in a test.

- [ ] **Step 3: Scan for mock-assertion-only tests**

```
grep -rn "assert_called_once\|assert_called_with\|assert_not_called\|assert_any_call\|call_args_list" tests/ --include="*.py"
```

Record every match. Each test body that consists **only** of mock assertions (no real game objects exercised) is a candidate.

- [ ] **Step 4: Scan for tests that only check isinstance with no behavior**

```
grep -n "assert isinstance" tests/*.py
```

Record matches. An `assert isinstance(x, SomeType)` as the **sole** assertion in a test is performative if `x` was just constructed a line above with `SomeType(...)`.

- [ ] **Step 5: Scan for single-line test bodies**

```
grep -n "^def test_" tests/*.py | python -c "
import sys, re
lines = [l.strip() for l in sys.stdin]
for l in lines:
    print(l)
" 2>/dev/null
```

This surfaces test names; cross-reference with visual inspection for very short tests.

### Phase B — Read flagged files in full depth

For each file that produced matches in Phase A:

- [ ] **Step 6: Read each flagged file end-to-end**

For every candidate match, apply the following judgment criteria **in order**:

1. **Can this assertion ever fail?** If `assert True`, `assert x == x`, or `assert len(items) >= 0` — the answer is no. Delete the test (or just the useless assertion if the test has other valuable assertions).

2. **Does the test exercise real code?** If the test body is only `Mock()` / `MagicMock()` calls with `assert_called_*` and no actual game objects are instantiated and used — remove it.

3. **Does `assert x is not None` actually guard anything?** If `x` was just set and can never be None (e.g. `x = SomeClass()`), the assertion is redundant. If `x` comes from a function that could return None (a lookup, a search), keep it.

4. **Is it a duplicate?** Two tests in the same file with identical setup that differ only by asserting two different fields on the same object should be merged into one test. Delete the duplicate, add the merged assertion.

5. **Check git blame for context.** If a test was added in a commit message like "fix: crash when X was None" — it is a regression guard, keep it regardless of how trivial it looks.

- [ ] **Step 7: For each confirmed low-value test: delete it, then run the full suite**

After each deletion (or batch of deletions within the same file):

```
.venv/Scripts/pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: all tests PASS (lower count than before). If any test fails, the deleted test was guarding real behavior — restore it.

- [ ] **Step 8: Commit after each file's cleanup**

```bash
git add tests/<filename>.py
git commit -m "test: remove performative tests in <filename>"
```

---

## Verification

After all three tasks are complete:

- [ ] **Run the full suite with durations**

```
.venv/Scripts/pytest tests/ --durations=10 -q 2>&1 | tail -20
```

Expected:
- Total time meaningfully below 388s (target: under ~250s)
- `test_dreadnought_spawn.py` no longer dominates the top 10
- The two removed colony/derelict crash tests no longer appear
- All remaining tests PASS

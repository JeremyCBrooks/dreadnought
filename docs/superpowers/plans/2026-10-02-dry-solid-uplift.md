# DRY and SOLID Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplication and responsibility/dependency problems found in the October 2026 audit, without changing game behaviour, generated maps, or the save format.

**Architecture:** Thirteen behaviour-preserving refactors, each shippable on its own. The first adds an end-to-end safety net; tasks 2–6 take `TacticalState` apart (snapshot, turn pipeline, turn resolution, interdiction lifecycle, HUD); tasks 7–9 replace repeated construction and type if-chains with factories and handler tables; task 8 fixes and then enforces the import layering; tasks 10–12 consolidate the generator's repeated algorithms; task 13 closes private reach-ins.

**Tech Stack:** Python 3.12, python-tcod, numpy, pytest, ruff, uv-managed `.venv`.

**Spec:** There is no separate design doc. The findings this plan implements are listed in "Findings addressed" below; they come from the audit in the session that produced commit `c132873`.

## Findings addressed

| Finding | Evidence | Task |
|---|---|---|
| Tests are unit-heavy; real flows untested | `turn_counter` bug passed 2016 tests | 1 |
| `_saved_player` dict built in 4 places | `ui/tactical_state.py` ×3, `ui/cargo_state.py` | 2 |
| Post-action turn handling written 4 times, inconsistently | `ev_key`, `_handle_ranged_input`, `_handle_interact_input`, `_handle_scan_input` | 3 |
| `TacticalState` owns input, physics, interdiction, saving, HUD (1,200+ lines) | `ui/tactical_state.py` | 3, 4, 5, 6 |
| Enemy and item entities built by hand in 6 places | `spawning.py`, `interdiction.py`, `enemies.py`, `actions.py`, `debug.py` | 7 |
| Layers import upward | `game→ui.colors`, `engine→ui.keys`, `engine→web`, `world→ui`, `data→game` | 7, 8 |
| Item-type if-chains | `TacticalState.on_exit`, `use_consumable` | 9 |
| Four hand-rolled BFS; neighbour-shift block repeated 5× | `environment.py`, `boarding_craft.py`, `hull.py` | 10 |
| Mirrored branches in building generation | `buildings.py` | 11 |
| Generator branches on name strings | `generate_dungeon` | 12 |
| 23 private reach-ins; `needs_animation` not on base `State`; animation check duplicated | `engine._state_stack`, `engine._saved_player`, `game_map._fov_cache` | 13 |

## Global Constraints

- Behaviour-preserving: no gameplay change unless a task says so explicitly (tasks 3 and 7 each name one).
- `tests/test_dungeon_gen_golden.py` must pass unchanged after every task. Never regenerate `tests/dungeon_gen_golden.json`.
- The save JSON format written by `web/save_load.py` must not change. Old saves must still load.
- RNG draw order in `world/dungeon_gen/` must not change: same calls, same order, same arguments.
- TDD: write the test, watch it fail (or, for characterisation tests, prove it can fail by mutation), then implement.
- Test quality bar - applies to every test in this plan and any an implementer adds:
  - Before writing a test, name the production bug that would make it fail. If you cannot, do not write it.
  - Expected values are literals or hand-derived. Never compute them with the code under test or its helpers.
  - No change detectors: do not assert a constant's value, a data table's contents, an attribute's existence, a getter's return, or source text. Assert the first player-visible or caller-visible result that depends on it.
  - No assertions on mocks. Drive real objects through public entry points (`ev_key`, `perform`, `generate_dungeon`, `engine_to_dict`).
  - A pure move or rename earns no new test: the existing suite and the golden digest are its tests. Each task says which existing tests cover it.
  - Fewer, sharper tests beat coverage. Delete a test rather than keep one that cannot fail for a real bug.
- After every task: full `pytest` green, `ruff check .` and `ruff format .` clean. Ruff is at `C:\Users\brook\AppData\Roaming\Python\Python313\Scripts\ruff.exe`.
- Activate the venv first: `.\.venv\Scripts\Activate.ps1`. Use `uv` for any dependency work; this plan adds no dependencies.
- One commit per task, conventional-commit subject, on branch `refactor/dry-solid-uplift`. It is cut from `refactor/dungeon-gen`, not `main`, because it builds on the audit fixes (`c132873`) and the `dungeon_gen` package split, neither of which is on `main` yet.
- Do not touch `debug.py` flag values.

## Review Focus

1. **Seeded maps drift.** A refactor in tasks 7, 10, 11 or 12 reorders an RNG draw and every existing world changes. Expected: identical maps. Pinned by the golden digest test, run as a gate in each of those tasks.
2. **An old save stops loading.** A player with a save written before the refactor resumes. Expected: same HP, inventory, equipped weapon, fuel and system. Pinned by the save fixture captured in task 1, before any production code changes, and loaded by a test that every later task must keep green.
3. **Death during a non-standard input mode.** The player dies from an interact hazard, a scan turn, or a firefight. Expected: death fade with the right cause, no extra enemy turn. Pinned in task 3.
4. **Import cycle at startup.** After moving modules, `main.py` or `web.server` fails to import in a fresh process even though pytest (which imports in a different order) passes. Expected: both import cleanly. Pinned by the subprocess test in task 8.
5. **Reconnect after a save flush.** A disconnect save must not disturb the live session. Expected: same state, player and entities. Already pinned by `test_mid_mission_save_leaves_the_live_session_untouched`; task 2 must keep it green.

---

### Task 1: End-to-end safety net and shared test helpers

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_audit_fixes.py` (use the shared helpers)
- Create: `tests/test_e2e_flows.py`
- Create: `tests/fixtures/make_save_fixture.py`, `tests/fixtures/save_before_refactor.json`

**Interfaces:**
- Produces (in `tests/conftest.py`): `new_game(seed: int = 1) -> tuple[Engine, StrategicState]`, `find_location(engine, loc_type: str) -> Location`, `enter_mission(engine, loc_type: str = "colony") -> TacticalState`, `enter_ship(engine) -> TacticalState`, `key_for(direction: tuple[int, int]) -> int`, `free_step_from(engine, x: int, y: int) -> tuple[int, int]`.

- [ ] **Step 1: Add the shared helpers to `tests/conftest.py`** (append; keep existing content)

```python
# ---- Whole-game helpers: a real Engine driven through real states ----


def new_game(seed: int = 1):
    """A fresh game on the strategic screen: (engine, strategic_state)."""
    from game.ship import Ship
    from ui.strategic_state import StrategicState
    from world.galaxy import Galaxy

    engine = Engine()
    engine.galaxy = Galaxy(seed=seed)
    engine.ship = Ship()
    engine.ship.generate_interior(engine.galaxy.seed)
    strategic = StrategicState(engine.galaxy)
    engine.push_state(strategic)
    return engine, strategic


def find_location(engine, loc_type: str):
    """First generated location of *loc_type*; fails the test if the seed has none."""
    for system in engine.galaxy.systems.values():
        for loc in system.locations:
            if loc.loc_type == loc_type:
                return loc
    pytest.fail(f"seed has no {loc_type}")


def enter_mission(engine, loc_type: str = "colony"):
    from ui.tactical_state import TacticalState

    state = TacticalState(location=find_location(engine, loc_type), depth=0)
    engine.push_state(state)
    return state


def enter_ship(engine):
    from ui.tactical_state import TacticalState

    state = TacticalState(explore_ship=True)
    engine.push_state(state)
    return state


def key_for(direction: tuple[int, int]) -> int:
    """A key that moves in *direction*."""
    from ui.keys import move_keys

    return next(key for key, move in move_keys().items() if move == direction)


def free_step_from(engine, x: int, y: int) -> tuple[int, int]:
    """A cardinal (dx, dy) from (x, y) onto a walkable tile with nothing standing on it."""
    game_map = engine.game_map
    return next(
        (dx, dy)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if game_map.is_walkable(x + dx, y + dy)
        and not game_map.get_blocking_entity(x + dx, y + dy)
        and not game_map.get_interactable_at(x + dx, y + dy)
    )
```

- [ ] **Step 2: Switch `tests/test_audit_fixes.py` to the shared helpers**

Delete its local `_new_game`, `_location`, `_enter_mission`, `_enter_ship` and `_key_for` definitions. Change the conftest import line to:

```python
from tests.conftest import (
    FakeEvent,
    enter_mission,
    enter_ship,
    key_for,
    make_heal_item,
    make_scanner,
    make_weapon,
    new_game,
)
```

Then rename the call sites in that file with:

```bash
sed -i -b -E 's/\b_new_game\(/new_game(/g; s/\b_enter_mission\(/enter_mission(/g; s/\b_enter_ship\(/enter_ship(/g; s/\b_key_for\(/key_for(/g' tests/test_audit_fixes.py
```

Remove the now-unused imports (`move_keys`, `Galaxy`, `Ship`, `StrategicState` if ruff reports them).

Run: `pytest tests/test_audit_fixes.py -q` - Expected: 38 passed.

- [ ] **Step 3: Write `tests/test_e2e_flows.py`**

```python
"""End-to-end flows: a real Engine driven through real states, the way a player would."""

from __future__ import annotations

import json

import tcod.console
import tcod.event

from engine.game_state import Engine
from game.entity import Entity
from tests.conftest import FakeEvent, enter_mission, free_step_from, key_for, new_game
from ui.game_over_state import GameOverState
from ui.strategic_state import StrategicState
from ui.title_state import TitleState
from web.save_load import dict_to_engine, engine_to_dict

K = tcod.event.KeySym


def _leave_by_the_exit(engine, state) -> None:
    ex, ey = state.exit_pos
    dx, dy = free_step_from(engine, ex, ey)
    state.ev_key(engine, FakeEvent(key_for((dx, dy))))
    state.ev_key(engine, FakeEvent(key_for((-dx, -dy))))


def _reload(engine: Engine) -> Engine:
    loaded = Engine()
    dict_to_engine(json.loads(json.dumps(engine_to_dict(engine))), loaded)
    return loaded


def test_mission_round_trip_converts_salvage_and_keeps_the_rest():
    engine, strategic = new_game()
    state = enter_mission(engine)
    core = Entity(name="Reactor Core", blocks_movement=False, item={"type": "reactor_core", "value": 5})
    medkit = Entity(name="Med-kit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory += [core, medkit]
    fuel_before = engine.ship.fuel

    _leave_by_the_exit(engine, state)

    assert engine.current_state is strategic
    assert engine.ship.fuel == min(engine.ship.max_fuel, fuel_before + 5)
    assert engine._saved_player["inventory"] == [medkit]
    assert engine.game_map is None and engine.player is None


def test_leaving_and_reentering_a_mission_keeps_the_player_record():
    engine, _ = new_game()
    state = enter_mission(engine)
    engine.player.fighter.hp = 6
    medkit = Entity(name="Med-kit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory.append(medkit)
    _leave_by_the_exit(engine, state)

    enter_mission(engine)

    assert engine.player.fighter.hp == 6
    assert engine.player.inventory == [medkit]


def test_same_seed_and_same_keys_play_out_identically():
    def play() -> tuple[list, list[str], int]:
        engine, _ = new_game(seed=3)
        state = enter_mission(engine, "derelict")
        for _ in range(20):
            if engine.current_state is not state:
                break
            state.ev_key(engine, FakeEvent(K.PERIOD))
        creatures = sorted((e.name, e.x, e.y, e.fighter.hp) for e in engine.game_map.entities if e.fighter)
        return creatures, [text for text, _ in engine.message_log.messages], engine.turn_counter

    first, second = play(), play()

    assert first == second
    assert first[2] == 20


def test_strategic_travel_survives_a_save_and_reload():
    engine, strategic = new_game()
    strategic.focus = "navigation"
    direction, destination = next(iter(strategic._connection_by_direction().items()))
    strategic.ev_key(engine, FakeEvent(key_for(direction)))
    assert engine.galaxy.current_system == destination

    loaded = _reload(engine)

    assert isinstance(loaded.current_state, StrategicState)
    assert loaded.galaxy.current_system == destination
    assert loaded.ship.fuel == engine.ship.fuel
    assert set(loaded.galaxy.systems) == set(engine.galaxy.systems)


def test_death_runs_through_game_over_to_a_new_game():
    engine, _ = new_game()
    state = enter_mission(engine)
    engine.player.fighter.hp = 0
    state.ev_key(engine, FakeEvent(K.PERIOD))
    assert state._death_cause is not None

    state._death_fade_start -= 5
    state.on_render(tcod.console.Console(Engine.CONSOLE_WIDTH, Engine.CONSOLE_HEIGHT, order="F"), engine)
    assert isinstance(engine.current_state, GameOverState)

    engine.current_state._fade_start -= 5
    engine.current_state.ev_key(engine, FakeEvent(K.RETURN))
    assert isinstance(engine.current_state, TitleState)
    assert engine.galaxy is None

    engine.current_state.ev_key(engine, FakeEvent(K.RETURN))
    assert isinstance(engine.current_state, StrategicState)
    assert engine.galaxy is not None
```

- [ ] **Step 4: Capture a save written by the pre-refactor code**

This must happen now, before any production file changes. Create `tests/fixtures/make_save_fixture.py`:

```python
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
engine._saved_player["hp"] = 7

strategic.focus = "navigation"
direction = next(iter(strategic._connection_by_direction()))
strategic.ev_key(engine, FakeEvent(key_for(direction)))
assert engine.galaxy.current_system != engine.galaxy.home_system

out = Path(__file__).with_name("save_before_refactor.json")
out.write_text(json.dumps(engine_to_dict(engine), indent=1), encoding="utf-8")
print(f"wrote {out}")
```

Run: `python tests/fixtures/make_save_fixture.py`
Expected: `wrote ...save_before_refactor.json`.

Add to `tests/test_e2e_flows.py` (and `from pathlib import Path` to its imports):

```python
SAVE_FIXTURE = Path(__file__).parent / "fixtures" / "save_before_refactor.json"


def test_a_save_written_before_the_refactor_still_loads_and_plays():
    loaded = Engine()
    dict_to_engine(json.loads(SAVE_FIXTURE.read_text(encoding="utf-8")), loaded)

    assert isinstance(loaded.current_state, StrategicState)
    assert loaded.galaxy.current_system != loaded.galaxy.home_system
    assert loaded.ship.fuel == 3
    record = loaded._saved_player
    assert record["hp"] == 7
    assert [item.name for item in record["inventory"]] == ["Combat Knife", "Medkit"]

    enter_mission(loaded)

    assert loaded.player.fighter.hp == 7
    # Base power 1 plus the knife's 3: only true if the knife came back equipped.
    assert loaded.player.fighter.power == 4
```

- [ ] **Step 5: Run it**

Run: `pytest tests/test_e2e_flows.py -q`
Expected: 6 passed. These are characterisation tests: they pin behaviour that already exists.

What each one catches:

| Test | Fails if |
|---|---|
| mission round trip | salvage is not converted, kept items are lost, or the map/player are not released on exit |
| leave and re-enter | HP or inventory is not carried between missions |
| same seed, same keys | any gameplay roll stops being a function of (seed, turn), or turns stop advancing |
| travel survives save/reload | the galaxy, position or fuel does not round-trip |
| death to new game | the death fade, game-over reset or title restart breaks |
| old save loads and plays | the save format or the snapshot/loadout restore changes shape |

- [ ] **Step 6: Prove the net can fail (mutation check)**

In `ui/tactical_state.py`, temporarily delete the line `engine.turn_counter += 1` in `_after_player_turn`.

Run: `pytest tests/test_e2e_flows.py::test_same_seed_and_same_keys_play_out_identically -q`
Expected: FAIL with `assert 0 == 20`.

Restore: `git checkout ui/tactical_state.py`.

- [ ] **Step 7: Full gate and commit**

Run: `pytest -q` - Expected: all pass. Run `ruff check .` and `ruff format .`.

```bash
git add tests/conftest.py tests/test_audit_fixes.py tests/test_e2e_flows.py tests/fixtures
git commit -m "test: add end-to-end flow tests, a pre-refactor save fixture and shared helpers"
```

---

### Task 2: One player-snapshot module

**Files:**
- Create: `game/player_state.py`
- Create: `tests/test_player_state.py`
- Modify: `ui/tactical_state.py` (`on_enter`, `on_exit`, `_restore_player_from_saved`, `_enter_ship`, `flush_for_save`)
- Modify: `ui/cargo_state.py` (`_ensure_loadout`)

**Interfaces:**
- Produces: `new_player(x: int, y: int) -> Entity`, `snapshot_player(player: Entity) -> dict`, `fresh_player_snapshot() -> dict`, `apply_snapshot(player: Entity, snapshot: dict | None) -> None`. The dict keys stay exactly `hp, max_hp, defense, power, base_power, inventory, loadout`.

- [ ] **Step 1: Write the failing tests** - `tests/test_player_state.py`

```python
"""The player's between-mission record: one place that builds, snapshots and restores it."""

from game.loadout import Loadout
from game.player_state import apply_snapshot, fresh_player_snapshot, new_player, snapshot_player
from tests.conftest import make_heal_item, make_melee_weapon
from web.save_load import _saved_player_from_dict, _saved_player_to_dict


def _wounded_player_with_knife():
    knife = make_melee_weapon(value=3)
    player = new_player(0, 0)
    player.fighter.hp = 4
    player.inventory.append(knife)
    player.loadout = Loadout(slot1=knife)
    return player, knife


def test_restored_player_carries_hp_inventory_and_equipped_weapon():
    wounded, knife = _wounded_player_with_knife()

    restored = new_player(5, 5)
    apply_snapshot(restored, snapshot_player(wounded))

    assert restored.fighter.hp == 4
    assert restored.inventory == [knife]
    assert restored.loadout.slot1 is knife
    # Base 1 plus the knife's 3: the melee bonus is re-derived, not lost and not doubled.
    assert restored.fighter.power == 4


def test_snapshot_is_isolated_from_later_inventory_changes():
    player = new_player(0, 0)
    player.inventory.append(make_heal_item())
    snapshot = snapshot_player(player)

    player.inventory.clear()

    assert [item.name for item in snapshot["inventory"]] == ["Medkit"]


def test_first_mission_player_with_no_record_keeps_starting_stats():
    player = new_player(0, 0)

    apply_snapshot(player, None)

    assert (player.fighter.hp, player.fighter.power) == (10, 1)


def test_two_new_games_do_not_share_an_inventory_or_loadout():
    first, second = fresh_player_snapshot(), fresh_player_snapshot()

    first["inventory"].append(make_heal_item())
    first["loadout"].equip(make_melee_weapon())

    assert second["inventory"] == []
    assert second["loadout"].all_items() == []


def test_snapshots_survive_the_save_file_round_trip():
    wounded, _ = _wounded_player_with_knife()

    loaded = _saved_player_from_dict(_saved_player_to_dict(snapshot_player(wounded)))
    blank = _saved_player_from_dict(_saved_player_to_dict(fresh_player_snapshot()))

    assert loaded["hp"] == 4
    assert [item.name for item in loaded["inventory"]] == ["Combat Knife"]
    assert loaded["loadout"].slot1 is loaded["inventory"][0]
    assert (blank["hp"], blank["inventory"], blank["loadout"].all_items()) == (10, [], [])
```

What each one catches:

| Test | Fails if |
|---|---|
| restored player carries… | a field is dropped from the record, or the melee bonus is lost or applied twice |
| snapshot is isolated | the record aliases the live inventory, so a later change rewrites history |
| no record keeps starting stats | a first mission crashes or zeroes the player |
| two new games do not share | the fresh record reuses one mutable list or loadout across games |
| save file round trip | the record's shape drifts from what `web/save_load.py` reads and writes |

The pre-refactor save fixture from Task 1 is the compatibility test for older records.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_player_state.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'game.player_state'`.

- [ ] **Step 3: Create `game/player_state.py`**

```python
"""The player's between-mission record: build the entity, snapshot it, restore it."""

from __future__ import annotations

from game.entity import Entity, Fighter
from game.loadout import Loadout, recalc_melee_power

PLAYER_HP = 10
PLAYER_DEFENSE = 0
PLAYER_POWER = 1


def new_player(x: int, y: int) -> Entity:
    """A player entity with starting stats at (x, y)."""
    return Entity(
        x=x,
        y=y,
        char="@",
        color=(255, 255, 255),
        name="Player",
        blocks_movement=True,
        fighter=Fighter(hp=PLAYER_HP, max_hp=PLAYER_HP, defense=PLAYER_DEFENSE, power=PLAYER_POWER),
    )


def snapshot_player(player: Entity) -> dict:
    """Record of *player* to carry between missions. Power resets to base: the melee bonus is re-derived on restore."""
    fighter = player.fighter
    return {
        "hp": fighter.hp,
        "max_hp": fighter.max_hp,
        "defense": fighter.defense,
        "power": fighter.base_power,
        "base_power": fighter.base_power,
        "inventory": list(player.inventory),
        "loadout": player.loadout,
    }


def fresh_player_snapshot() -> dict:
    """Record of a player who has not been on a mission yet."""
    return {**snapshot_player(new_player(0, 0)), "loadout": Loadout()}


def apply_snapshot(player: Entity, snapshot: dict | None) -> None:
    """Restore stats, inventory and loadout from *snapshot* onto a freshly built player."""
    if not snapshot:
        return
    player.fighter.hp = snapshot["hp"]
    player.fighter.max_hp = snapshot["max_hp"]
    player.fighter.defense = snapshot["defense"]
    player.fighter.power = snapshot["power"]
    player.fighter.base_power = snapshot["base_power"]
    player.inventory = snapshot.get("inventory", [])
    player.loadout = snapshot.get("loadout")
    recalc_melee_power(player)
```

Run: `pytest tests/test_player_state.py -q` - Expected: 5 passed.

- [ ] **Step 4: Replace the six hand-written sites**

In `ui/tactical_state.py`:

1. `on_enter`: replace the `player = Entity(x=px, y=py, char="@", ... fighter=Fighter(hp=10, ...))` block with `player = new_player(px, py)`.
2. `_enter_ship`: same replacement for its `player = Entity(...)` block.
3. `_restore_player_from_saved`: replace the whole body with `apply_snapshot(player, engine._saved_player)`.
4. `on_exit`, ship branch: replace the `engine._saved_player = {...}` literal with `engine._saved_player = snapshot_player(p)`.
5. `on_exit`, mission branch: replace

```python
                saved_inventory = list(p.inventory)
                saved_loadout = p.loadout

                engine._saved_player = {
                    ...seven keys...
                }
```

with

```python
                engine._saved_player = snapshot_player(p)
                saved_inventory = engine._saved_player["inventory"]
```

(the salvage code below it mutates `saved_inventory` in place, so it must be the list inside the snapshot).

6. `flush_for_save`: replace its `engine._saved_player = {...}` literal with `engine._saved_player = snapshot_player(p)`.

Import at the top of the functions that need it, matching the file's local-import style: `from game.player_state import apply_snapshot, new_player, snapshot_player`. Remove the now-unused local imports of `Entity` and `Fighter`.

In `ui/cargo_state.py`, `_ensure_loadout`: replace the `engine._saved_player = {"hp": 10, ...}` literal and the following `sp = engine._saved_player` with:

```python
            from game.player_state import fresh_player_snapshot

            engine._saved_player = fresh_player_snapshot()
            sp = engine._saved_player
```

- [ ] **Step 5: Verify nothing else builds the dict**

Run: `git grep -nE '_saved_player = \{' -- engine game ui web`
Expected: no output.

- [ ] **Step 6: Full gate and commit**

Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add game/player_state.py tests/test_player_state.py ui/tactical_state.py ui/cargo_state.py
git commit -m "refactor(player): build, snapshot and restore the player in one module"
```

---

### Task 3: One post-action pipeline in `TacticalState`

**Files:**
- Modify: `ui/tactical_state.py` (`ev_key`, `_handle_ranged_input`, `_handle_interact_input`, `_handle_scan_input`; new `_resolve_player_action`)
- Create: `tests/test_player_action_pipeline.py`

**Interfaces:**
- Produces: `TacticalState._resolve_player_action(self, engine, consumed: int, *, moved: bool = False, death_cause: str = "Killed in action.") -> None`.

**Deliberate behaviour change (the only one in this task):** a player killed by an interact hazard chosen through the direction prompt now dies with cause "Killed in action." and no enemy turn runs first. Today that path skips the death check, runs a full world turn, and reports "Succumbed to the environment."

- [ ] **Step 1: Write the failing tests** - `tests/test_player_action_pipeline.py`

```python
"""Every input mode resolves a consumed action through the same pipeline."""

import tcod.event

from game.entity import Entity
from tests.conftest import FakeEvent, enter_mission, free_step_from, key_for, make_scanner, make_weapon, new_game

K = tcod.event.KeySym


def _lethal_crate(x: int, y: int) -> Entity:
    hazard = {"type": "explosive", "damage": 99, "equipment_damage": False, "dot": 0, "duration": 0}
    return Entity(
        x=x, y=y, char="=", name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": hazard, "loot": None},
    )


def _mission_off_the_exit():
    engine, _ = new_game()
    state = enter_mission(engine)
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    state.ev_key(engine, FakeEvent(key_for((dx, dy))))
    assert engine.current_state is state
    return engine, state


def test_hazard_death_through_the_direction_prompt_is_killed_in_action():
    engine, state = _mission_off_the_exit()
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    engine.game_map.entities.append(_lethal_crate(engine.player.x + dx, engine.player.y + dy))
    engine.game_map.invalidate_entity_index()
    turn_before = engine.turn_counter
    state._interact_pending = True

    state.ev_key(engine, FakeEvent(key_for((dx, dy))))

    assert state._death_cause == "Killed in action."
    assert engine.turn_counter == turn_before


def test_hazard_death_through_the_single_target_shortcut_matches():
    engine, state = _mission_off_the_exit()
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    engine.game_map.entities.append(_lethal_crate(engine.player.x + dx, engine.player.y + dy))
    engine.game_map.invalidate_entity_index()
    assert len(state._adjacent_interact_dirs(engine)) == 1

    state.ev_key(engine, FakeEvent(K.E))

    assert state._death_cause == "Killed in action."


def test_scan_chosen_from_the_scanner_prompt_costs_one_turn():
    engine, _ = new_game()
    engine.mission_loadout = [make_scanner(name="A"), make_scanner(name="B")]
    state = enter_mission(engine)
    # Auto-equip only takes the first scanner; the prompt needs both equipped.
    engine.player.loadout.equip(engine.player.inventory[1])
    state.ev_key(engine, FakeEvent(K.S))
    assert state._scan_pending is not None
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.N1))

    assert engine.turn_counter == turn_before + 1
    assert engine.current_state is state


def test_firing_costs_one_turn_and_a_firefight_death_keeps_its_cause():
    engine, state = _mission_off_the_exit()
    engine.player.inventory.append(make_weapon())
    engine.player.loadout.equip(engine.player.inventory[-1])
    dx, dy = free_step_from(engine, engine.player.x, engine.player.y)
    target = Entity(x=engine.player.x + dx, y=engine.player.y + dy, char="r", name="Rat")
    from game.entity import Fighter

    target.fighter = Fighter(hp=50, max_hp=50, defense=0, power=0)
    engine.game_map.entities.append(target)
    engine.game_map.invalidate_entity_index()
    state._ranged_cursor = (target.x, target.y)
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.RETURN))

    assert engine.turn_counter == turn_before + 1
    assert state._ranged_cursor is None
    assert target.fighter.hp == 47


def test_an_action_that_achieves_nothing_costs_no_turn():
    engine, state = _mission_off_the_exit()
    assert engine.game_map.get_items_at(engine.player.x, engine.player.y) == []
    turn_before = engine.turn_counter

    state.ev_key(engine, FakeEvent(K.G))

    assert engine.turn_counter == turn_before
    assert engine.message_log.messages[-1][0] == "Nothing to pick up."
```

What each one catches:

| Test | Fails if |
|---|---|
| hazard death, direction prompt | the prompt path skips the death check or lets the world take a turn first |
| hazard death, shortcut | the two interact paths disagree about a death |
| scan from the prompt | the prompt path stops charging a turn |
| firing | a shot stops costing a turn, misses its damage, or leaves the targeting cursor up |
| action that achieves nothing | a refused action starts costing a turn |

All five drive `ev_key`, never the new method directly: the pipeline is an implementation detail and is tested through the inputs that reach it.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_player_action_pipeline.py -q`
Expected: `test_hazard_death_through_the_direction_prompt_is_killed_in_action` fails with `'Succumbed to the environment.' == 'Killed in action.'`. The other four pass: they pin behaviour the refactor must not disturb.

- [ ] **Step 3: Add the pipeline method** (in `ui/tactical_state.py`, directly above `_after_player_turn`)

```python
    def _resolve_player_action(
        self,
        engine: Engine,
        consumed: int,
        *,
        moved: bool = False,
        death_cause: str = "Killed in action.",
    ) -> None:
        """Run everything that follows a player action that took *consumed* ticks.

        Every input mode ends here, so they all agree on the order: leave by
        the hatch, die, let the world take its turns, refresh what the player sees.
        """
        if not consumed:
            return

        # Only walking onto the hatch leaves: the player spawns on it, so
        # scanning or waiting there must not end the mission.
        if moved and self.exit_pos and (engine.player.x, engine.player.y) == self.exit_pos:
            msg = "You return to the bridge." if self.explore_ship else "You return to your ship."
            engine.message_log.add_message(msg, EQUIP_MSG)
            engine.pop_state()
            return

        if engine.player.fighter.hp <= 0:
            self._handle_player_death(engine, death_cause)
            return

        position = (engine.player.x, engine.player.y)
        for _ in range(consumed):
            self._after_player_turn(engine)
            if engine.current_state is not self:
                return

        self._update_fov_with_scan(engine)
        if moved or (engine.player.x, engine.player.y) != position:
            self._update_ground_underfoot(engine)
```

- [ ] **Step 4: Route the four input paths through it**

`ev_key` - replace everything from `if not consumed:` to the final `return True` with:

```python
        self._resolve_player_action(engine, consumed, moved=moved)
        return True
```

`_handle_ranged_input` - replace the block

```python
                consumed = RangedAction(target).perform(engine, engine.player)
                self._ranged_cursor = None
                if consumed:
                    ...
                self._update_ground_underfoot(engine)
```

with

```python
                consumed = RangedAction(target).perform(engine, engine.player)
                self._ranged_cursor = None
                self._resolve_player_action(engine, consumed, death_cause="Killed in a firefight.")
                if engine.current_state is self and self._death_cause is None:
                    self._update_ground_underfoot(engine)
```

The `death_cause` parameter exists only to keep this path's existing wording. Firing cannot hurt the shooter, so that cause may be unreachable: run `git grep -n "firefight" -- tests`. If no existing test reaches it through real play, delete the parameter and let this call use the default (YAGNI); do not add a test that forces HP to zero just to exercise it.

`_handle_interact_input` - replace `if consumed: ... self._update_fov_with_scan(engine)` with `self._resolve_player_action(engine, consumed)`.

`_handle_scan_input` - replace `if consumed: ... self._update_fov_with_scan(engine)` with `self._resolve_player_action(engine, consumed)`.

- [ ] **Step 5: Run the new tests, then the suite**

Run: `pytest tests/test_player_action_pipeline.py -q` - Expected: 5 passed.
Run: `pytest -q` - Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ui/tactical_state.py tests/test_player_action_pipeline.py
git commit -m "refactor(tactical): resolve every player action through one pipeline"
```

---

### Task 4: Move turn resolution out of the UI

**Files:**
- Create: `game/turn.py`
- Create: `tests/test_turn.py`
- Modify: `ui/tactical_state.py` (`_after_player_turn` becomes a thin caller; delete `_lose_to_space`)

**Interfaces:**
- Produces: `advance_turn(engine) -> str | None` - advances the world one tick; returns the death cause if the player died this tick, else `None`. `lose_to_space(engine, entity) -> None`.
- Consumes: nothing from earlier tasks. `TacticalState._after_player_turn` keeps its name and signature (34 test call sites rely on it).

- [ ] **Step 1: Write the failing tests** - `tests/test_turn.py`

```python
"""World turn resolution, independent of any UI state."""

from game.turn import advance_turn
from tests.conftest import make_creature, make_engine
from world import tile_types


def test_a_survivable_turn_returns_none_and_ticks_the_counter():
    engine = make_engine()
    engine.game_map.entities.append(make_creature(x=6, y=5, power=3, ai_state="hunting"))

    assert advance_turn(engine) is None
    assert engine.turn_counter == 1
    assert engine.player.fighter.hp == 7


def test_death_by_enemy_reports_overwhelmed():
    engine = make_engine()
    engine.game_map.entities.append(make_creature(x=6, y=5, power=50, ai_state="hunting"))

    assert advance_turn(engine) == "Overwhelmed by hostiles."
    assert engine.message_log.messages[-1][0] == "You died."


def test_drifting_off_the_map_is_lost_to_the_void():
    engine = make_engine()
    engine.game_map.tiles[:] = tile_types.space
    engine.player.x, engine.player.y = 9, 5
    engine.player.drifting = True
    engine.player.drift_direction = (1, 0)

    assert advance_turn(engine) == "Lost to the void."
    assert engine.player.fighter.hp == 0


def test_drifting_into_a_hull_is_fatal():
    engine = make_engine()
    engine.game_map.tiles[5, 5] = tile_types.space
    engine.player.drifting = True
    engine.player.drift_direction = (1, 0)

    assert advance_turn(engine) == "Slammed into the hull."


def test_active_dot_effect_death_reports_the_environment_before_enemies_act():
    engine = make_engine()
    engine.active_effects.append({"type": "radiation", "dot": 99, "remaining": 2})
    enemy = make_creature(x=8, y=8, ai_state="wandering")
    engine.game_map.entities.append(enemy)

    assert advance_turn(engine) == "Succumbed to the environment."
    assert (enemy.x, enemy.y) == (8, 8)
```

These five test only what is new: the returned cause, which replaces the UI callback, and that a death stops the turn. Everything else the turn does (drift movement, decompression, enemy hazards, entities lost to space) is already covered by the 34 existing tests that call `TacticalState._after_player_turn`, which now delegates here. Do not duplicate them.

| Test | Fails if |
|---|---|
| survivable turn | the counter stops ticking, enemies stop acting, or a living player is reported dead |
| death by enemy | the cause or the "You died." line is lost in the move |
| drift off the map / into a hull | either drift death returns the wrong cause or none |
| DoT death | an environment death lets the rest of the turn run anyway |

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_turn.py -q`
Expected: `ModuleNotFoundError: No module named 'game.turn'`.

- [ ] **Step 3: Create `game/turn.py`**

```python
"""One world tick after a player action: hazards, decompression, drift, enemies."""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.environment import (
    apply_environment_tick,
    apply_environment_tick_entity,
    process_decompression_step,
    trigger_decompression,
)
from game.hazards import apply_dot_effects

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

_RED = (255, 0, 0)
_GREY = (200, 200, 200)
_VOID = (180, 100, 255)


def advance_turn(engine: Engine) -> str | None:
    """Advance the world one tick. Returns the cause if the player died during it, else None."""
    engine.turn_counter += 1
    game_map = engine.game_map
    game_map.invalidate_entity_index()
    game_map.clear_fov_cache()

    apply_environment_tick(engine)
    apply_dot_effects(engine)
    if engine.player.fighter.hp <= 0:
        return "Succumbed to the environment."

    _process_decompression(engine)
    if engine.player.fighter.hp <= 0:
        return "Crushed by explosive decompression."

    cause = _drift_player(engine)
    if cause is not None:
        return cause
    _drift_others(engine)

    game_map.invalidate_entity_index()
    _run_enemies(engine)

    if engine.player.fighter.hp <= 0:
        engine.message_log.add_message("You died.", _RED)
        return "Overwhelmed by hostiles."
    return None


def lose_to_space(engine: Engine, entity: Entity) -> None:
    """Kill and remove an entity that drifted off the map or into a hull.

    It must end up dead, not merely off the map: rosters that outlive the
    map (boarding pirates) decide who is still a threat by HP.
    """
    if entity.fighter is not None:
        entity.fighter.hp = 0
    if entity in engine.game_map.entities:
        engine.game_map.entities.remove(entity)


def _process_decompression(engine: Engine) -> None:
    """Start any pending decompression, pull tagged entities, and clear those it crushed."""
    game_map = engine.game_map
    pending = game_map._pending_decompression
    if pending:
        game_map._pull_directions = trigger_decompression(
            engine, pending["breach_sources"], pending["newly_exposed"]
        )
        game_map._pending_decompression = None

    pull_dirs = game_map._pull_directions
    if pull_dirs:
        for entity in list(game_map.entities):
            if entity.decompression_moves > 0:
                process_decompression_step(game_map, entity, pull_dirs)
        if not any(e.decompression_moves > 0 for e in game_map.entities):
            game_map._pull_directions = None

    for entity in list(game_map.entities):
        if entity is engine.player:
            continue
        if entity.fighter and entity.fighter.hp <= 0:
            engine.message_log.add_message(f"The {entity.name} is crushed by the decompression!", _GREY)
            game_map.entities.remove(entity)


def _is_space(engine: Engine, x: int, y: int) -> bool:
    from world import tile_types

    return engine.game_map.tiles["tile_id"][x, y] == int(tile_types.space["tile_id"])


def _drift_player(engine: Engine) -> str | None:
    """Carry a drifting player one tile. Returns the death cause if the drift ends them."""
    player = engine.player
    if not player.drifting:
        return None
    dx, dy = player.drift_direction
    nx, ny = player.x + dx, player.y + dy
    if not engine.game_map.in_bounds(nx, ny):
        engine.message_log.add_message("You drift beyond reach... lost to the void.", _RED)
        player.fighter.hp = 0
        return "Lost to the void."
    # Only space tiles are passable while drifting
    if not _is_space(engine, nx, ny):
        engine.message_log.add_message("You slam into the hull. The impact is fatal.", _RED)
        player.fighter.hp = 0
        return "Slammed into the hull."
    player.x, player.y = nx, ny
    engine.message_log.add_message("You drift further into space...", _VOID)
    return None


def _drift_others(engine: Engine) -> None:
    for entity in list(engine.game_map.entities):
        if entity is engine.player or not entity.drifting:
            continue
        dx, dy = entity.drift_direction
        nx, ny = entity.x + dx, entity.y + dy
        if not engine.game_map.in_bounds(nx, ny):
            lose_to_space(engine, entity)
            continue
        if not _is_space(engine, nx, ny):
            lose_to_space(engine, entity)
            engine.message_log.add_message(f"The {entity.name} slams into the hull!", _GREY)
            continue
        entity.x, entity.y = nx, ny


def _run_enemies(engine: Engine) -> None:
    """Enemy AI turns, then per-tile hazard damage for whoever is still standing."""
    import debug

    if not debug.DISABLE_ENEMY_AI:
        for entity in list(engine.game_map.entities):
            if entity is engine.player:
                continue
            if entity.ai and entity.fighter and entity.fighter.hp > 0:
                entity.ai.perform(entity, engine)

    for entity in list(engine.game_map.entities):
        if entity is engine.player:
            continue
        if entity.fighter and entity.fighter.hp > 0:
            apply_environment_tick_entity(engine, entity)
```

Run: `pytest tests/test_turn.py -q` - Expected: 5 passed.

- [ ] **Step 4: Make `TacticalState._after_player_turn` a thin caller**

Replace the whole method body, and delete the `_lose_to_space` static method below it:

```python
    def _after_player_turn(self, engine: Engine) -> None:
        """Advance the world one tick; start the death fade if it killed the player."""
        from game.turn import advance_turn

        cause = advance_turn(engine)
        if cause is not None:
            self._handle_player_death(engine, cause)
            return

        # Interdiction resolution: if we're aboard the player ship and every
        # pirate is dead, end the interdiction.
        if getattr(self, "explore_ship", False):
            self._check_interdiction_resolution(engine)
```

- [ ] **Step 5: Full gate and commit**

Run: `git grep -n "_lose_to_space"` - Expected: no output.
Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add game/turn.py tests/test_turn.py ui/tactical_state.py
git commit -m "refactor(turn): move world turn resolution out of the tactical UI state"
```

---

### Task 5: Move the interdiction lifecycle out of the UI

**Files:**
- Modify: `game/interdiction.py` (add four functions; `tile_in_player_ship_region` uses the first)
- Modify: `ui/tactical_state.py` (delete `_direction_name`, `_DIRECTION_NAMES`, `_current_interdiction`, `_activate_interdiction_if_any`, `_detach_interdiction_pirates`, `_check_interdiction_resolution`)
- Modify: `ui/strategic_state.py` (three `getattr(system, "interdiction", None)` lookups)
- Modify: the two tests that call the deleted private methods
- Create: `tests/test_interdiction_session.py`

**Interfaces:**
- Produces, all in `game/interdiction.py`:
  - `current_interdiction(engine) -> Interdiction | None`
  - `prepare_ship_entry(engine) -> None` (old `_activate_interdiction_if_any`)
  - `detach_pirates(engine) -> None` (old `_detach_interdiction_pirates`)
  - `resolve_if_cleared(engine) -> bool` (old `_check_interdiction_resolution`; returns True when it resolved now)

- [ ] **Step 1: Write the failing tests** - `tests/test_interdiction_session.py`

```python
"""Interdiction lifecycle driven through the game layer, with no UI state involved."""

from engine.game_state import Engine
from game.interdiction import Interdiction, current_interdiction, detach_pirates, prepare_ship_entry, resolve_if_cleared
from tests.conftest import new_game


def _boarded():
    engine, _ = new_game(11)
    interdiction = Interdiction()
    engine.galaxy.systems[engine.galaxy.current_system].interdiction = interdiction
    prepare_ship_entry(engine)
    engine.game_map = engine.ship.game_map
    return engine, interdiction


def test_lifecycle_calls_are_safe_with_no_galaxy():
    """After a game over the galaxy is gone but states still unwind through these."""
    engine = Engine()

    assert current_interdiction(engine) is None
    assert resolve_if_cleared(engine) is False
    prepare_ship_entry(engine)
    detach_pirates(engine)


def test_prepare_ship_entry_starts_a_queued_interdiction_and_attaches_pirates():
    engine, interdiction = _boarded()

    assert interdiction.started is True
    assert engine.ship.game_map is interdiction.composite_map
    assert all(p in engine.ship.game_map.entities for p in interdiction.pirate_entities)
    assert any("clamped onto" in text for text, _ in engine.message_log.messages)


def test_resolve_if_cleared_waits_for_the_last_pirate():
    engine, interdiction = _boarded()

    assert resolve_if_cleared(engine) is False
    for pirate in interdiction.pirate_entities:
        pirate.fighter.hp = 0

    assert resolve_if_cleared(engine) is True
    assert interdiction.resolved is True
    assert resolve_if_cleared(engine) is False


def test_detach_pirates_takes_them_off_the_map_and_drops_the_dead():
    engine, interdiction = _boarded()
    dead = interdiction.pirate_entities[0]
    dead.fighter.hp = 0
    living = interdiction.pirate_entities[1:]

    detach_pirates(engine)

    assert interdiction.pirate_entities == living
    assert all(p not in engine.game_map.entities for p in [dead, *living])
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_interdiction_session.py -q`
Expected: `ImportError: cannot import name 'current_interdiction'`.

- [ ] **Step 3: Add the functions to `game/interdiction.py`** (below `restore_original_ship_map`)

```python
# ---------------------------------------------------------------------------
# Session lifecycle (driven by whichever state puts the player aboard)
# ---------------------------------------------------------------------------

_DIRECTION_NAMES: dict[tuple[int, int], str] = {
    (0, -1): "north",
    (0, 1): "south",
    (-1, 0): "west",
    (1, 0): "east",
}


def _direction_name(direction: tuple[int, int] | None) -> str:
    if direction is None:
        return "outer"
    return _DIRECTION_NAMES.get(tuple(direction), "outer")


def current_interdiction(engine) -> Interdiction | None:
    """The current system's Interdiction, or None."""
    galaxy = getattr(engine, "galaxy", None)
    if galaxy is None:
        return None
    system = galaxy.systems.get(galaxy.current_system)
    return system.interdiction if system is not None else None


def prepare_ship_entry(engine) -> None:
    """Bring the interdiction up to date as the player boards their ship.

    * Resolved with a stale composite → restore the original ship map.
    * Queued → start it (may swap ``engine.ship.game_map`` to the composite).
    * Started but composite missing (post-load) → rebuild it.
    * Always: reveal the breach and re-attach live pirates to the active map.
    """
    interdiction = current_interdiction(engine)
    if interdiction is None:
        return

    if interdiction.resolved:
        restore_original_ship_map(interdiction, engine.ship)
        return

    if not interdiction.started:
        rng = engine.rng(f"start_interdiction:{engine.galaxy.current_system}")
        start_interdiction(interdiction, engine.ship, rng)
        if interdiction.started:
            heading = _direction_name(interdiction.attach_direction)
            engine.message_log.add_message(
                f"A pirate boarding craft has clamped onto the {heading} airlock!",
                (255, 200, 100),
            )
        elif interdiction.resolved:
            # No facing-airlock pair was available - boarding attempt failed.
            engine.message_log.add_message(
                "The pirate craft couldn't find a docking point and broke off.",
                (200, 200, 200),
            )
            return
    elif interdiction.composite_map is None:
        # Started, but the composite was wiped (e.g. by a save/load cycle).
        if not rebuild_composite(interdiction, engine.ship):
            interdiction.resolve()
            return

    game_map = engine.ship.game_map
    # Reveal the corridor + spawn-room tiles so the breach is visible
    # on the map even before the player walks into FOV range.
    for tx, ty in interdiction.connector_tiles:
        if game_map.in_bounds(tx, ty):
            game_map.explored[tx, ty] = True
    if interdiction.craft_room is not None:
        room = interdiction.craft_room
        for tx in range(room.x1, room.x2 + 1):
            for ty in range(room.y1, room.y2 + 1):
                if game_map.in_bounds(tx, ty):
                    game_map.explored[tx, ty] = True
    # Drop dead pirates from the roster, then re-attach the live ones.
    interdiction.pirate_entities = [p for p in interdiction.pirate_entities if p.fighter and p.fighter.hp > 0]
    for pirate in interdiction.pirate_entities:
        if pirate not in game_map.entities:
            game_map.entities.append(pirate)
    game_map.invalidate_entity_index()


def detach_pirates(engine) -> None:
    """Strip pirates from the active map; the roster on the Interdiction keeps the living ones."""
    interdiction = current_interdiction(engine)
    if interdiction is None or not interdiction.started:
        return
    for pirate in list(interdiction.pirate_entities):
        if pirate in engine.game_map.entities:
            engine.game_map.entities.remove(pirate)
    interdiction.pirate_entities = [p for p in interdiction.pirate_entities if p.fighter and p.fighter.hp > 0]
    engine.game_map.invalidate_entity_index()


def resolve_if_cleared(engine) -> bool:
    """Resolve the interdiction once every pirate is dead. Returns True if it resolved just now.

    Map restoration stays deferred to the next ship exit so the player is
    never left standing on a tile that is about to vanish.
    """
    interdiction = current_interdiction(engine)
    if interdiction is None or not interdiction.started or interdiction.resolved:
        return False
    if interdiction.alive_pirate_count() > 0:
        return False
    interdiction.resolve()
    engine.message_log.add_message("Interdiction repelled - system clear.", (100, 255, 100))
    return True
```

In the same file, replace the first twelve lines of `tile_in_player_ship_region` (from `galaxy = getattr(engine, "galaxy", None)` through `interdiction = getattr(system, "interdiction", None)`) with `interdiction = current_interdiction(engine)`. Keep the comment and the `if interdiction is None or ...: return True` check that follow.

Run: `pytest tests/test_interdiction_session.py -q` - Expected: 4 passed.

| Test | Fails if |
|---|---|
| safe with no galaxy | unwinding a ship session after game over raises instead of doing nothing |
| prepare starts and attaches | boarding works only when a `TacticalState` drives it (the point of the move) |
| resolve waits for the last pirate | it resolves early, never, or announces the win twice |
| detach drops the dead | dead pirates stay on the roster and re-attach on the next boarding |

The fuller lifecycle (save/load, restore, travel block) stays covered by the existing `test_interdiction_*.py` files, which run through the same code via the state.

- [ ] **Step 4: Remove the copies from `ui/tactical_state.py` and call the new functions**

Delete `_DIRECTION_NAMES`, `_direction_name`, `_current_interdiction`, `_activate_interdiction_if_any`, `_detach_interdiction_pirates` and `_check_interdiction_resolution`. Then:

| Old call | New call |
|---|---|
| `self._activate_interdiction_if_any(engine)` in `_enter_ship` | `prepare_ship_entry(engine)` |
| `self._detach_interdiction_pirates(engine)` in `on_exit` | `detach_pirates(engine)` |
| `self._check_interdiction_resolution(engine)` in `on_exit` and `_after_player_turn` | `resolve_if_cleared(engine)` |
| `interdiction = self._current_interdiction(engine)` in `on_exit` and `_render_stats` | `interdiction = current_interdiction(engine)` |

Add the matching local `from game.interdiction import ...` in each function, as the file already does for `restore_original_ship_map`.

- [ ] **Step 5: Use `current_interdiction` in `ui/strategic_state.py`**

There are three lookups of the form `active = getattr(system, "interdiction", None)` (in `ev_key`, `_drift`, `on_render`). In `ev_key` and `on_render`, replace with `active = current_interdiction(engine)`. In `_drift`, keep reading from `source` (it is the system being left): `active = source.interdiction`. Import `current_interdiction` from `game.interdiction` at the top of each of those two methods.

- [ ] **Step 6: Update the two tests that call deleted methods**

Run: `git grep -n "_activate_interdiction_if_any\|_detach_interdiction_pirates" -- tests`

For each hit, replace `state._activate_interdiction_if_any(engine)` with `prepare_ship_entry(engine)` and `state._detach_interdiction_pirates(engine)` with `detach_pirates(engine)`, and add `from game.interdiction import detach_pirates, prepare_ship_entry` to that test module's imports.

- [ ] **Step 7: Full gate and commit**

Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add game/interdiction.py ui/tactical_state.py ui/strategic_state.py tests/
git commit -m "refactor(interdiction): move the session lifecycle out of the tactical UI state"
```

---

### Task 6: Move the HUD out of `TacticalState`

**Files:**
- Create: `ui/tactical_hud.py`
- Create: `tests/test_tactical_hud.py`
- Modify: `ui/tactical_state.py` (`_render_stats` becomes a thin caller)

**Interfaces:**
- Produces: `HudView` dataclass and `render_stats(console, engine, layout, view: HudView) -> None` in `ui/tactical_hud.py`.
- `TacticalState._render_stats(self, console, engine, layout)` keeps its name and signature (9 test call sites).

- [ ] **Step 1: Write the failing test** - `tests/test_tactical_hud.py`

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_tactical_hud.py -q`
Expected: `ModuleNotFoundError: No module named 'ui.tactical_hud'`.

- [ ] **Step 3: Create `ui/tactical_hud.py` by moving the method body**

Start the file with:

```python
"""The tactical stats panel: vitals, suit, hazards, loadout, ground text, nearby list, key hints."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from ui.colors import DARK_GRAY, EQUIP_MSG, GRAY, HEADER_SEP, HP_GREEN, HP_RED, HP_YELLOW, PROMPT
from ui.keys import action_keys

if TYPE_CHECKING:
    from engine.game_state import Engine

Color = tuple[int, int, int]

CTRL_LINES = 4
GROUND_MAX_LINES_DEFAULT = 8


@dataclass
class HudView:
    """What the panel needs to know about the tactical state that owns it."""

    location_label: str
    explore_ship: bool
    look_cursor: tuple[int, int] | None
    ranged_cursor: tuple[int, int] | None
    ground_lines: list[tuple[str, Color]]


def _hint(name: str) -> str:
    """Build a HUD hint like '[x] look' from the action_keys registry."""
    _, label, verb = action_keys()[name]
    return f"[{label}] {verb}"


def render_stats(console: Any, engine: Engine, layout: SimpleNamespace, view: HudView) -> None:
```

Then move the body of `TacticalState._render_stats` under that `def` verbatim, applying exactly these substitutions:

| In the moved body | Becomes |
|---|---|
| the `if self.location: ... elif ... else: loc_label = ...` block | delete it; use `view.location_label` where `loc_label` was printed |
| `getattr(self, "explore_ship", False)` | `view.explore_ship` |
| `self._current_interdiction(engine)` / `current_interdiction(engine)` | `current_interdiction(engine)` with `from game.interdiction import current_interdiction` at the top of the function |
| `self._look_cursor` | `view.look_cursor` |
| `self._ranged_cursor` | `view.ranged_cursor` |
| `self._ground_lines` | `view.ground_lines` |
| the function-local `from ui.colors import ...` lines | delete (now module-level) |

Move `CTRL_LINES`, `GROUND_MAX_LINES_DEFAULT` and `_hint` out of `ui/tactical_state.py` (they are used only by the panel). If `tests/` import any of them from `ui.tactical_state`, run `git grep -n "GROUND_MAX_LINES_DEFAULT\|CTRL_LINES\|_hint" -- tests` and point those imports at `ui.tactical_hud`.

- [ ] **Step 4: Make `_render_stats` a thin caller**

```python
    def _render_stats(self, console: Any, engine: Engine, layout: SimpleNamespace) -> None:
        from ui.tactical_hud import HudView, render_stats

        if self.location:
            label = f"{self.location.name} ({self.location.loc_type})"
        elif getattr(self, "explore_ship", False):
            label = "YOUR SHIP"
        else:
            label = "DREADNOUGHT"
        view = HudView(
            location_label=label,
            explore_ship=getattr(self, "explore_ship", False),
            look_cursor=self._look_cursor,
            ranged_cursor=self._ranged_cursor,
            ground_lines=self._ground_lines,
        )
        render_stats(console, engine, layout, view)
```

- [ ] **Step 5: Full gate and commit**

Run: `pytest tests/test_tactical_hud.py -q` - Expected: 3 passed.
Run: `pytest -q` - Expected: all pass. Run ruff (it will flag imports left unused in `tactical_state.py`; remove them).

```bash
git add ui/tactical_hud.py ui/tactical_state.py tests/test_tactical_hud.py tests/
git commit -m "refactor(hud): render the tactical stats panel from its own module"
```

---

### Task 7: Entity factories

**Files:**
- Create: `game/factories.py`
- Create: `tests/test_factories.py`
- Modify: `data/enemies.py` (remove `build_enemy_inventory` and the `Entity` imports)
- Modify: `world/dungeon_gen/spawning.py` (`_spawn_enemies`, `_spawn_items`)
- Modify: `game/interdiction.py` (`_spawn_pirates_in_room`)
- Modify: `game/actions.py` (`InteractAction` loot)
- Modify: `debug.py` (`build_debug_inventory`)
- Modify: tests that import `build_enemy_inventory` from `data.enemies`

**Interfaces:**
- Produces, in `game/factories.py`:
  - `build_item_entity(definition: ItemDef | ScannerDef | dict, x: int = 0, y: int = 0, *, rng: random.Random | None = None) -> Entity`
  - `build_enemy_inventory(defn: EnemyDef, rng: random.Random) -> list[Entity]`
  - `build_enemy(defn: EnemyDef, x: int, y: int, rng: random.Random) -> Entity`

**Deliberate behaviour change (the only one in this task):** debug starting items are now built non-blocking like every other item. Today `debug.build_debug_inventory` omits `blocks_movement=False`, so those items block movement and cannot be picked up once dropped on the ship floor.

**RNG contract:** `build_enemy` draws only inside `build_enemy_inventory`, exactly as the two call sites do today. The caller still makes the `rng.choice(...)` that picks the definition.

- [ ] **Step 1: Write the failing tests** - `tests/test_factories.py`

```python
"""One place builds item and enemy entities from their data definitions."""

import random

from data.enemies import enemy_by_name
from data.items import item_by_name, scanner_by_name
from game.actions import PickupAction
from game.factories import build_enemy, build_enemy_inventory, build_item_entity
from tests.conftest import enter_ship, make_engine, new_game


def test_a_built_item_can_be_picked_up_and_used_as_what_it_is():
    engine = make_engine()
    engine.player.max_inventory = 10
    engine.game_map.entities.append(build_item_entity(item_by_name("Med-kit"), 5, 5))

    assert PickupAction().perform(engine, engine.player) == 1
    assert [(i.name, i.item) for i in engine.player.inventory] == [("Med-kit", {"type": "heal", "value": 5})]


def test_scanner_uses_come_from_the_given_rng_not_the_global_one():
    def eight_scanners(global_seed: int) -> list[int]:
        random.seed(global_seed)
        rng = random.Random(5)
        return [build_item_entity(scanner_by_name("Basic Scanner"), rng=rng).item["uses"] for _ in range(8)]

    assert eight_scanners(1) == eight_scanners(2)


def test_enemy_starts_in_the_state_and_body_its_definition_names():
    drone = build_enemy(enemy_by_name("Security Drone"), 0, 0, random.Random(1))
    rat = build_enemy(enemy_by_name("Rat"), 0, 0, random.Random(1))

    assert (drone.ai_state, drone.organic) == ("sleeping", False)
    assert (rat.ai_state, rat.organic) == ("wandering", True)


def test_enemy_melee_power_includes_its_best_weapon():
    defn = enemy_by_name("Pirate")
    for seed in range(200):
        enemy = build_enemy(defn, 0, 0, random.Random(seed))
        bonus = max(
            (i.item["value"] for i in enemy.inventory if i.item.get("weapon_class") == "melee"),
            default=0,
        )
        assert enemy.fighter.power == defn.power + bonus


def test_build_enemy_draws_exactly_what_the_inventory_roll_draws():
    defn = enemy_by_name("Pirate")
    via_factory, via_inventory = random.Random(9), random.Random(9)

    build_enemy(defn, 0, 0, via_factory)
    build_enemy_inventory(defn, via_inventory)

    assert via_factory.random() == via_inventory.random()


def test_a_debug_starting_item_on_the_ship_floor_can_be_picked_up():
    import debug

    debug.START_INVENTORY = [("item", "Med-kit")]
    engine, _ = new_game()
    engine.ship.cargo = debug.build_debug_inventory()
    enter_ship(engine)
    medkit = next(e for e in engine.game_map.entities if e.name == "Med-kit")
    engine.player.x, engine.player.y = medkit.x, medkit.y
    engine.game_map.invalidate_entity_index()

    assert PickupAction().perform(engine, engine.player) == 1
    assert medkit in engine.player.inventory
```

| Test | Fails if |
|---|---|
| built item can be picked up | the factory builds a blocking or mis-typed item |
| scanner uses from the given rng | the factory falls back to the global RNG, breaking seeded loot |
| enemy state and body | the definition's AI state or organic flag is not applied to the built enemy |
| melee power includes best weapon | power is not recalculated after the inventory roll |
| draws exactly the inventory roll | the factory adds or drops an RNG draw, shifting every seeded map |
| debug item can be picked up | debug items are still built as blocking entities (today's bug) |

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_factories.py -q`
Expected: `ModuleNotFoundError: No module named 'game.factories'`.

- [ ] **Step 3: Create `game/factories.py`**

```python
"""Build item and enemy entities from their data definitions."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from data.items import ItemDef, ScannerDef, build_item_data, item_by_name
from game.ai import CreatureAI
from game.entity import Entity, Fighter
from game.helpers import recalc_melee_power_ai

if TYPE_CHECKING:
    import random

    from data.enemies import EnemyDef


def build_item_entity(
    definition: ItemDef | ScannerDef | dict[str, Any],
    x: int = 0,
    y: int = 0,
    *,
    rng: random.Random | None = None,
) -> Entity:
    """An item lying at (x, y), from an item/scanner definition or a loot dict."""
    d = asdict(definition) if is_dataclass(definition) else definition
    return Entity(
        x=x,
        y=y,
        char=d["char"],
        color=d["color"],
        name=d["name"],
        blocks_movement=False,
        item=build_item_data(definition, rng=rng),
    )


def build_enemy_inventory(defn: EnemyDef, rng: random.Random) -> list[Entity]:
    """Roll loot table and return item Entities for an enemy's starting inventory."""
    if not defn.loot_table:
        return []
    # 25% chance this enemy carries nothing
    if rng.random() < 0.25:
        return []

    items: list[Entity] = []
    for item_name, prob in defn.loot_table:
        if len(items) >= defn.max_inventory:
            break
        if rng.random() < prob:
            items.append(build_item_entity(item_by_name(item_name)))
    return items


def build_enemy(defn: EnemyDef, x: int, y: int, rng: random.Random) -> Entity:
    """A creature of type *defn* at (x, y), with rolled inventory and melee power to match."""
    enemy = Entity(
        x=x,
        y=y,
        char=defn.char,
        color=defn.color,
        name=defn.name,
        blocks_movement=True,
        fighter=Fighter(hp=defn.hp, max_hp=defn.hp, defense=defn.defense, power=defn.power),
        ai=CreatureAI(),
        organic=defn.organic,
        gore_color=defn.gore_color,
    )
    enemy.ai_config = defn.to_ai_config()
    enemy.ai_state = enemy.ai_config.get("ai_initial_state", "wandering")
    enemy.inventory = build_enemy_inventory(defn, rng)
    enemy.max_inventory = defn.max_inventory
    recalc_melee_power_ai(enemy)
    return enemy
```

Note: `build_enemy_inventory` built its items with no `rng`, and `ITEMS` (the only things in loot tables) contains no scanners, so passing no `rng` to `build_item_entity` draws nothing, as before.

- [ ] **Step 4: Replace the hand-written constructions**

1. `data/enemies.py`: delete `build_enemy_inventory`, the `import random as _random_mod`, the `TYPE_CHECKING` import of `Entity`, and the now-empty `if TYPE_CHECKING:` block. Keep `_validate_loot_tables`.
2. `world/dungeon_gen/spawning.py`, `_spawn_enemies`: replace everything from `ai_config = defn.to_ai_config()` through `recalc_melee_power_ai(entity)` with `entity = build_enemy(defn, x, y, rng)`. The line `defn = rng.choice(ENEMIES)` stays directly above it.
3. Same file, `_spawn_items`: replace the `game_map.entities.append(Entity(... item=build_item_data(defn)))` with `game_map.entities.append(build_item_entity(defn, x, y))`.
4. Same file: fix imports to `from data.enemies import ENEMIES`, `from data.items import ITEMS, all_loot`, `from game.entity import Entity`, `from game.factories import build_enemy, build_item_entity`. (`Entity` is still used by `_make_interactable`.)
5. `game/interdiction.py`, `_spawn_pirates_in_room`: replace the loop body after `defn = rng.choice(defns)` with `pirates.append(build_enemy(defn, x, y, rng))`, and reduce the function's local imports to `from game.factories import build_enemy`.
6. `game/actions.py`, `InteractAction.perform`: replace the `item_data = build_item_data(loot)` / `item_ent = _Entity(...)` block with `item_ent = build_item_entity(loot, entity.x, entity.y)` and import `build_item_entity` from `game.factories` in place of the two old local imports.
7. `debug.py`, `build_debug_inventory`: replace the `item_data = ...` / `result.append(Entity(...))` lines with `result.append(build_item_entity(defn))`, importing `from game.factories import build_item_entity` in place of `from game.entity import Entity`.

- [ ] **Step 5: Repoint test imports**

```bash
git grep -l "build_enemy_inventory" -- tests | xargs sed -i -b -E 's/from data\.enemies import (.*)build_enemy_inventory/from game.factories import build_enemy_inventory\nfrom data.enemies import \1/'
```

Then open each changed file and tidy the two import lines by hand (remove a trailing comma or an empty `from data.enemies import` line). Verify: `git grep -n "data.enemies import.*build_enemy_inventory"` - Expected: no output.

- [ ] **Step 6: Gates and commit**

Run: `pytest tests/test_factories.py tests/test_dungeon_gen_golden.py -q` - Expected: all pass (the golden test proves the RNG order held).
Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add game/factories.py tests/ data/enemies.py world/dungeon_gen/spawning.py game/interdiction.py game/actions.py debug.py
git commit -m "refactor(factories): build item and enemy entities in one module"
```

---

### Task 8: Fix and enforce the import layering

**Files:**
- Move: `ui/colors.py` → `data/colors.py`
- Move: `ui/keys.py` → `engine/keys.py`
- Move: `web/console_serializer.py` → `engine/console_serializer.py`
- Modify: `world/game_map.py` (remove `animate_space`), `ui/viewport_renderer.py` (add `render_map_starfield`), `ui/tactical_state.py` (call it)
- Create: `tests/test_layering.py`

**Interfaces:**
- Produces: `render_map_starfield(console, game_map, cam_x: int, cam_y: int, vp_x: int, vp_y: int, vp_w: int, vp_h: int) -> None` in `ui/viewport_renderer.py`.
- Layer rule (runtime imports only; `if TYPE_CHECKING:` blocks are exempt):

| Package | May import |
|---|---|
| `data` | `data` |
| `engine` | `engine`, `data` |
| `game`, `world` | `game`, `world`, `engine`, `data` |
| `ui` | `ui`, `game`, `world`, `engine`, `data` |
| `web` | anything |

- [ ] **Step 1: Write the failing tests** - `tests/test_layering.py`

```python
"""Packages may only import from their own layer or the layers below it."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

ALLOWED: dict[str, set[str]] = {
    "data": {"data"},
    "engine": {"engine", "data"},
    "game": {"game", "world", "engine", "data"},
    "world": {"game", "world", "engine", "data"},
    "ui": {"ui", "game", "world", "engine", "data"},
}
PACKAGES = {*ALLOWED, "web"}


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_imports(path: Path) -> set[str]:
    """Top-level package names imported by *path* at runtime (TYPE_CHECKING blocks excluded)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    typing_only: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                typing_only.update(id(n) for n in ast.walk(child))
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in typing_only:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found & PACKAGES


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_only_imports_its_own_layer_or_below(package):
    violations = [
        f"{path.relative_to(ROOT).as_posix()} imports {target}"
        for path in sorted((ROOT / package).rglob("*.py"))
        for target in sorted(_runtime_imports(path) - ALLOWED[package])
    ]

    assert violations == []


@pytest.mark.parametrize("module", ["main", "web.server", "engine.game_state", "game.turn", "world.dungeon_gen"])
def test_module_imports_cleanly_in_a_fresh_process(module):
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", f"import {module}"], cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_layering.py -q`
Expected: the `engine`, `game` and `world` cases fail, listing `game/actions.py imports ui` (and six more `game` files), `engine/game_state.py imports ui`, `engine/game_state.py imports web`, `world/game_map.py imports ui`. `data`, `ui` and the fresh-process cases pass.

- [ ] **Step 3: Move the three modules and repoint every import**

```bash
git mv ui/colors.py data/colors.py
git mv ui/keys.py engine/keys.py
git mv web/console_serializer.py engine/console_serializer.py
git grep -lE 'ui\.colors|ui\.keys|web\.console_serializer' -- '*.py' | xargs sed -i -b -E 's/\bui\.colors\b/data.colors/g; s/\bui\.keys\b/engine.keys/g; s/\bweb\.console_serializer\b/engine.console_serializer/g'
```

Check for the other import spelling: `git grep -nE 'from (ui|web) import .*\b(colors|keys|console_serializer)\b'` - Expected: no output. If there is any, rewrite those lines to `from data import colors`, `from engine import keys`, `from engine import console_serializer`.

If `tests/test_engine_package.py` or `tests/test_console_serializer.py` assert on module locations, update the asserted paths to the new ones.

- [ ] **Step 4: Move the map starfield render from `world` to `ui`**

In `ui/viewport_renderer.py`, add at the end:

```python
def render_map_starfield(
    console,
    game_map,
    cam_x: int,
    cam_y: int,
    vp_x: int,
    vp_y: int,
    vp_w: int,
    vp_h: int,
) -> None:
    """Overlay the animated starfield on a map's visible space tiles within the viewport."""
    if not game_map.has_space:
        return

    from world import tile_types

    space_tid = int(tile_types.space["tile_id"])
    rw = min(vp_w, game_map.width - cam_x)
    rh = min(vp_h, game_map.height - cam_y)
    if rw <= 0 or rh <= 0:
        return

    ms = (slice(cam_x, cam_x + rw), slice(cam_y, cam_y + rh))
    mask = game_map.visible[ms] & (game_map.tiles["tile_id"][ms] == space_tid)
    if not np.any(mask):
        return

    # Exclude space tiles occupied by visible entities
    entity_positions = set()
    for e in game_map.entities:
        if game_map.in_bounds(e.x, e.y) and game_map.visible[e.x, e.y]:
            ex, ey = e.x - cam_x, e.y - cam_y
            if 0 <= ex < rw and 0 <= ey < rh:
                entity_positions.add((ex, ey))

    render_starfield_bg(
        console,
        vp_x,
        vp_y,
        rw,
        rh,
        seed=game_map.space_seed,
        t=time.time(),
        coord_x=cam_x,
        coord_y=cam_y,
        cell_mask=mask,
        skip_positions=entity_positions,
    )
```

Delete `GameMap.animate_space` from `world/game_map.py`.

In `ui/tactical_state.py` `on_render`, replace the `engine.game_map.animate_space(console, cam_x, cam_y, vp_x=0, vp_y=0, vp_w=..., vp_h=...)` call with:

```python
        from ui.viewport_renderer import render_map_starfield

        render_map_starfield(
            console,
            engine.game_map,
            cam_x,
            cam_y,
            vp_x=0,
            vp_y=0,
            vp_w=layout.viewport_w,
            vp_h=layout.viewport_h,
        )
```

Update tests that call the old method: run `git grep -n "animate_space" -- tests`. For each `gm.animate_space(console, a, b, ...)`, write `render_map_starfield(console, gm, a, b, ...)` and add `from ui.viewport_renderer import render_map_starfield` to that module. Where a test patches `ui.viewport_renderer.render_starfield_bg`, the patch target is unchanged.

- [ ] **Step 5: Run the layering tests**

Run: `pytest tests/test_layering.py -q`
Expected: 10 passed. If `game` still lists a violation, it is a leftover upward import; fix the import, do not widen `ALLOWED`.

- [ ] **Step 6: Full gate and commit**

Run: `pytest -q` - Expected: all pass. Run ruff. Update the "Project structure" block in `README.md`: move `colors.py` under `data/`, `keys.py` under `engine/`, and add `console_serializer.py` under `engine/`.

```bash
git add -A data engine ui web world tests README.md
git commit -m "refactor(layers): move colours, keys and the console serializer down and enforce import layering"
```

---

### Task 9: Type-keyed handlers for salvage, consumables and AI states

**Files:**
- Create: `game/salvage.py`
- Create: `tests/test_salvage.py`
- Modify: `ui/tactical_state.py` (`on_exit` mission branch)
- Modify: `game/consumables.py` (`use_consumable`)
- Modify: `game/ai.py` (`CreatureAI.perform`)

**Interfaces:**
- Produces: `unload_mission_salvage(engine, inventory: list[Entity]) -> None` in `game/salvage.py`. It mutates `inventory` in place, removing every item it hands to the ship.
- `use_consumable(engine, player, item) -> bool` keeps its signature.

- [ ] **Step 1: Write the failing tests** - `tests/test_salvage.py`

```python
"""Mission salvage is handed to the ship by item type, from one table."""

from game.entity import Entity
from game.salvage import unload_mission_salvage
from tests.conftest import make_heal_item, new_game


def _item(name: str, item_type: str, value: int) -> Entity:
    return Entity(name=name, blocks_movement=False, item={"type": item_type, "value": value})


def _texts(engine) -> list[str]:
    return [text for text, _ in engine.message_log.messages]


def test_reactor_core_becomes_fuel_and_leaves_the_inventory():
    engine, _ = new_game()
    engine.ship.fuel = 2
    inventory = [_item("Reactor Core", "reactor_core", 5), make_heal_item()]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.fuel == 7
    assert [i.name for i in inventory] == ["Medkit"]
    assert "Reactor core converted to fuel. (+5 fuel)" in _texts(engine)


def test_reactor_core_at_a_full_tank_is_consumed_silently():
    engine, _ = new_game()
    engine.ship.fuel = engine.ship.max_fuel
    inventory = [_item("Reactor Core", "reactor_core", 5)]

    unload_mission_salvage(engine, inventory)

    assert inventory == []
    assert not any("converted to fuel" in t for t in _texts(engine))


def test_hull_patch_repairs_the_hull():
    engine, _ = new_game()
    engine.ship.hull = 4
    inventory = [_item("Hull Patch", "hull_repair", 3)]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.hull == 7
    assert inventory == []


def test_dreadnought_core_goes_to_cargo():
    engine, _ = new_game()
    core = _item("Dreadnought Core", "dreadnought_core", 99)
    inventory = [core]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.cargo == [core]
    assert inventory == []


def test_last_nav_unit_reveals_the_dreadnought_once():
    engine, _ = new_game()
    engine.ship.nav_units = engine.ship.max_nav_units - 1
    inventory = [_item("Navigation Unit", "nav_unit", 1)]

    unload_mission_salvage(engine, inventory)

    assert engine.ship.nav_units == engine.ship.max_nav_units
    assert engine.galaxy.dreadnought_system is not None
    assert _texts(engine).count("All navigation units installed. The Dreadnought's coordinates are locked in!") == 1


def test_ordinary_items_are_left_alone():
    engine, _ = new_game()
    inventory = [make_heal_item()]

    unload_mission_salvage(engine, inventory)

    assert len(inventory) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_salvage.py -q`
Expected: `ModuleNotFoundError: No module named 'game.salvage'`.

- [ ] **Step 3: Create `game/salvage.py`**

```python
"""Hand mission salvage over to the ship when the player comes back aboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from data.colors import EQUIP_MSG

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

type SalvageHandler = Callable[[Engine, Entity], None]


def _convert_reactor_core(engine: Engine, core: Entity) -> None:
    added = engine.ship.add_fuel(core.item["value"])
    if added > 0:
        engine.message_log.add_message(f"Reactor core converted to fuel. (+{added} fuel)", EQUIP_MSG)


def _install_nav_unit(engine: Engine, unit: Entity) -> None:
    engine.ship.add_nav_unit()
    engine.message_log.add_message("Navigation unit installed.", (0, 255, 200))


def _patch_hull(engine: Engine, kit: Entity) -> None:
    repaired = engine.ship.repair_hull(kit.item["value"])
    if repaired > 0:
        engine.message_log.add_message(f"Hull patched. (+{repaired} hull integrity)", EQUIP_MSG)


def _stow_dreadnought_core(engine: Engine, core: Entity) -> None:
    engine.ship.add_cargo(core)
    engine.message_log.add_message("Dreadnought core secured in cargo hold.", (255, 50, 50))


def _reveal_dreadnought_if_ready(engine: Engine) -> None:
    """Spawn the Dreadnought system once every nav unit is installed."""
    if engine.ship.nav_units < engine.ship.max_nav_units:
        return
    if not engine.galaxy or engine.galaxy.dreadnought_system:
        return
    engine.galaxy.spawn_dreadnought()
    engine.message_log.add_message(
        "All navigation units installed. The Dreadnought's coordinates are locked in!",
        (255, 200, 0),
    )


# Item type → (what the ship does with one, what happens after all of that type are in).
# Order is the order the messages appear in. Add a salvage type here, nowhere else.
_SALVAGE: dict[str, tuple[SalvageHandler, Callable[[Engine], None] | None]] = {
    "reactor_core": (_convert_reactor_core, None),
    "nav_unit": (_install_nav_unit, _reveal_dreadnought_if_ready),
    "hull_repair": (_patch_hull, None),
    "dreadnought_core": (_stow_dreadnought_core, None),
}


def unload_mission_salvage(engine: Engine, inventory: list[Entity]) -> None:
    """Give the ship every salvage item in *inventory*, removing each from the list."""
    for item_type, (handle, afterwards) in _SALVAGE.items():
        for item in [i for i in inventory if i.item and i.item.get("type") == item_type]:
            handle(engine, item)
            inventory.remove(item)
        if afterwards is not None:
            afterwards(engine)
```

(`data.colors` exists after Task 8. If this task runs before Task 8, import `EQUIP_MSG` from `ui.colors` and let Task 8's rename fix it.)

Run: `pytest tests/test_salvage.py -q` - Expected: 6 passed. Each fails if its item type's handler is missing from the table, has the wrong effect, or leaves the item in the player's inventory; the last fails if the table swallows items it does not own. Message order is not asserted: it is a presentation detail, not correctness.

- [ ] **Step 4: Use it in `TacticalState.on_exit`**

In the mission branch, replace everything from `# Convert reactor cores to fuel` through the end of the `d_cores` loop (the whole `if engine.ship is not None:` block) with:

```python
                if engine.ship is not None:
                    from game.salvage import unload_mission_salvage

                    unload_mission_salvage(engine, saved_inventory)
```

- [ ] **Step 5: Table-drive `use_consumable`**

In `game/consumables.py`, split the three `if itype == ...` bodies into `_use_heal(engine, player, item) -> bool`, `_use_repair(engine, player, item) -> bool` and `_use_o2(engine, player, item) -> bool`. Each keeps its body exactly, except: drop the `_consume(player, item)` call and `return True` where it consumed, `return False` where it did not. Then:

```python
_EFFECTS: dict[str, Callable[[Engine, Entity, Entity], bool]] = {
    "heal": _use_heal,
    "repair": _use_repair,
    "o2": _use_o2,
}


def use_consumable(engine: Engine, player: Entity, item: Entity) -> bool:
    """Apply consumable effect. Removes item from player.inventory on success.

    Returns True if consumed, False if use failed (nothing to repair, no suit, etc).
    """
    effect = _EFFECTS.get(item.item.get("type")) if item.item else None
    if effect is None or not effect(engine, player, item):
        return False
    _consume(player, item)
    return True
```

Add `from collections.abc import Callable` under the `TYPE_CHECKING` guard's sibling imports (module-level, since the dict annotation is evaluated lazily under `from __future__ import annotations`). `tests/test_consumables.py` already covers all three effects and both outcomes; it is the test for this step.

- [ ] **Step 6: Table-drive the AI state dispatch**

In `game/ai.py`, replace the `if state == "sleeping": ... elif ...` chain at the end of `CreatureAI.perform` with:

```python
        handler = self._STATE_HANDLERS.get(owner.ai_state)
        if handler is not None:
            handler(self, owner, engine)
```

and add, after the last `_do_*` method in the class body:

```python
    _STATE_HANDLERS = {
        "sleeping": _do_sleeping,
        "wandering": _do_wandering,
        "hunting": _do_hunting,
        "fleeing": _do_fleeing,
    }
```

`tests/test_ai.py` (1,569 lines) is the test for this step.

- [ ] **Step 7: Full gate and commit**

Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add game/salvage.py tests/test_salvage.py ui/tactical_state.py game/consumables.py game/ai.py
git commit -m "refactor(handlers): dispatch salvage, consumables and AI states from tables"
```

---

### Task 10: Grid utilities - one BFS, one neighbour mask

**Files:**
- Create: `world/grid.py`
- Create: `tests/test_grid.py`
- Modify: `game/environment.py` (three BFS functions), `world/game_map.py` (flood-fill import), `world/boarding_craft.py` (`_bfs_corridor`), `world/dungeon_gen/hull.py` (`_convert_hull_to_space`)
- Modify: tests that import `_flood_fill_hazard`

**Interfaces:**
- Produces, in `world/grid.py`:
  - `CARDINALS`, `DIAGONALS`, `NEIGHBOURS_8`: tuples of `(dx, dy)`. `CARDINALS` is `((1, 0), (-1, 0), (0, 1), (0, -1))` - this exact order.
  - `bfs(sources: Iterable[Pos], passable: Callable[[int, int], bool], *, max_distance: int | None = None) -> tuple[dict[Pos, int], dict[Pos, Pos | None]]` returning `(distance, parent)`.
  - `path_to(parent: dict[Pos, Pos | None], goal: Pos) -> list[Pos] | None`
  - `flood_fill_walkable(game_map, sources: list[Pos]) -> np.ndarray`
  - `neighbour_any(mask: np.ndarray, offsets=CARDINALS) -> np.ndarray`
  - `neighbour_count(mask: np.ndarray, offsets=CARDINALS) -> np.ndarray`

**Determinism contract:** `bfs` expands neighbours in `CARDINALS` order and never revisits a node, exactly like the four functions it replaces. Pull directions and corridor routes depend on this.

- [ ] **Step 1: Write the failing tests** - `tests/test_grid.py`

```python
"""Shared grid primitives: breadth-first search and neighbour masks."""

import numpy as np

from tests.conftest import make_arena
from world import tile_types
from world.grid import DIAGONALS, NEIGHBOURS_8, bfs, flood_fill_walkable, neighbour_any, neighbour_count, path_to


def _open(w: int, h: int, blocked: set = frozenset()):
    return lambda x, y: 0 <= x < w and 0 <= y < h and (x, y) not in blocked


def test_bfs_distances_are_manhattan_on_an_open_grid():
    dist, parent = bfs([(0, 0)], _open(4, 4))

    assert dist[(3, 3)] == 6
    assert len(dist) == 16
    assert parent[(0, 0)] is None


def test_bfs_goes_round_obstacles_and_stops_at_walls():
    wall = {(1, 0), (1, 1), (1, 2)}
    dist, _ = bfs([(0, 0)], _open(3, 4, wall))

    assert dist[(2, 0)] == 8
    assert all(p not in dist for p in wall)


def test_bfs_respects_max_distance():
    dist, _ = bfs([(0, 0)], _open(10, 1), max_distance=3)

    assert max(dist.values()) == 3
    assert (4, 0) not in dist


def test_bfs_from_several_sources_takes_the_nearest():
    dist, _ = bfs([(0, 0), (9, 0)], _open(10, 1))

    assert dist[(4, 0)] == 4
    assert dist[(6, 0)] == 3


def test_sources_are_included_even_when_not_passable():
    dist, _ = bfs([(0, 0)], lambda x, y: False)

    assert dist == {(0, 0): 0}


def test_parent_prefers_the_first_cardinal_that_reaches_a_tile():
    # (1, 1) is reached from both (1, 0) and (0, 1). (1, 0) is discovered first
    # (east is the first cardinal), so it is expanded first and becomes the parent.
    _, parent = bfs([(0, 0)], _open(2, 2))

    assert parent[(1, 1)] == (1, 0)


def test_path_to_walks_the_parents_back():
    _, parent = bfs([(0, 0)], _open(3, 1))

    assert path_to(parent, (2, 0)) == [(0, 0), (1, 0), (2, 0)]
    assert path_to(parent, (9, 9)) is None


def test_flood_fill_walkable_marks_reachable_floor_and_its_sources():
    game_map = make_arena(7, 5)
    for y in range(5):
        game_map.tiles[3, y] = tile_types.wall

    filled = flood_fill_walkable(game_map, [(1, 1), (99, 99)])

    assert filled[2, 3] and not filled[4, 1]
    assert filled.shape == (7, 5)
    assert not filled[3, 1]


def test_neighbour_any_cardinal_and_eight_way():
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True

    cardinal = neighbour_any(mask)
    eight = neighbour_any(mask, NEIGHBOURS_8)

    assert cardinal.sum() == 4 and cardinal[0, 1] and not cardinal[0, 0] and not cardinal[1, 1]
    assert eight.sum() == 8 and eight[0, 0]
    assert neighbour_any(mask, DIAGONALS).sum() == 4


def test_neighbour_masks_do_not_wrap_at_the_edges():
    mask = np.zeros((3, 3), dtype=bool)
    mask[0, 0] = True

    assert neighbour_any(mask, NEIGHBOURS_8).sum() == 3
    assert not neighbour_any(mask)[2, 0]


def test_neighbour_count_counts_cardinal_neighbours():
    mask = np.ones((3, 3), dtype=bool)

    counts = neighbour_count(mask)

    assert counts[1, 1] == 4 and counts[0, 0] == 2 and counts[0, 1] == 3
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_grid.py -q`
Expected: `ModuleNotFoundError: No module named 'world.grid'`.

- [ ] **Step 3: Create `world/grid.py`**

```python
"""Grid primitives shared by hazards, decompression, corridor routing and hull cleanup."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from world.game_map import GameMap

type Pos = tuple[int, int]

# Expansion order is part of the contract: pull directions and corridor
# routes are whichever neighbour reaches a tile first.
CARDINALS: tuple[Pos, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONALS: tuple[Pos, ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))
NEIGHBOURS_8: tuple[Pos, ...] = CARDINALS + DIAGONALS


def bfs(
    sources: Iterable[Pos],
    passable: Callable[[int, int], bool],
    *,
    max_distance: int | None = None,
) -> tuple[dict[Pos, int], dict[Pos, Pos | None]]:
    """4-connected breadth-first search from *sources* through *passable* tiles.

    Returns ``(distance, parent)``. Sources are always included, at distance 0
    with parent ``None``, whether or not they are passable themselves.
    """
    distance: dict[Pos, int] = {}
    parent: dict[Pos, Pos | None] = {}
    queue: deque[Pos] = deque()
    for source in sources:
        if source not in distance:
            distance[source] = 0
            parent[source] = None
            queue.append(source)

    while queue:
        current = queue.popleft()
        steps = distance[current]
        if max_distance is not None and steps >= max_distance:
            continue
        for dx, dy in CARDINALS:
            neighbour = (current[0] + dx, current[1] + dy)
            if neighbour in distance or not passable(*neighbour):
                continue
            distance[neighbour] = steps + 1
            parent[neighbour] = current
            queue.append(neighbour)
    return distance, parent


def path_to(parent: dict[Pos, Pos | None], goal: Pos) -> list[Pos] | None:
    """The route from a source to *goal* recorded in *parent*, or None if the search never reached it."""
    if goal not in parent:
        return None
    path: list[Pos] = []
    node: Pos | None = goal
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


def walkable(game_map: GameMap) -> Callable[[int, int], bool]:
    """A *passable* predicate for in-bounds walkable tiles of *game_map*."""
    tiles = game_map.tiles["walkable"]
    return lambda x, y: game_map.in_bounds(x, y) and bool(tiles[x, y])


def flood_fill_walkable(game_map: GameMap, sources: list[Pos]) -> np.ndarray:
    """Bool array (width, height) of tiles reachable from in-bounds *sources* over walkable tiles."""
    result = np.full((game_map.width, game_map.height), fill_value=False, order="F")
    starts = [s for s in sources if game_map.in_bounds(*s)]
    distance, _ = bfs(starts, walkable(game_map))
    for x, y in distance:
        result[x, y] = True
    return result


def _neighbour(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """out[x, y] = mask[x + dx, y + dy], False where that falls off the grid."""
    w, h = mask.shape
    out = np.zeros_like(mask)
    dst_x, src_x = slice(max(-dx, 0), w - max(dx, 0)), slice(max(dx, 0), w - max(-dx, 0))
    dst_y, src_y = slice(max(-dy, 0), h - max(dy, 0)), slice(max(dy, 0), h - max(-dy, 0))
    out[dst_x, dst_y] = mask[src_x, src_y]
    return out


def neighbour_any(mask: np.ndarray, offsets: Iterable[Pos] = CARDINALS) -> np.ndarray:
    """True where any neighbour at *offsets* is set in *mask*."""
    result = np.zeros(mask.shape, dtype=bool)
    for dx, dy in offsets:
        result |= _neighbour(mask, dx, dy).astype(bool)
    return result


def neighbour_count(mask: np.ndarray, offsets: Iterable[Pos] = CARDINALS) -> np.ndarray:
    """How many neighbours at *offsets* are set in *mask*, per cell."""
    result = np.zeros(mask.shape, dtype=int)
    for dx, dy in offsets:
        result += _neighbour(mask, dx, dy)
    return result
```

Run: `pytest tests/test_grid.py -q` - Expected: 11 passed. Every expected value is worked out by hand on a grid small enough to check on paper. The neighbour-order contract is tested through its effect (`test_parent_prefers_the_first_cardinal_that_reaches_a_tile`), not by asserting the constant.

- [ ] **Step 4: Replace the three searches in `game/environment.py`**

Delete `_flood_fill_hazard`. Replace the other two bodies:

```python
def _bfs_toward_breach(
    game_map: GameMap,
    sources: list[tuple[int, int]],
    max_distance: int | None = None,
) -> tuple[dict[tuple[int, int], tuple[int, int]], dict[tuple[int, int], int]]:
    """(keep the existing docstring)"""
    starts = [s for s in sources if game_map.in_bounds(*s)]
    dist, parent = bfs(starts, walkable(game_map), max_distance=max_distance)
    # Pull direction: one step back along the search, toward the breach.
    # Source tiles have none (the entity is already at the breach).
    pull_dirs = {
        pos: (0, 0) if origin is None else (origin[0] - pos[0], origin[1] - pos[1])
        for pos, origin in parent.items()
    }
    return pull_dirs, dist


def _bfs_decompression_reach(
    game_map: GameMap,
    boundary: list[tuple[int, int]],
    old_vacuum: np.ndarray,
    max_distance: int = DECOMPRESSION_RANGE,
) -> dict[tuple[int, int], int]:
    """(keep the existing docstring)"""
    pressurised = walkable(game_map)
    # Don't expand into old vacuum (already depressurized)
    dist, _ = bfs(boundary, lambda x, y: pressurised(x, y) and not old_vacuum[x, y], max_distance=max_distance)
    return dist
```

Add `from world.grid import bfs, walkable` to the module imports and remove `from collections import deque` if nothing else uses it.

In `world/game_map.py` `recalculate_hazards`, replace

```python
            from game.environment import _flood_fill_hazard

            new_vacuum = _flood_fill_hazard(self, vacuum_sources)
```

with

```python
            from world.grid import flood_fill_walkable

            new_vacuum = flood_fill_walkable(self, vacuum_sources)
```

Repoint tests: `git grep -l "_flood_fill_hazard" -- tests | xargs sed -i -b -E 's/from game\.environment import (.*)\b_flood_fill_hazard\b/from world.grid import flood_fill_walkable as _flood_fill_hazard\nfrom game.environment import \1/'`, then tidy the import lines by hand as in Task 7 Step 5.

- [ ] **Step 5: Replace the corridor search in `world/boarding_craft.py`**

Replace the body of `_bfs_corridor`:

```python
    space_tid = int(tile_types.space["tile_id"])

    def passable(x: int, y: int) -> bool:
        return composite.in_bounds(x, y) and int(composite.tiles["tile_id"][x, y]) == space_tid

    if not passable(*start) or not passable(*goal):
        return None
    _, parent = bfs([start], passable)
    return path_to(parent, goal)
```

Import `from world.grid import bfs, path_to`; remove `from collections import deque`.

- [ ] **Step 6: Replace the shift blocks in `world/dungeon_gen/hull.py`**

In `_convert_hull_to_space`, replace each hand-written shift block, keeping every other line:

| Old block | New expression |
|---|---|
| `adj = np.zeros_like(interesting)` + 8 shifts | `adj = neighbour_any(interesting, NEIGHBOURS_8)` |
| `adj_walkable = ...` + 4 shifts | `adj_walkable = neighbour_any(is_walkable)` |
| `adj_window = ...` + 4 shifts | `adj_window = neighbour_any(is_window_now)` |
| `cardinal_interesting = ...` + 4 shifts | `cardinal_interesting = neighbour_any(is_walkable2 \| is_window_now2)` |
| `diag_window = ...` + 4 shifts | `diag_window = neighbour_any(is_window_now2, DIAGONALS)` |
| `space_neighbors = np.zeros(...)` + 4 `+=` | `space_neighbors = neighbour_count(is_space)` |

Import `from world.grid import DIAGONALS, NEIGHBOURS_8, neighbour_any, neighbour_count`.

- [ ] **Step 7: Gates and commit**

Run: `pytest tests/test_grid.py tests/test_dungeon_gen_golden.py tests/test_decompression.py tests/test_hazard_propagation.py tests/test_boarding_craft.py -q` - Expected: all pass.
Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add world/grid.py tests/ game/environment.py world/game_map.py world/boarding_craft.py world/dungeon_gen/hull.py
git commit -m "refactor(grid): share one BFS and one neighbour mask across hazards, routing and hull cleanup"
```

---

### Task 11: Collapse the mirrored branches in building generation

**Files:**
- Modify: `world/dungeon_gen/rooms.py` (receive `_wall_sides`)
- Modify: `world/dungeon_gen/windows.py` (import `_wall_sides` from `rooms`)
- Modify: `world/dungeon_gen/buildings.py` (`_carve_external_door`, `_carve_wing_doorway`, `_subdivide_building`)
- Create: `tests/test_buildings.py`

**Interfaces:**
- `_wall_sides(room: RectRoom) -> list[list[tuple[Pos, Pos, Pos]]]` moves to `rooms.py` unchanged: north, south, west, east; each entry `(wall, outside, inside)`.
- The three `buildings.py` functions keep their signatures and their exact RNG draws.

- [ ] **Step 1: Write the characterisation tests** - `tests/test_buildings.py`

These pin the current output before the rewrite, at a finer grain than the golden digest.

```python
"""Building helpers produce the same tiles whichever axis they work along."""

import random

import numpy as np

from world import tile_types
from world.dungeon_gen.buildings import _carve_wing_doorway, _subdivide_building
from world.dungeon_gen.rooms import RectRoom
from world.game_map import GameMap


def _walled(w: int = 30, h: int = 30) -> GameMap:
    return GameMap(w, h, fill_tile=tile_types.structure_wall)


def _floor(game_map: GameMap) -> np.ndarray:
    return game_map.tiles["tile_id"] == int(tile_types.dirt_floor["tile_id"])


def _carve(game_map: GameMap, room: RectRoom) -> None:
    game_map.tiles[room.inner] = tile_types.dirt_floor


def test_doorway_between_side_by_side_wings_is_centred_on_the_shared_wall():
    game_map = _walled()
    left, right = RectRoom(2, 2, 6, 6), RectRoom(8, 4, 6, 8)
    _carve(game_map, left)
    _carve(game_map, right)

    _carve_wing_doorway(game_map, left, right, tile_types.dirt_floor)

    # overlap of interiors along y: max(3, 5)..min(7, 11) = 5..7, midpoint 6
    assert _floor(game_map)[8, 6]


def test_doorway_is_the_same_whichever_wing_comes_first():
    for a, b in [
        (RectRoom(2, 2, 6, 6), RectRoom(8, 4, 6, 8)),
        (RectRoom(4, 2, 8, 6), RectRoom(2, 8, 6, 6)),
    ]:
        first, second = _walled(), _walled()
        for game_map in (first, second):
            _carve(game_map, a)
            _carve(game_map, b)
        _carve_wing_doorway(first, a, b, tile_types.dirt_floor)
        _carve_wing_doorway(second, b, a, tile_types.dirt_floor)

        assert np.array_equal(_floor(first), _floor(second))


def test_doorway_between_stacked_wings_is_centred_on_the_shared_wall():
    game_map = _walled()
    top, bottom = RectRoom(4, 2, 8, 6), RectRoom(2, 8, 6, 6)
    _carve(game_map, top)
    _carve(game_map, bottom)

    _carve_wing_doorway(game_map, top, bottom, tile_types.dirt_floor)

    # overlap of interiors along x: max(5, 3)..min(11, 7) = 5..7, midpoint 6
    assert _floor(game_map)[6, 8]


def test_wings_that_do_not_touch_get_no_doorway():
    game_map = _walled()
    a, b = RectRoom(2, 2, 5, 5), RectRoom(12, 12, 5, 5)
    _carve(game_map, a)
    _carve(game_map, b)
    before = _floor(game_map).copy()

    _carve_wing_doorway(game_map, a, b, tile_types.dirt_floor)

    assert np.array_equal(_floor(game_map), before)


def test_subdividing_a_wide_and_a_tall_footprint_are_transposes_of_each_other():
    """The vertical-split and horizontal-split paths must be the same algorithm on swapped axes."""
    for seed in range(25):
        wide, tall = _walled(), _walled()
        wide_rooms = _subdivide_building(
            wide, random.Random(seed), 2, 2, 20, 10, 3, tile_types.dirt_floor, tile_types.structure_wall
        )
        tall_rooms = _subdivide_building(
            tall, random.Random(seed), 2, 2, 10, 20, 3, tile_types.dirt_floor, tile_types.structure_wall
        )

        assert np.array_equal(_floor(wide), _floor(tall).T), f"seed {seed}"
        assert [(r.x1, r.y1, r.x2, r.y2) for r in wide_rooms] == [(r.y1, r.x1, r.y2, r.x2) for r in tall_rooms]


def test_subdivided_rooms_are_all_connected():
    for seed in range(25):
        game_map = _walled()
        rooms = _subdivide_building(
            game_map, random.Random(seed), 2, 2, 22, 14, 3, tile_types.dirt_floor, tile_types.structure_wall
        )
        from world.grid import flood_fill_walkable

        reached = flood_fill_walkable(game_map, [rooms[0].center])

        assert np.array_equal(reached, _floor(game_map)), f"seed {seed}"
```

- [ ] **Step 2: Run them against the current code**

Run: `pytest tests/test_buildings.py -q`
Expected: 6 passed. They are characterisation tests. Save the proof they can fail for Step 6. (`test_subdivided_rooms_are_all_connected` uses `world.grid` from Task 10; if this task runs first, that one test errors on the import and the other five pass.)

- [ ] **Step 3: Move `_wall_sides` and reuse it in `_carve_external_door`**

Cut `_wall_sides` (and the `type Pos = tuple[int, int]` alias) from `windows.py` into `rooms.py`; in `windows.py` import both from `world.dungeon_gen.rooms`.

In `buildings.py` `_carve_external_door`, replace the four `for` loops that build `door_candidates` with:

```python
    # Each entry: (wall_pos, inside_pos, outside_pos), in north, south, west, east order per wing.
    door_candidates = [
        (wall, inside, outside)
        for wing in wing_rooms
        for side in _wall_sides(wing)
        for wall, outside, inside in side
        if game_map.in_bounds(*outside) and int(game_map.tiles["tile_id"][outside]) == ground_tid
    ]
```

- [ ] **Step 4: Rewrite `_carve_wing_doorway` as one loop**

```python
def _carve_wing_doorway(
    game_map: GameMap,
    wing_a: RectRoom,
    wing_b: RectRoom,
    floor_tile: np.ndarray,
) -> None:
    """Carve a 1-tile doorway through the shared wall between two adjacent wings.

    Two wings that share a side have an overlapping range of wall tiles.
    We find that overlap, carve the shared wall tile, and force-clear the
    tiles on both sides so internal partition walls don't block the passage.
    """
    a = ((wing_a.x1, wing_a.x2), (wing_a.y1, wing_a.y2))
    b = ((wing_b.x1, wing_b.x2), (wing_b.y1, wing_b.y2))
    for axis in (0, 1):  # 0: side by side (shared wall is a column), 1: stacked (a row)
        along = 1 - axis
        # A's far wall against B's near wall, then A's near wall against B's far wall.
        for shared, b_wall in ((a[axis][1], b[axis][0]), (a[axis][0], b[axis][1])):
            if shared != b_wall:
                continue
            lo = max(a[along][0], b[along][0]) + 1
            hi = min(a[along][1], b[along][1]) - 1
            if lo > hi:
                continue
            door = (lo + hi) // 2
            for step in (0, -1, 1):
                pos = (shared + step, door) if axis == 0 else (door, shared + step)
                # The wall tile itself always opens; its neighbours only if still blocked.
                if game_map.in_bounds(*pos) and (step == 0 or not game_map.tiles["walkable"][pos]):
                    game_map.tiles[pos] = floor_tile
            return
```

- [ ] **Step 5: Rewrite `_subdivide_building` as one axis-generic body**

Keep the signature and docstring. Replace the body:

```python
    inner = (x2 - x1 - 1, y2 - y1 - 1)

    # Min sub-room interior 3×3 → each half needs outer width ≥ 4 → min_offset 4
    min_offset = 4
    can_split = tuple(size >= min_offset * 2 - 1 for size in inner)  # (split x, split y)

    # Base case: single room
    if num_rooms <= 1 or not any(can_split):
        _carve_room_interior(game_map, x1, y1, x2, y2, floor_tile)
        return [RectRoom(x1, y1, x2 - x1, y2 - y1, label=label)]

    # Choose the split axis from viable options; prefer the longer dimension.
    # axis 0 is a vertical partition (splits x), axis 1 a horizontal one (splits y).
    if all(can_split):
        if inner[0] > inner[1]:
            axis = 0
        elif inner[1] > inner[0]:
            axis = 1
        else:
            axis = 0 if rng.choice(["vertical", "horizontal"]) == "vertical" else 1
    else:
        axis = 0 if can_split[0] else 1

    lo_edge, hi_edge = ((x1, x2), (y1, y2))[axis]
    cross_lo, cross_hi = ((y1, y2), (x1, x2))[axis]

    def at(along: int, across: int) -> tuple[int, int]:
        """(x, y) of the tile *along* the split axis and *across* it."""
        return (along, across) if axis == 0 else (across, along)

    lo, hi = lo_edge + min_offset, hi_edge - min_offset
    # Asymmetric split: when we need >2 rooms, push the partition toward one
    # side so the larger half can subdivide further.
    if num_rooms > 2:
        split = lo if rng.random() < 0.5 else hi
    else:
        split = rng.randint(lo, hi)

    # Draw partition wall
    for across in range(cross_lo + 1, cross_hi):
        pos = at(split, across)
        if game_map.in_bounds(*pos):
            game_map.tiles[pos] = wall_tile

    # Give 1 room to the smaller half and the rest to the bigger; 2 rooms split evenly.
    if num_rooms == 2:
        counts = (1, 1)
    elif split - lo_edge >= hi_edge - split:
        counts = (num_rooms - 1, 1)
    else:
        counts = (1, num_rooms - 1)

    if axis == 0:
        halves = ((x1, y1, split, y2), (split, y1, x2, y2))
    else:
        halves = ((x1, y1, x2, split), (x1, split, x2, y2))
    rooms: list[RectRoom] = []
    for half, count in zip(halves, counts, strict=True):
        rooms += _subdivide_building(game_map, rng, *half, count, floor_tile, wall_tile, label)

    # Carve a 1-tile doorway, preferring positions with floor on both sides
    door = _find_door_position(game_map, rng, split, cross_lo, cross_hi, vertical=axis == 0)
    if door is not None:
        game_map.tiles[at(split, door)] = floor_tile
        # Only force-clear a side if it's still walled (perpendicular partition)
        # but never breach the building's outer boundary walls
        for side, inside_building in ((split - 1, split - 1 > lo_edge), (split + 1, split + 1 < hi_edge)):
            pos = at(side, door)
            if inside_building and game_map.in_bounds(*pos) and not game_map.tiles["walkable"][pos]:
                game_map.tiles[pos] = floor_tile

    return rooms
```

RNG check against the old code, in order: optional `rng.choice`, then `rng.random()` or `rng.randint(lo, hi)`, then the first half's recursion, then the second half's, then `_find_door_position`. Unchanged.

- [ ] **Step 6: Gates, mutation check, commit**

Run: `pytest tests/test_buildings.py tests/test_dungeon_gen_golden.py tests/test_dungeon_gen.py -q` - Expected: all pass.

Mutation check: in the new `_subdivide_building`, change `split - 1 > lo_edge` to `split - 1 >= lo_edge`, run `pytest tests/test_buildings.py tests/test_dungeon_gen_golden.py -q`, confirm at least one failure, then undo the change.

Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add world/dungeon_gen/rooms.py world/dungeon_gen/windows.py world/dungeon_gen/buildings.py tests/test_buildings.py
git commit -m "refactor(buildings): write the doorway and subdivision logic once for both axes"
```

---

### Task 12: Drive generation steps from the location profile

**Files:**
- Modify: `world/loc_profiles.py` (`LocationProfile` fields and the four `PROFILES`)
- Modify: `world/dungeon_gen/generator.py` (`generate_dungeon`)
- Modify: `tests/test_loc_profiles.py` (add tests)

**Interfaces:**
- Produces new `LocationProfile` fields:
  - `places_doors: bool = True`
  - `has_hull: bool = False` - airlocks, hull-to-space conversion, ship cosmetics
  - `hull_breach_chance: float = 0.0` - chance of hull breaches when `has_hull`
  - `rock_breaches: bool = False` - asteroid-style perimeter breaches
  - `themed_dressing: bool = False` - rooms already carry themed furnishings

**RNG contract:** today `rng.random()` is drawn for hull breaches only when the location is a starbase. Keep that: draw only when `0 < hull_breach_chance < 1`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_loc_profiles.py`)

The existing profiles' behaviour is already pinned by the golden digest. These tests prove the new capability instead: a profile nobody has written yet changes what gets generated, with no edit to the generator.

```python
from dataclasses import replace

from world import tile_types
from world.dungeon_gen import generate_dungeon
from world.loc_profiles import PROFILES

SEEDS = range(8)


def _generate(monkeypatch, profile, seed: int):
    """Generate a map for a made-up location type that uses *profile*."""
    monkeypatch.setitem(PROFILES, "custom", profile)
    return generate_dungeon(width=120, height=42, seed=seed, loc_type="custom")[0]


def _closed_doors(game_map) -> int:
    return int((game_map.tiles["tile_id"] == int(tile_types.door_closed["tile_id"])).sum())


def test_a_hulled_profile_with_no_breach_chance_never_breaches(monkeypatch):
    sealed = replace(PROFILES["derelict"], hull_breach_chance=0.0)

    for seed in SEEDS:
        game_map = _generate(monkeypatch, sealed, seed)
        assert game_map.hull_breaches == []
        assert game_map.airlocks != []


def test_a_hulled_profile_with_certain_breach_chance_always_breaches(monkeypatch):
    wrecked = replace(PROFILES["starbase"], hull_breach_chance=1.0)

    for seed in SEEDS:
        assert _generate(monkeypatch, wrecked, seed).hull_breaches != []


def test_a_profile_without_a_hull_gets_no_airlocks_and_no_space(monkeypatch):
    landlocked = replace(PROFILES["starbase"], has_hull=False)

    for seed in SEEDS:
        game_map = _generate(monkeypatch, landlocked, seed)
        assert game_map.airlocks == []
        assert game_map.has_space is False


def test_a_profile_can_turn_room_doors_off(monkeypatch):
    # A colony has no hull, so every closed door on it is a room door (16-32 per map on these seeds).
    with_doors = PROFILES["colony"]
    without_doors = replace(with_doors, places_doors=False)

    for seed in SEEDS:
        assert _closed_doors(_generate(monkeypatch, with_doors, seed)) > 0
        assert _closed_doors(_generate(monkeypatch, without_doors, seed)) == 0
```

| Test | Fails if |
|---|---|
| no breach chance never breaches | the generator still keys breaches off the location name instead of the flag |
| certain breach chance always breaches | the chance is ignored, or a certain chance is mis-rolled |
| no hull → no airlocks, no space | hull steps still run off the generator name |
| doors can be turned off | door placement ignores the flag (the control case proves the seeds do produce doors) |

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_loc_profiles.py -q`
Expected: the four new tests fail with `TypeError: LocationProfile.__init__() got an unexpected keyword argument` (the fields do not exist yet).

- [ ] **Step 3: Add the fields and set them per profile**

In `LocationProfile`, after `fov_radius`:

```python
    places_doors: bool = True  # doors at room entrances (caves have none)
    has_hull: bool = False  # airlocks, hull-to-space conversion and ship cosmetics
    hull_breach_chance: float = 0.0  # chance of hull breaches on a hulled map
    rock_breaches: bool = False  # perimeter breaches cut through rock to space
    themed_dressing: bool = False  # rooms already carry themed furnishings
```

In `PROFILES`: add `has_hull=True, hull_breach_chance=1.0, themed_dressing=True` to `derelict`; `has_hull=True, hull_breach_chance=0.2` to `starbase`; `places_doors=False, rock_breaches=True` to `asteroid`; nothing to `colony`.

- [ ] **Step 4: Replace the string checks in `generate_dungeon`**

| Old condition | New condition |
|---|---|
| `if rooms and profile.generator != "organic":` | `if rooms and profile.places_doors:` |
| `wants_interactables = profile.generator != "ship" or (profile.wall_interactable and len(rooms) > 1)` | `wants_interactables = not profile.themed_dressing or (profile.wall_interactable and len(rooms) > 1)` |
| the two consecutive `if profile.generator in ("ship", "standard"):` blocks (airlocks; hull conversion) | merge into one `if profile.has_hull:` block, bodies in the same order |
| `if not player_ship and (profile.loc_type != "starbase" or rng.random() < 0.2):` | `if not player_ship and _rolls_hull_breach(profile, rng):` |
| `if profile.generator == "organic":` | `if profile.rock_breaches:` |
| `if profile.generator in ("ship", "standard"):` before cosmetics | `if profile.has_hull:` |

Add above `generate_dungeon`:

```python
def _rolls_hull_breach(profile: LocationProfile, rng: random.Random) -> bool:
    """Whether this hulled map gets breaches. Draws only when the chance is genuinely uncertain."""
    if profile.hull_breach_chance >= 1.0:
        return True
    return profile.hull_breach_chance > 0.0 and rng.random() < profile.hull_breach_chance
```

and import `LocationProfile` alongside `get_profile`.

- [ ] **Step 5: Gates and commit**

Run: `pytest tests/test_loc_profiles.py tests/test_dungeon_gen_golden.py -q` - Expected: all pass.
Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add world/loc_profiles.py world/dungeon_gen/generator.py tests/test_loc_profiles.py
git commit -m "refactor(dungeon_gen): choose generation steps from the location profile"
```

---

### Task 13: Public engine and map API; animation flag on `State`

**Files:**
- Modify: `engine/game_state.py` (`State.needs_animation`, `Engine.states`, `Engine.has_state`, `Engine.state_below`, `Engine.needs_animation`, `seeded_rng`, rename `_saved_player` → `saved_player`)
- Modify: `world/game_map.py` (rename `_pending_decompression` → `pending_decompression`, `_pull_directions` → `pull_directions`; add `fov_from`)
- Modify: every caller of those private names (`game/`, `ui/`, `web/`, `tests/`)
- Create: `tests/test_engine_api.py`

**Interfaces:**
- Produces:
  - `State.needs_animation: bool = False` (class attribute; subclasses may override with an attribute or property)
  - `Engine.states -> tuple[State, ...]` (bottom to top)
  - `Engine.has_state(state_type: type[State]) -> bool`
  - `Engine.state_below(state: State) -> State | None`
  - `Engine.needs_animation() -> bool`
  - `seeded_rng(seed: int, turn: int, salt: str) -> random.Random` (module-level; `Engine.rng` and `MockEngine.rng` both call it)
  - `Engine.saved_player: dict | None`
  - `GameMap.pending_decompression`, `GameMap.pull_directions`, `GameMap.fov_from(x: int, y: int, radius: int) -> np.ndarray`

- [ ] **Step 1: Write the failing tests** - `tests/test_engine_api.py`

```python
"""The engine and map expose what other modules need, so nothing reaches into privates."""

from engine.game_state import Engine, State
from tests.conftest import MockEngine, make_arena
from world import tile_types


class _Still(State):
    pass


class _Animated(State):
    needs_animation = True


def test_has_state_finds_a_buried_state_and_respects_subclassing():
    class _StillChild(_Still):
        pass

    engine = Engine()
    engine.push_state(_StillChild())
    engine.push_state(_Animated())

    assert engine.has_state(_Still) is True
    assert engine.has_state(_StillChild) is True
    engine.pop_state()
    engine.pop_state()
    assert engine.has_state(_Still) is False


def test_state_below_returns_the_state_under_a_given_one():
    engine = Engine()
    bottom, top = _Still(), _Animated()
    engine.push_state(bottom)
    engine.push_state(top)

    assert engine.state_below(top) is bottom
    assert engine.state_below(bottom) is None
    assert engine.state_below(_Still()) is None


def test_engine_animates_for_the_state_the_map_or_a_scan_glow():
    engine = Engine()
    assert engine.needs_animation() is False
    engine.push_state(_Still())
    assert engine.needs_animation() is False

    engine.scan_glow = {"cx": 0, "cy": 0, "radius": 1, "start_time": 0.0}
    assert engine.needs_animation() is True
    engine.scan_glow = None

    engine.game_map = make_arena()
    engine.game_map.has_space = True
    assert engine.needs_animation() is True
    engine.game_map = None

    engine.push_state(_Animated())
    assert engine.needs_animation() is True


def test_the_test_double_rolls_exactly_what_the_real_engine_rolls():
    """Tests that use MockEngine are only meaningful if its dice match the engine's."""
    engine = Engine()
    mock = MockEngine(game_map=None, player=None)
    engine.turn_counter = mock.turn_counter = 4

    assert [engine.rng("salt").random() for _ in range(3)] == [mock.rng("salt").random() for _ in range(3)]
    assert engine.rng("salt").random() != engine.rng("other").random()


def test_map_fov_respects_walls_and_is_recomputed_after_the_cache_is_cleared():
    game_map = make_arena()
    assert game_map.fov_from(5, 5, 8)[2, 5]

    for y in range(1, 9):
        game_map.tiles[4, y] = tile_types.wall
    assert game_map.fov_from(5, 5, 8)[2, 5], "same turn: the cached view is reused"

    game_map.clear_fov_cache()
    assert not game_map.fov_from(5, 5, 8)[2, 5]
```

| Test | Fails if |
|---|---|
| has_state | a state under a modal is missed (mid-mission detection with the inventory open), or popped states still count |
| state_below | the quit dialog draws the wrong state, or crashes when it is the only one |
| engine animates | any one of the four animation triggers is dropped when the two loops share the check |
| test double rolls the same | `MockEngine` drifts from `Engine.rng`, silently invalidating every test built on it |
| map fov | AI vision ignores walls, recomputes every call, or keeps a stale view across turns |

The renames in this task (`saved_player`, `pending_decompression`, `pull_directions`) and the `states` property get no tests of their own: a missed rename fails the existing suite with `AttributeError`, and Step 6's grep proves none remain.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_engine_api.py -q`
Expected: every test fails with `AttributeError` (`has_state`, `state_below`, `needs_animation`, `fov_from`), except the test-double test, which passes today and guards the shared recipe through Step 3.

- [ ] **Step 3: Add the engine API**

In `engine/game_state.py`, add at module level:

```python
def seeded_rng(seed: int, turn: int, salt: str) -> random.Random:
    """A Random seeded from (seed, turn, salt): the same three always give the same stream."""
    digest = hashlib.sha256(f"{seed}:{turn}:{salt}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "little"))
```

with `import hashlib` and `import random` at the top (move `import random` out of the `TYPE_CHECKING` block). Then:

- `State`: add `needs_animation: bool = False` as the first line of the class body, with the docstring kept above it.
- `Engine.rng`: replace the body below the docstring with `return seeded_rng(self.galaxy.seed if self.galaxy is not None else 0, self.turn_counter, salt)`.
- `Engine.__init__`: rename `self._saved_player` to `self.saved_player`.
- Add to `Engine`:

```python
    @property
    def states(self) -> tuple[State, ...]:
        """The state stack, bottom to top."""
        return tuple(self._state_stack)

    def has_state(self, state_type: type[State]) -> bool:
        """True if a state of *state_type* is anywhere on the stack."""
        return any(isinstance(state, state_type) for state in self._state_stack)

    def state_below(self, state: State) -> State | None:
        """The state directly under *state*, or None if it is at the bottom or not on the stack."""
        if state not in self._state_stack:
            return None
        index = self._state_stack.index(state)
        return self._state_stack[index - 1] if index > 0 else None

    def needs_animation(self) -> bool:
        """True while something on screen changes without input: starfield, flicker, scan glow, fades."""
        game_map = self.game_map
        map_animates = game_map is not None and (game_map.has_space or game_map.has_flickering_lights)
        state = self.current_state
        return bool(map_animates or self.scan_glow or (state is not None and state.needs_animation))
```

- In both `run_async` and `run`, replace the `gm = self.game_map` / `needs_anim = (...)` block with `timeout = _ANIM_TIMEOUT if self.needs_animation() else None`.

In `tests/conftest.py`, replace the body of `MockEngine.rng` with:

```python
        from engine.game_state import seeded_rng

        return seeded_rng(self.galaxy.seed if self.galaxy is not None else 0, self.turn_counter, salt)
```

- [ ] **Step 4: Add the map API**

In `world/game_map.py`: rename `self._pending_decompression` → `self.pending_decompression` and `self._pull_directions` → `self.pull_directions` in `__init__` and `recalculate_hazards`, and add:

```python
    def fov_from(self, x: int, y: int, radius: int) -> np.ndarray:
        """Field of view from (x, y), cached until ``clear_fov_cache`` (once per turn)."""
        import tcod.map

        key = (x, y, radius)
        fov = self._fov_cache.get(key)
        if fov is None:
            fov = tcod.map.compute_fov(self.tiles["transparent"], (x, y), radius=radius)
            self._fov_cache[key] = fov
        return fov
```

In `game/ai.py` `_can_see_player`, replace everything after the `chebyshev` range check with `return bool(engine.game_map.fov_from(owner.x, owner.y, vision_radius)[target.x, target.y])` and drop the `import tcod.map`.

- [ ] **Step 5: Rename the callers**

```bash
git grep -lE '_saved_player\b|_pending_decompression|_pull_directions' -- '*.py' | xargs sed -i -b -E 's/\b(engine|self|e|e2|loaded|new_engine|reloaded)\._saved_player\b/\1.saved_player/g; s/"_saved_player"/"saved_player"/g; s/\._pending_decompression\b/.pending_decompression/g; s/\._pull_directions\b/.pull_directions/g'
```

Verify: `git grep -nE '\._saved_player\b|_pending_decompression|_pull_directions' -- '*.py'` - Expected: no output. Any remaining hit is a receiver name the pattern did not list; rename it by hand. (`_saved_player_to_dict` and `_saved_player_from_dict` in `web/save_load.py` are function names and must stay.)

Then replace the stack reach-ins:

| File | Old | New |
|---|---|---|
| `ui/confirm_quit_state.py` `on_render` | `if len(engine._state_stack) >= 2: engine._state_stack[-2].on_render(console, engine)` | `below = engine.state_below(self)` / `if below is not None: below.on_render(console, engine)` |
| `ui/inventory_state.py` `_in_tactical` | `any(isinstance(s, TacticalState) for s in engine._state_stack)` | `engine.has_state(TacticalState)` |
| `web/save_load.py` `is_mid_mission` | `any(isinstance(s, TacticalState) for s in engine._state_stack)` | `engine.has_state(TacticalState)` |
| `web/save_load.py` `_game_over_record`, `engine_to_dict` | `for state in engine._state_stack:` | `for state in engine.states:` |
| `ui/cargo_state.py` | `getattr(engine, "saved_player", None)` (two places) | `engine.saved_player` |

Tests that build a stack by hand with `engine._state_stack.append(...)` are test setup and may stay.

- [ ] **Step 6: Verify the reach-ins are gone**

Run: `git grep -nE 'engine\._(state_stack|saved_player)|game_map\._(pending|pull|fov_cache)' -- engine game ui world web`
Expected: no output.

- [ ] **Step 7: Full gate and commit**

Run: `pytest tests/test_engine_api.py -q` - Expected: 5 passed.
Run: `pytest -q` - Expected: all pass. Run ruff.

```bash
git add -A engine game ui world web tests
git commit -m "refactor(api): expose the engine and map state other modules were reaching into"
```

---

## Deliberately not in this plan

- **Protocols for every `engine` parameter (interface segregation).** Typing each function against a narrow protocol touches nearly every signature for little behavioural payoff. Tasks 4, 5 and 13 remove the worst of it (UI-owned logic, private reach-ins); revisit once those land.
- **Splitting `game` and `world`.** They import each other in both directions and the layering test treats them as one layer. Separating them is a design project of its own.
- **Merging the per-file web `client` fixtures.** They build different apps (auth-only versus full server) on purpose.
- **Changing generation so lockers avoid door tiles, and the mid-mission disconnect policy.** Both alter behaviour or seeded maps and need a product decision, not a refactor.
- **`debug.py` flag values.**

## Self-review notes

- Every finding in the table maps to a task; the three intentionally skipped items are listed above with reasons.
- Names used across tasks agree: `current_interdiction` (5, 6), `build_item_entity`/`build_enemy` (7), `data.colors` (8, 9), `bfs`/`flood_fill_walkable` (10, 11), `saved_player` (13 only; earlier tasks use `_saved_player` because they run first).
- Tasks 3–6 edit `ui/tactical_state.py` in sequence and must run in order. Tasks 7 and 9–12 are independent of each other once Task 8's renames are in or accounted for (see the note in Task 9 Step 3).

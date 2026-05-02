# Test Suite Audit Design

**Date:** 2026-05-02
**Scope:** Remove performative/low-value tests; fix slow tests where obvious improvements exist

---

## Context

The suite has 1,778 tests running in ~388 seconds. Two files account for ~45% of total runtime:
- `tests/test_dreadnought_spawn.py` — 10 tests × ~13–30s each = ~140s (36%)
- `tests/test_dungeon_gen.py` — 2 × 200-seed loops = ~35s (9%)

The remaining 1,754 tests across 103 files run in ~175s total and are generally fast.

---

## Approach: Targeted (Option B)

Fix the known slow tests first. For performative tests, run fast pattern scans across all files to surface candidates, then read flagged files in depth. This gets 90% of the value at 40% of the cost of a full line-by-line audit.

---

## Part 1: Slow Test Fixes

### Fix 1 — Share expanded galaxy across `TestSpawnDreadnought` (~130s savings)

**File:** `tests/test_dreadnought_spawn.py`

All 10 tests in `TestSpawnDreadnought` call a local `_expand_all(galaxy)` function that builds a full 50-system galaxy from scratch. The expanded galaxy is read-only during each test. Fix: convert into a `@pytest.fixture(scope="class")` that builds the galaxy once and injects it into all 10 tests.

**Expected result:** 10 tests share one galaxy build instead of 10. Runtime for the class drops from ~140s to ~14s.

### Fix 2 — Investigate and possibly reduce 200-seed dungeon loops (~35s)

**File:** `tests/test_dungeon_gen.py`

Two tests (`test_colony_no_crash_200_seeds`, `test_colony_no_crash_with_windows`) loop over 200 seeds to verify "doesn't crash." Before reducing the count, determine whether specific seed values were chosen to reproduce known bugs (load-bearing seeds) or whether 200 was an arbitrary round number.

- If seeds are arbitrary: reduce to 50. Expected savings: ~26s.
- If any specific seed is known to reproduce a bug: keep that seed as a named regression test, reduce the loop to 50 for the general case.

---

## Part 2: Performative Test Audit

### Scan Patterns

Run grep/AST scans across all 105 test files to flag candidates. Then read each flagged file in full depth and apply human judgment.

| Anti-pattern | What to scan for | Action |
|---|---|---|
| **Trivial assertion** | `assert True`, `assert x == x`, `assert len(x) >= 0` | Remove — can never fail |
| **Testing the default** | Assert value equals the literal passed into constructor on the same line | Remove if no real behavior is tested |
| **Pure mock test** | Test body contains only `Mock()`/`MagicMock()` with no real game objects | Remove if no real code path runs |
| **Duplicate scenario** | Two tests with identical setup differing only in one assertion already covered elsewhere | Merge or remove the duplicate |
| **Dead import test** | `import X; assert X` or `from X import Y; assert Y is not None` | Remove — validates nothing |

### What NOT to Remove

- Tests that look trivial but catch a specific regression (check git blame / commit message)
- Tests that are slow but correct (bcrypt in auth — intentionally expensive)
- Tests that seem redundant but cover genuinely separate failure modes
- Any test with a comment explaining why it exists

### Judgment Call Process

For each flagged candidate:
1. Read the full test and its surrounding tests for context
2. Check if the assertion could ever fail given valid inputs
3. Check git blame — was this added to catch a specific bug?
4. If the test provides zero additional coverage: delete it
5. If uncertain: keep it

---

## Success Criteria

- Total runtime reduced by at least 100s (from ~388s to under ~290s)
- No real coverage lost (suite still catches the same categories of bugs)
- Removed tests are ones that could never catch a real regression
- All remaining tests pass

---

## Out of Scope

- Restructuring test files or renaming tests
- Adding new tests
- Changing bcrypt work factor or any intentionally expensive operations
- Moving slow tests to a separate marked suite

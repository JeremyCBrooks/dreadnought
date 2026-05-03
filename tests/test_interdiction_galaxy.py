"""Tests for the Galaxy.arrive_at interdiction hook (Phase 2).

Covers: trigger gating (cargo, home, already-interdicted) and the actual
roll being performed when a ship is passed in. Backward compatibility:
``arrive_at(name)`` without a ship parameter must still work.
"""

from __future__ import annotations

from types import SimpleNamespace

from game.entity import Entity
from game.interdiction import Interdiction
from world.galaxy import Galaxy


def _ship(cargo_count: int = 1) -> SimpleNamespace:
    items = [
        Entity(x=0, y=0, char="!", color=(255, 255, 255), name=f"item{i}", item={"type": "junk"})
        for i in range(cargo_count)
    ]
    return SimpleNamespace(cargo=items)


class _ForceRng:
    """Always returns ``value`` from .random()."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


# ---- Backwards compatibility ----


def test_arrive_at_still_works_without_ship_param():
    """Existing callers (tests, save/load) call arrive_at(name) only. Must not break."""
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.arrive_at(name)  # no ship arg — must not raise


# ---- Gating ----


def test_arrive_at_does_not_trigger_in_home_system():
    g = Galaxy(seed=1)
    g.arrive_at(g.home_system, ship=_ship(cargo_count=3), rng=_ForceRng(0.0))
    assert g.systems[g.home_system].interdiction is None


def test_arrive_at_does_not_trigger_with_empty_cargo():
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.arrive_at(name, ship=_ship(cargo_count=0), rng=_ForceRng(0.0))
    assert g.systems[name].interdiction is None


def test_arrive_at_does_not_trigger_when_already_interdicted():
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.systems[name].interdiction = Interdiction(started=True)
    g.arrive_at(name, ship=_ship(), rng=_ForceRng(0.0))
    # The pre-existing interdiction must remain unchanged.
    assert g.systems[name].interdiction.started is True
    assert g.systems[name].interdiction.resolved is False


def test_arrive_at_does_not_retrigger_after_resolution():
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    resolved = Interdiction(started=True, resolved=True)
    g.systems[name].interdiction = resolved
    g.arrive_at(name, ship=_ship(), rng=_ForceRng(0.0))
    assert g.systems[name].interdiction is resolved
    assert g.systems[name].interdiction.resolved is True


# ---- Trigger ----


def test_arrive_at_queues_interdiction_when_roll_succeeds():
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.arrive_at(name, ship=_ship(cargo_count=2), rng=_ForceRng(0.0))
    interdiction = g.systems[name].interdiction
    assert interdiction is not None
    # Queued, not yet started.
    assert interdiction.started is False
    assert interdiction.resolved is False


def test_arrive_at_does_not_queue_when_roll_fails(monkeypatch):
    monkeypatch.setattr("game.interdiction.INTERDICTION_CHANCE", 0.1)
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.arrive_at(name, ship=_ship(cargo_count=2), rng=_ForceRng(0.999))
    assert g.systems[name].interdiction is None


def test_arrive_at_still_expands_frontier_on_trigger():
    """Triggering an interdiction must not skip the existing frontier expansion."""
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    before = len(g.systems[name].connections)
    g.arrive_at(name, ship=_ship(), rng=_ForceRng(0.0))
    after = len(g.systems[name].connections)
    # Frontier expansion may add 0+ new connections; never reduce.
    assert after >= before

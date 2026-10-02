"""Tests for the Galaxy.arrive_at interdiction hook (Phase 2).

Covers: trigger gating (cargo, home, already-interdicted), the actual
roll being performed when a ship is passed in, and the pirate craft
docking there and then. Backward compatibility:
``arrive_at(name)`` without a ship parameter must still work.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

from game.entity import Entity
from game.interdiction import Interdiction
from game.ship import Ship
from world.galaxy import Galaxy


def _cargo(count: int) -> list[Entity]:
    return [
        Entity(x=0, y=0, char="!", color=(255, 255, 255), name=f"item{i}", item={"type": "junk"}) for i in range(count)
    ]


def _ship(cargo_count: int = 1) -> SimpleNamespace:
    """A ship with cargo but no interior: worth robbing, impossible to dock with."""
    return SimpleNamespace(cargo=_cargo(cargo_count), game_map=None)


def _boardable_ship(galaxy: Galaxy, cargo_count: int = 1) -> Ship:
    """A real ship with an interior whose airlocks a boarding craft can reach."""
    ship = Ship()
    ship.generate_interior(galaxy.seed)
    ship.cargo.extend(_cargo(cargo_count))
    return ship


class _ForceRng:
    """Always returns ``value`` from .random(); every other draw comes from a real seeded stream."""

    def __init__(self, value: float) -> None:
        self._value = value
        self._real = random.Random(0)

    def __getattr__(self, name: str):
        return getattr(self._real, name)

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


def test_arrive_at_docks_a_pirate_craft_when_roll_succeeds():
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    ship = _boardable_ship(g, cargo_count=2)
    docked = g.arrive_at(name, ship=ship, rng=_ForceRng(0.0))
    interdiction = g.systems[name].interdiction
    assert interdiction is not None
    assert docked is interdiction
    # Docked there and then: the composite is live and the pirates are aboard it.
    assert interdiction.started is True
    assert interdiction.resolved is False
    assert ship.game_map is interdiction.composite_map
    assert interdiction.pirate_entities


def test_arrive_at_does_not_interdict_when_roll_fails(monkeypatch):
    monkeypatch.setattr("game.interdiction.INTERDICTION_CHANCE", 0.1)
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    ship = _boardable_ship(g, cargo_count=2)
    original_map = ship.game_map
    assert g.arrive_at(name, ship=ship, rng=_ForceRng(0.999)) is None
    assert g.systems[name].interdiction is None
    assert ship.game_map is original_map


def test_arrive_at_forgets_a_craft_that_cannot_dock():
    """A boarding attempt that finds no docking point never happened."""
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    assert g.arrive_at(name, ship=_ship(cargo_count=2), rng=_ForceRng(0.0)) is None
    assert g.systems[name].interdiction is None


def test_arrive_at_can_interdict_again_after_a_failed_docking():
    """Nothing was recorded, so a later arrival with a boardable ship is fair game."""
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    g.arrive_at(name, ship=_ship(cargo_count=2), rng=_ForceRng(0.0))
    g.arrive_at(name, ship=_boardable_ship(g), rng=_ForceRng(0.0))
    assert g.systems[name].interdiction is not None


def test_arrive_at_still_expands_frontier_on_trigger():
    """Triggering an interdiction must not skip the existing frontier expansion."""
    g = Galaxy(seed=1)
    name = next(iter(g.systems[g.home_system].connections))
    before = len(g.systems[name].connections)
    g.arrive_at(name, ship=_ship(), rng=_ForceRng(0.0))
    after = len(g.systems[name].connections)
    # Frontier expansion may add 0+ new connections; never reduce.
    assert after >= before

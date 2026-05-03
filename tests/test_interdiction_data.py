"""Tests for the Interdiction data model and probability gate."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from game.entity import Entity, Fighter
from game.interdiction import (
    INTERDICTION_CHANCE,
    Interdiction,
    should_attempt_interdiction,
)
from world.galaxy import Galaxy, StarSystem

# ---- StarSystem now carries an interdiction field ----


def test_star_system_has_interdiction_field_defaulting_to_none():
    sys = StarSystem("Test")
    assert sys.interdiction is None


def test_galaxy_init_systems_have_interdiction_none():
    g = Galaxy(seed=42)
    for sys in g.systems.values():
        assert sys.interdiction is None


# ---- Interdiction dataclass defaults ----


def test_interdiction_default_state():
    i = Interdiction()
    assert i.started is False
    assert i.resolved is False
    assert i.pirate_entities == []
    assert i.craft_room is None
    assert i.connector_tiles == []
    assert i.attach_pos is None
    assert i.pirate_ship_seed is None
    assert i.player_offset is None
    assert i.pirate_offset is None
    assert i.composite_map is None
    assert i.original_ship_map is None


def test_resolve_marks_resolved_true():
    i = Interdiction(started=True)
    i.resolve()
    assert i.resolved is True


# ---- alive_pirate_count ----


def _make_pirate(hp: int = 5) -> Entity:
    return Entity(
        x=0,
        y=0,
        char="p",
        color=(200, 50, 50),
        name="Pirate",
        blocks_movement=True,
        fighter=Fighter(hp=hp, max_hp=5, defense=1, power=3),
    )


def test_alive_pirate_count_zero_when_empty():
    i = Interdiction()
    assert i.alive_pirate_count() == 0


def test_alive_pirate_count_counts_alive_only():
    p1 = _make_pirate(hp=5)
    p2 = _make_pirate(hp=0)
    p3 = _make_pirate(hp=1)
    i = Interdiction(pirate_entities=[p1, p2, p3])
    assert i.alive_pirate_count() == 2


def test_alive_pirate_count_treats_missing_fighter_as_dead():
    p = Entity(x=0, y=0, char="p", color=(200, 50, 50), name="Ghost", fighter=None)
    i = Interdiction(pirate_entities=[p])
    assert i.alive_pirate_count() == 0


# ---- INTERDICTION_CHANCE constant ----


def test_interdiction_chance_constant_is_a_probability():
    assert 0.0 <= INTERDICTION_CHANCE <= 1.0


def test_interdiction_chance_default_value():
    # Currently set to 1.0 for active playtesting; revisit before release.
    assert INTERDICTION_CHANCE == pytest.approx(1.0)


# ---- should_attempt_interdiction gating ----


def _stub_ship(cargo_count: int = 1) -> SimpleNamespace:
    cargo = [
        Entity(x=0, y=0, char="!", color=(255, 255, 255), name=f"item{i}", item={"type": "junk"})
        for i in range(cargo_count)
    ]
    return SimpleNamespace(cargo=cargo)


def _stub_galaxy(home: str = "Home") -> SimpleNamespace:
    return SimpleNamespace(home_system=home)


class _ForceRng:
    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


def test_should_attempt_returns_false_when_cargo_empty():
    sys = StarSystem("Frontier")
    assert should_attempt_interdiction(sys, _stub_ship(0), _stub_galaxy(), _ForceRng(0.0)) is False


def test_should_attempt_returns_false_for_home_system():
    sys = StarSystem("Home")
    assert should_attempt_interdiction(sys, _stub_ship(3), _stub_galaxy(home="Home"), _ForceRng(0.0)) is False


def test_should_attempt_returns_false_if_system_already_interdicted():
    sys = StarSystem("Frontier")
    sys.interdiction = Interdiction(started=True)
    assert should_attempt_interdiction(sys, _stub_ship(), _stub_galaxy(), _ForceRng(0.0)) is False


def test_should_attempt_returns_false_if_system_already_resolved():
    sys = StarSystem("Frontier")
    sys.interdiction = Interdiction(started=True, resolved=True)
    assert should_attempt_interdiction(sys, _stub_ship(), _stub_galaxy(), _ForceRng(0.0)) is False


def test_should_attempt_returns_true_when_roll_succeeds():
    sys = StarSystem("Frontier")
    assert should_attempt_interdiction(sys, _stub_ship(2), _stub_galaxy(), _ForceRng(0.0)) is True


def test_should_attempt_returns_false_when_roll_fails(monkeypatch):
    """With a low chance, a high-value roll should fail."""
    monkeypatch.setattr("game.interdiction.INTERDICTION_CHANCE", 0.1)
    sys = StarSystem("Frontier")
    assert should_attempt_interdiction(sys, _stub_ship(2), _stub_galaxy(), _ForceRng(0.99)) is False


def test_should_attempt_distribution_roughly_matches_chance(monkeypatch):
    """Over 10k rolls, hit rate should land near INTERDICTION_CHANCE."""
    # Use a tunable mid-range chance to verify the distribution math regardless
    # of what the global constant is set to (currently 1.0 for playtest).
    monkeypatch.setattr("game.interdiction.INTERDICTION_CHANCE", 0.10)
    ship = _stub_ship()
    galaxy = _stub_galaxy()
    rng = random.Random(12345)
    hits = sum(1 for _ in range(10_000) if should_attempt_interdiction(StarSystem("F"), ship, galaxy, rng))
    rate = hits / 10_000
    assert abs(rate - 0.10) < 0.015, f"hit rate {rate:.4f} not within 1.5pp of 0.10"

"""Tests for Suit, environment, and active_effects round-trip."""

from __future__ import annotations

from game.suit import HAZARD_SUIT, Suit


# ── Suit ──────────────────────────────────────────────────────────────────────


def test_suit_basic_round_trip():
    from web.save_load import _suit_from_dict, _suit_to_dict

    suit = Suit("EVA Mk2", {"vacuum": 60, "cold": 12}, defense_bonus=1)
    d = _suit_to_dict(suit)
    assert d["name"] == "EVA Mk2"
    assert d["resistances"] == {"vacuum": 60, "cold": 12}
    assert d["defense_bonus"] == 1

    restored = _suit_from_dict(d)
    assert restored.name == "EVA Mk2"
    assert restored.resistances == {"vacuum": 60, "cold": 12}
    assert restored.defense_bonus == 1


def test_suit_current_pools_preserved():
    """current_pools may be drained below max — round-trip must keep that exactly."""
    from web.save_load import _suit_from_dict, _suit_to_dict

    suit = HAZARD_SUIT.copy()
    suit.current_pools["radiation"] = 7  # drained from 40
    suit.current_pools["heat"] = 0  # fully depleted

    restored = _suit_from_dict(_suit_to_dict(suit))
    assert restored.current_pools["radiation"] == 7
    assert restored.current_pools["heat"] == 0
    # Max resistances unchanged
    assert restored.resistances["radiation"] == 40
    assert restored.resistances["heat"] == 30


def test_suit_drain_ticks_preserved():
    from web.save_load import _suit_from_dict, _suit_to_dict

    suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    suit._drain_ticks = {"vacuum": 2}

    restored = _suit_from_dict(_suit_to_dict(suit))
    assert restored._drain_ticks == {"vacuum": 2}


def test_suit_none_round_trip():
    from web.save_load import _suit_from_dict, _suit_to_dict

    assert _suit_to_dict(None) is None
    assert _suit_from_dict(None) is None


def test_suit_drain_after_round_trip_works():
    """Restored suit must keep behaving correctly when drained."""
    from web.save_load import _suit_from_dict, _suit_to_dict

    suit = Suit("Test", {"vacuum": 5}, defense_bonus=0)
    suit.current_pools["vacuum"] = 1
    suit._drain_ticks["vacuum"] = Suit.DRAIN_INTERVAL - 1  # one more tick will drain

    restored = _suit_from_dict(_suit_to_dict(suit))
    # One more drain pulls the pool to 0
    assert restored.drain_pool("vacuum") is True
    assert restored.current_pools["vacuum"] == 0


# ── Engine env / active_effects via engine_to_dict ────────────────────────────


def test_engine_to_dict_includes_environment():
    from engine.game_state import Engine
    from web.save_load import engine_to_dict

    engine = Engine()
    engine.environment = {"vacuum": 1, "radiation": 2}

    d = engine_to_dict(engine)
    assert d["environment"] == {"vacuum": 1, "radiation": 2}


def test_engine_to_dict_includes_active_effects():
    from engine.game_state import Engine
    from web.save_load import engine_to_dict

    engine = Engine()
    engine.active_effects = [
        {"type": "radiation", "dot": 1, "remaining": 3},
        {"type": "gas", "dot": 2, "remaining": 1},
    ]

    d = engine_to_dict(engine)
    assert d["active_effects"] == [
        {"type": "radiation", "dot": 1, "remaining": 3},
        {"type": "gas", "dot": 2, "remaining": 1},
    ]


def test_engine_to_dict_includes_suit():
    from engine.game_state import Engine
    from web.save_load import engine_to_dict

    engine = Engine()
    engine.suit = HAZARD_SUIT.copy()
    engine.suit.current_pools["radiation"] = 10

    d = engine_to_dict(engine)
    assert d["suit"]["name"] == "Hazard Suit"
    assert d["suit"]["current_pools"]["radiation"] == 10


def test_dict_to_engine_restores_suit_and_environment():
    from engine.game_state import Engine
    from web.save_load import dict_to_engine, engine_to_dict
    from world.galaxy import Galaxy

    engine = Engine()
    engine.galaxy = Galaxy(seed=1)
    from game.ship import Ship

    engine.ship = Ship()
    engine.suit = HAZARD_SUIT.copy()
    engine.suit.current_pools["heat"] = 5
    engine.environment = {"vacuum": 1}
    engine.active_effects = [{"type": "gas", "dot": 1, "remaining": 2}]

    d = engine_to_dict(engine)
    new_engine = Engine()
    dict_to_engine(d, new_engine)

    assert new_engine.suit is not None
    assert new_engine.suit.name == "Hazard Suit"
    assert new_engine.suit.current_pools["heat"] == 5
    assert new_engine.environment == {"vacuum": 1}
    assert new_engine.active_effects == [{"type": "gas", "dot": 1, "remaining": 2}]


def test_dict_to_engine_with_no_suit():
    """Older save dicts without 'suit' key shouldn't crash."""
    from engine.game_state import Engine
    from web.save_load import dict_to_engine, engine_to_dict
    from world.galaxy import Galaxy

    engine = Engine()
    engine.galaxy = Galaxy(seed=1)
    from game.ship import Ship

    engine.ship = Ship()

    d = engine_to_dict(engine)
    # Drop suit field to simulate an older save format
    d.pop("suit", None)

    new_engine = Engine()
    dict_to_engine(d, new_engine)
    assert new_engine.suit is None

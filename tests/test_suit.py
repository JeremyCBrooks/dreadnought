"""Tests for Suit class."""
from game.suit import Suit, EVA_SUIT, HAZARD_SUIT


def test_suit_init():
    s = Suit("Test Suit", {"vacuum": 50, "cold": 10}, defense_bonus=2)
    assert s.name == "Test Suit"
    assert s.resistances == {"vacuum": 50, "cold": 10}
    assert s.defense_bonus == 2
    assert s.current_pools == {"vacuum": 50, "cold": 10}


def test_refill_pools():
    s = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    s.current_pools["vacuum"] = 5
    s.refill_pools()
    assert s.current_pools["vacuum"] == 50


def test_eva_suit():
    assert EVA_SUIT.name == "EVA Suit"
    assert "vacuum" in EVA_SUIT.resistances
    assert EVA_SUIT.resistances["vacuum"] == 50
    assert EVA_SUIT.defense_bonus == 0


def test_hazard_suit():
    assert HAZARD_SUIT.name == "Hazard Suit"
    assert "radiation" in HAZARD_SUIT.resistances
    assert HAZARD_SUIT.defense_bonus == 1

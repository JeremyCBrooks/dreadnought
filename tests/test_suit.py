"""Tests for Suit class."""

from game.suit import EVA_SUIT, HAZARD_SUIT, Suit


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


class TestHasProtection:
    def test_has_protection_with_pool(self):
        s = Suit("Test", {"vacuum": 10})
        assert s.has_protection("vacuum") is True

    def test_no_protection_when_depleted(self):
        s = Suit("Test", {"vacuum": 10})
        s.current_pools["vacuum"] = 0
        assert s.has_protection("vacuum") is False

    def test_no_protection_for_unknown_hazard(self):
        s = Suit("Test", {"vacuum": 10})
        assert s.has_protection("radiation") is False

    def test_no_protection_when_resistance_zero(self):
        s = Suit("Test", {"vacuum": 0})
        assert s.has_protection("vacuum") is False


class TestDrainPool:
    def test_drain_returns_true_when_protected(self):
        s = Suit("Test", {"vacuum": 10})
        assert s.drain_pool("vacuum") is True

    def test_drain_returns_false_when_depleted(self):
        s = Suit("Test", {"vacuum": 10})
        s.current_pools["vacuum"] = 0
        assert s.drain_pool("vacuum") is False

    def test_drain_returns_false_for_unknown_hazard(self):
        s = Suit("Test", {"vacuum": 10})
        assert s.drain_pool("radiation") is False

    def test_drain_decrements_after_interval(self):
        s = Suit("Test", {"vacuum": 10})
        for _ in range(Suit.DRAIN_INTERVAL):
            s.drain_pool("vacuum")
        assert s.current_pools["vacuum"] == 9

    def test_drain_no_decrement_before_interval(self):
        s = Suit("Test", {"vacuum": 10})
        for _ in range(Suit.DRAIN_INTERVAL - 1):
            s.drain_pool("vacuum")
        assert s.current_pools["vacuum"] == 10

    def test_drain_multiple_cycles(self):
        s = Suit("Test", {"vacuum": 3})
        for _ in range(3 * Suit.DRAIN_INTERVAL):
            s.drain_pool("vacuum")
        assert s.current_pools["vacuum"] == 0

    def test_refill_resets_drain_ticks(self):
        s = Suit("Test", {"vacuum": 10})
        # Partially drain
        for _ in range(Suit.DRAIN_INTERVAL - 1):
            s.drain_pool("vacuum")
        s.refill_pools()
        assert s.current_pools["vacuum"] == 10
        # Drain ticks should be reset — need full interval again
        for _ in range(Suit.DRAIN_INTERVAL - 1):
            s.drain_pool("vacuum")
        assert s.current_pools["vacuum"] == 10


class TestCopy:
    def test_copy_returns_new_instance(self):
        s = Suit("Test", {"vacuum": 10}, defense_bonus=2)
        c = s.copy()
        assert c is not s

    def test_copy_preserves_attributes(self):
        s = Suit("Test", {"vacuum": 10, "cold": 5}, defense_bonus=2)
        c = s.copy()
        assert c.name == s.name
        assert c.resistances == s.resistances
        assert c.defense_bonus == s.defense_bonus
        assert c.current_pools == s.current_pools

    def test_copy_isolates_mutation(self):
        s = Suit("Test", {"vacuum": 10})
        c = s.copy()
        c.drain_pool("vacuum")
        # Original should be unaffected
        assert s._drain_ticks == {}
        assert s.current_pools["vacuum"] == 10

    def test_copy_preserves_current_state(self):
        s = Suit("Test", {"vacuum": 10})
        s.current_pools["vacuum"] = 3
        s._drain_ticks["vacuum"] = 2
        c = s.copy()
        assert c.current_pools["vacuum"] == 3
        assert c._drain_ticks["vacuum"] == 2


class TestSingletonSafety:
    """Predefined suits should not be mutated by gameplay."""

    def test_eva_suit_not_mutated_after_drain(self):
        """Copying EVA_SUIT prevents mutation of the module constant."""
        copy = EVA_SUIT.copy()
        for _ in range(Suit.DRAIN_INTERVAL):
            copy.drain_pool("vacuum")
        assert EVA_SUIT.current_pools["vacuum"] == 50

    def test_hazard_suit_not_mutated_after_drain(self):
        copy = HAZARD_SUIT.copy()
        for _ in range(Suit.DRAIN_INTERVAL):
            copy.drain_pool("radiation")
        assert HAZARD_SUIT.current_pools["radiation"] == 40


class TestRepr:
    def test_repr(self):
        s = Suit("EVA Suit", {"vacuum": 50})
        r = repr(s)
        assert "EVA Suit" in r
        assert "Suit" in r

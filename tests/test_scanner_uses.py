"""Tests for scanner limited uses (1-3 random charges, unknown to player)."""

import random

from game.ai import CreatureAI
from game.entity import Entity, Fighter
from game.loadout import Loadout
from game.scanner import perform_area_scan
from tests.conftest import MockEngine, make_arena


def _make_engine_with_scanner(uses=2, tier=1, scan_range=8):
    """Helper: engine with player at (5,5) and an equipped scanner with explicit uses."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    scanner = Entity(
        name="Scanner",
        item={"type": "scanner", "scanner_tier": tier, "range": scan_range, "uses": uses},
    )
    player.loadout = Loadout(slot1=scanner)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    return engine, scanner


# ---- uses decrement on scan ----


def test_scan_decrements_uses():
    """Each scan should decrement the scanner's uses by 1."""
    engine, scanner = _make_engine_with_scanner(uses=3)
    perform_area_scan(engine, engine.player)
    assert scanner.item["uses"] == 2


def test_scan_works_until_uses_exhausted():
    """Scanner with 1 use should work once, then fail."""
    engine, scanner = _make_engine_with_scanner(uses=1)
    result = perform_area_scan(engine, engine.player)
    assert result is not None  # scan succeeds
    assert scanner.item["uses"] == 0


def test_scan_disabled_at_zero_uses():
    """Scanner with 0 uses should not perform a scan."""
    engine, scanner = _make_engine_with_scanner(uses=0)
    result = perform_area_scan(engine, engine.player)
    assert result is None


def test_scan_disabled_message():
    """When scanner has 0 uses, a log message should indicate it's junk."""
    engine, scanner = _make_engine_with_scanner(uses=0)
    perform_area_scan(engine, engine.player)
    msgs = [m[0].lower() for m in engine.message_log.messages]
    assert any("disabled" in m or "junk" in m for m in msgs)


def test_last_use_logs_disabled():
    """When the last use is consumed, the log should tell the player the scanner is disabled."""
    engine, scanner = _make_engine_with_scanner(uses=1)
    perform_area_scan(engine, engine.player)
    msgs = [m[0].lower() for m in engine.message_log.messages]
    assert any("disabled" in m or "junk" in m or "burns out" in m or "gives out" in m for m in msgs)


def test_uses_not_shown_to_player():
    """Scan success messages should NOT reveal remaining uses count."""
    engine, scanner = _make_engine_with_scanner(uses=3)
    # Add something to scan so we get a contacts message
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180), fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    perform_area_scan(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    # No message should contain the number of uses
    for m in msgs:
        assert "uses" not in m.lower()
        assert "charge" not in m.lower()


# ---- spawning assigns random uses ----


def test_build_item_data_assigns_uses_to_scanner():
    """build_item_data for a scanner should assign 'uses' between 1 and 3."""
    from data.items import build_item_data

    defn = {
        "char": "]",
        "color": [100, 200, 255],
        "name": "Basic Scanner",
        "scanner_tier": 1,
        "range": 8,
        "type": "scanner",
        "value": 1,
    }
    rng = random.Random(42)
    item_data = build_item_data(defn, rng=rng)
    assert "uses" in item_data
    assert 1 <= item_data["uses"] <= 3


def test_build_item_data_uses_vary_with_rng():
    """Different RNG seeds should produce different use counts (across many seeds)."""
    from data.items import build_item_data

    defn = {
        "char": "]",
        "color": [100, 200, 255],
        "name": "Basic Scanner",
        "scanner_tier": 1,
        "range": 8,
        "type": "scanner",
        "value": 1,
    }
    values = set()
    for seed in range(100):
        rng = random.Random(seed)
        item_data = build_item_data(defn, rng=rng)
        values.add(item_data["uses"])
    # Should see at least 2 distinct values across 100 seeds
    assert len(values) >= 2


def test_build_item_data_non_scanner_no_uses():
    """Non-scanner items should NOT get uses assigned."""
    from data.items import build_item_data

    defn = {"type": "weapon", "value": 3, "char": "/", "color": [200, 200, 200], "name": "Pipe"}
    item_data = build_item_data(defn)
    assert "uses" not in item_data


def test_scanner_multiple_scans_then_disabled():
    """Scanner with 2 uses works twice then becomes disabled."""
    engine, scanner = _make_engine_with_scanner(uses=2)
    r1 = perform_area_scan(engine, engine.player)
    assert r1 is not None
    assert scanner.item["uses"] == 1
    r2 = perform_area_scan(engine, engine.player)
    assert r2 is not None
    assert scanner.item["uses"] == 0
    r3 = perform_area_scan(engine, engine.player)
    assert r3 is None

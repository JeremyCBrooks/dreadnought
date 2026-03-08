"""Tests for the area-scan scanner refactor (game.scanner module)."""
import numpy as np

from game.entity import Entity, Fighter
from game.scanner import perform_area_scan, ScanEntry, ScanResults, build_nearby_entries, NearbyEntry
from game.loadout import Loadout
from game.ai import CreatureAI
from world import tile_types
from tests.conftest import make_arena, MockEngine


def _make_engine_with_scanner(tier=1, scan_range=8):
    """Helper: engine with player at (5,5) and an equipped scanner."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": tier, "range": scan_range, "uses": 99})
    player.loadout = Loadout(slot1=scanner)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    return engine


def _make_visible(gm, x, y):
    """Mark a tile as visible to the player."""
    gm.visible[x, y] = True


# ====================================================================
# perform_area_scan tests
# ====================================================================

def test_scan_no_scanner():
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    result = perform_area_scan(engine, player)
    assert result is None
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("scanner" in m.lower() for m in msgs)


def test_scan_finds_creature_in_range():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=8, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    assert results is not None
    creatures = [e for e in results.entries if e.category == "creature"]
    assert len(creatures) == 1
    assert creatures[0].distance == 3


def test_scan_ignores_out_of_range():
    engine = _make_engine_with_scanner(tier=2, scan_range=3)
    enemy = Entity(x=1, y=1, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    assert results is not None
    creatures = [e for e in results.entries if e.category == "creature"]
    assert len(creatures) == 0


def test_scan_through_walls():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    engine.game_map.tiles[6, 5] = tile_types.wall
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    creatures = [e for e in results.entries if e.category == "creature"]
    assert len(creatures) == 1


def test_scan_finds_items():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    item = Entity(x=7, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    engine.game_map.entities.append(item)
    results = perform_area_scan(engine, engine.player)
    items = [e for e in results.entries if e.category == "item"]
    assert len(items) == 1


def test_scan_finds_containers():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": None, "loot": None})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert len(containers) == 1


def test_scan_finds_env_hazards():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    results = perform_area_scan(engine, engine.player)
    hazards = [e for e in results.entries if e.category == "hazard"]
    assert len(hazards) == 1
    assert hazards[0].distance == 2


def test_tier1_creature_obscured():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    creatures = [e for e in results.entries if e.category == "creature"]
    assert len(creatures) == 1
    assert "???" in creatures[0].label
    assert creatures[0].display_char == "?"


def test_tier2_creature_shows_name():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    creatures = [e for e in results.entries if e.category == "creature"]
    assert "Bot" in creatures[0].label
    assert creatures[0].display_char == "b"


def test_tier3_creature_shows_state():
    engine = _make_engine_with_scanner(tier=3, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    enemy.ai_state = "hunting"
    engine.game_map.entities.append(enemy)
    results = perform_area_scan(engine, engine.player)
    creatures = [e for e in results.entries if e.category == "creature"]
    assert "Bot" in creatures[0].label
    assert "hunting" in creatures[0].label


def test_tier1_container_shows_generic():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": loot})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert "Crate" in containers[0].label
    assert "???" in containers[0].label
    assert "HAZARD" in containers[0].label


def test_tier2_container_shows_item():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": loot})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert "Med-kit" in containers[0].label
    assert "HAZARD" in containers[0].label


def test_tier3_container_shows_hazard_type():
    engine = _make_engine_with_scanner(tier=3, scan_range=8)
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": loot})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert "Med-kit" in containers[0].label
    assert "electric" in containers[0].label


def test_scan_marks_containers_scanned():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": None, "loot": None})
    engine.game_map.entities.append(crate)
    perform_area_scan(engine, engine.player)
    assert crate.interactable["scanned"] is True


def test_scan_results_on_engine():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    from game.actions import ScanAction
    consumed = ScanAction().perform(engine, engine.player)
    assert consumed == 1
    assert engine.scan_results is not None
    assert len(engine.scan_results.entries) >= 1


def test_scan_costs_turn():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    from game.actions import ScanAction
    consumed = ScanAction().perform(engine, engine.player)
    assert consumed == 1


def test_scan_then_interact_bypasses_hazard():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=6, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": None})
    engine.game_map.entities.append(crate)
    perform_area_scan(engine, engine.player)
    assert crate.interactable["scanned"] is True
    from game.actions import InteractAction
    InteractAction(dx=-1, dy=0).perform(engine, engine.player)
    assert engine.player.fighter.hp == 10


def test_tier1_container_hazard_only():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": None})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert "HAZARD" in containers[0].label
    assert "???" not in containers[0].label


def test_container_empty():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": None, "loot": None})
    engine.game_map.entities.append(crate)
    results = perform_area_scan(engine, engine.player)
    containers = [e for e in results.entries if e.category == "container"]
    assert containers[0].label == "Crate"


def test_env_hazard_tier1_label():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    results = perform_area_scan(engine, engine.player)
    hazards = [e for e in results.entries if e.category == "hazard"]
    assert "Hazard" in hazards[0].label


def test_env_hazard_tier2_label():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    results = perform_area_scan(engine, engine.player)
    hazards = [e for e in results.entries if e.category == "hazard"]
    assert "Vacuum" in hazards[0].label


def test_scan_all_clear():
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    from game.actions import ScanAction
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("all clear" in m.lower() for m in msgs)


def test_scan_contacts_message():
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    from game.actions import ScanAction
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("1 contact" in m.lower() for m in msgs)


def test_scan_inventory_only_fails():
    """Scanner in inventory but NOT in loadout should NOT work."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8, "uses": 99})
    player.inventory.append(scanner)
    player.loadout = Loadout()  # empty loadout
    engine = MockEngine(gm, player)
    engine.scan_results = None
    results = perform_area_scan(engine, player)
    assert results is None
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("scanner" in m.lower() for m in msgs)


def test_scan_with_explicit_scanner():
    """perform_area_scan accepts an explicit scanner entity."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 2, "range": 8, "uses": 99})
    # Scanner not in loadout at all
    engine = MockEngine(gm, player)
    engine.scan_results = None
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    gm.entities.append(enemy)
    results = perform_area_scan(engine, player, scanner=scanner)
    assert results is not None
    assert len(results.entries) == 1


def test_get_all_scanners_empty():
    """Empty loadout returns no scanners."""
    loadout = Loadout()
    assert loadout.get_all_scanners() == []


def test_get_all_scanners_tool_slot():
    """Scanner in tool slot is found."""
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8, "uses": 99})
    loadout = Loadout(slot1=scanner)
    assert loadout.get_all_scanners() == [scanner]


def test_get_all_scanners_multiple_slots():
    """Scanners in multiple slots are all returned."""
    s1 = Entity(name="Basic Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 6, "uses": 99})
    s2 = Entity(name="Advanced Scanner", item={"type": "scanner", "scanner_tier": 2, "range": 10, "uses": 99})
    loadout = Loadout(slot1=s1, slot2=s2)
    result = loadout.get_all_scanners()
    assert len(result) == 2
    assert s1 in result
    assert s2 in result


def test_get_all_scanners_ignores_non_scanners():
    """Non-scanner items in slots are ignored."""
    weapon = Entity(name="Pipe", item={"type": "weapon", "value": 3})
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8, "uses": 99})
    loadout = Loadout(slot1=weapon, slot2=scanner)
    result = loadout.get_all_scanners()
    assert result == [scanner]


def test_scan_action_with_explicit_scanner():
    """ScanAction can use an explicitly provided scanner."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8, "uses": 99})
    engine = MockEngine(gm, player)
    engine.scan_results = None
    engine.scan_glow = None
    from game.actions import ScanAction
    consumed = ScanAction(scanner=scanner).perform(engine, player)
    assert consumed == 1
    assert engine.scan_results is not None


# ====================================================================
# build_nearby_entries tests (unified NEARBY HUD)
# ====================================================================

def test_nearby_visible_creature():
    """Visible creature appears in nearby with full detail."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    enemy.ai_state = "hunting"
    gm.entities.append(enemy)
    _make_visible(gm, 7, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 1
    assert "Bot" in creatures[0].label
    assert "3/3" in creatures[0].label
    assert creatures[0].display_char == "b"


def test_nearby_visible_item():
    """Visible item on ground appears in nearby."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    item = Entity(x=7, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    gm.entities.append(item)
    _make_visible(gm, 7, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    items = [e for e in entries if e.category == "item"]
    assert len(items) == 1
    assert "Med-kit" in items[0].label


def test_nearby_visible_container():
    """Visible container appears in nearby."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": None, "loot": None})
    gm.entities.append(crate)
    _make_visible(gm, 7, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    containers = [e for e in entries if e.category == "container"]
    assert len(containers) == 1
    assert "Crate" in containers[0].label


def test_nearby_scanned_creature_not_visible():
    """Scanned-only creature (not visible) uses scan-tier label."""
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    engine.game_map.visible[:] = False
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 1
    assert "???" in creatures[0].label  # tier 1 obscured


def test_nearby_deduplicates_visible_and_scanned():
    """Entity that is both visible and scanned appears only once, with visible detail."""
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    enemy.ai_state = "hunting"
    engine.game_map.entities.append(enemy)
    _make_visible(engine.game_map, 7, 5)
    # Store scan results on engine so dedup path is actually tested
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 1
    # Visible detail wins over scan tier 1 "???"
    assert "Bot" in creatures[0].label
    assert "3/3" in creatures[0].label


def test_nearby_visible_creature_plus_scanned_creature():
    """One visible creature and one scanned-only creature: two entries, no duplicates."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    visible_enemy = Entity(x=6, y=5, name="Rat", char="r", color=(127, 127, 0),
                           fighter=Fighter(1, 1, 0, 1), ai=CreatureAI())
    visible_enemy.ai_state = "wandering"
    engine.game_map.entities.append(visible_enemy)
    _make_visible(engine.game_map, 6, 5)

    hidden_enemy = Entity(x=8, y=5, name="Bot", char="b", color=(127, 0, 180),
                          fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(hidden_enemy)
    # 8,5 NOT visible

    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 2
    # Visible one has HP info
    rat_entry = [e for e in creatures if "Rat" in e.label][0]
    assert "1/1" in rat_entry.label
    # Scanned-only one has tier 2 name but no HP
    bot_entry = [e for e in creatures if "Bot" in e.label][0]
    assert "Bot" in bot_entry.label


def test_nearby_hull_breach_hazard_source():
    """Known hull breach shows as hazard source in NEARBY."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    gm.hull_breaches.append((7, 5))
    _make_visible(gm, 7, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    assert len(hazards) >= 1
    assert any("Hull breach" in h.label for h in hazards)


def test_nearby_open_airlock_hazard_source():
    """Open exterior airlock door shows as hazard source in NEARBY when visible."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    gm.tiles[7, 5] = tile_types.airlock_ext_open
    gm.airlocks.append({"exterior_door": (7, 5), "switch": (4, 5)})
    _make_visible(gm, 7, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    assert len(hazards) >= 1
    assert any("Airlock" in h.label for h in hazards)


def test_nearby_no_scan_no_visible_empty():
    """No visible entities and no scan results -> empty list."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    assert entries == []


def test_nearby_sorted_by_category_then_distance():
    """Entries sorted: creatures first, then hazards, containers, items; within by distance."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=8, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    item = Entity(x=6, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    engine.game_map.entities.append(item)
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    categories = [e.category for e in entries]
    assert categories.index("creature") < categories.index("item")


def test_nearby_hull_breach_not_visible_not_shown():
    """Hull breach that is NOT visible and NOT scanned should not appear."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    gm.hull_breaches.append((7, 5))
    gm.visible[:] = False
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    assert len(hazards) == 0


def test_nearby_scanned_env_hazard_not_visible():
    """Env hazard found by scan but not visible still shows in nearby."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    engine.game_map.visible[:] = False
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    assert len(hazards) >= 1


def test_nearby_visible_item_not_at_player_pos():
    """Items at the player's own position should NOT appear (that's UNDERFOOT)."""
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    item = Entity(x=5, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    gm.entities.append(item)
    _make_visible(gm, 5, 5)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    entries = build_nearby_entries(engine)
    items = [e for e in entries if e.category == "item"]
    assert len(items) == 0


def test_nearby_scanned_hull_breach():
    """Hull breach within scan range but not visible still appears via scan."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    engine.game_map.hull_breaches.append((7, 5))
    engine.game_map.visible[:] = False
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    assert len(hazards) >= 1


# ====================================================================
# Regression / edge-case tests for review fixes
# ====================================================================

def test_nearby_stale_scan_entry_filtered():
    """Dead creature (removed from map) should not appear from stale scan results."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=7, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    engine.scan_results = perform_area_scan(engine, engine.player)
    # Verify it's there initially
    entries = build_nearby_entries(engine)
    assert any(e.category == "creature" for e in entries)
    # Kill the enemy (remove from map)
    engine.game_map.entities.remove(enemy)
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 0


def test_nearby_dist0_scan_entry_excluded():
    """Scanned item at player position should NOT appear (UNDERFOOT territory)."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    item = Entity(x=5, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    engine.game_map.entities.append(item)
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    items = [e for e in entries if e.category == "item"]
    assert len(items) == 0


def test_nearby_visible_scanned_container_shows_scan_detail():
    """Container that is both visible and scanned should show scan-tier detail, not bare name."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    hazard = {"type": "electric", "severity": "severe", "damage": 2, "equipment_damage": True}
    crate = Entity(x=7, y=5, name="Crate", char="=", color=(180, 160, 100),
                   blocks_movement=False,
                   interactable={"kind": "crate", "hazard": hazard, "loot": loot})
    engine.game_map.entities.append(crate)
    _make_visible(engine.game_map, 7, 5)
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    containers = [e for e in entries if e.category == "container"]
    assert len(containers) == 1
    # Should show scan detail (loot name + hazard) not bare "Crate"
    assert "Med-kit" in containers[0].label
    assert "HAZARD" in containers[0].label


def test_nearby_hull_breach_deduplicates_with_scan_vacuum():
    """Visible hull breach and scanned vacuum at same position should produce one entry, not two."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    engine.game_map.hull_breaches.append((7, 5))
    _make_visible(engine.game_map, 7, 5)
    overlay = np.full((10, 10), fill_value=False, order="F")
    overlay[7, 5] = True
    engine.game_map.hazard_overlays["vacuum"] = overlay
    engine.scan_results = perform_area_scan(engine, engine.player)
    entries = build_nearby_entries(engine)
    hazards = [e for e in entries if e.category == "hazard"]
    # Should be exactly 1 — the visible "Hull breach", not also a "Vacuum" duplicate
    assert len(hazards) == 1
    assert "Hull breach" in hazards[0].label


def test_scan_contact_count_excludes_player_position():
    """ScanAction contact count should not include items at the player's position."""
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    # Item at player position (should NOT count as a contact)
    item_under = Entity(x=5, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                        blocks_movement=False, item={"type": "heal", "value": 5})
    engine.game_map.entities.append(item_under)
    # Item elsewhere (should count)
    item_away = Entity(x=7, y=5, name="Bent Pipe", char="/", color=(0, 191, 255),
                       blocks_movement=False, item={"type": "weapon", "value": 2})
    engine.game_map.entities.append(item_away)
    from game.actions import ScanAction
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    # Should say "1 contact", not "2 contacts"
    assert any("1 contact" in m.lower() for m in msgs)
    # NEARBY should show only the distant item
    entries = build_nearby_entries(engine)
    items = [e for e in entries if e.category == "item"]
    assert len(items) == 1


def test_scan_entry_distance_updates_after_player_moves():
    """Scan entry distances should reflect current player position, not scan-time position."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    enemy = Entity(x=8, y=5, name="Bot", char="b", color=(127, 0, 180),
                   fighter=Fighter(3, 3, 0, 2), ai=CreatureAI())
    engine.game_map.entities.append(enemy)
    engine.scan_results = perform_area_scan(engine, engine.player)
    # Player was at (5,5), enemy at (8,5) -> dist 3
    entries = build_nearby_entries(engine)
    assert entries[0].distance == 3
    # Player moves to (6,5)
    engine.player.x = 6
    entries = build_nearby_entries(engine)
    creatures = [e for e in entries if e.category == "creature"]
    assert len(creatures) == 1
    # Distance should now be 2, not stale 3
    assert creatures[0].distance == 2


def test_scan_item_at_player_pos_not_scanned():
    """Item at player position is not included in scan results (it's underfoot, not a contact)."""
    engine = _make_engine_with_scanner(tier=2, scan_range=8)
    item = Entity(x=5, y=5, name="Med-kit", char="!", color=(0, 255, 100),
                  blocks_movement=False, item={"type": "heal", "value": 5})
    engine.game_map.entities.append(item)
    results = perform_area_scan(engine, engine.player)
    # Item at player position should not be in scan results at all
    items = [e for e in results.entries if e.category == "item"]
    assert len(items) == 0
    # And not in NEARBY
    engine.scan_results = results
    entries = build_nearby_entries(engine)
    assert len([e for e in entries if e.category == "item"]) == 0


# ====================================================================
# Scan glow tests
# ====================================================================

SCAN_GLOW_DURATION = 3.0  # mirror the constant from game_map


def test_scan_action_sets_scan_glow():
    """ScanAction sets engine.scan_glow with center, radius, and start_time."""
    import time
    from game.actions import ScanAction
    engine = _make_engine_with_scanner(tier=1, scan_range=8)
    before = time.time()
    ScanAction().perform(engine, engine.player)
    assert engine.scan_glow is not None
    assert engine.scan_glow["cx"] == 5
    assert engine.scan_glow["cy"] == 5
    assert engine.scan_glow["radius"] == 8
    assert engine.scan_glow["start_time"] >= before


def test_scan_glow_not_set_without_scanner():
    """ScanAction without scanner does not set scan_glow."""
    from game.actions import ScanAction
    gm = make_arena()
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.scan_results = None
    engine.scan_glow = None
    ScanAction().perform(engine, player)
    assert engine.scan_glow is None


def test_scan_glow_is_circular():
    """Scan glow uses Euclidean distance (circular), not Chebyshev (square)."""
    import tcod.console
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False
    gm.explored[:] = False

    # apply_scan_glow sets visibility; render adds the green tint
    gm.apply_scan_glow(5, 5, 3)

    scan_glow = {"cx": 5, "cy": 5, "radius": 3, "start_time": 0.0}
    console = tcod.console.Console(10, 10, order="F")
    gm.render(console, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)

    shroud_ch = int(tile_types.SHROUD["ch"])
    # (5, 2) is dist 3 along cardinal — should be visible
    assert console.rgb["ch"][5, 2] != shroud_ch
    # (2, 2) is dist sqrt(18) ~= 4.24 — outside radius 3, should be shroud
    assert console.rgb["ch"][2, 2] == shroud_ch
    # (3, 3) is dist sqrt(8) ~= 2.83 — inside radius 3, should be visible
    assert console.rgb["ch"][3, 3] != shroud_ch


def test_scan_glow_expands_visibility_during_render():
    """Tiles within circular scan glow radius are rendered as visible."""
    import tcod.console
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False
    gm.explored[:] = False

    gm.apply_scan_glow(5, 5, 3)

    scan_glow = {"cx": 5, "cy": 5, "radius": 3, "start_time": 0.0}
    console = tcod.console.Console(10, 10, order="F")
    gm.render(console, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)

    shroud_ch = int(tile_types.SHROUD["ch"])
    # Center should be rendered
    assert console.rgb["ch"][5, 5] != shroud_ch
    # Cardinal direction at range should be rendered
    assert console.rgb["ch"][8, 5] != shroud_ch
    # Far corner outside Euclidean radius should be shroud
    assert console.rgb["ch"][1, 1] == shroud_ch


def test_scan_glow_tints_green_at_full_intensity(monkeypatch):
    """At start of glow (alpha=1.0), tiles have full green tint."""
    import time
    import tcod.console
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False
    gm.explored[:] = False

    # Render without glow to get base colors
    console_base = tcod.console.Console(10, 10, order="F")
    gm.visible[5, 5] = True
    gm.render(console_base, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10)
    base_fg = console_base.rgb["fg"][5, 5].copy()
    gm.visible[5, 5] = False

    # Render with glow at t=0 (full intensity)
    start = 1000.0
    monkeypatch.setattr(time, "time", lambda: start)
    gm.apply_scan_glow(5, 5, 3)
    scan_glow = {"cx": 5, "cy": 5, "radius": 3, "start_time": start}
    console_glow = tcod.console.Console(10, 10, order="F")
    gm.render(console_glow, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)
    glow_fg = console_glow.rgb["fg"][5, 5]

    # The green channel should be boosted
    assert glow_fg[1] >= base_fg[1]


def test_scan_glow_fades_over_time(monkeypatch):
    """Green tint decreases as time passes, fully gone after DURATION."""
    import time
    import tcod.console
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False
    gm.explored[:] = False

    start = 1000.0
    # Full intensity (t=0)
    monkeypatch.setattr(time, "time", lambda: start)
    scan_glow = {"cx": 5, "cy": 5, "radius": 3, "start_time": start}
    c1 = tcod.console.Console(10, 10, order="F")
    gm.render(c1, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)
    green_full = int(c1.rgb["fg"][5, 5][1])

    # Half faded (t = duration/2)
    monkeypatch.setattr(time, "time", lambda: start + SCAN_GLOW_DURATION / 2)
    c2 = tcod.console.Console(10, 10, order="F")
    gm.render(c2, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)
    green_half = int(c2.rgb["fg"][5, 5][1])

    # Half intensity should have less green tint than full
    assert green_half <= green_full

    # Fully expired (t = duration + 1)
    monkeypatch.setattr(time, "time", lambda: start + SCAN_GLOW_DURATION + 1)
    c3 = tcod.console.Console(10, 10, order="F")
    gm.render(c3, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)
    # After expiry, tiles not in visible/explored should be shroud
    shroud_ch = int(tile_types.SHROUD["ch"])
    assert c3.rgb["ch"][5, 5] == shroud_ch


def test_scan_glow_reveals_entities():
    """Entities within scan glow radius are rendered even if not normally visible."""
    import tcod.console
    engine = _make_engine_with_scanner(tier=1, scan_range=4)
    gm = engine.game_map
    gm.visible[:] = False

    enemy = Entity(x=7, y=5, name="Rat", char="r", color=(200, 100, 0),
                   blocks_movement=True, fighter=Fighter(1, 1, 0, 1), ai=CreatureAI())
    gm.entities.append(enemy)

    gm.apply_scan_glow(5, 5, 4)
    scan_glow = {"cx": 5, "cy": 5, "radius": 4, "start_time": 0.0}
    console = tcod.console.Console(10, 10, order="F")
    gm.render(console, cam_x=0, cam_y=0, vp_x=0, vp_y=0, vp_w=10, vp_h=10,
              scan_glow=scan_glow)

    # Entity at (7, 5) dist=2, should be rendered
    assert chr(console.rgb["ch"][7, 5]) == "r"


def test_scan_glow_marks_explored():
    """Tiles within scan glow radius are marked as explored (known)."""
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False
    gm.explored[:] = False

    gm.apply_scan_glow(5, 5, 3)

    # Tiles within Euclidean radius should be explored
    assert gm.explored[5, 5]
    assert gm.explored[5, 2]  # cardinal dist 3
    # Diagonal at sqrt(18) ~= 4.24 should NOT be explored
    assert not gm.explored[2, 2]


def test_scan_glow_sets_visible():
    """While scan glow is active, tiles in radius are marked visible."""
    engine = _make_engine_with_scanner(tier=1, scan_range=3)
    gm = engine.game_map
    gm.visible[:] = False

    gm.apply_scan_glow(5, 5, 3)

    assert gm.visible[5, 5]
    assert gm.visible[5, 2]  # cardinal dist 3
    assert not gm.visible[2, 2]  # outside Euclidean radius

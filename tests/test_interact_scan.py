"""Tests for InteractAction and ScanAction."""
from game.entity import Entity, Fighter
from game.actions import InteractAction, ScanAction
from game.loadout import Loadout
from tests.conftest import make_engine as _make_engine


def test_interact_with_loot():
    engine = _make_engine()
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    inter = Entity(
        x=6, y=5, name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": None, "loot": loot},
    )
    engine.game_map.entities.append(inter)
    InteractAction().perform(engine, engine.player)
    assert len(engine.player.collection_tank) == 1
    assert engine.player.collection_tank[0].name == "Med-kit"
    assert inter not in engine.game_map.entities


def test_interact_no_loot():
    engine = _make_engine()
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    InteractAction().perform(engine, engine.player)
    assert len(engine.player.inventory) == 0
    assert inter not in engine.game_map.entities


def test_interact_with_hazard():
    engine = _make_engine()
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    InteractAction().perform(engine, engine.player)
    assert engine.player.fighter.hp == 8


def test_interact_nothing_nearby():
    engine = _make_engine()
    InteractAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("Nothing to interact" in m for m in msgs)


def test_scan_tier1():
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("WARNING" in m for m in msgs)
    assert inter.interactable["scanned"] is True


def test_scan_tier2():
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 2})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "radiation", "damage": 1, "severity": "moderate", "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("Radiation" in m for m in msgs)


def test_scan_safe():
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1})
    engine.player.loadout = Loadout(tool=scanner)
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("Safe" in m for m in msgs)


def test_scan_mitigates_hazard():
    """After scanning, interacting should NOT trigger the hazard."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    assert inter.interactable["scanned"] is True
    InteractAction().perform(engine, engine.player)
    assert engine.player.fighter.hp == 10  # No damage taken


def test_unscanned_still_triggers():
    """Without scanning first, hazard should still trigger."""
    engine = _make_engine()
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    InteractAction().perform(engine, engine.player)
    assert engine.player.fighter.hp == 8  # Took 2 damage


def test_scan_then_interact_full_flow():
    """Full flow: scan reveals hazard, interact bypasses it and gets loot."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 2})
    engine.player.loadout = Loadout(tool=scanner)
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    hazard = {"type": "radiation", "damage": 1, "severity": "moderate", "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": hazard, "loot": loot},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    InteractAction().perform(engine, engine.player)
    assert engine.player.fighter.hp == 10  # No damage
    # Loot goes to collection tank
    assert len(engine.player.collection_tank) == 1
    assert engine.player.collection_tank[0].name == "Med-kit"


def test_scan_no_scanner():
    engine = _make_engine()
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("need a scanner" in m for m in msgs)

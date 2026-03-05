"""Tests for InteractAction and ScanAction."""
from game.entity import Entity, Fighter
from game.actions import InteractAction, ScanAction, ToggleDoorAction
from game.loadout import Loadout
from world import tile_types
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
    """Area scan finds adjacent container and marks it scanned."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    assert inter.interactable["scanned"] is True
    assert engine.scan_results is not None
    containers = [e for e in engine.scan_results.entries if e.category == "container"]
    assert len(containers) == 1
    assert "HAZARD" in containers[0].label


def test_scan_tier2():
    """Tier 2 area scan shows hazard type in label."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 2, "range": 8})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "radiation", "damage": 1, "severity": "moderate", "equipment_damage": False}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    containers = [e for e in engine.scan_results.entries if e.category == "container"]
    assert "HAZARD" in containers[0].label


def test_scan_safe():
    """Area scan with no hazards reports all clear or finds container."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8})
    engine.player.loadout = Loadout(tool=scanner)
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    assert inter.interactable["scanned"] is True


def test_scan_mitigates_hazard():
    """After scanning, interacting should NOT trigger the hazard."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8})
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
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 2, "range": 8})
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


# --- Directed interaction tests ---


def test_interact_directed_entity():
    """InteractAction with dx/dy targets the specific offset."""
    engine = _make_engine()
    loot = {"char": "!", "color": (0, 255, 100), "name": "Med-kit", "type": "heal", "value": 5}
    inter = Entity(
        x=6, y=6, name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": None, "loot": loot},
    )
    engine.game_map.entities.append(inter)
    # Directed: dx=1, dy=1 (diagonal from player at 5,5)
    consumed = InteractAction(dx=1, dy=1).perform(engine, engine.player)
    assert consumed == 1
    assert len(engine.player.collection_tank) == 1
    assert inter not in engine.game_map.entities


def test_interact_directed_misses():
    """InteractAction with dx/dy targeting empty space finds nothing."""
    engine = _make_engine()
    inter = Entity(
        x=6, y=5, name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    # Point away from the entity
    consumed = InteractAction(dx=-1, dy=0).perform(engine, engine.player)
    assert consumed == 0
    # Entity still there
    assert inter in engine.game_map.entities


def test_scan_directed():
    """ScanAction (area scan) finds diagonal container."""
    engine = _make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8})
    engine.player.loadout = Loadout(tool=scanner)
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False}
    inter = Entity(
        x=6, y=6, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    consumed = ScanAction().perform(engine, engine.player)
    assert consumed == 1
    assert inter.interactable["scanned"] is True


def test_adjacent_interact_dirs_mixed():
    """_adjacent_interact_dirs finds both doors and entities in all 8 dirs."""
    from ui.tactical_state import TacticalState
    engine = _make_engine()
    # Place a door to the east (cardinal)
    engine.game_map.tiles[6, 5] = tile_types.door_closed
    # Place an interactable entity to the northeast (diagonal)
    inter = Entity(
        x=6, y=4, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": None, "loot": None},
    )
    engine.game_map.entities.append(inter)
    dirs = TacticalState._adjacent_interact_dirs(engine)
    kinds = {(dx, dy): kind for dx, dy, kind in dirs}
    assert kinds[(1, 0)] == "door"
    assert kinds[(1, -1)] == "entity"
    assert len(dirs) == 2


def test_adjacent_interact_dirs_diagonal_door():
    """Doors at diagonal offsets are now detected (8-directional)."""
    from ui.tactical_state import TacticalState
    engine = _make_engine()
    # Place a door diagonally (northeast)
    engine.game_map.tiles[6, 4] = tile_types.door_closed
    dirs = TacticalState._adjacent_interact_dirs(engine)
    assert len(dirs) == 1
    dx, dy, kind = dirs[0]
    assert (dx, dy) == (1, -1)
    assert kind == "door"

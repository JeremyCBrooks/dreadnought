"""Edge case tests for areas with insufficient coverage."""
from game.entity import Entity, Fighter
from game.actions import MeleeAction, ScanAction, InteractAction, PickupAction
from game.loadout import Loadout
from game.ai import HostileAI
from game.hazards import trigger_hazard, apply_dot_effects
from game.suit import Suit
from engine.game_state import Engine
from world.game_map import GameMap
from world import tile_types
from tests.conftest import make_engine, make_arena, MockEngine


# --- Scan tier 3 ---


def test_scan_tier3_shows_details():
    engine = make_engine()
    scanner = Entity(name="Military Scanner", item={"type": "scanner", "scanner_tier": 3, "range": 8, "uses": 99})
    engine.player.loadout = Loadout(slot1=scanner)
    hazard = {"type": "electric", "damage": 3, "severity": "severe", "equipment_damage": True}
    inter = Entity(
        x=6, y=5, name="Console", blocks_movement=False,
        interactable={"kind": "console", "hazard": hazard, "loot": None},
    )
    engine.game_map.entities.append(inter)
    ScanAction().perform(engine, engine.player)
    # Tier 3 shows hazard type in container label
    containers = [e for e in engine.scan_results.entries if e.category == "container"]
    assert any("electric" in c.label for c in containers)
    assert inter.interactable["scanned"] is True


def test_scan_nothing_nearby():
    """Area scan with nothing in range returns 1 (costs turn) and logs all clear."""
    engine = make_engine()
    scanner = Entity(name="Scanner", item={"type": "scanner", "scanner_tier": 1, "range": 8, "uses": 99})
    engine.player.loadout = Loadout(slot1=scanner)
    result = ScanAction().perform(engine, engine.player)
    assert result == 1
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("all clear" in m.lower() for m in msgs)


# --- Melee with missing fighter ---


def test_melee_returns_false_without_attacker_fighter():
    gm = make_arena()
    attacker = Entity(x=5, y=5, name="Broken")  # No fighter
    target = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 1))
    gm.entities.extend([attacker, target])
    result = MeleeAction(target).perform(MockEngine(gm, attacker), attacker)
    assert result == 0


def test_melee_returns_false_without_target_fighter():
    gm = make_arena()
    attacker = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 3))
    target = Entity(x=6, y=5, name="Prop")  # No fighter
    gm.entities.extend([attacker, target])
    result = MeleeAction(target).perform(MockEngine(gm, attacker), attacker)
    assert result == 0


# --- Electric hazard with equipment damage ---


def test_electric_equipment_damage(monkeypatch):
    """Electric hazard can damage equipment in loadout."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 1, "max_durability": 5})
    engine.player.loadout = Loadout(slot1=weapon)

    hazard = {"type": "electric", "damage": 1, "equipment_damage": True, "dot": 0, "duration": 0}

    # Force random to always trigger damage
    import random
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "choice", lambda lst: lst[0])

    trigger_hazard(engine, hazard, "Console")
    # Weapon had durability 1, reaches 0 — tagged as damaged, NOT removed
    assert engine.player.loadout.slot1 is weapon
    assert weapon.item["durability"] == 0
    assert weapon.item.get("damaged") is True
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("damaged" in m.lower() for m in msgs)


def test_electric_equipment_no_damage_when_random_high(monkeypatch):
    """Electric hazard doesn't damage equipment when random > 0.5."""
    engine = make_engine()
    weapon = Entity(name="Baton", item={"type": "weapon", "value": 2, "durability": 3, "max_durability": 5})
    engine.player.loadout = Loadout(slot1=weapon)

    hazard = {"type": "electric", "damage": 1, "equipment_damage": True, "dot": 0, "duration": 0}

    import random
    monkeypatch.setattr(random, "random", lambda: 0.9)

    trigger_hazard(engine, hazard, "Console")
    assert weapon.item["durability"] == 3  # Unchanged


# --- Gas hazard without suit ---


def test_gas_hazard_no_suit():
    engine = make_engine()
    engine.suit = None
    hazard = {"type": "gas", "damage": 2, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Vent")
    assert engine.player.fighter.hp == 8  # Just HP damage, no suit drain


# --- Multiple items at same position ---


def test_pickup_takes_first_item():
    gm = make_arena()
    item_a = Entity(x=5, y=5, name="Pipe", blocks_movement=False, item={"type": "weapon", "value": 1})
    item_b = Entity(x=5, y=5, name="Kit", blocks_movement=False, item={"type": "heal", "value": 5})
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.extend([p, item_a, item_b])
    eng = MockEngine(gm, p)
    eng.player = p
    PickupAction().perform(eng, p)
    # Should pick up the first item into inventory
    assert len(p.inventory) == 1
    assert p.inventory[0].name == "Pipe"
    # Second item remains on map
    assert item_b in gm.entities


# --- is_walkable out of bounds ---


def test_is_walkable_out_of_bounds():
    gm = make_arena()
    assert gm.is_walkable(-1, 5) is False
    assert gm.is_walkable(5, -1) is False
    assert gm.is_walkable(100, 5) is False
    assert gm.is_walkable(5, 100) is False


# --- RectRoom.intersects ---


def test_rect_room_intersects():
    from world.dungeon_gen import RectRoom

    a = RectRoom(0, 0, 5, 5)
    b = RectRoom(3, 3, 5, 5)
    assert a.intersects(b)
    assert b.intersects(a)


def test_rect_room_no_intersect():
    from world.dungeon_gen import RectRoom

    a = RectRoom(0, 0, 3, 3)
    b = RectRoom(10, 10, 3, 3)
    assert not a.intersects(b)
    assert not b.intersects(a)


def test_rect_room_touching_edge():
    from world.dungeon_gen import RectRoom

    a = RectRoom(0, 0, 5, 5)  # x2=4, y2=4
    b = RectRoom(4, 0, 5, 5)  # x1=4
    # Touching at edge: intersects returns True (inclusive boundary)
    assert a.intersects(b)


# --- Multiple simultaneous environment hazards ---


def test_multiple_environment_hazards():
    import numpy as np
    from game.environment import apply_environment_tick

    suit = Suit("Test", {"vacuum": 2, "radiation": 1}, defense_bonus=0)
    engine = make_engine(env={"vacuum": 1, "radiation": 1}, suit=suit)
    # Vacuum is spatial: add overlay covering the whole map
    gm = engine.game_map
    gm.hazard_overlays["vacuum"] = np.full(
        (gm.width, gm.height), fill_value=True, order="F"
    )
    gm._hazards_dirty = False

    DI = Suit.DRAIN_INTERVAL
    for _ in range(DI):
        apply_environment_tick(engine)
    # Vacuum pool: 2 -> 1 (protected), radiation pool: 1 -> 0 (protected)
    assert suit.current_pools["vacuum"] == 1
    assert suit.current_pools["radiation"] == 0
    assert engine.player.fighter.hp == 10

    for _ in range(DI):
        apply_environment_tick(engine)
    # Vacuum pool: 1 -> 0 (protected), radiation pool: 0 (damage each tick!)
    assert suit.current_pools["vacuum"] == 0
    assert engine.player.fighter.hp == 10 - DI

    apply_environment_tick(engine)
    # Both pools at 0: both deal damage per tick
    assert engine.player.fighter.hp == 10 - DI - 2


# --- Dungeon gen per loc_type doesn't crash ---


def test_all_loc_types_generate():
    from world.dungeon_gen import generate_dungeon

    for loc_type in ("derelict", "asteroid", "starbase", "colony"):
        game_map, rooms, exit_pos = generate_dungeon(
            seed=42, loc_type=loc_type, width=80, height=45
        )
        assert game_map is not None
        assert len(rooms) >= 1


# --- Fighter negative HP test ---


def test_fighter_hp_can_reach_zero():
    f = Fighter(1, 10, 0, 1)
    f.hp = 0
    assert f.hp == 0


# --- Environment tick with zero severity ---


def test_environment_tick_zero_severity():
    from game.environment import apply_environment_tick

    suit = Suit("Test", {"vacuum": 10}, defense_bonus=0)
    engine = make_engine(env={"vacuum": 0}, suit=suit)
    apply_environment_tick(engine)
    # Zero severity should be skipped
    assert engine.player.fighter.hp == 10
    assert suit.current_pools["vacuum"] == 10


# --- DoT no player guard ---


def test_dot_no_player():
    engine = Engine()
    engine.active_effects = [{"type": "rad", "dot": 1, "remaining": 3}]
    apply_dot_effects(engine)
    assert engine.active_effects[0]["remaining"] == 3  # Unchanged


# --- Interact with both hazard and loot ---


def test_interact_hazard_and_loot():
    engine = make_engine()
    hazard = {"type": "electric", "damage": 1, "equipment_damage": False}
    loot = {"char": "!", "color": (0, 255, 0), "name": "Med-kit", "type": "heal", "value": 5}
    inter = Entity(
        x=6, y=5, name="Crate", blocks_movement=False,
        interactable={"kind": "crate", "hazard": hazard, "loot": loot},
    )
    engine.game_map.entities.append(inter)
    InteractAction().perform(engine, engine.player)
    # Player takes hazard damage AND gets loot in inventory
    assert engine.player.fighter.hp == 9
    assert len(engine.player.inventory) == 1
    assert engine.player.inventory[0].name == "Med-kit"

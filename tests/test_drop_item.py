"""Tests for dropping items from inventory."""
import tcod.event

from game.entity import Entity, Fighter
from game.loadout import Loadout
from game.actions import DropAction
from ui.inventory_state import InventoryState
from ui.tactical_state import TacticalState
from tests.conftest import make_arena, make_engine, MockEngine


class FakeEvent:
    def __init__(self, sym):
        self.sym = sym


def _press(state, engine, sym):
    return state.ev_keydown(engine, FakeEvent(sym))


# --- DropAction: tile selection logic ---


def test_drop_on_player_tile():
    """Item drops on the player's tile when no item is there."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    p.inventory.append(item)
    gm.entities.append(p)
    result = DropAction(0).perform(MockEngine(gm, p), p)
    assert result == 1
    assert item not in p.inventory
    assert item in gm.entities
    assert (item.x, item.y) == (5, 5)


def test_drop_adjacent_when_player_tile_occupied():
    """When player's tile has an item, drop on an adjacent walkable tile."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    existing = Entity(x=5, y=5, name="Junk", blocks_movement=False, item={"type": "heal", "value": 1})
    item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    p.inventory.append(item)
    gm.entities.extend([p, existing])
    result = DropAction(0).perform(MockEngine(gm, p), p)
    assert result == 1
    assert item not in p.inventory
    assert item in gm.entities
    # Should NOT be on player tile (that has existing item)
    assert (item.x, item.y) != (5, 5)
    # Should be on a walkable adjacent tile
    dx = item.x - p.x
    dy = item.y - p.y
    assert abs(dx) <= 1 and abs(dy) <= 1
    assert gm.is_walkable(item.x, item.y)


def test_drop_skips_adjacent_tiles_with_items():
    """Adjacent tiles that already have items are skipped."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    # Fill player tile and some adjacent tiles with items
    items_on_ground = []
    for x, y in [(5, 5), (4, 4), (5, 4), (6, 4)]:
        e = Entity(x=x, y=y, name="Junk", blocks_movement=False, item={"type": "heal", "value": 1})
        items_on_ground.append(e)
    drop_item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    p.inventory.append(drop_item)
    gm.entities.append(p)
    gm.entities.extend(items_on_ground)
    result = DropAction(0).perform(MockEngine(gm, p), p)
    assert result == 1
    # Should not land on any occupied tile
    occupied = {(e.x, e.y) for e in items_on_ground}
    assert (drop_item.x, drop_item.y) not in occupied


def test_drop_skips_unwalkable_adjacent_tiles():
    """Adjacent wall tiles are not valid drop targets."""
    gm = make_arena()
    # Put player at corner: (1,1) — walls on three sides
    p = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
    # Place an item on (1,1) so it tries adjacent tiles
    existing = Entity(x=1, y=1, name="Junk", blocks_movement=False, item={"type": "heal", "value": 1})
    drop_item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    p.inventory.append(drop_item)
    gm.entities.extend([p, existing])
    result = DropAction(0).perform(MockEngine(gm, p), p)
    assert result == 1
    # Should be on a walkable tile
    assert gm.is_walkable(drop_item.x, drop_item.y)


def test_drop_fails_when_no_valid_tile():
    """Cannot drop if player tile and all adjacent walkable tiles have items."""
    gm = make_arena()
    # Player at (1,1) — only 3 walkable neighbors: (2,1), (1,2), (2,2)
    p = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
    # Fill player tile and all walkable adjacent tiles
    occupied_positions = [(1, 1), (2, 1), (1, 2), (2, 2)]
    for x, y in occupied_positions:
        e = Entity(x=x, y=y, name="Junk", blocks_movement=False, item={"type": "heal", "value": 1})
        gm.entities.append(e)
    drop_item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    p.inventory.append(drop_item)
    gm.entities.append(p)
    eng = MockEngine(gm, p)
    result = DropAction(0).perform(eng, p)
    assert result == 0
    assert drop_item in p.inventory
    # Should have a message about no space
    msgs = [m[0] for m in eng.message_log.messages]
    assert any("no room" in m.lower() or "no space" in m.lower() for m in msgs)


def test_drop_unequips_item():
    """Dropping an equipped item should unequip it first."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    weapon = Entity(name="Baton", blocks_movement=False, item={"type": "weapon", "value": 3})
    p.inventory.append(weapon)
    p.loadout = Loadout(slot1=weapon)
    gm.entities.append(p)
    eng = MockEngine(gm, p)
    result = DropAction(0).perform(eng, p)
    assert result == 1
    assert weapon not in p.inventory
    assert not p.loadout.has_item(weapon)
    assert weapon in gm.entities


def test_drop_invalid_index():
    """Invalid item index is a no-op."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    result = DropAction(0).perform(MockEngine(gm, p), p)
    assert result == 0


# --- InventoryState: drop key ---


def test_inventory_drop_key_in_tactical():
    """Pressing 'd' in inventory during tactical drops the selected item."""
    engine = make_engine()
    engine.game_map.entities.append(engine.player)  # already added by make_engine
    # Remove duplicate if any
    while engine.game_map.entities.count(engine.player) > 1:
        engine.game_map.entities.remove(engine.player)

    item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)
    engine.player.loadout = Loadout()

    # Simulate tactical state with inventory overlay
    tactical = TacticalState()
    engine._state_stack = [tactical]
    inv_state = InventoryState()
    engine._state_stack.append(inv_state)

    inv_state.selected = 0
    _press(inv_state, engine, tcod.event.KeySym.d)

    assert item not in engine.player.inventory
    assert item in engine.game_map.entities


def test_inventory_drop_key_not_in_tactical():
    """Pressing 'd' in inventory outside tactical state does nothing."""
    engine = make_engine()
    item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)
    engine.player.loadout = Loadout()

    # No tactical state in stack
    engine._state_stack = []
    inv_state = InventoryState()
    engine._state_stack.append(inv_state)

    inv_state.selected = 0
    _press(inv_state, engine, tcod.event.KeySym.d)

    assert item in engine.player.inventory


def test_drop_clamps_selected():
    """After dropping the last item, selected index should clamp."""
    engine = make_engine()
    while engine.game_map.entities.count(engine.player) > 1:
        engine.game_map.entities.remove(engine.player)

    item = Entity(name="Medkit", blocks_movement=False, item={"type": "heal", "value": 5})
    engine.player.inventory.append(item)
    engine.player.loadout = Loadout()

    tactical = TacticalState()
    engine._state_stack = [tactical]
    inv_state = InventoryState()
    engine._state_stack.append(inv_state)

    inv_state.selected = 0
    _press(inv_state, engine, tcod.event.KeySym.d)

    assert inv_state.selected == 0
    assert len(engine.player.inventory) == 0

"""Tests for ranged line-of-sight: shots must not pass through non-walkable tiles."""

from game.actions import RangedAction
from game.entity import Entity, Fighter
from game.helpers import has_clear_shot
from game.loadout import Loadout
from tests.conftest import make_arena, make_engine
from world import tile_types


def _ranged_weapon(ammo=5, range_=10, value=3):
    return Entity(
        name="Blaster",
        item={
            "type": "weapon",
            "weapon_class": "ranged",
            "value": value,
            "range": range_,
            "ammo": ammo,
            "max_ammo": 20,
        },
    )


# --- has_clear_shot helper ---


def test_clear_shot_open_floor():
    """Clear line on open floor returns True."""
    gm = make_arena(20, 20)
    assert has_clear_shot(gm, 5, 5, 10, 5) is True


def test_clear_shot_blocked_by_wall():
    """Wall tile between shooter and target blocks the shot."""
    gm = make_arena(20, 20)
    gm.tiles[7, 5] = tile_types.wall
    assert has_clear_shot(gm, 5, 5, 10, 5) is False


def test_clear_shot_blocked_by_closed_door():
    """Closed door between shooter and target blocks the shot."""
    gm = make_arena(20, 20)
    gm.tiles[7, 5] = tile_types.door_closed
    assert has_clear_shot(gm, 5, 5, 10, 5) is False


def test_clear_shot_through_open_door():
    """Open door does not block the shot."""
    gm = make_arena(20, 20)
    gm.tiles[7, 5] = tile_types.door_open
    assert has_clear_shot(gm, 5, 5, 10, 5) is True


def test_clear_shot_blocked_by_window():
    """Window (transparent but non-walkable) blocks the shot."""
    gm = make_arena(20, 20)
    gm.tiles[7, 5] = tile_types.structure_window
    assert has_clear_shot(gm, 5, 5, 10, 5) is False


def test_clear_shot_diagonal():
    """Diagonal shot through open floor succeeds."""
    gm = make_arena(20, 20)
    assert has_clear_shot(gm, 5, 5, 8, 8) is True


def test_clear_shot_diagonal_blocked():
    """Wall on diagonal path blocks the shot."""
    gm = make_arena(20, 20)
    gm.tiles[7, 7] = tile_types.wall
    assert has_clear_shot(gm, 5, 5, 8, 8) is False


def test_clear_shot_adjacent():
    """Adjacent targets always have clear shot (no intermediate tiles)."""
    gm = make_arena(20, 20)
    assert has_clear_shot(gm, 5, 5, 6, 5) is True


def test_clear_shot_same_tile():
    """Same position always returns True."""
    gm = make_arena(20, 20)
    assert has_clear_shot(gm, 5, 5, 5, 5) is True


def test_clear_shot_target_tile_not_checked():
    """The target's own tile is not checked — only intermediate tiles matter."""
    gm = make_arena(20, 20)
    # Set the target tile to non-walkable; shot should still succeed
    # because we only check *intermediate* tiles, not the endpoint
    gm.tiles[10, 5] = tile_types.wall
    # From adjacent tile — no intermediates, target tile ignored
    assert has_clear_shot(gm, 9, 5, 10, 5) is True
    # From farther away — intermediates (6..9) are floor, target (10) ignored
    assert has_clear_shot(gm, 5, 5, 10, 5) is True


# --- RangedAction integration ---


def test_ranged_blocked_by_wall():
    """RangedAction fails when a wall is between shooter and target."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=8, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[8, 5] = True
    # Place wall between player (5,5) and target (8,5)
    engine.game_map.tiles[7, 5] = tile_types.wall
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("clear shot" in m.lower() or "blocked" in m.lower() for m in msgs)


def test_ranged_blocked_by_window():
    """RangedAction fails when a window is between shooter and target."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=8, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[8, 5] = True
    engine.game_map.tiles[7, 5] = tile_types.structure_window
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0


def test_ranged_succeeds_clear_path():
    """RangedAction succeeds when path is clear."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=8, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[8, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 1

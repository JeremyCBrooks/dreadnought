"""Tests for code review fixes: loadout guard and entity index invalidation."""
from game.entity import Entity, Fighter
from game.loadout import recalc_melee_power
from game.actions import MovementAction
from tests.conftest import make_arena, MockEngine


def test_recalc_melee_power_no_fighter():
    """recalc_melee_power should not crash on entity without fighter."""
    entity = Entity(name="Civilian")
    assert entity.fighter is None
    # Should return without error
    recalc_melee_power(entity)


def test_movement_action_invalidates_entity_index():
    """After MovementAction, get_blocking_entity at new position should find the entity."""
    gm = make_arena(10, 10)
    player = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(player)
    engine = MockEngine(gm, player)

    # Move player right
    action = MovementAction(1, 0)
    ticks = action.perform(engine, player)
    assert ticks > 0
    assert player.x == 6
    assert player.y == 5

    # Entity index should reflect new position
    blocker = gm.get_blocking_entity(6, 5)
    assert blocker is player

    # Old position should be empty
    old_blocker = gm.get_blocking_entity(5, 5)
    assert old_blocker is None

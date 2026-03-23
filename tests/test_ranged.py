"""Tests for ranged combat: RangedAction, AI ranged attacks, and AI wander."""

from game.actions import RangedAction
from game.ai import HostileAI
from game.entity import Entity, Fighter
from game.helpers import get_equipped_ranged_weapon
from game.loadout import Loadout
from tests.conftest import make_engine


def _ranged_weapon(ammo=5, range_=5, value=3):
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


def _melee_weapon():
    return Entity(
        name="Pipe",
        item={"type": "weapon", "weapon_class": "melee", "value": 2},
    )


# --- get_equipped_ranged_weapon ---


def test_get_ranged_weapon_found():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_ranged_weapon())
    assert get_equipped_ranged_weapon(player) is not None


def test_get_ranged_weapon_no_ammo():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_ranged_weapon(ammo=0))
    assert get_equipped_ranged_weapon(player) is None


def test_get_ranged_weapon_only_melee():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_melee_weapon())
    assert get_equipped_ranged_weapon(player) is None


def test_get_ranged_weapon_empty_inventory():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    assert get_equipped_ranged_weapon(player) is None


def test_get_ranged_weapon_ignores_unequipped_inventory():
    """Player with empty-ammo loadout weapon must NOT fall back to unequipped inventory."""
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    equipped = _ranged_weapon(ammo=0)
    unequipped = _ranged_weapon(ammo=10)
    player.loadout = Loadout(slot1=equipped)
    player.inventory = [equipped, unequipped]
    # Should return None — the equipped weapon has no ammo,
    # and the unequipped one should NOT be auto-selected
    assert get_equipped_ranged_weapon(player) is None


def test_unequipped_ranged_weapon_cannot_fire():
    """Firing must fail when the equipped weapon has no ammo, even if
    another ranged weapon with ammo sits unequipped in inventory."""
    engine = make_engine()
    equipped = _ranged_weapon(ammo=0)
    spare = _ranged_weapon(ammo=10)
    engine.player.loadout = Loadout(slot1=equipped)
    engine.player.inventory = [equipped, spare]
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    assert target.fighter.hp == 5  # no damage
    assert spare.item["ammo"] == 10  # spare untouched


def test_ai_uses_inventory_ranged_weapon():
    """AI enemies (no loadout) should still fire from inventory."""
    make_engine()
    enemy = Entity(x=8, y=5, name="Drone", fighter=Fighter(4, 4, 0, 3), blocks_movement=True, ai=HostileAI())
    weapon = _ranged_weapon(ammo=5, range_=5, value=3)
    enemy.inventory = [weapon]
    assert get_equipped_ranged_weapon(enemy) is weapon  # AI can use inventory


# --- RangedAction ---


def test_ranged_hit():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 2), blocks_movement=True)
    engine.game_map.entities.append(target)
    # Make target visible
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 1
    assert target.fighter.hp < 5  # took damage


def test_ranged_ammo_decrement():
    engine = make_engine()
    weapon = _ranged_weapon(ammo=3)
    engine.player.loadout = Loadout(slot1=weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(10, 10, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    assert weapon.item["ammo"] == 2


def test_ranged_out_of_range():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(range_=2))
    target = Entity(x=8, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[8, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("out of range" in m for m in msgs)


def test_ranged_no_weapon():
    engine = make_engine()
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No ranged weapon equipped" in m for m in msgs)


def test_ranged_no_ammo():
    """Weapon equipped but ammo=0 → blocked, message mentions ammo."""
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(ammo=0))
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    assert target.fighter.hp == 5  # no damage dealt
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("ammo" in m.lower() for m in msgs)


def test_ranged_no_ammo_message_distinct_from_no_weapon():
    """Out-of-ammo message should differ from 'no ranged weapon' message."""
    engine = make_engine()
    # Case 1: weapon equipped, no ammo
    engine.player.loadout = Loadout(slot1=_ranged_weapon(ammo=0))
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    ammo_msgs = [m[0] for m in engine.message_log.messages]

    # Case 2: no weapon at all
    engine2 = make_engine()
    engine2.player.loadout = Loadout()  # empty loadout
    target2 = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine2.game_map.entities.append(target2)
    engine2.game_map.visible[7, 5] = True
    RangedAction(target2).perform(engine2, engine2.player)
    no_weapon_msgs = [m[0] for m in engine2.message_log.messages]

    # Messages should be different
    assert ammo_msgs != no_weapon_msgs


def test_ranged_last_bullet_then_blocked():
    """Fire the last bullet (ammo 1→0), then verify next shot is blocked."""
    engine = make_engine()
    weapon = _ranged_weapon(ammo=1)
    engine.player.loadout = Loadout(slot1=weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(50, 50, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    # Fire last bullet
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 1
    assert weapon.item["ammo"] == 0
    # Now try again — should fail
    result2 = RangedAction(target).perform(engine, engine.player)
    assert result2 == 0
    assert weapon.item["ammo"] == 0  # must not go negative


def test_ranged_ammo_never_negative():
    """Firing with ammo=0 must not decrement ammo below zero."""
    engine = make_engine()
    weapon = _ranged_weapon(ammo=0)
    engine.player.loadout = Loadout(slot1=weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(10, 10, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    assert weapon.item["ammo"] >= 0


def test_ranged_exhaust_all_ammo_then_blocked():
    """Fire every shot until ammo=0, then verify weapon refuses to fire."""
    engine = make_engine()
    starting_ammo = 5
    weapon = _ranged_weapon(ammo=starting_ammo, value=1)
    engine.player.loadout = Loadout(slot1=weapon)
    # Also place weapon in inventory (matching real gameplay)
    engine.player.inventory.append(weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(500, 500, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True

    # Fire all shots
    for i in range(starting_ammo):
        result = RangedAction(target).perform(engine, engine.player)
        assert result == 1, f"Shot {i + 1} should fire (ammo was {starting_ammo - i})"
        assert weapon.item["ammo"] == starting_ammo - i - 1

    assert weapon.item["ammo"] == 0

    # Now EVERY subsequent attempt must fail
    for _ in range(3):
        result = RangedAction(target).perform(engine, engine.player)
        assert result == 0, "Should NOT fire with 0 ammo"
        assert weapon.item["ammo"] == 0, "Ammo must not go negative"
        assert target.fighter.hp == 500 - starting_ammo  # no extra damage


def test_ui_enter_ranged_blocked_when_no_ammo():
    """_enter_ranged must refuse to activate targeting when ammo is 0."""
    from ui.tactical_state import TacticalState

    engine = make_engine()
    weapon = _ranged_weapon(ammo=0)
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True

    state = TacticalState()
    state._enter_ranged(engine)
    # Targeting must NOT activate
    assert state._ranged_cursor is None
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("ammo" in m.lower() for m in msgs)


def test_ui_confirm_blocked_when_ammo_depleted_mid_targeting():
    """If ammo somehow reaches 0 while in targeting mode, confirm must not fire."""
    import tcod.event

    from ui.tactical_state import TacticalState

    engine = make_engine()
    weapon = _ranged_weapon(ammo=1)
    engine.player.loadout = Loadout(slot1=weapon)
    engine.player.inventory.append(weapon)
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(500, 500, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True

    state = TacticalState()
    state._enter_ranged(engine)
    assert state._ranged_cursor is not None

    # Manually set ammo to 0 (simulating external drain or edge case)
    weapon.item["ammo"] = 0

    # Pressing confirm must NOT fire
    state._handle_ranged_input(engine, tcod.event.KeySym.RETURN)
    assert state._ranged_cursor is None  # exited targeting
    assert target.fighter.hp == 500  # no damage dealt
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("ammo" in m.lower() for m in msgs)


def test_ranged_kills_removes():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(value=10))
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(1, 1, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    assert target not in engine.game_map.entities


def test_ranged_not_visible():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0), blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = False
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0


# --- AI ranged attack ---


def test_ai_ranged_attack():
    engine = make_engine()
    enemy = Entity(x=8, y=5, name="Drone", fighter=Fighter(4, 4, 0, 3), blocks_movement=True, ai=HostileAI())
    enemy.inventory = [_ranged_weapon(ammo=5, range_=5, value=3)]
    engine.game_map.entities.append(enemy)
    # Make both enemy and player positions visible (FOV is player-centric)
    engine.game_map.visible[8, 5] = True
    engine.game_map.visible[5, 5] = True
    old_hp = engine.player.fighter.hp
    enemy.ai.perform(enemy, engine)
    # Enemy should have fired (not moved)
    assert enemy.x == 8 and enemy.y == 5  # didn't move
    assert engine.player.fighter.hp < old_hp  # player took damage


def test_ai_wander_when_not_visible():
    engine = make_engine()
    enemy = Entity(x=3, y=3, name="Rat", fighter=Fighter(1, 1, 0, 1), blocks_movement=True, ai=HostileAI())
    engine.game_map.entities.append(enemy)
    engine.game_map.visible[3, 3] = False
    old_x, old_y = enemy.x, enemy.y
    enemy.ai.perform(enemy, engine)
    # Should have wandered (moved to adjacent tile or stayed if blocked)
    dist = abs(enemy.x - old_x) + abs(enemy.y - old_y)
    assert dist <= 2  # moved at most 1 step (Manhattan distance for diagonal)


def test_ai_boxed_in_no_crash():
    """Enemy surrounded by walls should not crash when trying to wander."""
    engine = make_engine()
    # Place enemy at (1, 1) — surrounded by walls on all sides in the 10x10 arena
    # Actually (1,1) is floor, but let's put it in a corner where 3 sides are walls
    enemy = Entity(x=1, y=1, name="Rat", fighter=Fighter(1, 1, 0, 1), blocks_movement=True, ai=HostileAI())
    engine.game_map.entities.append(enemy)
    engine.game_map.visible[1, 1] = False
    # Fill surrounding tiles with blocking entities to box in
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = 1 + dx, 1 + dy
            if engine.game_map.is_walkable(nx, ny):
                blocker = Entity(x=nx, y=ny, name="Wall", blocks_movement=True)
                engine.game_map.entities.append(blocker)
    enemy.ai.perform(enemy, engine)
    # Should not crash, enemy stays put
    assert enemy.x == 1 and enemy.y == 1

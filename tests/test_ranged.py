"""Tests for ranged combat: RangedAction, AI ranged attacks, and AI wander."""
from game.entity import Entity, Fighter
from game.actions import RangedAction, _get_equipped_ranged_weapon
from game.loadout import Loadout
from game.ai import HostileAI
from tests.conftest import make_engine, make_arena, MockEngine


def _ranged_weapon(ammo=5, range_=5, value=3):
    return Entity(
        name="Blaster",
        item={
            "type": "weapon", "weapon_class": "ranged",
            "value": value, "range": range_, "ammo": ammo, "max_ammo": 20,
        },
    )


def _melee_weapon():
    return Entity(
        name="Pipe",
        item={"type": "weapon", "weapon_class": "melee", "value": 2},
    )


# --- _get_equipped_ranged_weapon ---

def test_get_ranged_weapon_found():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_ranged_weapon())
    assert _get_equipped_ranged_weapon(player) is not None


def test_get_ranged_weapon_no_ammo():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_ranged_weapon(ammo=0))
    assert _get_equipped_ranged_weapon(player) is None


def test_get_ranged_weapon_only_melee():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    player.loadout = Loadout(slot1=_melee_weapon())
    assert _get_equipped_ranged_weapon(player) is None


def test_get_ranged_weapon_empty_inventory():
    player = Entity(name="Player", fighter=Fighter(10, 10, 0, 1))
    assert _get_equipped_ranged_weapon(player) is None


# --- RangedAction ---

def test_ranged_hit():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 2),
                    blocks_movement=True)
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
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(10, 10, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    assert weapon.item["ammo"] == 2


def test_ranged_out_of_range():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(range_=2))
    target = Entity(x=8, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[8, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("out of range" in m for m in msgs)


def test_ranged_no_weapon():
    engine = make_engine()
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0
    msgs = [m[0] for m in engine.message_log.messages]
    assert any("No ranged weapon" in m for m in msgs)


def test_ranged_no_ammo():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(ammo=0))
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0


def test_ranged_kills_removes():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon(value=10))
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(1, 1, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = True
    RangedAction(target).perform(engine, engine.player)
    assert target not in engine.game_map.entities


def test_ranged_not_visible():
    engine = make_engine()
    engine.player.loadout = Loadout(slot1=_ranged_weapon())
    target = Entity(x=7, y=5, name="Bot", fighter=Fighter(5, 5, 0, 0),
                    blocks_movement=True)
    engine.game_map.entities.append(target)
    engine.game_map.visible[7, 5] = False
    result = RangedAction(target).perform(engine, engine.player)
    assert result == 0


# --- AI ranged attack ---

def test_ai_ranged_attack():
    engine = make_engine()
    enemy = Entity(x=8, y=5, name="Drone", fighter=Fighter(4, 4, 0, 3),
                   blocks_movement=True, ai=HostileAI())
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
    enemy = Entity(x=3, y=3, name="Rat", fighter=Fighter(1, 1, 0, 1),
                   blocks_movement=True, ai=HostileAI())
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
    enemy = Entity(x=1, y=1, name="Rat", fighter=Fighter(1, 1, 0, 1),
                   blocks_movement=True, ai=HostileAI())
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

"""Tests for low gravity environment hazard."""
from game.entity import Entity, Fighter
from game.actions import MovementAction, BumpAction, WaitAction
from game.environment import apply_environment_tick, has_low_gravity
from game.suit import Suit
from tests.conftest import make_arena, make_engine, MockEngine


# -- has_low_gravity helper --


def test_has_low_gravity_true():
    engine = make_engine(env={"low_gravity": 1})
    assert has_low_gravity(engine) is True


def test_has_low_gravity_false_when_absent():
    engine = make_engine(env={"vacuum": 1})
    assert has_low_gravity(engine) is False


def test_has_low_gravity_false_when_no_env():
    engine = make_engine(env=None)
    assert has_low_gravity(engine) is False


# -- Movement costs 2 ticks in low gravity --


def test_movement_returns_2_in_low_gravity():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p, environment={"low_gravity": 1})
    result = MovementAction(1, 0).perform(eng, p)
    assert result == 2
    assert (p.x, p.y) == (6, 5)


def test_movement_returns_1_without_low_gravity():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p, environment={"vacuum": 1})
    result = MovementAction(1, 0).perform(eng, p)
    assert result == 1


def test_blocked_movement_returns_0_in_low_gravity():
    gm = make_arena()
    p = Entity(x=1, y=1, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p, environment={"low_gravity": 1})
    result = MovementAction(-1, 0).perform(eng, p)
    assert result == 0


def test_bump_move_returns_2_in_low_gravity():
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    gm.entities.append(p)
    eng = MockEngine(gm, p, environment={"low_gravity": 1})
    result = BumpAction(1, 0).perform(eng, p)
    assert result == 2


def test_bump_attack_returns_1_in_low_gravity():
    """Melee attacks are not slowed by low gravity."""
    gm = make_arena()
    p = Entity(x=5, y=5, name="Player", fighter=Fighter(10, 10, 0, 3))
    e = Entity(x=6, y=5, name="Rat", fighter=Fighter(3, 3, 0, 1))
    gm.entities.extend([p, e])
    eng = MockEngine(gm, p, environment={"low_gravity": 1})
    result = BumpAction(1, 0).perform(eng, p)
    assert result == 1


def test_wait_returns_1_in_low_gravity():
    """Waiting is not affected by low gravity."""
    gm = make_arena()
    p = Entity(x=5, y=5, fighter=Fighter(10, 10, 0, 1))
    eng = MockEngine(gm, p, environment={"low_gravity": 1})
    result = WaitAction().perform(eng, p)
    assert result == 1


# -- Low gravity does not deal damage --


def test_low_gravity_no_damage():
    suit = Suit("Test", {}, defense_bonus=0)
    engine = make_engine(env={"low_gravity": 1}, suit=suit)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 10


def test_low_gravity_with_other_hazards():
    """Low gravity itself deals no damage; other hazards in same env still do."""
    suit = Suit("Test", {}, defense_bonus=0)
    engine = make_engine(env={"low_gravity": 1, "radiation": 1}, suit=suit)
    apply_environment_tick(engine)
    assert engine.player.fighter.hp == 9  # radiation deals 1, low_gravity deals 0


# -- Low gravity restricted to asteroids and derelicts --


def test_low_gravity_allowed_on_asteroid():
    from world.galaxy import Location
    loc = Location("Test Rock", "asteroid", environment={"vacuum": 1, "low_gravity": 1})
    assert loc.environment.get("low_gravity") == 1


def test_low_gravity_allowed_on_derelict():
    from world.galaxy import Location
    loc = Location("Ghost Ship", "derelict", environment={"vacuum": 1, "low_gravity": 1})
    assert loc.environment.get("low_gravity") == 1


def test_low_gravity_stripped_from_colony():
    from world.galaxy import Location
    loc = Location("Greenville", "colony", environment={"low_gravity": 1})
    assert "low_gravity" not in loc.environment


def test_low_gravity_stripped_from_starbase():
    from world.galaxy import Location
    loc = Location("Station Alpha", "starbase", environment={"low_gravity": 1})
    assert "low_gravity" not in loc.environment

"""Tests for organic vs machine entity behavior with environmental hazards."""
import numpy as np

from game.ai import HostileAI
from game.entity import Entity, Fighter
from game.environment import apply_environment_tick_entity
from tests.conftest import MockEngine, make_arena


# ===================================================================
# Entity organic attribute
# ===================================================================


def test_entity_defaults_to_organic():
    e = Entity()
    assert e.organic is True


def test_entity_can_be_non_organic():
    e = Entity(organic=False)
    assert e.organic is False


def test_entity_has_move_cooldown_default():
    e = Entity()
    assert e.move_cooldown == 0


# ===================================================================
# Data integrity: entities.json organic flags
# ===================================================================


def test_entities_json_organic_flags():
    """Bot and Security Drone are machines; Rat and Pirate are organic."""
    from data import db
    enemies = {e["name"]: e.get("organic", True) for e in db.enemies()}
    assert enemies["Rat"] is True
    assert enemies["Pirate"] is True
    assert enemies["Bot"] is False
    assert enemies["Security Drone"] is False


# ===================================================================
# Dungeon generation passes organic through
# ===================================================================


def test_spawn_passes_organic_flag():
    """Spawned enemies inherit the organic flag from data definitions."""
    from world.dungeon_gen import generate_dungeon
    gm, rooms, _ = generate_dungeon(seed=42, max_rooms=8, max_enemies=3, max_items=0)
    fighters = [e for e in gm.entities if e.fighter]
    assert len(fighters) > 0, "Need at least one enemy to test"
    for e in fighters:
        if e.name in ("Bot", "Security Drone"):
            assert e.organic is False, f"{e.name} should be non-organic"
        elif e.name in ("Rat", "Pirate"):
            assert e.organic is True, f"{e.name} should be organic"


# ===================================================================
# Vacuum immunity for machines
# ===================================================================


class TestMachineVacuumImmunity:
    """Non-organic entities should not take vacuum damage."""

    @staticmethod
    def _make_vacuum_engine(entity_x=5, entity_y=5, organic=False, hp=3):
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[entity_x, entity_y] = True
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        entity = Entity(
            x=entity_x, y=entity_y, name="TestEntity",
            fighter=Fighter(hp, hp, 0, 1), organic=organic,
        )
        gm.entities.extend([player, entity])
        engine = MockEngine(gm, player, environment={"vacuum": 1})
        return engine, entity

    def test_machine_takes_no_vacuum_damage(self):
        engine, bot = self._make_vacuum_engine(organic=False, hp=3)
        apply_environment_tick_entity(engine, bot)
        assert bot.fighter.hp == 3

    def test_organic_takes_vacuum_damage(self):
        engine, rat = self._make_vacuum_engine(organic=True, hp=3)
        apply_environment_tick_entity(engine, rat)
        assert rat.fighter.hp == 2

    def test_machine_survives_sustained_vacuum(self):
        """Machine takes no damage after many vacuum ticks."""
        engine, bot = self._make_vacuum_engine(organic=False, hp=3)
        for _ in range(10):
            apply_environment_tick_entity(engine, bot)
        assert bot.fighter.hp == 3

    def test_organic_dies_from_sustained_vacuum(self):
        """Organic entity with low HP dies after enough vacuum ticks."""
        engine, rat = self._make_vacuum_engine(organic=True, hp=2)
        apply_environment_tick_entity(engine, rat)
        assert rat.fighter.hp == 1
        apply_environment_tick_entity(engine, rat)
        assert rat.fighter.hp <= 0
        assert rat not in engine.game_map.entities

    def test_machine_at_1hp_survives_vacuum(self):
        """Machine with 1 HP on vacuum tile should not die."""
        engine, bot = self._make_vacuum_engine(organic=False, hp=1)
        apply_environment_tick_entity(engine, bot)
        assert bot.fighter.hp == 1
        assert bot in engine.game_map.entities

    def test_organic_and_machine_same_tile(self):
        """Organic dies while machine survives on the same vacuum tile."""
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[5, 5] = True
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     blocks_movement=False, organic=True)
        bot = Entity(x=5, y=5, name="Bot", fighter=Fighter(1, 1, 0, 2),
                     blocks_movement=False, organic=False)
        gm.entities.extend([player, rat, bot])
        engine = MockEngine(gm, player, environment={"vacuum": 1})
        apply_environment_tick_entity(engine, rat)
        apply_environment_tick_entity(engine, bot)
        assert rat.fighter.hp <= 0
        assert rat not in gm.entities
        assert bot.fighter.hp == 1
        assert bot in gm.entities


# ===================================================================
# Machines still take non-vacuum hazard damage
# ===================================================================


class TestMachineOtherHazards:
    """Non-organic entities are only immune to vacuum, not other hazards."""

    def test_machine_takes_radiation_damage(self):
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=5, y=5, name="Bot", fighter=Fighter(3, 3, 0, 2), organic=False)
        gm.entities.extend([player, bot])
        engine = MockEngine(gm, player, environment={"radiation": 1})
        apply_environment_tick_entity(engine, bot)
        assert bot.fighter.hp == 2

    def test_machine_in_vacuum_and_radiation(self):
        """Machine in vacuum + radiation should only take radiation damage."""
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[5, 5] = True
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=5, y=5, name="Bot", fighter=Fighter(5, 5, 0, 2), organic=False)
        gm.entities.extend([player, bot])
        engine = MockEngine(gm, player, environment={"vacuum": 1, "radiation": 1})
        apply_environment_tick_entity(engine, bot)
        assert bot.fighter.hp == 4  # 1 radiation, 0 vacuum

    def test_organic_in_vacuum_and_radiation(self):
        """Organic entity in vacuum + radiation takes damage from both."""
        gm = make_arena()
        overlay = np.full((gm.width, gm.height), fill_value=False, order="F")
        overlay[5, 5] = True
        gm.hazard_overlays["vacuum"] = overlay
        gm._hazards_dirty = False
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(5, 5, 0, 1), organic=True)
        gm.entities.extend([player, rat])
        engine = MockEngine(gm, player, environment={"vacuum": 1, "radiation": 1})
        apply_environment_tick_entity(engine, rat)
        assert rat.fighter.hp == 3  # 1 vacuum + 1 radiation


# ===================================================================
# Low gravity movement cooldown for organic enemies
# ===================================================================


class TestLowGravityOrganicEnemy:
    """Organic enemies get a 2-tick movement penalty in low gravity."""

    def test_move_skip_move_pattern(self):
        """Organic enemy: move, skip, move, skip — 50% movement rate."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moved = []
        for _ in range(6):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            moved.append((rat.x, rat.y) != (old_x, old_y))

        # Pattern should be: True, False, True, False, True, False
        assert moved == [True, False, True, False, True, False]

    def test_melee_attack_unaffected_by_cooldown(self):
        """Adjacent organic enemy attacks every turn in low gravity."""
        gm = make_arena()
        player = Entity(x=5, y=5, name="Player", fighter=Fighter(20, 20, 0, 1))
        pirate = Entity(x=5, y=6, name="Pirate", fighter=Fighter(5, 5, 1, 3),
                        ai=HostileAI(), organic=True)
        gm.entities.extend([player, pirate])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        for _ in range(4):
            old_hp = player.fighter.hp
            pirate.ai.perform(pirate, engine)
            assert player.fighter.hp < old_hp, "Should attack every turn"
        # 4 attacks, each dealing at least 1 damage
        assert player.fighter.hp <= 20 - 4

    def test_ranged_attack_unaffected_by_cooldown(self):
        """Ranged organic enemy fires every turn in low gravity."""
        gm = make_arena()
        player = Entity(x=2, y=5, name="Player", fighter=Fighter(20, 20, 0, 1))
        blaster = Entity(
            char="}", color=(200, 80, 80), name="Blaster",
            blocks_movement=False,
            item={"type": "weapon", "value": 2, "weapon_class": "ranged",
                  "range": 5, "ammo": 10, "max_ammo": 10},
        )
        pirate = Entity(x=7, y=5, name="Pirate", fighter=Fighter(5, 5, 1, 3),
                        ai=HostileAI(), organic=True)
        pirate.inventory.append(blaster)
        gm.entities.extend([player, pirate])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        hits = 0
        for _ in range(4):
            old_hp = player.fighter.hp
            pirate.ai.perform(pirate, engine)
            if player.fighter.hp < old_hp:
                hits += 1
        assert hits == 4, "Should fire every turn regardless of cooldown"

    def test_wander_slowed_in_low_gravity(self):
        """Organic enemy wandering (not visible) is also slowed."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        gm.visible[:] = False  # enemy not visible -> wanders
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moved = []
        for _ in range(4):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            moved.append((rat.x, rat.y) != (old_x, old_y))

        assert moved == [True, False, True, False]


class TestLowGravityMachineEnemy:
    """Non-organic enemies are unaffected by low gravity movement penalty."""

    def test_moves_every_turn(self):
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=7, y=7, name="Bot", fighter=Fighter(3, 3, 0, 2),
                     ai=HostileAI(), organic=False)
        gm.entities.extend([player, bot])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(4):
            old_x, old_y = bot.x, bot.y
            bot.ai.perform(bot, engine)
            if (bot.x, bot.y) != (old_x, old_y):
                moves += 1
        assert moves == 4

    def test_wander_every_turn(self):
        """Machine wanders every turn even in low gravity."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=5, y=5, name="Bot", fighter=Fighter(3, 3, 0, 2),
                     ai=HostileAI(), organic=False)
        gm.entities.extend([player, bot])
        gm.visible[:] = False
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(4):
            old_x, old_y = bot.x, bot.y
            bot.ai.perform(bot, engine)
            if (bot.x, bot.y) != (old_x, old_y):
                moves += 1
        assert moves == 4


class TestLowGravityCooldownEdgeCases:
    """Edge cases for the low gravity movement cooldown system."""

    def test_no_cooldown_without_low_gravity(self):
        """Organic enemies move every turn when there's no low gravity."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=7, y=7, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={})

        moves = 0
        for _ in range(4):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            if (rat.x, rat.y) != (old_x, old_y):
                moves += 1
        assert moves == 4

    def test_cooldown_resets_when_low_gravity_removed(self):
        """Removing low gravity mid-game should clear cooldown immediately."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        # Move once (sets cooldown)
        rat.ai.perform(rat, engine)
        assert rat.move_cooldown == 1

        # Remove low gravity
        engine.environment = {}

        # Should move immediately (cooldown cleared)
        old_x, old_y = rat.x, rat.y
        rat.ai.perform(rat, engine)
        assert (rat.x, rat.y) != (old_x, old_y)
        assert rat.move_cooldown == 0

    def test_cooldown_set_after_move(self):
        """After moving in low gravity, move_cooldown should be 1."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=5, y=5, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        assert rat.move_cooldown == 0
        rat.ai.perform(rat, engine)  # moves
        assert rat.move_cooldown == 1
        rat.ai.perform(rat, engine)  # skips (cooldown consumed)
        assert rat.move_cooldown == 0

    def test_machine_cooldown_stays_zero(self):
        """Machine move_cooldown should always remain 0."""
        gm = make_arena()
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=5, y=5, name="Bot", fighter=Fighter(3, 3, 0, 2),
                     ai=HostileAI(), organic=False)
        gm.entities.extend([player, bot])
        gm.visible[:] = True
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        for _ in range(4):
            bot.ai.perform(bot, engine)
            assert bot.move_cooldown == 0

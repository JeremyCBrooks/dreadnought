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
        """Organic enemy in low gravity moves ~50% of turns (energy-based)."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=15, y=15, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        # Block LOS so creature wanders
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(6):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            if (rat.x, rat.y) != (old_x, old_y):
                moves += 1

        # Default speed 4, halved to 2 in low gravity, ACTION_COST=4
        # Move every other turn: 3 moves in 6 turns
        assert moves == 3

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
        """Organic enemy wandering is slowed by low gravity."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=15, y=15, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        # Block LOS so creature wanders
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(4):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            if (rat.x, rat.y) != (old_x, old_y):
                moves += 1

        # Speed 4 halved to 2 → moves every other turn = 2 moves in 4 turns
        assert moves == 2


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
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=15, y=15, name="Bot", fighter=Fighter(3, 3, 0, 2),
                     ai=HostileAI(), organic=False)
        gm.entities.extend([player, bot])
        # Wall between player and bot so creature can't see player
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(4):
            old_x, old_y = bot.x, bot.y
            bot.ai.perform(bot, engine)
            if (bot.x, bot.y) != (old_x, old_y):
                moves += 1
        assert moves == 4


class TestLowGravityEnergyEdgeCases:
    """Edge cases for the energy-based movement speed system in low gravity."""

    def test_no_slowdown_without_low_gravity(self):
        """Organic enemies move every turn when there's no low gravity."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=15, y=15, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={})

        moves = 0
        for _ in range(4):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            if (rat.x, rat.y) != (old_x, old_y):
                moves += 1
        assert moves == 4

    def test_speed_recovers_when_low_gravity_removed(self):
        """Removing low gravity mid-game restores full movement speed."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=15, y=15, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        # Two turns in low gravity: move, skip
        rat.ai.perform(rat, engine)  # gains 2 energy, spends 4? No: gains 2, total 2 < 4
        # Actually: turn 1 gains 2, energy=2, can't move. Turn 2 gains 2, energy=4, moves.
        rat.ai.perform(rat, engine)

        # Remove low gravity — energy should accumulate at full speed now
        engine.environment = {}
        old_x, old_y = rat.x, rat.y
        rat.ai.perform(rat, engine)  # gains 4, can move
        assert (rat.x, rat.y) != (old_x, old_y)

    def test_low_gravity_move_pattern(self):
        """Organic creature in low gravity: skip, move, skip, move (speed halved)."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        rat = Entity(x=15, y=15, name="Rat", fighter=Fighter(1, 1, 0, 1),
                     ai=HostileAI(), organic=True)
        gm.entities.extend([player, rat])
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moved = []
        for _ in range(4):
            old_x, old_y = rat.x, rat.y
            rat.ai.perform(rat, engine)
            moved.append((rat.x, rat.y) != (old_x, old_y))
        # Speed 4 // 2 = 2 energy/turn. Need 4 to move.
        # T1: 0+2=2, no. T2: 2+2=4, yes. T3: 0+2=2, no. T4: 2+2=4, yes.
        assert moved == [False, True, False, True]

    def test_machine_unaffected_by_low_gravity(self):
        """Non-organic machine moves every turn in low gravity."""
        from world import tile_types
        gm = make_arena(20, 20)
        player = Entity(x=1, y=1, name="Player", fighter=Fighter(10, 10, 0, 1))
        bot = Entity(x=15, y=15, name="Bot", fighter=Fighter(3, 3, 0, 2),
                     ai=HostileAI(), organic=False)
        gm.entities.extend([player, bot])
        for y in range(0, 20):
            gm.tiles[10, y] = tile_types.wall
        engine = MockEngine(gm, player, environment={"low_gravity": 1})

        moves = 0
        for _ in range(4):
            old_x, old_y = bot.x, bot.y
            bot.ai.perform(bot, engine)
            if (bot.x, bot.y) != (old_x, old_y):
                moves += 1
        assert moves == 4

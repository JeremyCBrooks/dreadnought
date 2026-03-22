"""Tests for enemy pickpocketing / item stealing (Emergent Interaction #2)."""
from unittest.mock import patch

from tests.conftest import (
    make_creature, make_engine, make_heal_item, make_weapon,
    make_melee_weapon, DEFAULT_AI_CONFIG,
)
from game.entity import Entity, Fighter
from game.loadout import Loadout
from game.actions import MeleeAction


def _pirate(x=4, y=5, **kw):
    """Create a pirate creature with can_steal=True."""
    cfg = dict(DEFAULT_AI_CONFIG, can_steal=True, flee_threshold=0.3)
    cfg.update(kw.pop("ai_config", {}))
    return make_creature(x=x, y=y, name="Pirate", power=3, ai_config=cfg,
                         organic=True, **kw)


def _engine_with_pirate(pirate=None):
    """Set up engine with player at (5,5) and a pirate adjacent."""
    engine = make_engine()
    player = engine.player
    player.loadout = Loadout()
    player.max_inventory = 10
    if pirate is None:
        pirate = _pirate()
    engine.game_map.entities.append(pirate)
    return engine, player, pirate


def _force_steal(enabled=True):
    """Patch random.random to force steal (0.0) or prevent it (1.0)."""
    return patch("random.random", return_value=0.0 if enabled else 1.0)


# ---- Basic steal mechanics ----

class TestStealOnMeleeHit:
    def test_steal_transfers_item_from_player_to_enemy(self):
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert medkit in pirate.inventory
        assert medkit not in player.inventory

    def test_no_steal_on_failed_roll(self):
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal(enabled=False):
            MeleeAction(player).perform(engine, pirate)

        assert medkit in player.inventory
        assert medkit not in pirate.inventory

    def test_steal_message_logged(self):
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        msgs = [text for text, color in engine.message_log.messages]
        assert any("snatches" in m and "Medkit" in m for m in msgs)

    def test_no_steal_without_can_steal(self):
        """Enemies without can_steal never steal."""
        engine, player, _ = _engine_with_pirate()
        bot = make_creature(x=4, y=5, name="Bot", organic=False)
        engine.game_map.entities.append(bot)
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, bot)

        assert medkit in player.inventory
        assert medkit not in bot.inventory

    def test_equipped_items_not_stolen(self):
        """Items in loadout slots cannot be stolen."""
        engine, player, pirate = _engine_with_pirate()
        weapon = make_melee_weapon()
        player.inventory.append(weapon)
        player.loadout.equip(weapon)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert weapon in player.inventory
        assert player.loadout.has_item(weapon)

    def test_steal_only_non_equipped_item(self):
        """When player has equipped + non-equipped items, only non-equipped can be stolen."""
        engine, player, pirate = _engine_with_pirate()
        weapon = make_melee_weapon(name="Knife")
        medkit = make_heal_item()
        player.inventory.extend([weapon, medkit])
        player.loadout.equip(weapon)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert medkit in pirate.inventory
        assert weapon in player.inventory
        assert player.loadout.has_item(weapon)

    def test_no_steal_from_empty_inventory(self):
        """Stealing from a player with no stealable items is a no-op."""
        engine, player, pirate = _engine_with_pirate()

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert len(pirate.inventory) == 0

    def test_no_steal_when_all_items_equipped(self):
        """If all player items are equipped, nothing can be stolen."""
        engine, player, pirate = _engine_with_pirate()
        w1 = make_melee_weapon(name="Knife")
        w2 = make_weapon(name="Blaster")
        player.inventory.extend([w1, w2])
        player.loadout.equip(w1)
        player.loadout.equip(w2)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert w1 in player.inventory
        assert w2 in player.inventory
        assert len(pirate.inventory) == 0

    def test_no_steal_when_enemy_inventory_full(self):
        """Enemy can't steal if their inventory is full."""
        engine, player, pirate = _engine_with_pirate()
        pirate.max_inventory = 1
        pirate.inventory.append(make_heal_item(name="EnemyKit"))
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert medkit in player.inventory

    def test_no_steal_when_player_dies(self):
        """No steal attempt if the hit kills the player."""
        engine, player, pirate = _engine_with_pirate()
        player.fighter.hp = 1  # Will die from pirate's hit
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert medkit not in pirate.inventory

    def test_player_attacking_enemy_never_triggers_steal(self):
        """Steal only happens when the enemy attacks the player, not vice versa."""
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        pirate.inventory.append(medkit)

        with _force_steal():
            MeleeAction(pirate).perform(engine, player)

        assert medkit in pirate.inventory


# ---- Stolen loot tracking ----

class TestStolenLootTracking:
    def test_stolen_item_tracked_on_entity(self):
        """Stolen items are tracked in entity.stolen_loot."""
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        player.inventory.append(medkit)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert medkit in pirate.stolen_loot

    def test_killed_pirate_drops_stolen_item(self):
        """When pirate dies, stolen items drop to the map."""
        engine, player, pirate = _engine_with_pirate()
        medkit = make_heal_item()
        pirate.inventory.append(medkit)
        pirate.stolen_loot = [medkit]

        pirate.fighter.hp = 1
        MeleeAction(pirate).perform(engine, player)

        map_items = [e for e in engine.game_map.entities if e is medkit]
        assert len(map_items) == 1

    def test_stolen_loot_cleaned_when_item_consumed(self):
        """When pirate uses a stolen consumable, stolen_loot is cleaned up."""
        engine, player, pirate = _engine_with_pirate(
            pirate=_pirate(hp=10)
        )
        medkit = make_heal_item(value=3)
        pirate.inventory.append(medkit)
        pirate.stolen_loot = [medkit]
        pirate.fighter.hp = 3  # below 50%, will try to heal

        # Force the 40% heal RNG to succeed
        with patch("game.ai.random.random", return_value=0.1):
            pirate.ai._try_use_item(pirate, engine)

        assert medkit not in pirate.inventory
        assert medkit not in pirate.stolen_loot


# ---- Melee power recalc after steal ----

class TestMeleePowerRecalcAfterSteal:
    def test_pirate_gets_melee_bonus_from_stolen_weapon(self):
        """Pirate's melee power increases after stealing a melee weapon."""
        engine, player, pirate = _engine_with_pirate()
        base_power = pirate.fighter.power
        weapon = make_melee_weapon(name="Combat Knife", value=3)
        player.inventory.append(weapon)

        with _force_steal():
            MeleeAction(player).perform(engine, pirate)

        assert weapon in pirate.inventory
        assert pirate.fighter.power == base_power + 3


# ---- Flee urgency with stolen loot ----

class TestFleeUrgencyWithStolenLoot:
    def test_stolen_loot_boosts_flee_threshold(self):
        """Pirates with stolen loot flee at a higher HP ratio."""
        engine, player, pirate = _engine_with_pirate(
            pirate=_pirate(hp=10, ai_config={"flee_threshold": 0.3})
        )
        pirate.ai_state = "hunting"
        pirate.ai_target = (player.x, player.y)

        medkit = make_heal_item()
        pirate.inventory.append(medkit)
        pirate.stolen_loot = [medkit]

        # 50% HP — above 0.3 base threshold but below 0.5 boosted threshold
        pirate.fighter.hp = 5
        pirate.x, pirate.y = 6, 5

        pirate.ai.perform(pirate, engine)
        assert pirate.ai_state == "fleeing"

    def test_no_flee_boost_without_stolen_loot(self):
        """Pirates without stolen loot use normal flee threshold."""
        engine, player, pirate = _engine_with_pirate(
            pirate=_pirate(x=6, y=5, hp=10, ai_config={"flee_threshold": 0.3})
        )
        pirate.ai_state = "hunting"
        pirate.ai_target = (player.x, player.y)
        pirate.stolen_loot = []

        # 50% HP — above 0.3 threshold, should NOT flee
        pirate.fighter.hp = 5

        pirate.ai.perform(pirate, engine)
        assert pirate.ai_state != "fleeing"


# ---- Scanner integration ----

class TestScannerShowsStolenItems:
    def test_tier3_scanner_shows_stolen_tag(self):
        """Tier 3 scanner labels stolen items in creature format."""
        from game.scanner import _format_creature
        pirate = _pirate()
        medkit = make_heal_item()
        pirate.inventory.append(medkit)
        pirate.stolen_loot = [medkit]

        _, _, label = _format_creature(pirate, tier=3)
        assert "STOLEN" in label

    def test_tier2_scanner_does_not_show_stolen(self):
        """Tier 2 scanner does not reveal stolen items."""
        from game.scanner import _format_creature
        pirate = _pirate()
        medkit = make_heal_item()
        pirate.inventory.append(medkit)
        pirate.stolen_loot = [medkit]

        _, _, label = _format_creature(pirate, tier=2)
        assert "stolen" not in label.lower()

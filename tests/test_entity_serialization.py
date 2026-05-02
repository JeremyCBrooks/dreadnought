"""Tests for extended entity serialization (Step 1 of mid-mission save).

Beyond the existing minimal entity round-trip in test_save_load.py, full resume
needs every per-entity field — position, AI state, inventory, loadout, stolen
loot, drifting/decompression — to round-trip identically.
"""

from __future__ import annotations

from game.ai import CreatureAI
from game.entity import Entity, Fighter
from game.loadout import Loadout


# ── Position and physics ──────────────────────────────────────────────────────


def test_entity_position_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(x=12, y=7, name="Drone")
    d = _entity_to_dict(e)
    assert d["x"] == 12
    assert d["y"] == 7

    restored = _entity_from_dict(d)
    assert restored.x == 12
    assert restored.y == 7


def test_entity_drifting_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(x=0, y=0, name="Spacer")
    e.drifting = True
    e.drift_direction = (1, -1)
    e.decompression_moves = 3
    e.decompression_direction = (-1, 0)
    e.move_cooldown = 2

    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.drifting is True
    assert restored.drift_direction == (1, -1)
    assert restored.decompression_moves == 3
    assert restored.decompression_direction == (-1, 0)
    assert restored.move_cooldown == 2


def test_entity_organic_and_gore_color_preserved():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(name="Bot", organic=False, gore_color=(50, 50, 200))
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.organic is False
    assert restored.gore_color == (50, 50, 200)


def test_entity_max_inventory_preserved():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(name="Player", max_inventory=10)
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.max_inventory == 10


def test_entity_interactable_preserved():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(
        x=4, y=5, name="Crate",
        interactable={"kind": "container", "scanned": True, "loot": {"name": "Coin", "char": "*", "color": [255, 255, 0]}},
    )
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.interactable == {
        "kind": "container",
        "scanned": True,
        "loot": {"name": "Coin", "char": "*", "color": [255, 255, 0]},
    }


# ── AI state ──────────────────────────────────────────────────────────────────


def test_entity_ai_fields_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(x=3, y=4, name="Pirate", fighter=Fighter(8, 10, 0, 2))
    e.ai = CreatureAI()
    e.ai_config = {"aggro_distance": 6, "vision_radius": 7, "can_steal": True}
    e.ai_state = "hunting"
    e.ai_target = (10, 10)
    e.ai_wander_goal = (15, 8)
    e.ai_turns_since_seen = 3
    e.ai_stuck_turns = 1
    e.ai_energy = 5

    restored = _entity_from_dict(_entity_to_dict(e))
    assert isinstance(restored.ai, CreatureAI)
    assert restored.ai_config == {"aggro_distance": 6, "vision_radius": 7, "can_steal": True}
    assert restored.ai_state == "hunting"
    assert restored.ai_target == (10, 10)
    assert restored.ai_wander_goal == (15, 8)
    assert restored.ai_turns_since_seen == 3
    assert restored.ai_stuck_turns == 1
    assert restored.ai_energy == 5


def test_entity_no_ai_means_no_ai_after_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(name="Sword", item={"type": "weapon"})
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.ai is None


def test_entity_ai_target_none_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(name="Drone", ai=CreatureAI())
    e.ai_target = None
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.ai_target is None


# ── Inventory and loadout (recursive + identity) ──────────────────────────────


def test_entity_inventory_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    sword = Entity(name="Sword", item={"type": "weapon", "value": 3})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    player = Entity(name="Player", fighter=Fighter(8, 10, 0, 2))
    player.inventory = [sword, medkit]

    restored = _entity_from_dict(_entity_to_dict(player))
    assert len(restored.inventory) == 2
    assert restored.inventory[0].name == "Sword"
    assert restored.inventory[1].name == "Medkit"


def test_entity_loadout_preserves_identity_with_inventory():
    """slot1/slot2 must be the SAME Python objects as the inventory entries."""
    from web.save_load import _entity_from_dict, _entity_to_dict

    sword = Entity(name="Sword", item={"type": "weapon", "weapon_class": "melee", "value": 3})
    scanner = Entity(name="Scanner", item={"type": "scanner"})
    player = Entity(name="Player", fighter=Fighter(8, 10, 0, 2))
    player.inventory = [sword, scanner]
    player.loadout = Loadout(slot1=sword, slot2=scanner)

    restored = _entity_from_dict(_entity_to_dict(player))
    assert restored.loadout is not None
    # Identity preserved within the entity's own object graph
    assert restored.loadout.slot1 is restored.inventory[0]
    assert restored.loadout.slot2 is restored.inventory[1]


def test_entity_loadout_partial_slot_round_trip():
    from web.save_load import _entity_from_dict, _entity_to_dict

    sword = Entity(name="Sword", item={"type": "weapon"})
    player = Entity(name="Player", fighter=Fighter(8, 10, 0, 2))
    player.inventory = [sword]
    player.loadout = Loadout(slot1=sword, slot2=None)

    restored = _entity_from_dict(_entity_to_dict(player))
    assert restored.loadout.slot1 is restored.inventory[0]
    assert restored.loadout.slot2 is None


def test_entity_stolen_loot_preserves_identity_with_inventory():
    """stolen_loot must hold the SAME Entity objects that are in inventory."""
    from web.save_load import _entity_from_dict, _entity_to_dict

    coin = Entity(name="Coin", item={"type": "junk"})
    medkit = Entity(name="Medkit", item={"type": "heal", "value": 5})
    plain = Entity(name="Wrench", item={"type": "tool"})
    thief = Entity(name="Pirate", fighter=Fighter(8, 10, 0, 2), ai=CreatureAI())
    thief.inventory = [plain, coin, medkit]
    thief.stolen_loot = [coin, medkit]  # plain was always theirs

    restored = _entity_from_dict(_entity_to_dict(thief))
    assert len(restored.stolen_loot) == 2
    # Both stolen items must be the same objects in restored.inventory
    assert restored.stolen_loot[0] is restored.inventory[1]
    assert restored.stolen_loot[1] is restored.inventory[2]


def test_entity_empty_inventory_and_loadout():
    from web.save_load import _entity_from_dict, _entity_to_dict

    e = Entity(name="Bare")
    restored = _entity_from_dict(_entity_to_dict(e))
    assert restored.inventory == []
    assert restored.loadout is None
    assert restored.stolen_loot == []


# ── Backwards compatibility ───────────────────────────────────────────────────


def test_old_dict_without_new_fields_still_loads():
    """A pre-mid-mission save dict shouldn't crash from_dict."""
    from web.save_load import _entity_from_dict

    minimal = {
        "name": "Old",
        "char": "?",
        "color": [255, 255, 255],
        "item": None,
        "blocks_movement": False,
    }
    restored = _entity_from_dict(minimal)
    assert restored.name == "Old"
    # Defaults
    assert restored.x == 0
    assert restored.y == 0
    assert restored.ai is None
    assert restored.inventory == []

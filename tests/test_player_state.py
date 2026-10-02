"""The player's between-mission record: one place that builds, snapshots and restores it."""

from game.loadout import Loadout
from game.player_state import apply_snapshot, fresh_player_snapshot, new_player, snapshot_player
from tests.conftest import make_heal_item, make_melee_weapon
from web.save_load import _saved_player_from_dict, _saved_player_to_dict


def _wounded_player_with_knife():
    knife = make_melee_weapon(value=3)
    player = new_player(0, 0)
    player.fighter.hp = 4
    player.inventory.append(knife)
    player.loadout = Loadout(slot1=knife)
    return player, knife


def test_restored_player_carries_hp_inventory_and_equipped_weapon():
    wounded, knife = _wounded_player_with_knife()

    restored = new_player(5, 5)
    apply_snapshot(restored, snapshot_player(wounded))

    assert restored.fighter.hp == 4
    assert restored.inventory == [knife]
    assert restored.loadout.slot1 is knife
    # Base 1 plus the knife's 3: the melee bonus is re-derived, not lost and not doubled.
    assert restored.fighter.power == 4


def test_snapshot_is_isolated_from_later_inventory_changes():
    player = new_player(0, 0)
    player.inventory.append(make_heal_item())
    snapshot = snapshot_player(player)

    player.inventory.clear()

    assert [item.name for item in snapshot["inventory"]] == ["Medkit"]


def test_first_mission_player_with_no_record_keeps_starting_stats():
    player = new_player(0, 0)

    apply_snapshot(player, None)

    assert (player.fighter.hp, player.fighter.power) == (10, 1)


def test_two_new_games_do_not_share_an_inventory_or_loadout():
    first, second = fresh_player_snapshot(), fresh_player_snapshot()

    first["inventory"].append(make_heal_item())
    first["loadout"].equip(make_melee_weapon())

    assert second["inventory"] == []
    assert second["loadout"].all_items() == []


def test_snapshots_survive_the_save_file_round_trip():
    wounded, _ = _wounded_player_with_knife()

    loaded = _saved_player_from_dict(_saved_player_to_dict(snapshot_player(wounded)))
    blank = _saved_player_from_dict(_saved_player_to_dict(fresh_player_snapshot()))

    assert loaded["hp"] == 4
    assert [item.name for item in loaded["inventory"]] == ["Combat Knife"]
    assert loaded["loadout"].slot1 is loaded["inventory"][0]
    assert (blank["hp"], blank["inventory"], blank["loadout"].all_items()) == (10, [], [])

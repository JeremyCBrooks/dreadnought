"""Tests for scanner display of enemy equipment (Phase 6)."""
from game.scanner import _format_creature
from tests.conftest import make_creature, make_melee_weapon, make_heal_item, make_weapon


def _creature_with_items(items=None, ai_state="wandering"):
    enemy = make_creature(ai_state=ai_state)
    if items:
        enemy.inventory.extend(items)
    return enemy


class TestScannerEnemyItems:
    def test_tier1_shows_unknown(self):
        enemy = _creature_with_items([make_melee_weapon()])
        char, color, label = _format_creature(enemy, tier=1)
        assert label == "???"
        assert char == "?"

    def test_tier2_shows_name_plus_weapon(self):
        weapon = make_melee_weapon(name="Stun Baton")
        enemy = _creature_with_items([weapon])
        char, color, label = _format_creature(enemy, tier=2)
        assert enemy.name in label
        assert "Stun Baton" in label

    def test_tier2_no_weapon_shows_name_only(self):
        enemy = _creature_with_items([make_heal_item()])
        char, color, label = _format_creature(enemy, tier=2)
        assert label == enemy.name

    def test_tier3_shows_state_and_full_inventory(self):
        weapon = make_melee_weapon(name="Bent Pipe")
        medkit = make_heal_item(name="Med-kit")
        enemy = _creature_with_items([weapon, medkit], ai_state="hunting")
        char, color, label = _format_creature(enemy, tier=3)
        assert "hunting" in label
        assert "Bent Pipe" in label
        assert "Med-kit" in label

    def test_tier3_empty_inventory(self):
        enemy = _creature_with_items([], ai_state="fleeing")
        char, color, label = _format_creature(enemy, tier=3)
        assert "fleeing" in label
        assert enemy.name in label

    def test_tier2_ranged_weapon_shown(self):
        ranged = make_weapon(name="Low-power Blaster", weapon_class="ranged", value=3)
        enemy = _creature_with_items([ranged])
        char, color, label = _format_creature(enemy, tier=2)
        assert "Low-power Blaster" in label

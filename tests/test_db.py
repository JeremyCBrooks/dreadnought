"""Tests for data.db entity definition loader."""
import pytest

from data import db


@pytest.fixture(autouse=True)
def _reload_db():
    """Ensure fresh cache for every test."""
    db.reload()
    yield
    db.reload()


class TestLoadCategories:
    def test_enemies_returns_list(self):
        assert isinstance(db.enemies(), list)
        assert len(db.enemies()) == 4

    def test_items_returns_list(self):
        assert isinstance(db.items(), list)
        assert len(db.items()) == 7

    def test_scanners_returns_list(self):
        assert isinstance(db.scanners(), list)
        assert len(db.scanners()) == 3

    def test_interactables_returns_list(self):
        assert isinstance(db.interactables(), list)
        assert len(db.interactables()) == 5

    def test_hazards_returns_list(self):
        assert isinstance(db.hazards(), list)
        assert len(db.hazards()) == 5


class TestColorConversion:
    def test_enemy_colors_are_tuples(self):
        for e in db.enemies():
            assert isinstance(e["color"], tuple), f"{e['name']} color not a tuple"
            assert len(e["color"]) == 3

    def test_item_colors_are_tuples(self):
        for i in db.items():
            assert isinstance(i["color"], tuple)

    def test_scanner_colors_are_tuples(self):
        for s in db.scanners():
            assert isinstance(s["color"], tuple)

    def test_interactable_colors_are_tuples(self):
        for i in db.interactables():
            assert isinstance(i["color"], tuple)


class TestSpotCheckValues:
    """Verify exact values match the old hardcoded definitions."""

    def test_rat_enemy(self):
        rat = next(e for e in db.enemies() if e["name"] == "Rat")
        assert rat["char"] == "r"
        assert rat["color"] == (127, 127, 0)
        assert rat["hp"] == 1
        assert rat["defense"] == 0
        assert rat["power"] == 1

    def test_bot_enemy(self):
        bot = next(e for e in db.enemies() if e["name"] == "Bot")
        assert bot["char"] == "b"
        assert bot["color"] == (127, 0, 180)
        assert bot["hp"] == 3
        assert bot["defense"] == 0
        assert bot["power"] == 2

    def test_medkit_item(self):
        mk = next(i for i in db.items() if i["name"] == "Med-kit")
        assert mk["char"] == "!"
        assert mk["color"] == (0, 255, 100)
        assert mk["type"] == "heal"
        assert mk["value"] == 5

    def test_stun_baton_item(self):
        sb = next(i for i in db.items() if i["name"] == "Stun Baton")
        assert sb["char"] == "/"
        assert sb["color"] == (220, 180, 0)
        assert sb["type"] == "weapon"
        assert sb["value"] == 3
        assert sb["durability"] == 5
        assert sb["max_durability"] == 5

    def test_basic_scanner(self):
        bs = next(s for s in db.scanners() if s["name"] == "Basic Scanner")
        assert bs["char"] == "]"
        assert bs["color"] == (100, 200, 255)
        assert bs["scanner_tier"] == 1

    def test_electric_hazard(self):
        eh = next(h for h in db.hazards() if h["type"] == "electric")
        assert eh["damage"] == 2
        assert eh["equipment_damage"] is True

    def test_gas_hazard(self):
        gh = next(h for h in db.hazards() if h["type"] == "gas")
        assert gh["damage"] == 1
        assert gh["equipment_damage"] is False

    def test_radiation_hazard_dot_fields(self):
        rh = next(h for h in db.hazards() if h["type"] == "radiation")
        assert rh["dot"] == 1
        assert rh["duration"] == 3

    def test_electric_hazard_no_dot(self):
        eh = next(h for h in db.hazards() if h["type"] == "electric")
        assert eh["dot"] == 0
        assert eh["duration"] == 0

    def test_all_hazards_have_dot_and_duration(self):
        for h in db.hazards():
            assert "dot" in h, f"{h['type']} missing 'dot'"
            assert "duration" in h, f"{h['type']} missing 'duration'"

    def test_pirate_enemy(self):
        pirate = next(e for e in db.enemies() if e["name"] == "Pirate")
        assert pirate["char"] == "p"
        assert pirate["hp"] == 5
        assert pirate["defense"] == 1
        assert pirate["power"] == 3

    def test_security_drone_enemy(self):
        drone = next(e for e in db.enemies() if e["name"] == "Security Drone")
        assert drone["char"] == "d"
        assert drone["hp"] == 4
        assert drone["defense"] == 0
        assert drone["power"] == 3

    def test_bent_pipe_weapon_class(self):
        bp = next(i for i in db.items() if i["name"] == "Bent Pipe")
        assert bp["weapon_class"] == "melee"

    def test_blaster_ranged_weapon(self):
        blaster = next(i for i in db.items() if i["name"] == "Low-power Blaster")
        assert blaster["weapon_class"] == "ranged"
        assert blaster["range"] == 5
        assert blaster["ammo"] == 20
        assert blaster["max_ammo"] == 20

    def test_shotgun_ranged_weapon(self):
        sg = next(i for i in db.items() if i["name"] == "Shotgun")
        assert sg["weapon_class"] == "ranged"
        assert sg["range"] == 3
        assert sg["ammo"] == 10

    def test_console_interactable(self):
        c = next(i for i in db.interactables() if i["name"] == "Console")
        assert c["char"] == "&"
        assert c["color"] == (100, 200, 255)


class TestAllLoot:
    def test_length(self):
        loot = db.all_loot()
        assert len(loot) == len(db.items()) + len(db.scanners())

    def test_items_have_type_and_value(self):
        for entry in db.all_loot():
            assert "type" in entry
            assert "value" in entry
            assert "char" in entry
            assert "color" in entry
            assert "name" in entry

    def test_scanners_normalized(self):
        scanner_names = {s["name"] for s in db.scanners()}
        for entry in db.all_loot():
            if entry["name"] in scanner_names:
                assert entry["type"] == "scanner"
                assert "scanner_tier" in entry


class TestBuildItemData:
    def test_heal_item(self):
        defn = {"type": "heal", "value": 5, "char": "!", "color": (0, 255, 100), "name": "Med-kit"}
        result = db.build_item_data(defn)
        assert result == {"type": "heal", "value": 5}

    def test_weapon_item(self):
        defn = {"type": "weapon", "value": 2, "durability": 5, "max_durability": 5,
                "weapon_class": "melee",
                "char": "/", "color": (0, 191, 255), "name": "Bent Pipe"}
        result = db.build_item_data(defn)
        assert result == {"type": "weapon", "value": 2, "durability": 5, "max_durability": 5, "weapon_class": "melee"}

    def test_ranged_weapon_item(self):
        defn = {"type": "weapon", "value": 3, "weapon_class": "ranged",
                "range": 5, "ammo": 20, "max_ammo": 20,
                "char": "}", "color": (200, 80, 80), "name": "Low-power Blaster"}
        result = db.build_item_data(defn)
        assert result == {"type": "weapon", "value": 3, "weapon_class": "ranged",
                          "range": 5, "ammo": 20, "max_ammo": 20}

    def test_scanner_item(self):
        import random
        defn = {"type": "scanner", "value": 1, "scanner_tier": 1,
                "char": "]", "color": (100, 200, 255), "name": "Basic Scanner"}
        result = db.build_item_data(defn, rng=random.Random(0))
        assert result["type"] == "scanner"
        assert result["value"] == 1
        assert result["scanner_tier"] == 1
        assert 1 <= result["uses"] <= 3

    def test_repair_item(self):
        defn = {"type": "repair", "value": 5, "char": "#", "color": (180, 140, 80), "name": "Repair Kit"}
        result = db.build_item_data(defn)
        assert result == {"type": "repair", "value": 5}

    def test_o2_item(self):
        defn = {"type": "o2", "value": 20, "char": "O", "color": (100, 200, 255), "name": "O2 Canister"}
        result = db.build_item_data(defn)
        assert result == {"type": "o2", "value": 20}


class TestReload:
    def test_reload_clears_cache(self):
        _ = db.enemies()
        db.reload()
        # After reload, should re-read and still return valid data
        assert len(db.enemies()) == 4

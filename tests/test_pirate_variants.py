"""Tests for pirate species — human, alien, and mech pirate entities."""
import random

from data import db
from game.entity import Entity, Fighter
from game.gore import place_death_gore, _BLOOD_CHARS, _DEBRIS_CHARS
from tests.conftest import make_arena
from world import tile_types


def _make_gore_map(w=20, h=20):
    return make_arena(w, h)


def _pirate_by_name(name):
    db.reload()
    return next(e for e in db.enemies() if e["name"] == name)


class TestPirateEntitiesExist:
    """All four pirate types should be defined in entities.json."""

    def test_human_pirate_exists(self):
        p = _pirate_by_name("Pirate")
        assert p["char"] == "p"
        assert p["color"][0] > 150, "Human pirate should be red"
        assert p["organic"] is True

    def test_xeno_pirate_exists(self):
        p = _pirate_by_name("Xeno Pirate")
        assert p["char"] == "p"
        assert p["color"][1] > 150, "Xeno pirate should be green"
        assert p["organic"] is True

    def test_vek_pirate_exists(self):
        p = _pirate_by_name("Vek Pirate")
        assert p["char"] == "p"
        assert p["color"][2] > 150, "Vek pirate should be blue"
        assert p["organic"] is True

    def test_mech_pirate_exists(self):
        p = _pirate_by_name("Mech Pirate")
        assert p["char"] == "p"
        assert p["organic"] is False

    def test_all_pirates_share_char(self):
        """All pirate types use the same display character."""
        db.reload()
        pirates = [e for e in db.enemies() if "Pirate" in e["name"] or "pirate" in e["name"]]
        assert len(pirates) == 4
        assert all(p["char"] == "p" for p in pirates)


class TestPirateGore:
    """Each pirate species should leave the correct gore type."""

    def test_human_pirate_red_blood(self):
        p = _pirate_by_name("Pirate")
        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char=p["char"], color=p["color"], name=p["name"],
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=p["hp"], defense=p["defense"], power=p["power"]),
            organic=p["organic"], gore_color=p.get("gore_color"),
        )
        place_death_gore(gm, enemy, random.Random(42))
        fg = gm.tiles["light"]["fg"][10, 10]
        assert int(fg[0]) > int(fg[1]), "Human pirate gore should be red-tinted"
        ch = int(gm.tiles["light"]["ch"][10, 10])
        assert ch in _BLOOD_CHARS, "Organic pirate should leave blood chars"

    def test_xeno_pirate_green_blood(self):
        p = _pirate_by_name("Xeno Pirate")
        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char=p["char"], color=p["color"], name=p["name"],
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=p["hp"], defense=p["defense"], power=p["power"]),
            organic=p["organic"], gore_color=p.get("gore_color"),
        )
        place_death_gore(gm, enemy, random.Random(42))
        fg = gm.tiles["light"]["fg"][10, 10]
        assert int(fg[1]) > int(fg[0]), "Xeno pirate gore should be green-tinted"
        ch = int(gm.tiles["light"]["ch"][10, 10])
        assert ch in _BLOOD_CHARS, "Organic alien pirate should leave blood chars"

    def test_vek_pirate_blue_blood(self):
        p = _pirate_by_name("Vek Pirate")
        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char=p["char"], color=p["color"], name=p["name"],
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=p["hp"], defense=p["defense"], power=p["power"]),
            organic=p["organic"], gore_color=p.get("gore_color"),
        )
        place_death_gore(gm, enemy, random.Random(42))
        fg = gm.tiles["light"]["fg"][10, 10]
        assert int(fg[2]) > int(fg[0]), "Vek pirate gore should be blue-tinted"
        ch = int(gm.tiles["light"]["ch"][10, 10])
        assert ch in _BLOOD_CHARS, "Organic alien pirate should leave blood chars"

    def test_mech_pirate_oil_debris(self):
        p = _pirate_by_name("Mech Pirate")
        gm = _make_gore_map()
        enemy = Entity(
            x=10, y=10, char=p["char"], color=p["color"], name=p["name"],
            blocks_movement=True,
            fighter=Fighter(hp=0, max_hp=p["hp"], defense=p["defense"], power=p["power"]),
            organic=p["organic"], gore_color=p.get("gore_color"),
        )
        place_death_gore(gm, enemy, random.Random(42))
        ch = int(gm.tiles["light"]["ch"][10, 10])
        assert ch in _DEBRIS_CHARS, "Mech pirate should leave debris chars, not blood"

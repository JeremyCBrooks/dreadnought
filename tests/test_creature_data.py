"""The menagerie as data: every creature is well formed, and the roster fits its worlds."""

from __future__ import annotations

import pytest

from data.enemies import BOARDING, CHORES, ENEMIES, TEMPERAMENTS, creatures_for, enemy_by_name
from data.hazards import HAZARD_BY_TYPE
from data.interactables import FLOOR_INTERACTABLES
from data.items import ITEMS, NATURAL_WEAPONS, all_loot, natural_weapon_by_name
from data.names import WRECK_LOC_TYPE
from world.loc_profiles import PROFILES

LOCATION_TYPES = tuple(PROFILES)
KNOWN_HABITATS = {*LOCATION_TYPES, BOARDING}


def _ids(defs):
    return [d.name for d in defs]


@pytest.mark.parametrize("creature", ENEMIES, ids=_ids(ENEMIES))
class TestEveryCreatureIsWellFormed:
    def test_draws_as_a_single_glyph(self, creature):
        assert len(creature.char) == 1

    def test_has_a_description_for_look_mode(self, creature):
        assert creature.description.strip()

    def test_temperament_is_known(self, creature):
        assert creature.temperament in TEMPERAMENTS

    def test_lives_somewhere(self, creature):
        assert creature.habitats, "a creature with no habitat never appears"
        assert set(creature.habitats) <= KNOWN_HABITATS

    def test_spawn_settings_are_sane(self, creature):
        low, high = creature.group
        assert 1 <= low <= high
        assert creature.spawn_weight > 0
        assert creature.min_depth >= 0

    def test_natural_weapon_exists(self, creature):
        if creature.natural_weapon is not None:
            assert natural_weapon_by_name(creature.natural_weapon)

    def test_disguise_is_a_floor_furnishing(self, creature):
        if creature.disguise is not None:
            assert creature.disguise in {i.name for i in FLOOR_INTERACTABLES}

    def test_death_effect_is_a_known_hazard(self, creature):
        if creature.death_effect is not None:
            assert creature.death_effect.hazard in HAZARD_BY_TYPE
            assert creature.death_effect.message.strip()

    def test_immunities_are_known_hazards(self, creature):
        assert set(creature.hazard_immunities) <= {*HAZARD_BY_TYPE, "vacuum"}

    def test_chores_are_known(self, creature):
        assert set(creature.chores) <= CHORES

    def test_light_is_a_radius_and_colour(self, creature):
        if creature.light is not None:
            radius, color = creature.light
            assert radius > 0
            assert len(color) == 3

    def test_ai_config_is_plain_json_data(self, creature):
        import json

        json.dumps(creature.to_ai_config())


class TestRosterShape:
    def test_both_flesh_and_machine(self):
        assert any(c.organic for c in ENEMIES)
        assert any(not c.organic for c in ENEMIES)

    def test_threats_and_harmless_life(self):
        hostile = [c for c in ENEMIES if TEMPERAMENTS[c.temperament].attacks_on_sight]
        harmless = [c for c in ENEMIES if not TEMPERAMENTS[c.temperament].attacks]
        assert len(hostile) >= 8
        assert len(harmless) >= 3

    def test_something_will_follow_the_player(self):
        assert any(TEMPERAMENTS[c.temperament].on_sight == "follow" for c in ENEMIES)

    def test_something_only_fights_back(self):
        territorial = TEMPERAMENTS["territorial"]
        assert territorial.attacks and not territorial.attacks_on_sight
        assert any(c.temperament == "territorial" for c in ENEMIES)

    @pytest.mark.parametrize("loc_type", LOCATION_TYPES)
    def test_every_location_has_a_threat_from_the_start(self, loc_type):
        assert [c for c in creatures_for(loc_type, depth=0) if TEMPERAMENTS[c.temperament].attacks_on_sight]

    @pytest.mark.parametrize("loc_type", LOCATION_TYPES)
    def test_every_location_has_harmless_life(self, loc_type):
        assert [c for c in creatures_for(loc_type, depth=5) if not TEMPERAMENTS[c.temperament].attacks_on_sight]

    @pytest.mark.parametrize("loc_type", LOCATION_TYPES)
    def test_going_deeper_adds_new_threats(self, loc_type):
        shallow = set(_ids(creatures_for(loc_type, depth=0)))
        deep = set(_ids(creatures_for(loc_type, depth=5)))
        assert deep > shallow

    def test_nothing_lives_on_a_wreck(self):
        assert creatures_for(WRECK_LOC_TYPE, depth=5) == []


class TestCreaturesFor:
    def test_only_creatures_of_that_habitat(self):
        for creature in creatures_for("asteroid", depth=5):
            assert "asteroid" in creature.habitats

    def test_respects_minimum_depth(self):
        shallow = creatures_for("starbase", depth=0)
        assert all(c.min_depth == 0 for c in shallow)
        assert enemy_by_name("Sentry Turret") not in shallow
        assert enemy_by_name("Sentry Turret") in creatures_for(
            "starbase", depth=enemy_by_name("Sentry Turret").min_depth
        )

    def test_boarding_crews_are_pirates_and_their_heavy(self):
        crew = set(_ids(creatures_for(BOARDING, depth=0)))
        assert {"Pirate", "Xeno Pirate", "Vek Pirate", "Breacher"} <= crew
        assert all("Pirate" in name or name == "Breacher" for name in crew)

    def test_unknown_habitat_is_empty(self):
        assert creatures_for("nowhere", depth=9) == []


class TestTemperaments:
    def test_hostile_hunts_on_sight(self):
        assert TEMPERAMENTS["hostile"].on_sight == "hunt"

    def test_harmless_temperaments_never_attack(self):
        for name in ("skittish", "docile", "friendly"):
            assert not TEMPERAMENTS[name].attacks

    def test_being_hurt_changes_a_temperament_into_a_known_one(self):
        for temperament in TEMPERAMENTS.values():
            assert temperament.when_hurt is None or temperament.when_hurt in TEMPERAMENTS

    def test_territorial_turns_hostile_when_hurt(self):
        assert TEMPERAMENTS["territorial"].when_hurt == "hostile"


class TestNaturalWeapons:
    def test_are_never_found_as_loot(self):
        natural = {w.name for w in NATURAL_WEAPONS}
        assert not natural & {i.name for i in ITEMS}
        assert not natural & {d["name"] for d in all_loot()}

    def test_are_weapons(self):
        for weapon in NATURAL_WEAPONS:
            assert weapon.type == "weapon"
            assert weapon.weapon_class == "ranged"
            assert weapon.range and weapon.range > 1


class TestAiConfigCarriesBehaviour:
    def test_temperament_and_traits_reach_the_entity_config(self):
        cfg = enemy_by_name("Hull Mite").to_ai_config()
        assert cfg["temperament"] == "hostile"
        assert "vacuum" in cfg["hazard_immunities"]

    def test_light_and_chores_and_death_effects_are_carried(self):
        assert enemy_by_name("Glowmoth").to_ai_config()["light"]
        assert enemy_by_name("Custodian").to_ai_config()["chores"]
        assert enemy_by_name("Spore Drifter").to_ai_config()["death_effect"]["hazard"] == "gas"

    def test_plain_creatures_carry_no_optional_traits(self):
        cfg = enemy_by_name("Rat").to_ai_config()
        for key in ("light", "chores", "death_effect", "disguise", "hazard_immunities"):
            assert not cfg.get(key)

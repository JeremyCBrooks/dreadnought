"""Tests for galaxy, star system, and location generation."""
from data.db import location_types, location_words, system_words
from world.galaxy import Galaxy


def test_galaxy_has_three_systems():
    g = Galaxy(seed=1)
    assert len(g.systems) == 3


def test_systems_are_connected():
    g = Galaxy(seed=1)
    first = g.systems[g.current_system]
    assert len(first.connections) >= 1


def test_locations_generated():
    g = Galaxy(seed=1)
    for system in g.systems.values():
        assert len(system.locations) >= 2


def test_location_words_cover_all_types():
    words = location_words()
    for lt in location_types():
        assert len(words[lt]["adjectives"]) >= 20
        assert len(words[lt]["nouns"]) >= 20


def test_enough_system_words():
    sw = system_words()
    assert len(sw["primaries"]) >= 20
    assert len(sw["suffixes"]) >= 20


def test_location_names_are_unique_across_seeds():
    names = set()
    for seed in range(20):
        g = Galaxy(seed=seed)
        for system in g.systems.values():
            for loc in system.locations:
                names.add(loc.name)
    assert len(names) >= 30


def test_location_name_formats():
    """Names should be: adj+noun, noun only, or noun+number."""
    one_word = False
    two_word_alpha = False
    with_number = False
    for seed in range(50):
        g = Galaxy(seed=seed)
        for system in g.systems.values():
            for loc in system.locations:
                parts = loc.name.split()
                if len(parts) == 1:
                    one_word = True
                elif len(parts) == 2 and parts[-1].isdigit():
                    with_number = True
                elif len(parts) == 2 and parts[-1].isalpha():
                    two_word_alpha = True
    assert one_word, "Expected some single-noun names"
    assert two_word_alpha, "Expected some adjective+noun names"
    assert with_number, "Expected some noun+number names"

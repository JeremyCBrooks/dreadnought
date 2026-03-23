"""Tests for data.names word banks and structure."""

from data.names import LOCATION_TYPES, LOCATION_WORDS, SYSTEM_WORDS


def test_location_types_derived_from_location_words():
    """LOCATION_TYPES must always match LOCATION_WORDS keys (DRY)."""
    assert set(LOCATION_TYPES) == set(LOCATION_WORDS.keys())


def test_location_types_is_list():
    """LOCATION_TYPES must be a list (used by rng.choice)."""
    assert isinstance(LOCATION_TYPES, list)


def test_system_words_has_required_keys():
    assert "primaries" in SYSTEM_WORDS
    assert "suffixes" in SYSTEM_WORDS


def test_location_words_each_type_has_adjectives_and_nouns():
    for lt in LOCATION_TYPES:
        assert "adjectives" in LOCATION_WORDS[lt], f"{lt} missing adjectives"
        assert "nouns" in LOCATION_WORDS[lt], f"{lt} missing nouns"


def test_no_duplicate_primaries():
    primaries = SYSTEM_WORDS["primaries"]
    assert len(primaries) == len(set(primaries)), "Duplicate primaries found"


def test_no_duplicate_suffixes():
    suffixes = SYSTEM_WORDS["suffixes"]
    assert len(suffixes) == len(set(suffixes)), "Duplicate suffixes found"


def test_no_duplicate_location_words():
    for loc_type, groups in LOCATION_WORDS.items():
        for key, words in groups.items():
            assert len(words) == len(set(words)), (
                f"Duplicate in LOCATION_WORDS[{loc_type}][{key}]"
            )


def test_location_word_lists_balanced():
    """Each location type should have the same number of adjectives and nouns."""
    adj_counts = {lt: len(g["adjectives"]) for lt, g in LOCATION_WORDS.items()}
    noun_counts = {lt: len(g["nouns"]) for lt, g in LOCATION_WORDS.items()}
    assert len(set(adj_counts.values())) == 1, f"Adjective counts differ: {adj_counts}"
    assert len(set(noun_counts.values())) == 1, f"Noun counts differ: {noun_counts}"


def test_all_entries_are_non_empty_strings():
    for word in SYSTEM_WORDS["primaries"]:
        assert isinstance(word, str) and word.strip(), f"Bad primary: {word!r}"
    for word in SYSTEM_WORDS["suffixes"]:
        assert isinstance(word, str) and word.strip(), f"Bad suffix: {word!r}"
    for loc_type, groups in LOCATION_WORDS.items():
        for key, words in groups.items():
            for word in words:
                assert isinstance(word, str) and word.strip(), (
                    f"Bad entry in LOCATION_WORDS[{loc_type}][{key}]: {word!r}"
                )

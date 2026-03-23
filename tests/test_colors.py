"""Tests for ui.colors — shared color constants."""

from ui import colors


def test_color_type_alias_is_rgb_tuple():
    """Color type alias should represent an (R, G, B) tuple."""
    assert colors.Color == tuple[int, int, int]


def test_all_colors_are_rgb_tuples():
    """Every public color constant must be a 3-tuple of ints in [0, 255]."""
    for name in dir(colors):
        if name.startswith("_") or name == "Color":
            continue
        val = getattr(colors, name)
        if not isinstance(val, tuple):
            continue
        assert len(val) == 3, f"{name} should be a 3-tuple, got length {len(val)}"
        for i, component in enumerate(val):
            assert isinstance(component, int), f"{name}[{i}] should be int, got {type(component)}"
            assert 0 <= component <= 255, f"{name}[{i}]={component} out of range [0, 255]"


def test_no_unused_hint_color():
    """HINT_COLOR was identified as unused and should be removed."""
    assert not hasattr(colors, "HINT_COLOR"), "HINT_COLOR should be removed (unused)"


def test_expected_color_groups_exist():
    """Key color groups must be present."""
    # General
    assert colors.WHITE == (255, 255, 255)
    assert colors.GRAY == (150, 150, 150)
    assert colors.DARK_GRAY == (100, 100, 100)

    # Dialog
    assert colors.DIALOG_BG == (15, 15, 30)

    # Tabs
    assert hasattr(colors, "TAB_SELECTED")
    assert hasattr(colors, "TAB_UNSELECTED")

    # Headers
    assert hasattr(colors, "HEADER_SEP")
    assert hasattr(colors, "HEADER_TEXT")
    assert hasattr(colors, "HEADER_TITLE")

    # HP
    assert colors.HP_GREEN == (0, 255, 0)
    assert colors.HP_YELLOW == (255, 255, 0)
    assert colors.HP_RED == (255, 0, 0)

    # Threat
    assert hasattr(colors, "THREAT_LOW")
    assert hasattr(colors, "THREAT_MODERATE")
    assert hasattr(colors, "THREAT_HIGH")


def test_message_log_combat_colors():
    """Combat message colors must be present."""
    for name in ("PLAYER_ATTACK", "ENEMY_ATTACK", "PLAYER_RANGED", "ENEMY_RANGED", "DEATH_MSG", "ENEMY_DEATH"):
        assert hasattr(colors, name), f"Missing combat color: {name}"


def test_message_log_general_colors():
    """General message colors must be present."""
    for name in (
        "NEUTRAL",
        "WARNING",
        "PICKUP",
        "INTERACT_LOOT",
        "INTERACT_SAFE",
        "INTERACT_EMPTY",
        "SCAN_MSG",
        "EQUIP_MSG",
        "PROMPT",
    ):
        assert hasattr(colors, name), f"Missing general color: {name}"


def test_message_log_hazard_colors():
    """Hazard message colors must be present."""
    for name in (
        "HAZARD_ELECTRIC",
        "HAZARD_RADIATION",
        "HAZARD_EXPLOSIVE",
        "HAZARD_GAS",
        "HAZARD_STRUCTURAL",
        "HAZARD_ENV_DAMAGE",
        "HAZARD_VOID",
    ):
        assert hasattr(colors, name), f"Missing hazard color: {name}"


def test_consumers_import_successfully():
    """Files that depend on ui.colors should import without error."""
    from game import (
        actions,  # noqa: F401
        consumables,  # noqa: F401
        hazards,  # noqa: F401
        loadout,  # noqa: F401
    )

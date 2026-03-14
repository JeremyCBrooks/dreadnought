"""Debug configuration flags for development. Toggle these to alter game behavior."""

GOD_MODE = True          # Player takes no damage from any source
DISABLE_OXYGEN = False    # Suit O2 pools never deplete
DISABLE_HAZARDS = False   # Interactable hazards don't trigger
DISABLE_ENEMY_AI = False  # Enemies skip their turns
ONE_HIT_KILL = False      # Player attacks always kill
VISIBLE_ALL = False        # All tiles visible, lit, and explored
MAX_NAV_UNITS = 1       # Override Ship.MAX_NAV_UNITS (None = use default 6)

# Debug starting inventory — list of (category, name) tuples.
# category is "scanner", "item", etc. matching data module categories.
# Set to None to disable.
START_INVENTORY = [
    ("scanner", "Basic Scanner"),
    ("scanner", "Advanced Scanner"),
    ("scanner", "Military Scanner"),
]


def build_debug_inventory():
    """Build Entity list from START_INVENTORY definitions. Returns [] if disabled."""
    if not START_INVENTORY:
        return []
    from dataclasses import asdict
    from data.items import ITEMS, SCANNERS, build_item_data
    from game.entity import Entity

    lookup = {}
    for s in SCANNERS:
        entry = asdict(s)
        lookup[("scanner", entry["name"])] = entry
    for i in ITEMS:
        lookup[("item", i.name)] = asdict(i)

    result = []
    for key in START_INVENTORY:
        defn = lookup.get(key)
        if defn is None:
            continue
        item_data = build_item_data(defn)
        result.append(Entity(
            char=defn["char"],
            color=tuple(defn["color"]),
            name=defn["name"],
            item=item_data,
        ))
    return result


def seed_ship_cargo(engine):
    """Place debug starting items into ship cargo."""
    for item in build_debug_inventory():
        engine.ship.add_cargo(item)

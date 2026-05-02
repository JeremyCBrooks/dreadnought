"""Serialization helpers: engine ↔ JSON dict for between-mission save state."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.game_state import Engine


# ── Entity ────────────────────────────────────────────────────────────────────


def _entity_to_dict(entity) -> dict:
    d: dict = {
        "name": entity.name,
        "char": entity.char,
        "color": list(entity.color),
        "item": entity.item,
        "blocks_movement": entity.blocks_movement,
        "x": entity.x,
        "y": entity.y,
        "organic": entity.organic,
        "max_inventory": entity.max_inventory,
        "interactable": entity.interactable,
        # Drifting / decompression
        "drifting": entity.drifting,
        "drift_direction": list(entity.drift_direction),
        "decompression_moves": entity.decompression_moves,
        "decompression_direction": list(entity.decompression_direction),
        "move_cooldown": entity.move_cooldown,
    }
    if entity.gore_color is not None:
        d["gore_color"] = list(entity.gore_color)
    if entity.fighter:
        f = entity.fighter
        d["fighter"] = {
            "hp": f.hp,
            "max_hp": f.max_hp,
            "defense": f.defense,
            "power": f.power,
            "base_power": f.base_power,
        }
    if entity.ai is not None:
        d["has_ai"] = True
        d["ai_config"] = entity.ai_config
        d["ai_state"] = entity.ai_state
        d["ai_target"] = list(entity.ai_target) if entity.ai_target is not None else None
        d["ai_wander_goal"] = list(entity.ai_wander_goal) if entity.ai_wander_goal is not None else None
        d["ai_turns_since_seen"] = entity.ai_turns_since_seen
        d["ai_stuck_turns"] = entity.ai_stuck_turns
        d["ai_energy"] = entity.ai_energy

    # Inventory + loadout + stolen_loot — indices preserve in-graph identity.
    inv = entity.inventory
    d["inventory"] = [_entity_to_dict(child) for child in inv]
    if entity.loadout is not None:
        slot1_idx = inv.index(entity.loadout.slot1) if entity.loadout.slot1 in inv else None
        slot2_idx = inv.index(entity.loadout.slot2) if entity.loadout.slot2 in inv else None
        d["loadout"] = {"slot1_idx": slot1_idx, "slot2_idx": slot2_idx}
    if entity.stolen_loot:
        d["stolen_loot_idxs"] = [inv.index(it) for it in entity.stolen_loot if it in inv]
    return d


def _entity_from_dict(d: dict):
    from game.entity import Entity, Fighter

    fighter = None
    if "fighter" in d:
        f = d["fighter"]
        fighter = Fighter(f["hp"], f["max_hp"], f["defense"], f["power"])
        fighter.base_power = f["base_power"]

    gore_color = tuple(d["gore_color"]) if d.get("gore_color") is not None else None

    entity = Entity(
        x=d.get("x", 0),
        y=d.get("y", 0),
        char=d["char"],
        color=tuple(d["color"]),
        name=d["name"],
        item=d.get("item"),
        fighter=fighter,
        blocks_movement=d.get("blocks_movement", False),
        organic=d.get("organic", True),
        gore_color=gore_color,
        max_inventory=d.get("max_inventory"),
    )
    entity.interactable = d.get("interactable")
    entity.drifting = d.get("drifting", False)
    entity.drift_direction = tuple(d.get("drift_direction", [0, 0]))
    entity.decompression_moves = d.get("decompression_moves", 0)
    entity.decompression_direction = tuple(d.get("decompression_direction", [0, 0]))
    entity.move_cooldown = d.get("move_cooldown", 0)

    if d.get("has_ai"):
        from game.ai import CreatureAI

        entity.ai = CreatureAI()
        entity.ai_config = d.get("ai_config", {})
        entity.ai_state = d.get("ai_state", "wandering")
        target = d.get("ai_target")
        entity.ai_target = tuple(target) if target is not None else None
        wander = d.get("ai_wander_goal")
        entity.ai_wander_goal = tuple(wander) if wander is not None else None
        entity.ai_turns_since_seen = d.get("ai_turns_since_seen", 0)
        entity.ai_stuck_turns = d.get("ai_stuck_turns", 0)
        entity.ai_energy = d.get("ai_energy", 0)

    inv_dicts = d.get("inventory", []) or []
    entity.inventory = [_entity_from_dict(child) for child in inv_dicts]

    lo_data = d.get("loadout")
    if lo_data is not None:
        from game.loadout import Loadout

        lo = Loadout()
        s1 = lo_data.get("slot1_idx")
        s2 = lo_data.get("slot2_idx")
        if s1 is not None and 0 <= s1 < len(entity.inventory):
            lo.slot1 = entity.inventory[s1]
        if s2 is not None and 0 <= s2 < len(entity.inventory):
            lo.slot2 = entity.inventory[s2]
        entity.loadout = lo

    stolen_idxs = d.get("stolen_loot_idxs", []) or []
    entity.stolen_loot = [entity.inventory[i] for i in stolen_idxs if 0 <= i < len(entity.inventory)]

    return entity


# ── Ship ──────────────────────────────────────────────────────────────────────


def _ship_to_dict(ship) -> dict | None:
    if ship is None:
        return None
    return {
        "fuel": ship.fuel,
        "max_fuel": ship.max_fuel,
        "hull": ship.hull,
        "max_hull": ship.max_hull,
        "scanner_quality": ship.scanner_quality,
        "nav_units": ship.nav_units,
        "cargo": [_entity_to_dict(e) for e in ship.cargo],
    }


def _ship_from_dict(d: dict | None):
    if d is None:
        return None
    from game.ship import Ship

    ship = Ship(
        fuel=d["fuel"],
        max_fuel=d["max_fuel"],
        scanner_quality=d["scanner_quality"],
        hull=d["hull"],
        max_hull=d["max_hull"],
    )
    ship.nav_units = d.get("nav_units", 0)
    ship.cargo = [_entity_from_dict(e) for e in d.get("cargo", [])]
    return ship


# ── Galaxy ────────────────────────────────────────────────────────────────────


def _galaxy_to_dict(galaxy) -> dict | None:
    if galaxy is None:
        return None
    systems = {}
    for name, sys in galaxy.systems.items():
        systems[name] = {
            "gx": sys.gx,
            "gy": sys.gy,
            "depth": sys.depth,
            "star_type": sys.star_type,
            "connections": sys.connections,
            "locations": [
                {
                    "name": loc.name,
                    "loc_type": loc.loc_type,
                    "environment": loc.environment,
                    "visited": loc.visited,
                    "scanned": loc.scanned,
                    "has_nav_unit": loc.has_nav_unit,
                    "is_dreadnought": loc.is_dreadnought,
                    "system_name": loc.system_name,
                }
                for loc in sys.locations
            ],
        }

    return {
        "seed": galaxy.seed,
        "home_system": galaxy.home_system,
        "current_system": galaxy.current_system,
        "dreadnought_system": galaxy.dreadnought_system,
        "generated_frontiers": list(galaxy._generated_frontiers),
        "unexplored_frontier": list(galaxy._unexplored_frontier),
        "nav_unit_rings": {str(k): v for k, v in galaxy._nav_unit_rings.items()},
        "systems": systems,
    }


def _galaxy_from_dict(d: dict | None):
    if d is None:
        return None
    from world.galaxy import DREADNOUGHT_LOCATION_NAME, DREADNOUGHT_SYSTEM_NAME, Galaxy, Location, StarSystem

    galaxy = Galaxy.__new__(Galaxy)
    galaxy.seed = d["seed"]
    galaxy.systems = {}
    galaxy._used_names: set[str] = {DREADNOUGHT_SYSTEM_NAME, DREADNOUGHT_LOCATION_NAME}
    galaxy._occupied_positions: dict = {}
    galaxy._generated_frontiers: set[str] = set(d.get("generated_frontiers", []))
    galaxy._unexplored_frontier: set[str] = set(d.get("unexplored_frontier", []))
    galaxy._nav_unit_rings: dict[int, str] = {int(k): v for k, v in d.get("nav_unit_rings", {}).items()}
    galaxy.dreadnought_system = d.get("dreadnought_system")

    # Lazy data tables (populated on first use by methods that need generation)
    from data.names import LOCATION_TYPES, LOCATION_WORDS, SYSTEM_WORDS

    galaxy._sw = SYSTEM_WORDS
    galaxy._loc_types = LOCATION_TYPES
    galaxy._loc_words = LOCATION_WORDS

    for name, sys_data in d["systems"].items():
        locations = []
        for loc_data in sys_data["locations"]:
            loc = Location(
                name=loc_data["name"],
                loc_type=loc_data["loc_type"],
                environment=loc_data.get("environment") or None,
                system_name=loc_data.get("system_name", name),
            )
            loc.visited = loc_data.get("visited", False)
            loc.scanned = loc_data.get("scanned", False)
            loc.has_nav_unit = loc_data.get("has_nav_unit", False)
            loc.is_dreadnought = loc_data.get("is_dreadnought", False)
            locations.append(loc)
            galaxy._used_names.add(loc_data["name"])

        system = StarSystem(
            name=name,
            locations=locations,
            depth=sys_data["depth"],
            star_type=sys_data["star_type"],
            gx=sys_data["gx"],
            gy=sys_data["gy"],
        )
        system.connections = sys_data["connections"]
        galaxy.systems[name] = system
        galaxy._occupied_positions[(sys_data["gx"], sys_data["gy"])] = name
        galaxy._used_names.add(name)

    galaxy.home_system = d["home_system"]
    galaxy.current_system = d["current_system"]

    return galaxy


# ── _saved_player ─────────────────────────────────────────────────────────────


def _saved_player_to_dict(sp: dict | None) -> dict | None:
    if sp is None:
        return None

    inventory: list = sp.get("inventory", [])
    loadout = sp.get("loadout")

    slot1_idx: int | None = None
    slot2_idx: int | None = None
    if loadout is not None:
        if loadout.slot1 is not None:
            try:
                slot1_idx = inventory.index(loadout.slot1)
            except ValueError:
                pass
        if loadout.slot2 is not None:
            try:
                slot2_idx = inventory.index(loadout.slot2)
            except ValueError:
                pass

    return {
        "hp": sp["hp"],
        "max_hp": sp["max_hp"],
        "defense": sp["defense"],
        "power": sp["power"],
        "base_power": sp["base_power"],
        "inventory": [_entity_to_dict(e) for e in inventory],
        "loadout": {"slot1_idx": slot1_idx, "slot2_idx": slot2_idx},
    }


def _saved_player_from_dict(d: dict | None) -> dict | None:
    if d is None:
        return None

    from game.loadout import Loadout

    inventory = [_entity_from_dict(e) for e in d.get("inventory", [])]

    lo_data = d.get("loadout", {})
    slot1_idx = lo_data.get("slot1_idx") if lo_data else None
    slot2_idx = lo_data.get("slot2_idx") if lo_data else None

    lo = Loadout()
    if slot1_idx is not None and slot1_idx < len(inventory):
        lo.slot1 = inventory[slot1_idx]
    if slot2_idx is not None and slot2_idx < len(inventory):
        lo.slot2 = inventory[slot2_idx]

    return {
        "hp": d["hp"],
        "max_hp": d["max_hp"],
        "defense": d["defense"],
        "power": d["power"],
        "base_power": d["base_power"],
        "inventory": inventory,
        "loadout": lo,
    }


# ── Suit ──────────────────────────────────────────────────────────────────────


def _suit_to_dict(suit) -> dict | None:
    if suit is None:
        return None
    return {
        "name": suit.name,
        "resistances": dict(suit.resistances),
        "defense_bonus": suit.defense_bonus,
        "current_pools": dict(suit.current_pools),
        "drain_ticks": dict(suit._drain_ticks),
    }


def _suit_from_dict(d: dict | None):
    if d is None:
        return None
    from game.suit import Suit

    suit = Suit(d["name"], d["resistances"], defense_bonus=d.get("defense_bonus", 0))
    suit.current_pools = dict(d.get("current_pools", d["resistances"]))
    suit._drain_ticks = dict(d.get("drain_ticks", {}))
    return suit


# ── MessageLog ────────────────────────────────────────────────────────────────


def _log_to_list(log) -> list:
    return [[text, list(color)] for text, color in log.messages]


def _log_from_list(lst: list):
    from engine.message_log import MessageLog

    log = MessageLog()
    for text, color in lst:
        log.add_message(text, tuple(color))
    return log


# ── Public API ────────────────────────────────────────────────────────────────


def is_mid_mission(engine: Engine) -> bool:
    """True if any TacticalState is somewhere on the engine's state stack.

    Used to detect when a disconnect or force-end should be treated as death:
    the player can't escape danger by yanking the websocket.
    """
    from ui.tactical_state import TacticalState

    return any(isinstance(s, TacticalState) for s in engine._state_stack)


def make_death_save_dict(cause: str = "Mission abandoned") -> dict:
    """Build the minimal save record used when a player force-ends mid-mission.

    Loading this dict pushes a GameOverState — the next login lands on the
    death screen instead of teleporting them back to the ship.
    """
    return {"dead": True, "cause": cause}


def engine_to_dict(engine: Engine) -> dict:
    """Serialize between-mission engine state to a JSON-safe dict."""
    return {
        "galaxy": _galaxy_to_dict(engine.galaxy),
        "ship": _ship_to_dict(engine.ship),
        "saved_player": _saved_player_to_dict(engine._saved_player),
        "message_log": _log_to_list(engine.message_log),
        "suit": _suit_to_dict(engine.suit),
        "environment": dict(engine.environment) if engine.environment else None,
        "active_effects": [dict(e) for e in engine.active_effects],
        "turn_counter": engine.turn_counter,
    }


def dict_to_engine(data: dict, engine: Engine) -> None:
    """Restore engine state from a save dict and push the appropriate state.

    Death saves (force-end mid-mission) push GameOverState directly, so the
    player can't resume the abandoned mission.
    """
    if data.get("dead"):
        from ui.game_over_state import GameOverState

        engine.push_state(
            GameOverState(
                victory=False,
                cause=data.get("cause", "Mission abandoned"),
                title="MISSION FAILED",
            )
        )
        return

    from ui.strategic_state import StrategicState

    engine.galaxy = _galaxy_from_dict(data["galaxy"])
    engine.ship = _ship_from_dict(data["ship"])
    engine._saved_player = _saved_player_from_dict(data.get("saved_player"))
    engine.message_log = _log_from_list(data.get("message_log", []))
    engine.suit = _suit_from_dict(data.get("suit"))
    engine.environment = dict(data["environment"]) if data.get("environment") else None
    engine.active_effects = [dict(e) for e in data.get("active_effects", [])]
    engine.turn_counter = data.get("turn_counter", 0)

    if engine.ship is not None:
        from world.dungeon_gen import generate_player_ship

        gm, rooms, exit_pos = generate_player_ship(seed=engine.galaxy.seed)
        engine.ship.game_map = gm
        engine.ship.rooms = rooms
        engine.ship.exit_pos = exit_pos

    engine.push_state(StrategicState(engine.galaxy))

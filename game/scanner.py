"""Area-scan logic and unified NEARBY HUD builder. Independently testable (no tcod needed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from game.helpers import chebyshev as _chebyshev
from ui.colors import HAZARD_ENV_DAMAGE, HP_YELLOW, INTERACT_EMPTY, NEUTRAL, WARNING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

# ---- Data classes ----


@dataclass(slots=True)
class ScanEntry:
    x: int
    y: int
    distance: int
    category: str  # "creature" | "item" | "container" | "hazard"
    display_char: str
    display_color: tuple[int, int, int]
    label: str
    entity: Entity | None = None  # back-ref for dedup; None for env hazards


@dataclass(slots=True)
class ScanResults:
    entries: list[ScanEntry]
    scanner_range: int


@dataclass(slots=True)
class NearbyEntry:
    x: int
    y: int
    distance: int
    category: str  # "creature" | "item" | "container" | "hazard"
    display_char: str
    display_color: tuple[int, int, int]
    label: str


# ---- Helpers ----

_CAT_ORDER = {"creature": 0, "hazard": 1, "container": 2, "item": 3}

# ---- Scan-tier formatting (used by perform_area_scan) ----


def _get_primary_weapon(entity: Entity) -> str | None:
    """Return the name of the first weapon in entity's inventory, or None."""
    for e in getattr(entity, "inventory", []):
        if e.item and e.item.get("type") == "weapon":
            return e.name
    return None


def _get_inventory_summary(entity: Entity) -> str:
    """Return comma-separated names of all inventory items, tagging stolen ones."""
    stolen = {id(i) for i in getattr(entity, "stolen_loot", [])}
    parts = []
    for e in getattr(entity, "inventory", []):
        if e.item:
            tag = " (STOLEN)" if id(e) in stolen else ""
            parts.append(f"{e.name}{tag}")
    return ", ".join(parts)


def _format_creature(entity: Entity, tier: int) -> tuple[str, tuple[int, int, int], str]:
    if tier <= 1:
        return "?", NEUTRAL, "???"
    if tier == 2:
        weapon = _get_primary_weapon(entity)
        label = f"{entity.name} [{weapon}]" if weapon else entity.name
        return entity.char, entity.color, label
    state = getattr(entity, "ai_state", "wandering")
    inv_summary = _get_inventory_summary(entity)
    label = f"{entity.name} [{state}] {inv_summary}" if inv_summary else f"{entity.name} [{state}]"
    return entity.char, entity.color, label


def _format_item(entity: Entity, tier: int) -> tuple[str, tuple[int, int, int], str]:
    if tier <= 1:
        return "?", NEUTRAL, "???"
    if tier == 2:
        return entity.char, entity.color, entity.name
    itype = entity.item.get("type", "") if entity.item else ""
    return entity.char, entity.color, f"{entity.name} ({itype})" if itype else entity.name


def _format_container(entity: Entity, tier: int) -> tuple[str, tuple[int, int, int], str]:
    ih = entity.interactable
    name = entity.name
    loot = ih.get("loot") if ih else None
    hazard = ih.get("hazard") if ih else None
    has_loot = loot and isinstance(loot, dict) and "name" in loot
    has_hazard = bool(hazard)

    parts = [name]

    if has_loot and has_hazard:
        if tier <= 1:
            parts.append("- ???, HAZARD")
        elif tier == 2:
            parts.append(f"- {loot['name']}, HAZARD")
        else:
            parts.append(f"- {loot['name']}, {hazard.get('type', 'unknown')}")
    elif has_loot:
        if tier <= 1:
            parts.append("- ???")
        else:
            parts.append(f"- {loot['name']}")
    elif has_hazard:
        if tier >= 3:
            parts.append(f"- {hazard.get('type', 'unknown')}")
        else:
            parts.append("- HAZARD")

    label = " ".join(parts)
    return entity.char, entity.color, label


def _format_env_hazard(hazard_name: str, tier: int) -> tuple[str, tuple[int, int, int], str]:
    if tier <= 1:
        return "!", HP_YELLOW, "Hazard"
    else:
        return "!", HP_YELLOW, hazard_name.title()


# ---- Visible-level formatting (full detail, used by build_nearby_entries) ----

_STATE_INDICATORS = {
    "sleeping": "Zzz",
    "wandering": "...",
    "hunting": "!!!",
    "fleeing": "~~~",
}


def _visible_creature_entry(entity: Entity, dist: int) -> NearbyEntry:
    st = getattr(entity, "ai_state", "wandering")
    indicator = _STATE_INDICATORS.get(st, "...")
    hp_str = f"{entity.fighter.hp}/{entity.fighter.max_hp}"
    label = f"{entity.name} {hp_str} {indicator}"
    return NearbyEntry(entity.x, entity.y, dist, "creature", entity.char, entity.color, label)


def _visible_item_entry(entity: Entity, dist: int) -> NearbyEntry:
    return NearbyEntry(entity.x, entity.y, dist, "item", entity.char, entity.color, entity.name)


def _visible_container_entry(entity: Entity, dist: int) -> NearbyEntry:
    return NearbyEntry(entity.x, entity.y, dist, "container", entity.char, entity.color, entity.name)


# ---- perform_area_scan ----


def perform_area_scan(engine: Engine, entity: Entity, *, scanner: Entity | None = None) -> ScanResults | None:
    """Scan an area around entity using equipped scanner. Returns None if no scanner."""
    if scanner is None:
        if getattr(entity, "loadout", None):
            scanner = entity.loadout.get_scanner()
    if not scanner:
        engine.message_log.add_message("You need a scanner in your loadout.", INTERACT_EMPTY)
        return None

    # Check remaining uses
    uses = scanner.item.get("uses", 0)
    if uses <= 0:
        engine.message_log.add_message(f"The {scanner.name} is disabled junk.", INTERACT_EMPTY)
        return None

    # Consume one use
    scanner.item["uses"] = uses - 1

    scan_range = scanner.item.get("range", 8)
    tier = scanner.item.get("scanner_tier", 1)
    px, py = entity.x, entity.y
    gm = engine.game_map
    entries: list[ScanEntry] = []

    for e in gm.entities:
        if e is entity:
            continue
        dist = _chebyshev(px, py, e.x, e.y)
        if dist > scan_range or dist == 0:
            continue

        if e.fighter and e.ai:
            char, color, label = _format_creature(e, tier)
            entries.append(ScanEntry(e.x, e.y, dist, "creature", char, color, label, entity=e))
        elif e.interactable:
            char, color, label = _format_container(e, tier)
            entries.append(ScanEntry(e.x, e.y, dist, "container", char, color, label, entity=e))
            e.interactable["scanned"] = True
        elif e.item and not e.fighter:
            char, color, label = _format_item(e, tier)
            entries.append(ScanEntry(e.x, e.y, dist, "item", char, color, label, entity=e))

    # Environmental hazard overlays (numpy-accelerated nearest-cell search)
    for hazard_name, overlay in gm.hazard_overlays.items():
        x_lo = max(0, px - scan_range)
        x_hi = min(gm.width, px + scan_range + 1)
        y_lo = max(0, py - scan_range)
        y_hi = min(gm.height, py + scan_range + 1)
        region = overlay[x_lo:x_hi, y_lo:y_hi]
        hxs, hys = np.where(region)
        if hxs.size == 0:
            continue
        hxs += x_lo
        hys += y_lo
        dists = np.maximum(np.abs(hxs - px), np.abs(hys - py))
        mask = dists <= scan_range
        if not np.any(mask):
            continue
        dists = dists[mask]
        hxs = hxs[mask]
        hys = hys[mask]
        idx = int(np.argmin(dists))
        char, color, label = _format_env_hazard(hazard_name, tier)
        entries.append(ScanEntry(int(hxs[idx]), int(hys[idx]), int(dists[idx]), "hazard", char, color, label))

    entries.sort(key=lambda e: e.distance)

    # Warn player if the scanner just burned out
    if scanner.item.get("uses", 0) <= 0:
        engine.message_log.add_message(f"The {scanner.name} gives out and is now junk.", (255, 180, 50))

    return ScanResults(entries=entries, scanner_range=scan_range)


# ---- build_nearby_entries (unified NEARBY HUD) ----


def _collect_visible_hazard_sources(engine: Engine, px: int, py: int) -> list[NearbyEntry]:
    """Collect known hazard sources (hull breaches, open airlocks) that the player can see."""
    from world import tile_types

    gm = engine.game_map
    results: list[NearbyEntry] = []

    # Hull breaches
    for bx, by in gm.hull_breaches:
        if gm.in_bounds(bx, by) and gm.visible[bx, by]:
            dist = _chebyshev(px, py, bx, by)
            results.append(NearbyEntry(bx, by, dist, "hazard", "X", HAZARD_ENV_DAMAGE, "Hull breach"))

    # Open exterior airlock doors — use airlocks list instead of scanning all tiles
    ext_open_tid = int(tile_types.airlock_ext_open["tile_id"])
    for al in gm.airlocks:
        dx, dy = al["exterior_door"]
        if gm.in_bounds(dx, dy) and gm.visible[dx, dy]:
            if int(gm.tiles["tile_id"][dx, dy]) == ext_open_tid:
                dist = _chebyshev(px, py, dx, dy)
                results.append(NearbyEntry(dx, dy, dist, "hazard", "+", WARNING, "Airlock (open)"))

    return results


def build_nearby_entries(engine: Engine) -> list[NearbyEntry]:
    """Build a unified, deduplicated list of nearby entries from visible + scan data."""
    gm = engine.game_map
    p = engine.player
    px, py = p.x, p.y
    scan_results = getattr(engine, "scan_results", None)

    # Build a set of entities still alive on the map for staleness filtering
    live_entity_ids = {id(e) for e in gm.entities}

    # Track which entities we've already added (by identity) to avoid duplicates
    seen_entities: set[int] = set()
    # Track hazard source positions to avoid duplicates
    seen_hazard_positions: set[tuple[int, int]] = set()
    entries: list[NearbyEntry] = []

    # Build a lookup: entity id -> scan entry, for merging scan detail into visible entries
    scan_by_entity: dict[int, ScanEntry] = {}
    if scan_results:
        for se in scan_results.entries:
            if se.entity is not None:
                scan_by_entity[id(se.entity)] = se

    # 1. Visible entities get full detail (takes priority over scan)
    for e in gm.entities:
        if e is p:
            continue
        if not gm.in_bounds(e.x, e.y) or not gm.visible[e.x, e.y]:
            continue
        # Skip entities at the player's position (that's UNDERFOOT territory)
        if e.x == px and e.y == py:
            continue
        dist = _chebyshev(px, py, e.x, e.y)

        if e.fighter and e.ai:
            entries.append(_visible_creature_entry(e, dist))
            seen_entities.add(id(e))
        elif e.interactable:
            # If this container was also scanned, use the scan label (has hazard/loot detail)
            se = scan_by_entity.get(id(e))
            if se is not None:
                entries.append(NearbyEntry(e.x, e.y, dist, "container", se.display_char, se.display_color, se.label))
            else:
                entries.append(_visible_container_entry(e, dist))
            seen_entities.add(id(e))
        elif e.item and not e.fighter:
            entries.append(_visible_item_entry(e, dist))
            seen_entities.add(id(e))

    # 2. Visible hazard sources (hull breaches, open airlocks)
    visible_hazards = _collect_visible_hazard_sources(engine, px, py)
    for h in visible_hazards:
        pos_key = (h.x, h.y)
        if pos_key not in seen_hazard_positions:
            entries.append(h)
            seen_hazard_positions.add(pos_key)

    # 3. Scan results: add anything not already covered by visibility
    if scan_results:
        for se in scan_results.entries:
            # Skip entities already shown via visibility
            if se.entity is not None and id(se.entity) in seen_entities:
                continue
            # Skip stale entries for entities no longer on the map
            if se.entity is not None and id(se.entity) not in live_entity_ids:
                continue
            # Recalculate distance from current player position (not stale scan-time)
            if se.entity is not None:
                cur_dist = _chebyshev(px, py, se.entity.x, se.entity.y)
            else:
                cur_dist = _chebyshev(px, py, se.x, se.y)
            # Skip distance-0 entries (player's own tile = UNDERFOOT)
            if cur_dist == 0:
                continue
            if se.category == "hazard":
                # Env hazard from scan — add if no visible hazard at same position
                pos_key = (se.x, se.y)
                if pos_key not in seen_hazard_positions:
                    entries.append(
                        NearbyEntry(se.x, se.y, cur_dist, se.category, se.display_char, se.display_color, se.label)
                    )
                    seen_hazard_positions.add(pos_key)
            else:
                entries.append(
                    NearbyEntry(se.x, se.y, cur_dist, se.category, se.display_char, se.display_color, se.label)
                )
            if se.entity is not None:
                seen_entities.add(id(se.entity))

    entries.sort(key=lambda e: (_CAT_ORDER.get(e.category, 9), e.distance))
    return entries

"""The tactical stats panel: vitals, suit, hazards, loadout, ground text, nearby list, key hints."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from ui.colors import DARK_GRAY, EQUIP_MSG, GRAY, HEADER_SEP, HP_GREEN, HP_RED, HP_YELLOW, PROMPT
from ui.keys import action_keys

if TYPE_CHECKING:
    from engine.game_state import Engine

Color = tuple[int, int, int]

CTRL_LINES = 4
GROUND_MAX_LINES_DEFAULT = 8


@dataclass
class HudView:
    """What the panel needs to know about the tactical state that owns it."""

    location_label: str
    explore_ship: bool
    look_cursor: tuple[int, int] | None
    ranged_cursor: tuple[int, int] | None
    ground_lines: list[tuple[str, Color]]


def _hint(name: str) -> str:
    """Build a HUD hint like '[x] look' from the action_keys registry."""
    _, label, verb = action_keys()[name]
    return f"[{label}] {verb}"


def render_stats(console: Any, engine: Engine, layout: SimpleNamespace, view: HudView) -> None:
    from game.interdiction import current_interdiction

    x = layout.stats_x + 1
    p = engine.player
    stats_h = layout.viewport_h
    ctrl_y = stats_h - CTRL_LINES

    console.print(x=x, y=1, string=view.location_label, fg=(180, 180, 255))
    console.print(x=x, y=2, string="-" * (layout.stats_w - 2), fg=HEADER_SEP)

    # Interdiction banner: live pirate count while aboard our ship.
    if view.explore_ship:
        interdiction = current_interdiction(engine)
        if interdiction is not None and interdiction.started and not interdiction.resolved:
            remaining = interdiction.alive_pirate_count()
            console.print(
                x=x,
                y=3,
                string=f"INTRUDERS: {remaining} remain",
                fg=(255, 200, 100),
            )

    hp_ratio = p.fighter.hp / max(1, p.fighter.max_hp)
    if hp_ratio > 0.5:
        hp_color = HP_GREEN
    elif hp_ratio > 0.25:
        hp_color = HP_YELLOW
    else:
        hp_color = HP_RED
    console.print(x=x, y=4, string=f"HP: {p.fighter.hp}/{p.fighter.max_hp}", fg=hp_color)
    eff_def = p.fighter.defense + (engine.suit.defense_bonus if engine.suit else 0)
    console.print(x=x, y=5, string=f"DEF: {eff_def}", fg=(200, 200, 200))
    console.print(x=x, y=6, string=f"POW: {p.fighter.power}", fg=(200, 200, 200))

    # Suit resource bars (Phase 3)
    row = 8
    if engine.suit and engine.environment:
        console.print(x=x, y=row, string="SUIT:", fg=(180, 180, 200))
        row += 1
        for hazard_type in engine.environment:
            max_turns = engine.suit.resistances.get(hazard_type, 0)
            current = engine.suit.current_pools.get(hazard_type, 0)
            if hazard_type == "vacuum":
                label = "O2 "
            elif hazard_type == "low_gravity":
                label = "GRV"
            else:
                label = hazard_type[:3].upper()
            if max_turns > 0:
                ratio = current / max_turns
                if ratio > 0.5:
                    bar_color = (0, 255, 0)
                elif ratio > 0.25:
                    bar_color = (255, 255, 0)
                else:
                    bar_color = (255, 0, 0)
                bar_w = min(10, layout.stats_w - 8)
                filled = max(0, int(bar_w * ratio))
                bar = "█" * filled + "░" * (bar_w - filled)
                console.print(x=x, y=row, string=f"{label}: {bar}", fg=bar_color)
                console.print(x=x + 4 + bar_w + 1, y=row, string=f"{current}/{max_turns}", fg=GRAY)
            else:
                console.print(x=x, y=row, string=f"{label}: --", fg=DARK_GRAY)
            row += 1
        row += 1

    # Active hazards at player position
    from game.environment import GLOBAL_HAZARDS, NON_DAMAGING_HAZARDS

    engine.game_map.recalculate_hazards()
    active = engine.game_map.get_hazards_at(p.x, p.y)
    # Include global hazards from environment
    if engine.environment:
        for h in engine.environment:
            if h in GLOBAL_HAZARDS and engine.environment[h] > 0:
                active.add(h)
    if active:
        console.print(x=x, y=row, string="HAZARDS:", fg=(255, 100, 100))
        row += 1
        for h in sorted(active):
            label = h.replace("_", " ").upper()
            if h in NON_DAMAGING_HAZARDS:
                color = PROMPT
            else:
                color = (255, 80, 80)
            console.print(x=x, y=row, string=f"! {label}", fg=color)
            row += 1
        row += 1
    elif engine.environment and any(v > 0 and k not in NON_DAMAGING_HAZARDS for k, v in engine.environment.items()):
        console.print(x=x, y=row, string="NO HAZARDS", fg=(0, 200, 100))
        row += 2

    # LOADOUT display (2 slots)
    loadout_section_start = row + 1
    ground_header_y = loadout_section_start + 3  # 1 header + 2 slot lines
    ground_max_lines = min(GROUND_MAX_LINES_DEFAULT, max(1, ctrl_y - 1 - ground_header_y))

    console.print(x=x, y=row, string="LOADOUT:", fg=(180, 180, 200))
    row += 1
    lo = p.loadout
    inv_width = layout.stats_w - 2
    if lo:
        for si, slot_item in enumerate((lo.slot1, lo.slot2)):
            label = f"S{si + 1}"
            if slot_item:
                ammo = slot_item.item.get("ammo") if slot_item.item else None
                max_ammo = slot_item.item.get("max_ammo") if slot_item.item else None
                if ammo is not None and max_ammo is not None:
                    slot_label = f"{label}: {slot_item.name} {ammo}/{max_ammo}"
                else:
                    slot_label = f"{label}: {slot_item.name}"
            else:
                slot_label = f"{label}: --"
            console.print(x=x, y=row + si, string=slot_label[:inv_width], fg=(150, 150, 255))
    else:
        console.print(x=x, y=row, string="(none)", fg=(80, 80, 80))

    # --- Ground text block (non-persistent) ---
    if view.look_cursor is not None:
        header = "LOOKING AT:"
        header_color = PROMPT
    else:
        header = "UNDERFOOT:"
        header_color = (140, 140, 170)
    console.print(x=x, y=ground_header_y, string=header, fg=header_color)
    ground_width = max(1, layout.stats_w - 2)
    wrapped: list[tuple[str, Color]] = []
    for text, color in view.ground_lines:
        for line in textwrap.wrap(text, width=ground_width):
            wrapped.append((line, color))
    for i, (text, color) in enumerate(wrapped[:ground_max_lines]):
        console.print(
            x=x,
            y=ground_header_y + 1 + i,
            string=text,
            fg=color,
        )

    # NEARBY section (below UNDERFOOT) — unified visible + scan data
    from game.scanner import build_nearby_entries

    nearby_y = ground_header_y + 1 + min(len(wrapped), ground_max_lines) + 1
    nearby_entries = build_nearby_entries(engine)
    if nearby_entries:
        _cat_colors = {
            "creature": (255, 80, 80),
            "hazard": (255, 255, 0),
            "container": (80, 200, 80),
            "item": (100, 200, 255),
        }
        header = "NEARBY:"
        header_color = (180, 180, 200)
        console.print(x=x, y=nearby_y, string=header, fg=header_color)
        nearby_y += 1
        for entry in nearby_entries[:8]:
            targeted = (
                view.ranged_cursor is not None and entry.x == view.ranged_cursor[0] and entry.y == view.ranged_cursor[1]
            )
            color = _cat_colors.get(entry.category, (180, 180, 200))
            prefix = ">" if targeted else entry.display_char
            line = f"{prefix} {entry.label} {entry.distance}"
            if targeted:
                color = (255, 255, 255)
            console.print(x=x, y=nearby_y, string=line[: layout.stats_w - 2], fg=color)
            nearby_y += 1

    # --- Controls ---
    if view.ranged_cursor is not None:
        cx, cy = view.ranged_cursor
        dx = abs(p.x - cx)
        dy = abs(p.y - cy)
        dist = max(dx, dy)
        from game.helpers import get_equipped_ranged_weapon

        wpn_ctrl = get_equipped_ranged_weapon(p)
        max_range = wpn_ctrl.item.get("range", 5) if wpn_ctrl else 0
        in_range = dist <= max_range
        look_label = f"[f] {dist}/{max_range}"
        look_color = EQUIP_MSG if in_range else (255, 100, 100)
    elif view.look_cursor is not None:
        ak = action_keys()
        look_label = f"[{ak['look'][1]}] LOOKING"
        look_color = PROMPT
    else:
        look_label = _hint("look")
        look_color = (70, 70, 70)

    col2_x = x + layout.stats_w // 2
    hint_color = (70, 70, 70)
    console.print(x=x, y=ctrl_y, string=look_label, fg=look_color)
    console.print(x=col2_x, y=ctrl_y, string=_hint("fire"), fg=hint_color)
    console.print(x=x, y=ctrl_y + 1, string=_hint("inventory"), fg=hint_color)
    console.print(x=col2_x, y=ctrl_y + 1, string=_hint("scan"), fg=hint_color)
    console.print(x=x, y=ctrl_y + 2, string=_hint("interact"), fg=hint_color)
    console.print(x=col2_x, y=ctrl_y + 2, string=_hint("get"), fg=hint_color)
    console.print(x=x, y=ctrl_y + 3, string=_hint("wait"), fg=hint_color)
    console.print(x=col2_x, y=ctrl_y + 3, string=_hint("quit"), fg=hint_color)

"""Loadout selection state: choose suit and 4 typed equipment slots before a mission."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

# Panel indices
_SUIT = 0
_WEAPON = 1
_TOOL = 2
_CONSUMABLE1 = 3
_CONSUMABLE2 = 4
_NUM_PANELS = 5

_PANEL_NAMES = ["SUIT", "WEAPON", "TOOL", "CONSUMABLE 1", "CONSUMABLE 2"]


class LoadoutState(State):
    """Select suit and 4 typed equipment slots to bring on mission."""

    def __init__(self, location: Any = None, depth: int = 0) -> None:
        self._panel = 0
        self._suit_index = 0
        self._cursor = 0  # cursor within current equipment panel's filtered list
        self._selections: Dict[int, Optional[int]] = {
            _WEAPON: None, _TOOL: None, _CONSUMABLE1: None, _CONSUMABLE2: None,
        }  # panel -> index into _filtered_items for that panel
        self._suits: list = []
        self.location = location
        self.depth = depth

    def on_enter(self, engine: Engine) -> None:
        from game.suit import EVA_SUIT, HAZARD_SUIT
        self._suits = [EVA_SUIT, HAZARD_SUIT]
        if engine.suit:
            for i, s in enumerate(self._suits):
                if s.name == engine.suit.name:
                    self._suit_index = i
                    break

    @staticmethod
    def _get_slot_map() -> Dict:
        from game.loadout import SlotType
        return {
            _WEAPON: SlotType.WEAPON,
            _TOOL: SlotType.TOOL,
            _CONSUMABLE1: SlotType.CONSUMABLE,
            _CONSUMABLE2: SlotType.CONSUMABLE,
        }

    def _filtered_cargo(self, engine: Engine, panel: int, *, exclude_cross: bool = True) -> List[Entity]:
        """Return cargo items matching the panel's slot type.

        If *exclude_cross* is True (default), items already selected in other panels are excluded.
        """
        from game.loadout import item_slot_type

        slot_map = self._get_slot_map()
        target_slot = slot_map.get(panel)
        if not target_slot:
            return []

        ship = getattr(engine, "ship", None)
        cargo = ship.cargo if ship else []

        if not exclude_cross:
            return [item for item in cargo if item_slot_type(item) == target_slot]

        # Collect items already selected in OTHER panels
        already_selected: set = set()
        for p, sel_idx in self._selections.items():
            if p != panel and sel_idx is not None:
                items = self._filtered_cargo(engine, p, exclude_cross=False)
                if sel_idx < len(items):
                    already_selected.add(id(items[sel_idx]))

        return [
            item for item in cargo
            if item_slot_type(item) == target_slot
            and id(item) not in already_selected
        ]

    def _selected_item(self, engine: Engine, panel: int) -> Optional[Entity]:
        """Return the actual Entity selected for a panel, or None."""
        sel = self._selections.get(panel)
        if sel is None:
            return None
        items = self._filtered_cargo(engine, panel, exclude_cross=False)
        if sel < len(items):
            return items[sel]
        return None

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event
        from ui.keys import move_keys, confirm_keys, cancel_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        if key in confirm_keys():
            self._confirm(engine)
            return True

        direction = move_keys().get(key)
        if direction:
            dx, dy = direction
            if dx > 0 and dy == 0:
                self._panel = (self._panel + 1) % _NUM_PANELS
                self._cursor = 0
                return True
            if dx < 0 and dy == 0:
                self._panel = (self._panel - 1) % _NUM_PANELS
                self._cursor = 0
                return True
            if dy < 0:
                if self._panel == _SUIT:
                    self._suit_index = max(0, self._suit_index - 1)
                else:
                    self._cursor = max(0, self._cursor - 1)
                return True
            if dy > 0:
                if self._panel == _SUIT:
                    self._suit_index = min(len(self._suits) - 1, self._suit_index + 1)
                else:
                    items = self._filtered_cargo(engine, self._panel)
                    if items:
                        self._cursor = min(len(items) - 1, self._cursor + 1)
                return True
            return True

        if self._panel != _SUIT:
            items = self._filtered_cargo(engine, self._panel)
            if key == tcod.event.KeySym.SPACE:
                if items and 0 <= self._cursor < len(items):
                    # Find the raw index for this item
                    raw_items = self._filtered_cargo(engine, self._panel, exclude_cross=False)
                    selected_entity = items[self._cursor]
                    raw_idx = None
                    for ri, raw_item in enumerate(raw_items):
                        if raw_item is selected_entity:
                            raw_idx = ri
                            break
                    if raw_idx is not None:
                        if self._selections[self._panel] == raw_idx:
                            self._selections[self._panel] = None  # deselect
                        else:
                            self._selections[self._panel] = raw_idx

        return True

    def _confirm(self, engine: Engine) -> None:
        from game.loadout import Loadout

        engine.suit = self._suits[self._suit_index]

        weapon = self._selected_item(engine, _WEAPON)
        tool = self._selected_item(engine, _TOOL)
        c1 = self._selected_item(engine, _CONSUMABLE1)
        c2 = self._selected_item(engine, _CONSUMABLE2)

        loadout = Loadout(weapon=weapon, tool=tool, consumable1=c1, consumable2=c2)

        # Remove selected items from cargo
        ship = getattr(engine, "ship", None)
        if ship:
            for item in loadout.all_items():
                ship.remove_cargo(item)

        engine._pending_loadout = loadout

        from ui.tactical_state import TacticalState
        engine.switch_state(TacticalState(
            location=self.location,
            depth=self.depth,
        ))

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(72, cw - 10)
        bh = min(35, ch - 6)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        from ui.colors import DIALOG_BG, HEADER_TITLE
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        console.print(x=bx + 2, y=by + 1, string="=== LOADOUT ===", fg=HEADER_TITLE)

        # Panel tabs
        tab_y = by + 2
        tx = bx + 2
        for i, name in enumerate(_PANEL_NAMES):
            from ui.colors import TAB_SELECTED, TAB_UNSELECTED
            color = TAB_SELECTED if i == self._panel else TAB_UNSELECTED
            console.print(x=tx, y=tab_y, string=name, fg=color)
            tx += len(name) + 2

        row = by + 4

        if self._panel == _SUIT:
            console.print(x=bx + 2, y=row, string="Select suit:", fg=(200, 200, 200))
            row += 1
            for i, suit in enumerate(self._suits):
                prefix = ">" if i == self._suit_index else " "
                color = (255, 255, 255) if i == self._suit_index else (150, 150, 150)
                res_str = ", ".join(f"{k}:{v}" for k, v in suit.resistances.items())
                label = f"{prefix} {suit.name} (DEF+{suit.defense_bonus}, {res_str})"
                console.print(x=bx + 4, y=row, string=label[:max(1, bw - 6)], fg=color)
                row += 1
        else:
            panel_label = _PANEL_NAMES[self._panel]
            console.print(x=bx + 2, y=row, string=f"Select {panel_label}:", fg=(200, 200, 200))
            row += 1
            items = self._filtered_cargo(engine, self._panel)
            if not items:
                console.print(x=bx + 4, y=row, string="(no matching cargo)", fg=(80, 80, 80))
            else:
                raw_items = self._filtered_cargo(engine, self._panel, exclude_cross=False)
                for j, item in enumerate(items):
                    cursor = j == self._cursor
                    # Check if this item is the currently selected one
                    raw_idx = None
                    for ri, raw_item in enumerate(raw_items):
                        if raw_item is item:
                            raw_idx = ri
                            break
                    selected = self._selections[self._panel] == raw_idx
                    mark = "[X]" if selected else "[ ]"
                    prefix = ">" if cursor else " "
                    color = (100, 255, 100) if selected else (255, 255, 255) if cursor else (150, 150, 150)
                    label = f"{prefix} {mark} {item.name}"
                    console.print(x=bx + 4, y=row + j, string=label[:max(1, bw - 6)], fg=color)

        # Summary
        summary_y = by + bh - 4
        suit_name = self._suits[self._suit_index].name
        wpn = self._selected_item(engine, _WEAPON)
        tool = self._selected_item(engine, _TOOL)
        c1 = self._selected_item(engine, _CONSUMABLE1)
        c2 = self._selected_item(engine, _CONSUMABLE2)
        console.print(x=bx + 2, y=summary_y, string=f"Suit: {suit_name}", fg=(200, 200, 200))
        console.print(x=bx + 2, y=summary_y + 1,
                      string=f"WPN: {wpn.name if wpn else '--'} | TOOL: {tool.name if tool else '--'}",
                      fg=(200, 200, 200))
        console.print(x=bx + 2, y=summary_y + 2,
                      string=f"C1: {c1.name if c1 else '--'} | C2: {c2.name if c2 else '--'}",
                      fg=(200, 200, 200))
        console.print(
            x=bx + 2, y=by + bh - 1,
            string="[LEFT/RIGHT] Panel [SPACE] Toggle [ENTER] Confirm [ESC] Back",
            fg=(100, 100, 100),
        )

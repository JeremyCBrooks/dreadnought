"""Cargo management overlay: transfer items between ship cargo and personal loadout."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from engine.game_state import State
from ui.colors import DARK_GRAY, GRAY, WARNING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity
    from game.loadout import Loadout

_PERSONAL = 0
_CARGO = 1


class CargoState(State):
    """Two-column UI for choosing which cargo items to bring on a mission."""

    def __init__(self) -> None:
        self.selected = 0
        self._section = _CARGO

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _personal_list(self, engine: Engine) -> list:
        """Return the personal inventory list (mission_loadout or saved_player inventory)."""
        if hasattr(engine, 'mission_loadout') and engine.mission_loadout is not None:
            ml = engine.mission_loadout
            if ml or not getattr(engine, '_saved_player', None):
                return ml
        sp = getattr(engine, '_saved_player', None)
        if sp and "inventory" in sp:
            return sp["inventory"]
        return engine.mission_loadout

    def _get_loadout(self, engine: Engine) -> Optional[Loadout]:
        """Return the Loadout, lazily initializing _saved_player if needed."""
        from game.loadout import Loadout

        sp = getattr(engine, '_saved_player', None)
        if sp is None:
            engine._saved_player = {
                "hp": 10, "max_hp": 10, "defense": 0,
                "power": 1, "base_power": 1,
                "inventory": [], "loadout": Loadout(),
            }
            sp = engine._saved_player
        lo = sp.get("loadout")
        if lo is None:
            lo = Loadout()
            sp["loadout"] = lo
        return lo

    def _combined_personal(self, engine: Engine) -> List[Tuple[Entity, bool]]:
        """Return [(item, is_equipped), ...] in stable insertion order."""
        from game.loadout import combined_items
        return combined_items(self._personal_list(engine), self._get_loadout(engine))

    def _personal_count(self, engine: Engine) -> int:
        """Total personal items (equipped items are kept in inventory)."""
        return len(self._personal_list(engine))

    def _current_list_len(self, engine: Engine) -> int:
        """Length of the current section's list (combined for personal)."""
        if self._section == _PERSONAL:
            return len(self._combined_personal(engine))
        return len(engine.ship.cargo)

    def _clamp_selected(self, engine: Engine) -> None:
        """Clamp selected index to valid range after changes."""
        length = self._current_list_len(engine)
        if length > 0:
            self.selected = min(self.selected, length - 1)
        else:
            self.selected = 0

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        from ui.keys import move_keys, confirm_keys, cancel_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        direction = move_keys().get(key)
        if direction:
            dx, dy = direction
            if dx < 0:
                self._section = _PERSONAL
                self.selected = 0
                return True
            if dx > 0:
                self._section = _CARGO
                self.selected = 0
                return True
            if dy != 0:
                length = self._current_list_len(engine)
                if dy < 0:
                    self.selected = max(0, self.selected - 1)
                elif dy > 0 and length > 0:
                    self.selected = min(length - 1, self.selected + 1)
                return True
            return True

        if key in confirm_keys():
            self._transfer(engine)
            return True

        # 'e' key for equip/unequip
        import tcod.event
        if key == tcod.event.KeySym.e:
            self._equip_unequip(engine)
            return True

        return True

    # ------------------------------------------------------------------
    # Equip / Unequip
    # ------------------------------------------------------------------

    def _equip_unequip(self, engine: Engine) -> None:
        """Handle 'e' key: equip or unequip the selected personal item."""
        from game.loadout import toggle_equip
        from game.entity import Entity as _Entity

        if self._section != _PERSONAL:
            return

        lo = self._get_loadout(engine)
        if lo is None:
            return

        combined = self._combined_personal(engine)
        if not combined or self.selected >= len(combined):
            return

        item, _is_equipped = combined[self.selected]

        # Build a proxy entity carrying the saved loadout + inventory
        # so toggle_equip sees the real item list (no fighter → skip melee recalc).
        proxy = _Entity()
        proxy.loadout = lo
        proxy.inventory = self._personal_list(engine)
        toggle_equip(engine, proxy, item)
        self._clamp_selected(engine)

    # ------------------------------------------------------------------
    # Transfer
    # ------------------------------------------------------------------

    def _transfer(self, engine: Engine) -> None:
        from game.entity import PLAYER_MAX_INVENTORY

        personal = self._personal_list(engine)

        if self._section == _CARGO:
            cargo = engine.ship.cargo
            if not cargo or self.selected >= len(cargo):
                return
            item = cargo[self.selected]
            if item.item and item.item.get("type") == "dreadnought_core":
                engine.message_log.add_message(
                    "The Dreadnought core must stay in cargo.", WARNING)
                return
            if self._personal_count(engine) >= PLAYER_MAX_INVENTORY:
                engine.message_log.add_message("Personal inventory full.", WARNING)
                return
            cargo.pop(self.selected)
            personal.append(item)
        else:
            combined = self._combined_personal(engine)
            if not combined or self.selected >= len(combined):
                return
            item, is_equipped = combined[self.selected]
            if is_equipped:
                lo = self._get_loadout(engine)
                if lo:
                    lo.unequip(item)
            personal.remove(item)
            engine.ship.add_cargo(item)

        self._clamp_selected(engine)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def on_render(self, console: Any, engine: Engine) -> None:
        from game.entity import PLAYER_MAX_INVENTORY
        from ui.colors import DIALOG_BG, TAB_SELECTED, TAB_UNSELECTED, HEADER_TITLE

        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(60, cw - 10)
        bh = min(30, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        console.print(x=bx + 2, y=by + 1, string="=== CARGO MANAGEMENT ===", fg=HEADER_TITLE)

        # Section tabs
        p_color = TAB_SELECTED if self._section == _PERSONAL else TAB_UNSELECTED
        c_color = TAB_SELECTED if self._section == _CARGO else TAB_UNSELECTED
        cap = self._personal_count(engine)
        console.print(x=bx + 2, y=by + 3,
                       string=f"PERSONAL ({cap}/{PLAYER_MAX_INVENTORY})", fg=p_color)
        console.print(x=bx + bw // 2, y=by + 3, string="SHIP CARGO", fg=c_color)

        max_visible = max(0, bh - 8)
        row = by + 5
        label_width = bw // 2 - 4

        # Personal column (combined: equipped + inventory)
        combined = self._combined_personal(engine)
        if not combined:
            console.print(x=bx + 2, y=row, string="(empty)", fg=DARK_GRAY)
        else:
            p_start = max(0, min(self.selected - max_visible + 1, len(combined) - max_visible)) if self._section == _PERSONAL else 0
            for j in range(min(max_visible, len(combined) - p_start)):
                i = p_start + j
                item, is_equipped = combined[i]
                prefix = ">" if self._section == _PERSONAL and i == self.selected else " "
                color = (255, 255, 255) if self._section == _PERSONAL and i == self.selected else GRAY
                eq_tag = "[E] " if is_equipped else ""
                line = f"{prefix} {eq_tag}{item.name}"
                if label_width > 3 and len(line) > label_width:
                    line = line[:label_width - 3] + "..."
                console.print(x=bx + 2, y=row + j, string=line, fg=color)

        # Cargo column
        cargo = engine.ship.cargo
        col_x = bx + bw // 2
        if not cargo:
            console.print(x=col_x, y=row, string="(empty)", fg=DARK_GRAY)
        else:
            c_start = max(0, min(self.selected - max_visible + 1, len(cargo) - max_visible)) if self._section == _CARGO else 0
            for j in range(min(max_visible, len(cargo) - c_start)):
                i = c_start + j
                item = cargo[i]
                prefix = ">" if self._section == _CARGO and i == self.selected else " "
                color = (255, 255, 255) if self._section == _CARGO and i == self.selected else GRAY
                line = f"{prefix} {item.name}"
                if label_width > 3 and len(line) > label_width:
                    line = line[:label_width - 3] + "..."
                console.print(x=col_x, y=row + j, string=line, fg=color)

        console.print(
            x=bx + 2, y=by + bh - 2,
            string=self._footer_text(),
            fg=DARK_GRAY,
        )

    def _footer_text(self) -> str:
        base = "[LEFT/RIGHT] Switch [ENTER] Transfer"
        if self._section == _PERSONAL:
            base += " [E] Equip"
        return base + " [ESC] Back"

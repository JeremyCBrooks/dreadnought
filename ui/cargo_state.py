"""Cargo management overlay: transfer items between ship cargo and personal loadout."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
        """Return the personal inventory list.

        In strategic mode (between missions), items live in ``_saved_player["inventory"]``.
        During briefing, items live in ``engine.mission_loadout``.  We distinguish
        the two contexts by checking whether ``_saved_player`` has an inventory
        *and* ``mission_loadout`` is empty (briefing resets it to ``[]``).
        """
        sp = getattr(engine, "_saved_player", None)
        if sp and "inventory" in sp and not engine.mission_loadout:
            return sp["inventory"]
        return engine.mission_loadout

    def _ensure_loadout(self, engine: Engine) -> Loadout:
        """Return the Loadout, lazily initializing ``_saved_player`` if needed."""
        from game.loadout import Loadout

        sp = getattr(engine, "_saved_player", None)
        if sp is None:
            engine._saved_player = {
                "hp": 10,
                "max_hp": 10,
                "defense": 0,
                "power": 1,
                "base_power": 1,
                "inventory": [],
                "loadout": Loadout(),
            }
            sp = engine._saved_player
        lo = sp.get("loadout")
        if lo is None:
            lo = Loadout()
            sp["loadout"] = lo
        return lo

    def _combined_personal(self, engine: Engine) -> list[tuple[Entity, bool]]:
        """Return [(item, is_equipped), ...] in stable insertion order."""
        from game.loadout import combined_items

        return combined_items(self._personal_list(engine), self._ensure_loadout(engine))

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

    def ev_key(self, engine: Engine, event: Any) -> bool:
        from ui.keys import cancel_keys, confirm_keys, move_keys

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
        from game.entity import Entity as EntityCls
        from game.loadout import toggle_equip

        if self._section != _PERSONAL:
            return

        combined = self._combined_personal(engine)
        if not combined or self.selected >= len(combined):
            return

        item, _is_equipped = combined[self.selected]

        lo = self._ensure_loadout(engine)
        # Build a proxy entity carrying the saved loadout + inventory
        # so toggle_equip sees the real item list (no fighter → skip melee recalc).
        proxy = EntityCls()
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
                engine.message_log.add_message("The Dreadnought core must stay in cargo.", WARNING)
                return
            if self._personal_count(engine) >= PLAYER_MAX_INVENTORY:
                engine.message_log.add_message("Personal inventory full.", WARNING)
                return
            engine.ship.remove_cargo(item)
            personal.append(item)
        else:
            combined = self._combined_personal(engine)
            if not combined or self.selected >= len(combined):
                return
            item, is_equipped = combined[self.selected]
            if is_equipped:
                self._ensure_loadout(engine).unequip(item)
            personal.remove(item)
            engine.ship.add_cargo(item)

        self._clamp_selected(engine)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_column(
        self,
        console: Any,
        items: list[tuple[Entity, bool]],
        *,
        is_active: bool,
        x: int,
        y: int,
        max_visible: int,
        label_width: int,
    ) -> None:
        """Render a scrollable item column. Each item is (entity, is_equipped)."""
        if not items:
            console.print(x=x, y=y, string="(empty)", fg=DARK_GRAY)
            return
        if is_active:
            # Scroll so the cursor is always visible within the window.
            start = max(0, min(self.selected - max_visible + 1, len(items) - max_visible))
        else:
            start = 0
        for j in range(min(max_visible, len(items) - start)):
            i = start + j
            item, is_equipped = items[i]
            selected = is_active and i == self.selected
            prefix = ">" if selected else " "
            color = (255, 255, 255) if selected else GRAY
            eq_tag = "[E] " if is_equipped else ""
            line = f"{prefix} {eq_tag}{item.name}"
            if label_width > 3 and len(line) > label_width:
                line = line[: label_width - 3] + "..."
            console.print(x=x, y=y + j, string=line, fg=color)

    def on_render(self, console: Any, engine: Engine) -> None:
        from game.entity import PLAYER_MAX_INVENTORY
        from ui.colors import DIALOG_BG, HEADER_TITLE, TAB_SELECTED, TAB_UNSELECTED

        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(65, cw - 10)
        bh = min(30, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        title = "=== CARGO MANAGEMENT ==="
        console.print(x=bx + (bw - len(title)) // 2, y=by + 1, string=title, fg=HEADER_TITLE)

        # Section tabs
        p_color = TAB_SELECTED if self._section == _PERSONAL else TAB_UNSELECTED
        c_color = TAB_SELECTED if self._section == _CARGO else TAB_UNSELECTED
        cap = self._personal_count(engine)
        console.print(x=bx + 2, y=by + 3, string=f"PERSONAL ({cap}/{PLAYER_MAX_INVENTORY})", fg=p_color)
        console.print(x=bx + bw // 2, y=by + 3, string="SHIP CARGO", fg=c_color)

        max_visible = max(0, bh - 8)
        row = by + 5
        label_width = bw // 2 - 4

        # Personal column (combined: equipped + inventory)
        self._render_column(
            console,
            self._combined_personal(engine),
            is_active=self._section == _PERSONAL,
            x=bx + 2,
            y=row,
            max_visible=max_visible,
            label_width=label_width,
        )

        # Cargo column (wrap as (item, False) tuples to match the column interface)
        cargo_items = [(item, False) for item in engine.ship.cargo]
        self._render_column(
            console,
            cargo_items,
            is_active=self._section == _CARGO,
            x=bx + bw // 2,
            y=row,
            max_visible=max_visible,
            label_width=label_width,
        )

        console.print(
            x=bx + 2,
            y=by + bh - 2,
            string=self._footer_text(),
            fg=DARK_GRAY,
        )

    def _footer_text(self) -> str:
        base = "[LEFT/RIGHT] Switch [ENTER] Transfer"
        if self._section == _PERSONAL:
            base += " [E] Equip"
        return base + " [ESC] Back"

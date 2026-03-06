"""Inventory overlay state: two sections (EQUIPPED + INVENTORY)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine

# Sections
_EQUIPPED = 0
_INVENTORY = 1


class InventoryState(State):
    def __init__(self) -> None:
        self.selected = 0
        self._section = _EQUIPPED  # 0=equipped, 1=inventory

    def _equipped_slots(self, engine: Engine) -> list:
        """Return list of (label, item_or_None) tuples for equipped slots."""
        lo = engine.player.loadout
        if not lo:
            return []
        return [
            ("S1", lo.slot1),
            ("S2", lo.slot2),
        ]

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        from ui.keys import move_keys, confirm_keys, cancel_keys

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        direction = move_keys().get(key)
        if direction:
            dx, dy = direction
            if dx < 0:  # left
                if self._section != _EQUIPPED:
                    self._section = _EQUIPPED
                    self.selected = 0
                return True
            if dx > 0:  # right
                if self._section != _INVENTORY:
                    self._section = _INVENTORY
                    self.selected = 0
                return True
            if dy != 0:
                if self._section == _EQUIPPED:
                    return self._handle_equipped_nav(engine, dy)
                else:
                    return self._handle_inventory_nav(engine, dy)
            return True

        if self._section == _EQUIPPED:
            return self._handle_equipped(engine, key)
        else:
            return self._handle_inventory(engine, key)

    def _handle_equipped_nav(self, engine: Engine, dy: int) -> bool:
        slots = self._equipped_slots(engine)
        if not slots:
            return True
        if dy < 0:
            self.selected = max(0, self.selected - 1)
        elif dy > 0:
            self.selected = min(len(slots) - 1, self.selected + 1)
        return True

    def _handle_inventory_nav(self, engine: Engine, dy: int) -> bool:
        inv = engine.player.inventory
        if dy < 0:
            self.selected = max(0, self.selected - 1)
        elif dy > 0 and inv:
            self.selected = min(len(inv) - 1, self.selected + 1)
        return True

    def _handle_equipped(self, engine: Engine, key: Any) -> bool:
        from ui.keys import confirm_keys

        if key in confirm_keys():
            slots = self._equipped_slots(engine)
            if self.selected < len(slots):
                _, item = slots[self.selected]
                if item:
                    self._unequip(engine, item)
            return True

        return True

    def _handle_inventory(self, engine: Engine, key: Any) -> bool:
        from ui.keys import confirm_keys

        if key in confirm_keys():
            inv = engine.player.inventory
            if 0 <= self.selected < len(inv):
                item = inv[self.selected]
                self._use_or_equip(engine, item)
            return True

        return True

    def _unequip(self, engine: Engine, item: Any) -> None:
        """Unequip item from loadout back to inventory."""
        if engine.player.loadout:
            result = engine.player.loadout.unequip(item)
            if result:
                engine.player.inventory.append(result)
                from game.loadout import recalc_melee_power
                recalc_melee_power(engine.player)
                engine.message_log.add_message(
                    f"Unequipped {item.name}.", (200, 200, 200)
                )

    def _use_or_equip(self, engine: Engine, item: Any) -> None:
        """Equip (weapon/tool) or use (consumable) an inventory item."""
        from game.loadout import is_equippable, recalc_melee_power

        if is_equippable(item):
            lo = engine.player.loadout
            if lo and not lo.is_full():
                engine.player.inventory.remove(item)
                lo.equip(item)
                recalc_melee_power(engine.player)
                engine.message_log.add_message(
                    f"Equipped {item.name}.", (100, 255, 100)
                )
            elif lo and lo.is_full():
                engine.message_log.add_message(
                    "Equipment slots full. Unequip something first.", (255, 200, 100)
                )
        else:
            from game.consumables import use_consumable
            use_consumable(engine, engine.player, item)
        self._clamp_selected(engine)

    def _clamp_selected(self, engine: Engine) -> None:
        """Clamp selected index to valid range after changes."""
        if self._section == _EQUIPPED:
            slots = self._equipped_slots(engine)
            self.selected = max(0, min(self.selected, len(slots) - 1))
        else:
            inv = engine.player.inventory
            if inv:
                self.selected = max(0, min(self.selected, len(inv) - 1))
            else:
                self.selected = 0

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(50, cw - 10)
        bh = min(30, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        from ui.colors import DIALOG_BG, TAB_SELECTED, TAB_UNSELECTED
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        # Section tabs
        eq_color = TAB_SELECTED if self._section == _EQUIPPED else TAB_UNSELECTED
        inv_color = TAB_SELECTED if self._section == _INVENTORY else TAB_UNSELECTED
        console.print(x=bx + 2, y=by + 1, string="EQUIPPED", fg=eq_color)
        console.print(x=bx + 12, y=by + 1, string="INVENTORY", fg=inv_color)

        label_width = bw - 4
        max_visible = max(0, bh - 6)
        row = by + 3

        if self._section == _EQUIPPED:
            slots = self._equipped_slots(engine)
            if not slots:
                console.print(x=bx + 2, y=row, string="(no loadout)", fg=(100, 100, 100))
            else:
                for j, (label, item) in enumerate(slots):
                    prefix = ">" if j == self.selected else " "
                    color = (255, 255, 255) if j == self.selected else (150, 150, 150)
                    item_name = item.name if item else "--"
                    use_hint = " [ENTER]" if item else ""
                    line = f"{prefix} {label}: {item_name}{use_hint}"
                    if label_width > 3 and len(line) > label_width:
                        line = line[:label_width - 3] + "..."
                    console.print(x=bx + 2, y=row + j, string=line, fg=color)
        else:
            inv = engine.player.inventory
            if not inv:
                console.print(x=bx + 2, y=row, string="(empty)", fg=(100, 100, 100))
            else:
                start = max(0, min(self.selected - max_visible + 1, len(inv) - max_visible))
                for j in range(min(max_visible, len(inv) - start)):
                    i = start + j
                    item = inv[i]
                    prefix = ">" if i == self.selected else " "
                    color = (255, 255, 255) if i == self.selected else (150, 150, 150)
                    line = f"{prefix} {item.name}"
                    if item.item:
                        line += f" [{item.item.get('type', '?')}]"
                    if label_width > 3 and len(line) > label_width:
                        line = line[:label_width - 3] + "..."
                    console.print(x=bx + 2, y=row + j, string=line, fg=color)

        console.print(
            x=bx + 2, y=by + bh - 2,
            string="[LEFT/RIGHT] Switch [ENTER] Use/Equip [ESC] Close",
            fg=(100, 100, 100),
        )

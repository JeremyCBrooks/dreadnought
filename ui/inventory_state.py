"""Inventory overlay state: single combined list with equipped status."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Tuple

from engine.game_state import State
from ui.colors import DARK_GRAY, GRAY

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity


class InventoryState(State):
    def __init__(self) -> None:
        self.selected = 0

    def _combined_items(self, engine: Engine) -> List[Tuple[Entity, bool]]:
        """Return [(item, is_equipped), ...] in stable insertion order."""
        from game.loadout import combined_items
        return combined_items(engine.player.inventory, engine.player.loadout)

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        from ui.keys import move_keys, cancel_keys, is_action

        key = event.sym

        if key in cancel_keys():
            engine.pop_state()
            return True

        direction = move_keys().get(key)
        if direction:
            _, dy = direction
            if dy != 0:
                combined = self._combined_items(engine)
                if combined:
                    if dy < 0:
                        self.selected = max(0, self.selected - 1)
                    elif dy > 0:
                        self.selected = min(len(combined) - 1, self.selected + 1)
            return True

        if is_action("interact", key):
            self._activate(engine)
            return True

        import tcod.event
        if key == tcod.event.KeySym.d:
            self._drop(engine)
            return True

        return True

    def _activate(self, engine: Engine) -> None:
        """ENTER on selected item: unequip, equip, or use consumable."""
        from game.loadout import is_equippable, toggle_equip

        combined = self._combined_items(engine)
        if not combined or self.selected >= len(combined):
            return

        item, is_equipped = combined[self.selected]

        if is_equipped or is_equippable(item):
            toggle_equip(engine, engine.player, item)
        else:
            from game.consumables import use_consumable
            use_consumable(engine, engine.player, item)

        self._clamp_selected(engine)

    def _in_tactical(self, engine: Engine) -> bool:
        """Return True if the inventory is overlaid on a TacticalState."""
        from ui.tactical_state import TacticalState
        return any(isinstance(s, TacticalState) for s in engine._state_stack)

    def _drop(self, engine: Engine) -> None:
        """Drop the selected item onto the map (tactical state only)."""
        if not self._in_tactical(engine):
            return
        combined = self._combined_items(engine)
        if not combined or self.selected >= len(combined):
            return
        item, _is_equipped = combined[self.selected]
        idx = engine.player.inventory.index(item)
        from game.actions import DropAction
        DropAction(idx).perform(engine, engine.player)
        self._clamp_selected(engine)

    def _clamp_selected(self, engine: Engine) -> None:
        combined = self._combined_items(engine)
        if combined:
            self.selected = max(0, min(self.selected, len(combined) - 1))
        else:
            self.selected = 0

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(55, cw - 10)
        bh = min(30, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        from ui.colors import DIALOG_BG, HEADER_TITLE
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        title = "=== INVENTORY ==="
        console.print(x=bx + (bw - len(title)) // 2, y=by + 1, string=title, fg=HEADER_TITLE)

        label_width = bw - 4
        max_visible = max(0, bh - 6)
        row = by + 3

        combined = self._combined_items(engine)
        if not combined:
            console.print(x=bx + 2, y=row, string="(empty)", fg=DARK_GRAY)
        else:
            start = max(0, min(self.selected - max_visible + 1, len(combined) - max_visible))
            for j in range(min(max_visible, len(combined) - start)):
                i = start + j
                item, is_equipped = combined[i]
                prefix = ">" if i == self.selected else " "
                color = (255, 255, 255) if i == self.selected else GRAY
                eq_tag = "[E] " if is_equipped else ""
                line = f"{prefix} {eq_tag}{item.name}"
                if item.item:
                    line += f" [{item.item.get('type', '?')}]"
                if label_width > 3 and len(line) > label_width:
                    line = line[:label_width - 3] + "..."
                console.print(x=bx + 2, y=row + j, string=line, fg=color)

        console.print(
            x=bx + 2, y=by + bh - 2,
            string="[UP/DOWN] Select [E] Use/Equip [D] Drop [ESC] Close",
            fg=DARK_GRAY,
        )

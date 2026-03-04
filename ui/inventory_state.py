"""Inventory overlay state: two sections (LOADOUT + COLLECTION TANK)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine

# Sections
_LOADOUT = 0
_COLLECTION = 1


class InventoryState(State):
    def __init__(self) -> None:
        self.selected = 0
        self._section = _LOADOUT  # 0=loadout, 1=collection tank

    def _loadout_slots(self, engine: Engine) -> list:
        """Return list of (label, item_or_None, usable) tuples for the loadout."""
        lo = engine.player.loadout
        if not lo:
            return []
        return [
            ("WPN", lo.weapon, False),
            ("TOOL", lo.tool, False),
            ("C1", lo.consumable1, True),
            ("C2", lo.consumable2, True),
        ]

    def ev_keydown(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        key = event.sym

        if key == tcod.event.KeySym.ESCAPE:
            engine.pop_state()
            return True

        if key == tcod.event.KeySym.TAB:
            self._section = 1 - self._section
            self.selected = 0
            return True

        if self._section == _LOADOUT:
            return self._handle_loadout(engine, key)
        else:
            return self._handle_collection(engine, key)

    def _handle_loadout(self, engine: Engine, key: Any) -> bool:
        import tcod.event

        slots = self._loadout_slots(engine)
        if not slots:
            return True

        if key in (tcod.event.KeySym.UP, tcod.event.KeySym.k):
            self.selected = max(0, self.selected - 1)
            return True
        if key in (tcod.event.KeySym.DOWN, tcod.event.KeySym.j):
            self.selected = min(len(slots) - 1, self.selected + 1)
            return True

        if key == tcod.event.KeySym.RETURN:
            if self.selected < len(slots):
                label, item, usable = slots[self.selected]
                if usable and item:
                    self._use_consumable(engine, item)
            return True

        return True

    def _handle_collection(self, engine: Engine, key: Any) -> bool:
        import tcod.event

        tank = engine.player.collection_tank

        if key in (tcod.event.KeySym.UP, tcod.event.KeySym.k):
            self.selected = max(0, self.selected - 1)
            return True
        if key in (tcod.event.KeySym.DOWN, tcod.event.KeySym.j):
            if tank:
                self.selected = min(len(tank) - 1, self.selected + 1)
            return True

        return True

    def _use_consumable(self, engine: Engine, item: Any) -> None:
        """Apply consumable effect and clear slot."""
        itype = item.item.get("type") if item.item else None

        if itype == "heal":
            heal = item.item["value"]
            engine.player.fighter.hp = min(
                engine.player.fighter.max_hp,
                engine.player.fighter.hp + heal,
            )
            engine.message_log.add_message(
                f"Used {item.name}. Healed {heal} HP.", (0, 255, 0)
            )
            engine.player.loadout.use_consumable(item)
            self.selected = max(0, min(self.selected, len(self._loadout_slots(engine)) - 1))

        elif itype == "repair":
            repaired = None
            if engine.player.loadout:
                for other in engine.player.loadout.all_items():
                    if other is not item and other.item and other.item.get("durability") is not None:
                        d = other.item.get("durability", 0)
                        max_d = other.item.get("max_durability", 5)
                        if d < max_d:
                            other.item["durability"] = min(max_d, d + item.item["value"])
                            repaired = other.name
                            break
            if repaired:
                engine.message_log.add_message(
                    f"Used {item.name}. Repaired {repaired}.", (200, 200, 100)
                )
                engine.player.loadout.use_consumable(item)
                self.selected = max(0, min(self.selected, len(self._loadout_slots(engine)) - 1))
            else:
                engine.message_log.add_message(
                    "No damaged items to repair.", (150, 150, 100)
                )

        elif itype == "o2":
            if getattr(engine, "suit", None) and "vacuum" in engine.suit.resistances:
                max_o2 = engine.suit.resistances["vacuum"]
                cur = engine.suit.current_pools.get("vacuum", 0)
                engine.suit.current_pools["vacuum"] = min(max_o2, cur + item.item["value"])
                engine.message_log.add_message(
                    f"Used {item.name}. O2 restored.", (100, 200, 255)
                )
                engine.player.loadout.use_consumable(item)
                self.selected = max(0, min(self.selected, len(self._loadout_slots(engine)) - 1))
            else:
                engine.message_log.add_message("No suit O2 to restore.", (150, 150, 150))

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw = min(50, cw - 10)
        bh = min(30, ch - 10)
        bx = (cw - bw) // 2
        by = (ch - bh) // 2
        console.draw_rect(bx, by, bw, bh, ch=32, bg=(15, 15, 30))

        # Section tabs
        loadout_color = (255, 255, 100) if self._section == _LOADOUT else (100, 100, 120)
        tank_color = (255, 255, 100) if self._section == _COLLECTION else (100, 100, 120)
        console.print(x=bx + 2, y=by + 1, string="LOADOUT", fg=loadout_color)
        console.print(x=bx + 12, y=by + 1, string="COLLECTION TANK", fg=tank_color)

        label_width = bw - 4
        max_visible = max(0, bh - 6)
        row = by + 3

        if self._section == _LOADOUT:
            slots = self._loadout_slots(engine)
            if not slots:
                console.print(x=bx + 2, y=row, string="(no loadout)", fg=(100, 100, 100))
            else:
                for j, (label, item, usable) in enumerate(slots):
                    prefix = ">" if j == self.selected else " "
                    color = (255, 255, 255) if j == self.selected else (150, 150, 150)
                    item_name = item.name if item else "--"
                    use_hint = " [ENTER]" if usable and item else ""
                    line = f"{prefix} {label}: {item_name}{use_hint}"
                    if len(line) > label_width:
                        line = line[:label_width - 3] + "..."
                    console.print(x=bx + 2, y=row + j, string=line, fg=color)
        else:
            tank = engine.player.collection_tank
            if not tank:
                console.print(x=bx + 2, y=row, string="(empty)", fg=(100, 100, 100))
            else:
                start = max(0, min(self.selected - max_visible + 1, len(tank) - max_visible))
                for j in range(min(max_visible, len(tank) - start)):
                    i = start + j
                    item = tank[i]
                    prefix = ">" if i == self.selected else " "
                    color = (255, 255, 255) if i == self.selected else (150, 150, 150)
                    line = f"{prefix} {item.name}"
                    if item.item:
                        line += f" [{item.item.get('type', '?')}]"
                    if len(line) > label_width:
                        line = line[:label_width - 3] + "..."
                    console.print(x=bx + 2, y=row + j, string=line, fg=color)

        console.print(
            x=bx + 2, y=by + bh - 2,
            string="[TAB] Switch [ENTER] Use [ESC] Close",
            fg=(100, 100, 100),
        )

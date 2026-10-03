"""Trade overlay: barter with a Trader Bot, selling what you carry for credit and spending it on its stock."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from data.colors import DARK_GRAY, DIALOG_BG, GRAY, HEADER_TEXT, HEADER_TITLE, INTERACT_LOOT, WARNING, WHITE
from engine.game_state import State

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity

_COLUMNS = ("sell", "buy")


def _value(name: str) -> int:
    from data.items import TRADE_VALUES

    return TRADE_VALUES.get(name, 1)


class TradeState(State):
    """Two lists: your pack on the left (sell), the trader's stock on the right (buy).

    Credit lives on the trader, so it is still there when you come back.
    """

    def __init__(self, trader: Entity) -> None:
        self.trader = trader
        self.column = "sell"
        self.selected = {"sell": 0, "buy": 0}

    # ---- the deal itself ----

    @property
    def credit(self) -> int:
        return self.trader.ai_config.get("credit", 0)

    @property
    def stock(self) -> list[str]:
        return self.trader.ai_config.get("stock", [])

    def sell(self, engine: Engine, index: int) -> None:
        """Hand over the item at *index* of the player's pack for its trade value in credit."""
        player = engine.player
        if not 0 <= index < len(player.inventory):
            return
        item = player.inventory[index]
        if player.loadout and player.loadout.has_item(item):
            from game.loadout import recalc_melee_power

            player.loadout.unequip(item)
            recalc_melee_power(player)
        player.inventory.remove(item)
        value = _value(item.name)
        self.trader.ai_config["credit"] = self.credit + value
        engine.message_log.add_message(f"Sold the {item.name} for {value} credit.", INTERACT_LOOT)

    def buy(self, engine: Engine, index: int) -> None:
        """Take the stock item at *index* if the player's credit covers it and their pack has room."""
        if not 0 <= index < len(self.stock):
            return
        name = self.stock[index]
        price = _value(name)
        if price > self.credit:
            engine.message_log.add_message(f"Not enough credit for the {name} ({price} needed).", WARNING)
            return
        if not engine.player.can_carry():
            engine.message_log.add_message("Inventory full.", WARNING)
            return
        from data.items import item_definition
        from game.factories import build_item_entity

        engine.player.inventory.append(build_item_entity(item_definition(name)))
        self.trader.ai_config["credit"] = self.credit - price
        engine.message_log.add_message(f"Bought a {name} for {price} credit.", INTERACT_LOOT)

    # ---- input ----

    def _rows(self, engine: Engine) -> list[str]:
        return [item.name for item in engine.player.inventory] if self.column == "sell" else self.stock

    def ev_key(self, engine: Engine, event: Any) -> bool:
        import tcod.event

        from engine.keys import cancel_keys, confirm_keys, is_action, move_keys

        key = event.sym
        if key in cancel_keys():
            engine.pop_state()
            return True
        if key == tcod.event.KeySym.TAB:
            self.column = _COLUMNS[1 - _COLUMNS.index(self.column)]
            return True
        direction = move_keys().get(key)
        if direction and direction[1]:
            rows = self._rows(engine)
            self.selected[self.column] = max(0, min(len(rows) - 1, self.selected[self.column] + direction[1]))
            return True
        if key in confirm_keys() or is_action("interact", key):
            if self.column == "sell":
                self.sell(engine, self.selected["sell"])
                self.selected["sell"] = max(0, min(self.selected["sell"], len(engine.player.inventory) - 1))
            else:
                self.buy(engine, self.selected["buy"])
            return True
        return True

    # ---- drawing ----

    def on_render(self, console: Any, engine: Engine) -> None:
        cw, ch = engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT
        bw, bh = min(70, cw - 10), min(26, ch - 10)
        bx, by = (cw - bw) // 2, (ch - bh) // 2
        console.draw_rect(bx, by, bw, bh, ch=32, bg=DIALOG_BG)

        title = f"=== TRADING WITH THE {self.trader.name.upper()} ==="
        console.print(x=bx + (bw - len(title)) // 2, y=by + 1, string=title, fg=HEADER_TITLE)
        console.print(x=bx + 2, y=by + 3, string=f"Credit: {self.credit}", fg=INTERACT_LOOT)

        col_w = (bw - 6) // 2
        columns = (
            ("YOUR PACK (sell)", "sell", [(item.name, _value(item.name)) for item in engine.player.inventory]),
            ("STOCK (buy)", "buy", [(name, _value(name)) for name in self.stock]),
        )
        for c, (heading, column, rows) in enumerate(columns):
            x = bx + 2 + c * (col_w + 2)
            active = column == self.column
            console.print(x=x, y=by + 5, string=heading, fg=HEADER_TEXT if active else DARK_GRAY)
            if not rows:
                console.print(x=x, y=by + 7, string="(nothing)", fg=DARK_GRAY)
            for i, (name, value) in enumerate(rows[: bh - 10]):
                chosen = active and i == self.selected[column]
                affordable = column == "sell" or value <= self.credit
                color = WHITE if chosen else (GRAY if affordable else DARK_GRAY)
                line = f"{'>' if chosen else ' '} {name}"[: col_w - 5]
                console.print(x=x, y=by + 7 + i, string=line, fg=color)
                console.print(x=x + col_w - 3, y=by + 7 + i, string=f"{value:>2}", fg=color)

        console.print(
            x=bx + 2,
            y=by + bh - 2,
            string="[TAB] Switch  [UP/DOWN] Select  [ENTER] Sell/Buy  [ESC] Done",
            fg=DARK_GRAY,
        )

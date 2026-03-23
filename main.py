"""Dreadnought roguelike -- entry point."""

from engine.game_state import Engine
from ui.title_state import TitleState


def main() -> None:
    engine = Engine()
    engine.push_state(TitleState())
    engine.run()


if __name__ == "__main__":
    main()

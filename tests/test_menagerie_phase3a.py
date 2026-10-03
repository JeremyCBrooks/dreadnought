"""The Dreadnought's own guardians, and creatures you can deal with: Medic Drone, Hermit, Trader Bot."""

from __future__ import annotations

import random
from types import SimpleNamespace

import numpy as np
import pytest

from data.enemies import COMMUNITIES, DREADNOUGHT, enemy_by_name
from data.items import ITEMS, SALVAGE_ITEMS, SCANNERS, TRADE_VALUES, item_definition
from game.actions import InteractAction, MeleeAction
from game.entity import Entity, Fighter
from game.factories import build_enemy, build_item_entity
from tests.conftest import MockEngine, make_arena

# ---------------------------------------------------------------------------
# Dreadnought guardians
# ---------------------------------------------------------------------------


class TestDreadnoughtGuardians:
    def _guardians(self):
        (guardians,) = COMMUNITIES[DREADNOUGHT]
        return guardians

    def test_guard_the_dreadnought(self):
        guardians = self._guardians()
        assert {"Reactor Wisp", "Warden", "Sentry Turret"} <= set(guardians.members)
        assert not guardians.peaceful
        assert guardians.report.strip()

    def test_are_who_the_dreadnought_holds(self):
        from game.creatures import community_of

        location = SimpleNamespace(name="Dreadnought", loc_type="derelict", is_dreadnought=True)
        assert community_of(location) == self._guardians()

    def test_spawn_aboard_it(self):
        from world.dungeon_gen import generate_dungeon

        members = set(self._guardians().members)
        for seed in range(1, 11):
            game_map, _, _ = generate_dungeon(
                seed=seed, loc_type="derelict", depth=8, max_enemies=3, community="Dreadnought guardians"
            )
            species = {e.ai_config.get("species") for e in game_map.entities if e.ai}
            assert species and species <= members

    def test_community_names_are_unique(self):
        names = [c.name for communities in COMMUNITIES.values() for c in communities]
        assert len(names) == len(set(names))


class TestReactorWisp:
    def test_is_born_of_the_reactor(self):
        wisp = enemy_by_name("Reactor Wisp")
        assert {"radiation", "electric"} <= set(wisp.hazard_immunities)
        assert wisp.death_effect.hazard == "radiation"
        assert wisp.light is not None


# ---------------------------------------------------------------------------
# Creatures you deal with
# ---------------------------------------------------------------------------


def _arena(player_at=(2, 2), hp: int = 20, max_hp: int = 20):
    gm = make_arena(24, 16)
    gm.visible[:] = True
    gm.explored[:] = True
    player = Entity(x=player_at[0], y=player_at[1], name="Player", fighter=Fighter(hp, max_hp, 0, 1))
    player.inventory = []
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.pushed = []
    engine.push_state = engine.pushed.append
    return engine, player


def _spawn(engine, species: str, x: int, y: int) -> Entity:
    creature = build_enemy(enemy_by_name(species), x, y, random.Random(0))
    engine.game_map.entities.append(creature)
    return creature


def _messages(engine) -> str:
    return " ".join(text for text, *_ in engine.message_log.messages)


def _members(loc_type: str, community: str) -> tuple[str, ...]:
    return next(c for c in COMMUNITIES[loc_type] if c.name == community).members


class TestServicesInGeneral:
    @pytest.mark.parametrize("species", ["Medic Drone", "Hermit", "Trader Bot"])
    def test_look_mode_offers_to_interact(self, species):
        engine, _ = _arena()
        _spawn(engine, species, 6, 6)
        text = " ".join(line for line, _ in engine.game_map.describe_at(6, 6))
        assert f"{species} (" in text and "[e]" in text

    @pytest.mark.parametrize("species", ["Medic Drone", "Hermit", "Trader Bot"])
    def test_listed_as_harmless_company(self, species):
        from game.scanner import build_nearby_entries

        engine, _ = _arena()
        _spawn(engine, species, 6, 6)
        (entry,) = [e for e in build_nearby_entries(engine) if (e.x, e.y) == (6, 6)]
        assert entry.category == "neutral"

    def test_a_creature_you_have_hurt_will_not_deal_with_you(self):
        engine, player = _arena(hp=5)
        medic = _spawn(engine, "Medic Drone", 3, 2)
        medic.fighter.hp = medic.fighter.max_hp = 30
        MeleeAction(medic).perform(engine, player)
        InteractAction(1, 0).perform(engine, player)
        assert player.fighter.hp == 5
        assert "won't" in _messages(engine)


class TestMedicDrone:
    def test_tends_peaceful_places(self):
        assert "Medic Drone" in _members("colony", "Holdouts")

    def test_patches_you_up(self):
        engine, player = _arena(hp=5)
        _spawn(engine, "Medic Drone", 3, 2)
        InteractAction(1, 0).perform(engine, player)
        assert player.fighter.hp > 5

    def test_supplies_run_out(self):
        engine, player = _arena(hp=1, max_hp=200)
        medic = _spawn(engine, "Medic Drone", 3, 2)
        for _ in range(10):
            InteractAction(1, 0).perform(engine, player)
        healed = player.fighter.hp
        InteractAction(1, 0).perform(engine, player)
        assert player.fighter.hp == healed
        assert medic.ai_config["charges"] == 0

    def test_does_not_waste_supplies_on_the_healthy(self):
        engine, player = _arena(hp=20)
        medic = _spawn(engine, "Medic Drone", 3, 2)
        charges = medic.ai_config["charges"]
        InteractAction(1, 0).perform(engine, player)
        assert medic.ai_config["charges"] == charges


class TestHermit:
    def test_lives_on_quiet_rocks(self):
        assert "Hermit" in _members("asteroid", "Quiet rock")
        assert enemy_by_name("Hermit").char == "@"

    def test_points_you_to_a_navigation_unit(self):
        from world.galaxy import Galaxy

        engine, player = _arena()
        engine.galaxy = Galaxy(seed=3)
        _spawn(engine, "Hermit", 3, 2)
        InteractAction(1, 0).perform(engine, player)
        targets = [
            loc.name
            for system in engine.galaxy.systems.values()
            for loc in system.locations
            if loc.has_nav_unit and not loc.visited
        ]
        assert targets
        assert any(name in _messages(engine) for name in targets)

    def test_has_nothing_to_tell_once_every_unit_is_found(self):
        from world.galaxy import Galaxy

        engine, player = _arena()
        engine.galaxy = Galaxy(seed=3)
        for system in engine.galaxy.systems.values():
            for loc in system.locations:
                loc.visited = True
        _spawn(engine, "Hermit", 3, 2)
        InteractAction(1, 0).perform(engine, player)
        assert "Hermit" in _messages(engine)


class TestTradeData:
    def test_every_tradeable_item_has_a_value(self):
        for definition in [*ITEMS, *SCANNERS, *SALVAGE_ITEMS]:
            assert TRADE_VALUES.get(definition.name, 0) > 0, definition.name

    def test_the_trader_stocks_real_goods(self):
        stock = enemy_by_name("Trader Bot").stock
        assert stock
        for name in stock:
            assert item_definition(name)


class TestTraderBot:
    def _shop(self, *carried: str):
        engine, player = _arena()
        trader = _spawn(engine, "Trader Bot", 3, 2)
        for name in carried:
            player.inventory.append(build_item_entity(item_definition(name)))
        InteractAction(1, 0).perform(engine, player)
        from ui.screens import open_requested_screen

        open_requested_screen(engine)
        (shop,) = engine.pushed
        return engine, player, trader, shop

    def test_runs_the_station_shop(self):
        assert "Trader Bot" in _members("starbase", "Skeleton crew")

    def test_interacting_opens_the_trade_screen(self):
        from ui.trade_state import TradeState

        _, _, _, shop = self._shop()
        assert isinstance(shop, TradeState)

    def test_selling_earns_credit(self):
        engine, player, trader, shop = self._shop("Shotgun")
        shop.sell(engine, 0)
        assert player.inventory == []
        assert trader.ai_config["credit"] == TRADE_VALUES["Shotgun"]

    def test_buying_spends_credit(self):
        engine, player, trader, shop = self._shop("Shotgun")
        shop.sell(engine, 0)
        name = next(n for n in trader.ai_config["stock"] if TRADE_VALUES[n] <= TRADE_VALUES["Shotgun"])
        shop.buy(engine, trader.ai_config["stock"].index(name))
        assert [i.name for i in player.inventory] == [name]
        assert trader.ai_config["credit"] == TRADE_VALUES["Shotgun"] - TRADE_VALUES[name]

    def test_no_credit_no_sale(self):
        engine, player, trader, shop = self._shop()
        shop.buy(engine, 0)
        assert player.inventory == []
        assert "credit" in _messages(engine).lower()

    def test_a_full_pack_cannot_take_more(self):
        engine, player, trader, shop = self._shop("Shotgun")
        shop.sell(engine, 0)
        player.max_inventory = 0
        shop.buy(engine, 0)
        assert player.inventory == []

    def test_selling_your_equipped_weapon_unequips_it(self):
        from game.loadout import Loadout

        engine, player, trader, shop = self._shop("Shotgun")
        shotgun = player.inventory[0]
        player.loadout = Loadout()
        player.loadout.equip(shotgun)
        shop.sell(engine, 0)
        assert shotgun not in player.inventory
        assert not player.loadout.has_item(shotgun)

    def test_the_screen_renders(self):
        engine, player, trader, shop = self._shop("Med-kit")
        engine.CONSOLE_WIDTH, engine.CONSOLE_HEIGHT = 160, 50
        printed = []
        console = SimpleNamespace(rgb=np.zeros((160, 50), dtype=[("ch", np.int32), ("fg", "3u1"), ("bg", "3u1")]))
        console.print = lambda *, x, y, string, fg=(255, 255, 255): printed.append(string)
        console.draw_rect = lambda *a, **kw: None
        shop.on_render(console, engine)
        text = " ".join(printed)
        assert "Med-kit" in text and "credit" in text.lower()


def test_pressing_interact_beside_a_trader_in_a_mission_opens_the_shop():
    from engine.keys import action_keys
    from tests.conftest import FakeEvent, enter_mission, key_for, new_game
    from ui.trade_state import TradeState

    engine, _ = new_game(1)
    enter_mission(engine, "starbase")
    player = engine.player
    spot = next(
        (player.x + dx, player.y + dy)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if engine.game_map.is_walkable(player.x + dx, player.y + dy)
        and not engine.game_map.get_blocking_entity(player.x + dx, player.y + dy)
    )
    trader = build_enemy(enemy_by_name("Trader Bot"), *spot, random.Random(0))
    engine.game_map.entities.append(trader)
    engine.game_map.invalidate_entity_index()
    interact_key = next(iter(action_keys()["interact"][0]))
    engine.current_state.ev_key(engine, FakeEvent(interact_key))
    if not isinstance(engine.current_state, TradeState):
        engine.current_state.ev_key(engine, FakeEvent(key_for((spot[0] - player.x, spot[1] - player.y))))
    assert isinstance(engine.current_state, TradeState)

"""Tests for hazard triggering and DoT effects."""

from engine.game_state import Engine
from game.entity import Entity
from game.hazards import apply_dot_effects, trigger_hazard
from game.suit import Suit
from tests.conftest import make_engine as _make_engine


def test_electric_hazard_deals_damage():
    engine = _make_engine()
    hazard = {"type": "electric", "damage": 3, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Console")
    assert engine.player.fighter.hp == 7


def test_radiation_hazard_sets_dot_effect():
    engine = _make_engine()
    hazard = {"type": "radiation", "damage": 1, "equipment_damage": False, "dot": 1, "duration": 3}
    trigger_hazard(engine, hazard, "Console")
    assert len(engine.active_effects) == 1
    eff = engine.active_effects[0]
    assert eff["type"] == "radiation"
    assert eff["dot"] == 1
    assert eff["remaining"] == 3
    assert engine.player.fighter.hp == 9


def test_explosive_hazard_deals_damage():
    engine = _make_engine()
    hazard = {"type": "explosive", "damage": 4, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Crate")
    assert engine.player.fighter.hp == 6


def test_gas_hazard_drains_o2():
    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    hazard = {"type": "gas", "damage": 1, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Vent")
    assert engine.suit.current_pools["vacuum"] == 45
    assert engine.player.fighter.hp == 9


def test_structural_hazard_deals_damage():
    engine = _make_engine()
    hazard = {"type": "structural", "damage": 2, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Beam")
    assert engine.player.fighter.hp == 8


def test_dot_tick_countdown():
    engine = _make_engine()
    engine.active_effects = [{"type": "radiation", "dot": 1, "remaining": 3}]
    apply_dot_effects(engine)
    assert len(engine.active_effects) == 1
    assert engine.active_effects[0]["remaining"] == 2
    assert engine.player.fighter.hp == 9
    apply_dot_effects(engine)
    assert engine.active_effects[0]["remaining"] == 1
    assert engine.player.fighter.hp == 8
    apply_dot_effects(engine)
    assert len(engine.active_effects) == 0
    assert engine.player.fighter.hp == 7
    # No more damage once effects are gone
    apply_dot_effects(engine)
    assert engine.player.fighter.hp == 7


def test_dot_tick_no_player():
    engine = Engine()
    engine.active_effects = [{"type": "radiation", "dot": 1, "remaining": 3}]
    # Should not raise
    apply_dot_effects(engine)
    # Effect unchanged when no player
    assert len(engine.active_effects) == 1
    assert engine.active_effects[0]["remaining"] == 3


def test_dot_from_data():
    """Trigger a hazard with custom dot/duration, verify effect is added and ticks down."""
    engine = _make_engine()
    hazard = {"type": "gas", "damage": 2, "equipment_damage": False, "dot": 3, "duration": 2}
    trigger_hazard(engine, hazard, "Toxic Vent")
    assert len(engine.active_effects) == 1
    eff = engine.active_effects[0]
    assert eff["type"] == "gas"
    assert eff["dot"] == 3
    assert eff["remaining"] == 2
    # Tick once: 3 dot damage, remaining 1
    apply_dot_effects(engine)
    assert engine.player.fighter.hp == 10 - 2 - 3  # instant + 1 tick
    assert engine.active_effects[0]["remaining"] == 1
    # Tick again: 3 more dot damage, effect removed
    apply_dot_effects(engine)
    assert engine.player.fighter.hp == 10 - 2 - 3 - 3
    assert len(engine.active_effects) == 0


def test_no_dot_when_zero():
    """Trigger a hazard with dot: 0 — no effect should be added."""
    engine = _make_engine()
    hazard = {"type": "electric", "damage": 2, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Console")
    assert len(engine.active_effects) == 0


def test_infinite_duration():
    """Trigger with duration: -1, verify effect persists after multiple ticks."""
    engine = _make_engine()
    hazard = {"type": "radiation", "damage": 0, "equipment_damage": False, "dot": 1, "duration": -1}
    trigger_hazard(engine, hazard, "Reactor")
    assert len(engine.active_effects) == 1
    assert engine.active_effects[0]["remaining"] == -1
    # Tick several times — effect should persist
    for i in range(5):
        apply_dot_effects(engine)
    assert len(engine.active_effects) == 1
    assert engine.active_effects[0]["remaining"] == -1
    assert engine.player.fighter.hp == 10 - 5  # 1 dot * 5 ticks


def test_dot_duration_zero_not_added():
    engine = _make_engine()
    hazard = {"type": "radiation", "damage": 1, "dot": 2, "duration": 0}
    trigger_hazard(engine, hazard, "Reactor")
    assert len(engine.active_effects) == 0


def test_dot_duration_positive_still_works():
    engine = _make_engine()
    hazard = {"type": "radiation", "damage": 1, "dot": 1, "duration": 2}
    trigger_hazard(engine, hazard, "Reactor")
    assert len(engine.active_effects) == 1
    assert engine.active_effects[0]["remaining"] == 2


def test_dot_effects_no_fighter_no_crash():
    """apply_dot_effects should not crash if player has no fighter."""
    from tests.conftest import MockEngine, make_arena

    gm = make_arena()
    player = Entity(x=5, y=5, name="Player")  # no fighter
    gm.entities.append(player)
    engine = MockEngine(gm, player)
    engine.active_effects = [{"type": "electric", "dot": 1, "remaining": 2}]

    # Should not raise
    apply_dot_effects(engine)


def test_hazard_by_type_lookup():
    """HAZARD_BY_TYPE provides O(1) lookup keyed by hazard type string."""
    from data.hazards import HAZARD_BY_TYPE, HAZARDS

    assert isinstance(HAZARD_BY_TYPE, dict)
    assert len(HAZARD_BY_TYPE) == len(HAZARDS)
    for h in HAZARDS:
        assert HAZARD_BY_TYPE[h.type] is h


def test_unknown_hazard_type_does_not_say_structural():
    """An unknown hazard type must NOT produce 'Structural collapse' message."""
    engine = _make_engine()
    hazard = {"type": "unknown_type", "damage": 1, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Widget")
    msgs = [text for text, _color in engine.message_log.messages]
    assert len(msgs) == 1
    assert "Structural" not in msgs[0]
    assert "Widget" in msgs[0]


def test_all_hazard_types_produce_messages():
    """Every defined hazard type produces a message when triggered."""
    from dataclasses import asdict

    from data.hazards import HAZARDS

    for hdef in HAZARDS:
        engine = _make_engine()
        hazard = asdict(hdef)
        trigger_hazard(engine, hazard, "TestSource")
        msgs = [text for text, _color in engine.message_log.messages]
        assert len(msgs) >= 1, f"No message for hazard type '{hdef.type}'"
        assert "TestSource" in msgs[0], f"Source name missing for '{hdef.type}'"


def test_equipment_damage_inventory_fallback():
    """When player has no loadout, equipment damage falls back to inventory items."""
    from game.hazards import _apply_equipment_damage
    from tests.conftest import force_rng

    engine = _make_engine()
    engine.player.loadout = None
    weapon = Entity(name="Pistol", item={"type": "weapon", "durability": 2, "max_durability": 5})
    engine.player.inventory.append(weapon)

    force_rng(engine, 0.1)

    _apply_equipment_damage(engine, engine.player)
    assert weapon.item["durability"] == 1


def test_equipment_damage_inventory_fallback_skips_zero_durability():
    """Inventory fallback skips items with durability <= 0."""
    from game.hazards import _apply_equipment_damage
    from tests.conftest import force_rng

    engine = _make_engine()
    engine.player.loadout = None
    broken = Entity(name="Broken", item={"type": "weapon", "durability": 0, "max_durability": 5})
    engine.player.inventory.append(broken)

    force_rng(engine, 0.1)

    _apply_equipment_damage(engine, engine.player)
    assert broken.item["durability"] == 0  # unchanged — no candidates


def test_equipment_damage_is_data_driven():
    """Any hazard type with equipment_damage=True should trigger equipment damage, not just electric."""
    from tests.conftest import force_rng

    engine = _make_engine()
    weapon = Entity(name="Rifle", item={"type": "weapon", "durability": 3, "max_durability": 5})
    engine.player.inventory.append(weapon)
    from game.loadout import Loadout

    engine.player.loadout = Loadout(slot1=weapon)

    force_rng(engine, 0.1)

    # A non-electric hazard with equipment_damage=True should still damage equipment
    hazard = {"type": "explosive", "damage": 2, "equipment_damage": True, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Crate")
    assert weapon.item["durability"] == 2


def test_god_mode_prevents_trigger_hazard_damage():
    """GOD_MODE should prevent HP damage from trigger_hazard, like all other damage sources."""
    import debug

    engine = _make_engine()
    hp_before = engine.player.fighter.hp
    debug.GOD_MODE = True
    hazard = {"type": "electric", "damage": 5, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Console")
    assert engine.player.fighter.hp == hp_before


def test_gas_o2_drain_respects_disable_oxygen():
    """DISABLE_OXYGEN should prevent gas hazard from draining suit O2."""
    import debug

    engine = _make_engine()
    engine.suit = Suit("Test", {"vacuum": 50}, defense_bonus=0)
    debug.DISABLE_OXYGEN = True
    hazard = {"type": "gas", "damage": 1, "equipment_damage": False, "dot": 0, "duration": 0}
    trigger_hazard(engine, hazard, "Vent")
    assert engine.suit.current_pools["vacuum"] == 50

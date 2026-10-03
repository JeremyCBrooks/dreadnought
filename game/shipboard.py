"""Life aboard the player's ship, and life that moves into the places they leave behind.

Vermin can stow away in the cargo when the player leaves a mission, and get
up to mischief between jumps (see each creature's ``stowaway``). A friendly
companion at the player's heels may come aboard as crew and hunt them. Wrecks
left alone are settled, in time, by one of the wreck communities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from data.colors import INTERACT_SAFE, NEUTRAL, WARNING

if TYPE_CHECKING:
    from engine.game_state import Engine
    from game.entity import Entity
    from world.game_map import GameMap

# How close a companion must be when the player leaves to follow them aboard.
_FOLLOW_ABOARD = 2
# Chance per jump that an unsettled wreck gets settlers.
WRECK_SETTLE_CHANCE = 0.3
# Cargo vermin will eat: supplies, never mission items.
_EDIBLE = frozenset({"heal", "o2"})


def _living(game_map: GameMap) -> list[Entity]:
    return [e for e in game_map.entities if e.ai is not None and e.fighter and e.fighter.hp > 0]


# ---- Leaving a mission ----


def take_on_stowaways(engine: Engine, game_map: GameMap, rng: Any) -> None:
    """Let at most one of the vermin left alive here slip into the cargo hold."""
    if engine.ship is None:
        return
    for creature in _living(game_map):
        stowaway = creature.ai_config.get("stowaway")
        if stowaway and rng.random() < stowaway["chance"]:
            engine.ship.stowaways.append(creature.ai_config["species"])
            engine.message_log.add_message("Something scrabbles into the cargo hold behind you.", WARNING)
            return


def adopt_companions(engine: Engine, game_map: GameMap) -> None:
    """A friendly companion at the player's heels follows them aboard, unless one already has."""
    from game.creatures import temperament_of
    from game.helpers import chebyshev

    if engine.ship is None or engine.player is None:
        return
    player = engine.player
    for creature in _living(game_map):
        cfg = creature.ai_config
        if not cfg.get("adoptable") or cfg.get("wronged") or temperament_of(creature).on_sight != "follow":
            continue
        if chebyshev(creature.x, creature.y, player.x, player.y) > _FOLLOW_ABOARD:
            continue
        if cfg["species"] in engine.ship.crew:
            continue
        engine.ship.crew.append(cfg["species"])
        game_map.entities.remove(creature)
        game_map.invalidate_entity_index()
        engine.message_log.add_message(
            f"The {creature.name} follows you aboard. It has decided you are its crew.", INTERACT_SAFE
        )


# ---- Between jumps ----


def life_between_jumps(engine: Engine, rng: Any) -> int:
    """Crew hunt stowaways, then the rest get up to mischief. Returns the hull damage done."""
    from data.enemies import enemy_by_name

    ship = engine.ship
    if ship is None or not ship.stowaways:
        return 0
    for hunter in ship.crew:
        prey = next((s for s in ship.stowaways if s in enemy_by_name(hunter).hunts), None)
        if prey is not None:
            ship.stowaways.remove(prey)
            engine.message_log.add_message(f"Your {hunter} catches a {prey} in the cargo hold.", INTERACT_SAFE)
    hull_damage = 0
    for species in ship.stowaways:
        mischief = enemy_by_name(species).stowaway.mischief
        if mischief == "chew_hull":
            hull_damage += 1
        elif mischief == "eat_cargo":
            _eat_supplies(engine, species, rng)
    return hull_damage


def _eat_supplies(engine: Engine, species: str, rng: Any) -> None:
    food = [item for item in engine.ship.cargo if item.item and item.item.get("type") in _EDIBLE]
    if not food:
        return
    meal = rng.choice(food)
    engine.ship.cargo.remove(meal)
    engine.message_log.add_message(f"{species}s have been at the stores: a {meal.name} is gone.", WARNING)


# ---- Aboard ----


def welcome_aboard(engine: Engine, game_map: GameMap) -> None:
    """Put stowaways in the cargo hold and the crew at the player's side as they come aboard."""
    from data.enemies import enemy_by_name
    from game.creatures import start_hunting
    from game.factories import build_enemy

    ship = engine.ship
    if ship is None:
        return
    rng = engine.rng("welcome_aboard")
    hold = next((r for r in (ship.rooms or []) if r.label == "cargo"), None)
    for species in ship.stowaways:
        spot = _free_spot(game_map, hold.center if hold else ship.exit_pos, rng)
        if spot is None:
            continue
        creature = build_enemy(enemy_by_name(species), *spot, rng)
        creature.ai_config["aboard"] = "stowaway"
        game_map.entities.append(creature)
        if engine.player is not None:
            start_hunting(engine, creature)
    ship.stowaways = []
    for species in ship.crew:
        anchor = (engine.player.x, engine.player.y) if engine.player else ship.exit_pos
        spot = _free_spot(game_map, anchor, rng)
        if spot is None:
            continue
        companion = build_enemy(enemy_by_name(species), *spot, rng)
        companion.ai_config["aboard"] = "crew"
        game_map.entities.append(companion)
    game_map.invalidate_entity_index()


def settle_ship_life(engine: Engine, game_map: GameMap) -> None:
    """As the player leaves the ship, surviving stowaways go back into hiding; the crew stays aboard."""
    if engine.ship is None:
        return
    for creature in [e for e in game_map.entities if e.ai is not None and e.ai_config.get("aboard")]:
        if creature.ai_config["aboard"] == "stowaway" and creature.fighter and creature.fighter.hp > 0:
            engine.ship.stowaways.append(creature.ai_config["species"])
        game_map.entities.remove(creature)
    game_map.invalidate_entity_index()


def _free_spot(game_map: GameMap, near: tuple[int, int] | None, rng: Any) -> tuple[int, int] | None:
    """A free floor tile as close to *near* as can be found."""
    if near is None:
        return None
    nx, ny = near
    for radius in range(1, 6):
        ring = [
            (nx + dx, ny + dy)
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
            if max(abs(dx), abs(dy)) == radius
        ]
        rng.shuffle(ring)
        for x, y in ring:
            if game_map.is_walkable(x, y) and not game_map.get_blocking_entity(x, y):
                return x, y
    return None


# ---- Wrecks ----


def colonise_wrecks(galaxy: Any, rng: Any, chance: float = WRECK_SETTLE_CHANCE) -> None:
    """Each unsettled wreck in the galaxy may be moved into by one of the wreck communities."""
    from data.enemies import pick_community
    from data.names import WRECK_LOC_TYPE

    for system in galaxy.systems.values():
        for location in system.locations:
            record = getattr(location, "wreck", None)
            if record is None or record.community or rng.random() >= chance:
                continue
            record.community = pick_community(WRECK_LOC_TYPE, rng).name


def report_settlement(engine: Engine, location: Any) -> None:
    """Note in the log that a wreck the player is entering has been settled."""
    record = getattr(location, "wreck", None)
    if record is not None and record.community:
        engine.message_log.add_message(f"Something has moved into {location.name}.", NEUTRAL)

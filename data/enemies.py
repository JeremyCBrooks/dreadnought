"""Creature definitions: the galaxy's menagerie, from boarding pirates to ship's cats.

Everything a creature is and does lives here as data. Where it is found
(``habitats``, ``min_depth``, ``spawn_weight``, ``group``), how it treats the
player (``temperament``) and any special trait (a built-in weapon, an
immunity, a death throe, a glow, a disguise, chores it keeps doing) are
fields; the AI and spawners only interpret them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

# Pseudo-habitat: the crews of pirate boarding craft.
BOARDING = "boarding"

# Upkeep a creature may keep doing while it wanders (see game.creatures).
CHORES: frozenset[str] = frozenset({"close_doors", "seal_breaches"})

_AI_CONFIG_KEYS: tuple[str, ...] = (
    "ai_initial_state",
    "aggro_distance",
    "sleep_aggro_distance",
    "can_open_doors",
    "flee_threshold",
    "memory_turns",
    "vision_radius",
    "move_speed",
    "can_steal",
    "temperament",
)

_ORGANIC_RED = (140, 20, 20)
_MACHINE_OIL = (50, 50, 60)
_INSECT_GREEN = (90, 140, 40)


@dataclass(frozen=True, slots=True)
class Temperament:
    """How a creature treats the player.

    on_sight: what it does on noticing the player ("hunt", "flee", "follow", or nothing).
    attacks: whether it ever fights (cornered or provoked).
    when_hurt: the temperament it takes on once the player hurts it.
    """

    on_sight: Literal["hunt", "flee", "follow"] | None
    attacks: bool
    when_hurt: str | None = None

    @property
    def attacks_on_sight(self) -> bool:
        return self.on_sight == "hunt"


TEMPERAMENTS: dict[str, Temperament] = {
    "hostile": Temperament(on_sight="hunt", attacks=True),
    # Minds its own business; strike it and it fights to the end.
    "territorial": Temperament(on_sight=None, attacks=True, when_hurt="hostile"),
    "skittish": Temperament(on_sight="flee", attacks=False),
    "docile": Temperament(on_sight=None, attacks=False, when_hurt="skittish"),
    "friendly": Temperament(on_sight="follow", attacks=False, when_hurt="skittish"),
}


@dataclass(frozen=True, slots=True)
class DeathEffect:
    """A hazard released on whoever stands next to the creature when it dies."""

    hazard: str  # a key of data.hazards.HAZARD_BY_TYPE
    message: str  # "{name}" is the creature's name


@dataclass(frozen=True, slots=True)
class EnemyDef:
    char: str
    color: tuple[int, int, int]
    name: str
    hp: int
    defense: int
    power: int
    organic: bool
    gore_color: tuple[int, int, int]
    description: str = ""
    # --- Behaviour ---
    ai_initial_state: str = "wandering"
    aggro_distance: int = 8
    sleep_aggro_distance: int = 3
    can_open_doors: bool = False
    flee_threshold: float = 0.0
    memory_turns: int = 15
    vision_radius: int = 8
    move_speed: int = 4  # 0 never moves
    temperament: str = "hostile"
    # --- Where it is found ---
    habitats: tuple[str, ...] = ()
    min_depth: int = 0
    spawn_weight: int = 10
    group: tuple[int, int] = (1, 1)
    # --- Possessions ---
    loot_table: tuple[tuple[str, float], ...] = ()
    max_inventory: int = 3
    can_steal: bool = False
    natural_weapon: str | None = None  # a data.items.NATURAL_WEAPONS name; never dropped
    # --- Traits ---
    hazard_immunities: tuple[str, ...] = ()
    death_effect: DeathEffect | None = None
    light: tuple[int, tuple[int, int, int]] | None = None  # (radius, colour) it glows with
    disguise: str | None = None  # a floor furnishing it passes for until found out
    chores: tuple[str, ...] = ()

    def to_ai_config(self) -> dict[str, object]:
        """The per-creature behaviour config, as plain JSON data (it is saved with the entity)."""
        cfg: dict[str, object] = {k: getattr(self, k) for k in _AI_CONFIG_KEYS}
        cfg["species"] = self.name
        if self.disguise:
            cfg["ai_initial_state"] = "lurking"
        optional: dict[str, object] = {
            "hazard_immunities": list(self.hazard_immunities),
            "chores": list(self.chores),
            "death_effect": (
                {"hazard": self.death_effect.hazard, "message": self.death_effect.message}
                if self.death_effect
                else None
            ),
            "light": [self.light[0], list(self.light[1])] if self.light else None,
        }
        cfg.update({key: value for key, value in optional.items() if value})
        return cfg


_PIRATE_LOOT: tuple[tuple[str, float], ...] = (
    ("Med-kit", 0.4),
    ("Bent Pipe", 0.3),
    ("Stun Baton", 0.15),
    ("Low-power Blaster", 0.15),
    ("O2 Canister", 0.2),
)

_PIRATE_BASE = EnemyDef(
    char="p",
    color=(0, 0, 0),
    name="",
    hp=5,
    defense=1,
    power=3,
    organic=True,
    gore_color=(0, 0, 0),
    description="",
    aggro_distance=8,
    sleep_aggro_distance=4,
    can_open_doors=True,
    flee_threshold=0.3,
    memory_turns=15,
    vision_radius=8,
    move_speed=4,
    habitats=(BOARDING, "derelict", "asteroid", "starbase"),
    spawn_weight=4,
    loot_table=_PIRATE_LOOT,
    can_steal=True,
)

ENEMIES: list[EnemyDef] = [
    # ---- Vermin and old machines: the background hum of any ruin ----
    EnemyDef(
        char="r",
        color=(127, 127, 0),
        name="Rat",
        hp=1,
        defense=0,
        power=1,
        organic=True,
        gore_color=_ORGANIC_RED,
        description="A ship rat, fat on ration packs and wiring insulation.",
        aggro_distance=5,
        sleep_aggro_distance=2,
        memory_turns=12,
        vision_radius=6,
        move_speed=6,
        habitats=("derelict", "starbase", "colony"),
    ),
    EnemyDef(
        char="b",
        color=(127, 0, 180),
        name="Bot",
        hp=3,
        defense=0,
        power=2,
        organic=False,
        gore_color=_MACHINE_OIL,
        description="A worker bot whose task list was overwritten with something hostile.",
        can_open_doors=True,
        memory_turns=20,
        move_speed=3,
        habitats=("derelict", "starbase"),
        spawn_weight=8,
        loot_table=(("Repair Kit", 0.3),),
    ),
    # ---- Pirates: raiders in ruins, and the crews of boarding craft ----
    replace(
        _PIRATE_BASE,
        name="Pirate",
        color=(200, 50, 50),
        gore_color=_ORGANIC_RED,
        description="A human raider in patched armour, eyeing your pack.",
    ),
    replace(
        _PIRATE_BASE,
        name="Xeno Pirate",
        color=(50, 200, 50),
        gore_color=(30, 120, 30),
        description="A green-skinned raider from the outer colonies, quick with a blade and quicker with your gear.",
    ),
    replace(
        _PIRATE_BASE,
        name="Vek Pirate",
        color=(50, 80, 200),
        gore_color=(30, 40, 140),
        description="A blue-scaled Vek raider. Vek crews strip a ship to the frame.",
    ),
    EnemyDef(
        char="p",
        color=(180, 150, 150),
        name="Mech Pirate",
        hp=6,
        defense=2,
        power=3,
        organic=False,
        gore_color=_MACHINE_OIL,
        description="A pirate more machine than man, every limb a salvaged prosthetic.",
        sleep_aggro_distance=4,
        can_open_doors=True,
        flee_threshold=0.2,
        memory_turns=20,
        move_speed=3,
        habitats=("derelict", "starbase"),
        min_depth=1,
        spawn_weight=3,
        loot_table=(("Repair Kit", 0.4), ("Low-power Blaster", 0.3), ("Shotgun", 0.1)),
    ),
    EnemyDef(
        char="P",
        color=(220, 140, 60),
        name="Breacher",
        hp=9,
        defense=3,
        power=4,
        organic=True,
        gore_color=_ORGANIC_RED,
        description=(
            "A boarding specialist in breach armour, a demolition charge strapped to its chest. "
            "Don't be standing next to it when it goes down."
        ),
        sleep_aggro_distance=4,
        can_open_doors=True,
        memory_turns=20,
        move_speed=2,
        habitats=(BOARDING,),
        spawn_weight=1,
        loot_table=(("Hull Patch", 0.5), ("Repair Kit", 0.4)),
        death_effect=DeathEffect(hazard="explosive", message="The {name}'s demolition charge detonates!"),
    ),
    # ---- Station security, still on duty ----
    EnemyDef(
        char="d",
        color=(150, 150, 200),
        name="Security Drone",
        hp=4,
        defense=0,
        power=3,
        organic=False,
        gore_color=_MACHINE_OIL,
        description="A floating security drone, still guarding corridors nobody walks any more.",
        ai_initial_state="sleeping",
        aggro_distance=10,
        can_open_doors=True,
        memory_turns=30,
        vision_radius=10,
        move_speed=3,
        habitats=("starbase", "derelict"),
        spawn_weight=6,
        loot_table=(("Repair Kit", 0.3),),
    ),
    EnemyDef(
        char="T",
        color=(200, 190, 90),
        name="Sentry Turret",
        hp=6,
        defense=2,
        power=2,
        organic=False,
        gore_color=_MACHINE_OIL,
        description="A ceiling-mounted sentry turret. It cannot move, but it watches the whole room.",
        ai_initial_state="sleeping",
        sleep_aggro_distance=7,
        memory_turns=5,
        move_speed=0,
        habitats=("starbase", "derelict"),
        min_depth=1,
        spawn_weight=4,
        natural_weapon="Turret Blaster",
    ),
    EnemyDef(
        char="w",
        color=(120, 200, 255),
        name="Arc Wraith",
        hp=3,
        defense=0,
        power=2,
        organic=False,
        gore_color=(60, 90, 140),
        description=(
            "A knot of living current that crawled out of a ruptured power main. It hungers for anything conductive."
        ),
        aggro_distance=9,
        sleep_aggro_distance=4,
        vision_radius=9,
        move_speed=8,
        habitats=("starbase", "derelict"),
        min_depth=2,
        spawn_weight=3,
        hazard_immunities=("electric",),
        death_effect=DeathEffect(hazard="electric", message="The {name} collapses in a crackling discharge!"),
        light=(2, (120, 200, 255)),
    ),
    # ---- Things that moved into the dark ----
    EnemyDef(
        char="L",
        color=(120, 170, 90),
        name="Vent Lurker",
        hp=4,
        defense=0,
        power=3,
        organic=True,
        gore_color=_INSECT_GREEN,
        description="A pale, eyeless thing that nests in leaking ducts. Gas and radiation don't trouble it.",
        ai_initial_state="sleeping",
        aggro_distance=6,
        memory_turns=10,
        vision_radius=6,
        move_speed=5,
        habitats=("derelict", "starbase"),
        spawn_weight=4,
        hazard_immunities=("gas", "radiation"),
    ),
    EnemyDef(
        char="M",
        color=(200, 120, 60),
        name="Scrap Mimic",
        hp=5,
        defense=1,
        power=3,
        organic=True,
        gore_color=(120, 90, 40),
        description="A shell-grower that wears scavenged plating like a hermit crab, and waits for hands to reach in.",
        aggro_distance=6,
        sleep_aggro_distance=1,
        memory_turns=10,
        vision_radius=6,
        habitats=("derelict", "starbase"),
        min_depth=1,
        spawn_weight=3,
        loot_table=(("Med-kit", 0.3), ("Repair Kit", 0.3)),
        disguise="Crate",
    ),
    EnemyDef(
        char="m",
        color=(170, 170, 140),
        name="Hull Mite",
        hp=1,
        defense=0,
        power=1,
        organic=True,
        gore_color=(110, 110, 70),
        description="A palm-sized mite that lives in vacuum. They drift in swarms and chew through thin plating.",
        aggro_distance=6,
        sleep_aggro_distance=2,
        memory_turns=8,
        vision_radius=6,
        move_speed=6,
        habitats=("derelict", "asteroid"),
        spawn_weight=4,
        group=(3, 5),
        hazard_immunities=("vacuum",),
    ),
    # ---- Native life of caves and colonies ----
    EnemyDef(
        char="s",
        color=(150, 220, 60),
        name="Acid Spitter",
        hp=3,
        defense=0,
        power=1,
        organic=True,
        gore_color=(90, 160, 40),
        description="A long-necked cave lizard that spits caustic slime from a safe distance.",
        aggro_distance=7,
        flee_threshold=0.3,
        memory_turns=12,
        habitats=("asteroid", "colony"),
        min_depth=1,
        spawn_weight=4,
        natural_weapon="Acid Spit",
    ),
    EnemyDef(
        char="h",
        color=(170, 120, 80),
        name="Feral Hound",
        hp=3,
        defense=0,
        power=2,
        organic=True,
        gore_color=_ORGANIC_RED,
        description="A colony guard dog gone wild after the settlers left. Hounds hunt in packs.",
        aggro_distance=9,
        flee_threshold=0.2,
        vision_radius=9,
        move_speed=6,
        habitats=("colony",),
        spawn_weight=5,
        group=(2, 3),
    ),
    # ---- Neutral and harmless company ----
    EnemyDef(
        char="j",
        color=(130, 190, 170),
        name="Custodian",
        hp=4,
        defense=1,
        power=2,
        organic=False,
        gore_color=_MACHINE_OIL,
        description=(
            "A maintenance unit still running its rounds, closing doors and welding breaches. "
            "It minds its own business unless you damage it."
        ),
        temperament="territorial",
        aggro_distance=6,
        sleep_aggro_distance=2,
        can_open_doors=True,
        memory_turns=10,
        vision_radius=6,
        move_speed=3,
        habitats=("derelict", "starbase"),
        spawn_weight=4,
        loot_table=(("Hull Patch", 0.4), ("Repair Kit", 0.3)),
        chores=("seal_breaches", "close_doors"),
    ),
    EnemyDef(
        char="C",
        color=(200, 190, 160),
        name="Colonist",
        hp=4,
        defense=0,
        power=2,
        organic=True,
        gore_color=_ORGANIC_RED,
        description=(
            "A settler who stayed on after the evacuation. Wary of strangers, but no threat unless you start one."
        ),
        temperament="territorial",
        aggro_distance=6,
        can_open_doors=True,
        flee_threshold=0.4,
        habitats=("colony",),
        spawn_weight=6,
        group=(1, 2),
        loot_table=(("Med-kit", 0.3), ("O2 Canister", 0.2)),
    ),
    EnemyDef(
        char="☼",
        color=(255, 230, 140),
        name="Glowmoth",
        hp=1,
        defense=0,
        power=0,
        organic=True,
        gore_color=(200, 180, 90),
        description="A moth the size of your hand, its abdomen glowing like a lamp. They gather in dark places.",
        temperament="docile",
        aggro_distance=5,
        sleep_aggro_distance=2,
        memory_turns=5,
        vision_radius=6,
        move_speed=3,
        habitats=("derelict", "asteroid"),
        spawn_weight=3,
        group=(1, 3),
        light=(4, (255, 210, 120)),
    ),
    EnemyDef(
        char="g",
        color=(150, 130, 110),
        name="Lithovore",
        hp=4,
        defense=1,
        power=1,
        organic=True,
        gore_color=(120, 80, 50),
        description=(
            "A slow rock-grazer that cracks ice for its oxygen. Its gut sacs are full of it, if you can catch one."
        ),
        temperament="skittish",
        aggro_distance=6,
        memory_turns=8,
        vision_radius=7,
        move_speed=3,
        habitats=("asteroid",),
        spawn_weight=4,
        loot_table=(("O2 Canister", 0.6),),
    ),
    EnemyDef(
        char="o",
        color=(190, 140, 200),
        name="Spore Drifter",
        hp=2,
        defense=0,
        power=0,
        organic=True,
        gore_color=(150, 110, 170),
        description="A drifting puffball, harmless to look at. It bursts into a choking cloud when popped.",
        temperament="docile",
        aggro_distance=4,
        vision_radius=5,
        move_speed=2,
        habitats=("colony", "asteroid"),
        spawn_weight=4,
        group=(1, 2),
        death_effect=DeathEffect(hazard="gas", message="The {name} bursts in a cloud of spores!"),
    ),
    EnemyDef(
        char="f",
        color=(230, 180, 90),
        name="Ship's Cat",
        hp=2,
        defense=0,
        power=1,
        organic=True,
        gore_color=_ORGANIC_RED,
        description="A ship's cat. It decides, after some consideration, that you are acceptable company.",
        temperament="friendly",
        aggro_distance=6,
        vision_radius=8,
        move_speed=5,
        habitats=("colony", "starbase", "derelict"),
        spawn_weight=2,
    ),
]

_ENEMIES_BY_NAME: dict[str, EnemyDef] = {e.name: e for e in ENEMIES}

assert len(_ENEMIES_BY_NAME) == len(ENEMIES), "Duplicate enemy name detected"


def enemy_by_name(name: str) -> EnemyDef:
    """Look up an EnemyDef by its name. Raises KeyError if not found."""
    return _ENEMIES_BY_NAME[name]


def creatures_for(habitat: str, depth: int) -> list[EnemyDef]:
    """The creatures that live in *habitat* and have come up as shallow as *depth*."""
    return [c for c in ENEMIES if habitat in c.habitats and depth >= c.min_depth]


def _validate_loot_tables() -> None:
    """Verify all loot table entries reference valid items at import time."""
    from data.items import item_by_name

    for defn in ENEMIES:
        for item_name, prob in defn.loot_table:
            item_by_name(item_name)  # raises KeyError on typo


_validate_loot_tables()

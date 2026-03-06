"""Colony biome palettes and tile color variation."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from world import tile_types
from world.noise import box_blur, fractal_noise

Color = Tuple[int, int, int]


@dataclass
class PathMaterial:
    name: str
    dark_fg: Color
    dark_bg: Color
    light_fg: Color
    light_bg: Color


@dataclass
class FloraEntry:
    char: str           # "*" for low clusters, "|" for tall stalks
    dark_fg: Color
    light_fg: Color
    density: float      # 0.0-1.0, fraction of ground tiles to replace


@dataclass
class ColonyPalette:
    name: str
    ground_dark_bg: Color
    ground_light_bg: Color
    wall_colors: list[Color]
    noise_range: int
    path_materials: list[PathMaterial] = None  # type: ignore[assignment]
    flora: list[FloraEntry] = None  # type: ignore[assignment]
    blur_size: int = 5


BIOMES: dict[str, ColonyPalette] = {
    "desert": ColonyPalette(
        name="desert",
        ground_dark_bg=(20, 17, 11),
        ground_light_bg=(43, 37, 26),
        wall_colors=[
            (160, 140, 100),  # sandstone
            (200, 195, 185),  # white plaster
            (170, 120, 80),   # adobe
        ],
        noise_range=15,
        path_materials=[
            PathMaterial("stone", (90, 90, 100), (18, 18, 22), (160, 160, 175), (35, 35, 42)),
            PathMaterial("asphalt", (70, 70, 75), (12, 12, 14), (130, 130, 140), (24, 24, 28)),
        ],
        flora=[
            FloraEntry("*", (55, 60, 30), (110, 120, 60), 0.03),   # dry scrub
            FloraEntry("|", (60, 55, 25), (120, 110, 50), 0.01),   # desert stalk
            FloraEntry(";", (50, 50, 28), (100, 100, 55), 0.04),   # dead brush
            FloraEntry(":", (55, 55, 30), (105, 105, 58), 0.02),   # sand pebbles
        ],
    ),
    "grassland": ColonyPalette(
        name="grassland",
        ground_dark_bg=(9, 16, 7),
        ground_light_bg=(20, 34, 14),
        wall_colors=[
            (140, 145, 150),  # grey stone
            (120, 100, 70),   # timber
            (190, 185, 175),  # whitewash
        ],
        noise_range=12,
        path_materials=[
            PathMaterial("gravel", (100, 90, 70), (16, 14, 10), (180, 165, 130), (32, 28, 20)),
            PathMaterial("stone", (90, 90, 95), (16, 16, 18), (160, 160, 170), (32, 32, 36)),
        ],
        flora=[
            FloraEntry("*", (60, 45, 70), (140, 100, 160), 0.06),  # wildflowers
            FloraEntry("|", (35, 65, 25), (70, 140, 50), 0.08),    # tall grass
            FloraEntry(";", (30, 55, 22), (60, 115, 45), 0.05),    # low brush
            FloraEntry(":", (35, 60, 28), (70, 125, 55), 0.04),    # clover
        ],
    ),
    "dirt": ColonyPalette(
        name="dirt",
        ground_dark_bg=(14, 12, 8),
        ground_light_bg=(30, 26, 17),
        wall_colors=[
            (155, 155, 160),  # concrete
            (120, 100, 80),   # brown metal
            (185, 180, 170),  # off-white
        ],
        noise_range=12,
        path_materials=[
            PathMaterial("stone", (90, 90, 100), (18, 18, 22), (160, 160, 175), (35, 35, 42)),
            PathMaterial("asphalt", (70, 70, 75), (12, 12, 14), (130, 130, 140), (24, 24, 28)),
        ],
        flora=[
            FloraEntry("*", (50, 55, 30), (100, 110, 60), 0.02),   # weeds
            FloraEntry(";", (45, 48, 28), (90, 96, 55), 0.03),     # dead scrub
            FloraEntry(":", (48, 50, 30), (95, 100, 58), 0.02),    # grit sprouts
        ],
    ),
    "frozen": ColonyPalette(
        name="frozen",
        ground_dark_bg=(11, 14, 20),
        ground_light_bg=(22, 28, 42),
        wall_colors=[
            (180, 190, 200),  # frost steel
            (150, 160, 175),  # slate blue
            (200, 205, 210),  # ice white
        ],
        noise_range=9,
        path_materials=[
            PathMaterial("ice", (120, 140, 160), (14, 16, 20), (200, 220, 240), (36, 42, 52)),
            PathMaterial("stone", (95, 100, 110), (16, 18, 22), (170, 178, 190), (32, 36, 44)),
        ],
        flora=[
            FloraEntry("*", (60, 75, 80), (130, 160, 170), 0.02),  # frost lichen
            FloraEntry(";", (55, 65, 72), (115, 140, 150), 0.02),  # ice moss
            FloraEntry(":", (50, 60, 68), (105, 130, 145), 0.01),  # frozen buds
        ],
    ),
    "alien": ColonyPalette(
        name="alien",
        ground_dark_bg=(16, 6, 20),
        ground_light_bg=(32, 14, 42),
        wall_colors=[
            (100, 60, 140),   # dark violet
            (50, 130, 120),   # deep teal
            (80, 90, 150),    # muted indigo
        ],
        noise_range=18,
        path_materials=[
            PathMaterial("chitin", (90, 50, 110), (18, 10, 24), (160, 100, 190), (38, 22, 48)),
            PathMaterial("resin", (50, 100, 95), (12, 20, 18), (100, 175, 165), (26, 40, 38)),
        ],
        flora=[
            FloraEntry("*", (70, 30, 90), (150, 60, 190), 0.05),   # spore clusters
            FloraEntry("|", (30, 80, 75), (60, 170, 155), 0.04),   # tentacle stalks
            FloraEntry(";", (55, 25, 75), (120, 50, 160), 0.03),   # fungal mat
            FloraEntry(":", (40, 65, 60), (80, 140, 130), 0.03),   # polyp buds
        ],
    ),
    "red_earth": ColonyPalette(
        name="red_earth",
        ground_dark_bg=(18, 10, 5),
        ground_light_bg=(38, 22, 12),
        wall_colors=[
            (160, 110, 80),   # clay
            (170, 165, 160),  # pale grey
            (140, 90, 60),    # rust metal
        ],
        noise_range=18,
        path_materials=[
            PathMaterial("stone", (100, 100, 105), (20, 20, 22), (175, 175, 185), (38, 38, 42)),
            PathMaterial("gravel", (110, 100, 80), (18, 16, 12), (190, 175, 145), (36, 32, 24)),
        ],
        flora=[
            FloraEntry("*", (70, 50, 30), (140, 95, 55), 0.03),    # iron scrub
            FloraEntry("|", (65, 45, 25), (130, 85, 45), 0.02),    # rusty stalks
            FloraEntry(";", (60, 42, 22), (120, 80, 40), 0.03),    # scrub brush
            FloraEntry(":", (55, 40, 20), (110, 75, 38), 0.02),    # red sprouts
        ],
    ),
}


_gid = int(tile_types.ground["tile_id"])
_pid = int(tile_types.path["tile_id"])
_flid = int(tile_types.flora_low["tile_id"])
_ftid = int(tile_types.flora_tall["tile_id"])
_fsid = int(tile_types.flora_scrub["tile_id"])
_fpid = int(tile_types.flora_sprout["tile_id"])

FLORA_CHAR_MAP: dict[str, int] = {
    "*": _flid,
    "|": _ftid,
    ";": _fsid,
    ":": _fpid,
}

BIOME_FLAVORS: dict[str, dict[int, tuple[str, list[str]]]] = {
    "desert": {
        _gid: ("Desert Ground", [
            "Sun-bleached sand crunches underfoot.",
            "Dry, cracked earth radiates heat.",
            "Fine dust swirls around your boots.",
            "Parched terrain stretches to the horizon.",
        ]),
        _pid: ("Desert Path", [
            "A sandy trail worn between structures.",
            "Heat-cracked flagstones mark the way.",
            "A dusty path, half-buried in sand.",
        ]),
        _flid: ("Dry Scrub", [
            "A clump of desiccated brush, barely alive.",
            "Thorny scrub clings to the parched soil.",
            "Brittle desert plants crackle underfoot.",
        ]),
        _ftid: ("Desert Stalk", [
            "A woody stalk juts up from cracked earth.",
            "A drought-hardened stem, pale and dry.",
        ]),
        _fsid: ("Dead Brush", [
            "Dried-out twigs crumble at a touch.",
            "Bleached, skeletal brush dots the sand.",
            "A tangle of dead stems, sun-scorched and brittle.",
        ]),
        _fpid: ("Sand Pebbles", [
            "Tiny stones and seed husks litter the ground.",
            "Windswept grit collects in shallow drifts.",
        ]),
    },
    "grassland": {
        _gid: ("Grassland", [
            "Tough scrub grass springs back underfoot.",
            "Low vegetation rustles in the breeze.",
            "Damp soil yields slightly beneath you.",
            "Hardy weeds push through cracked earth.",
        ]),
        _pid: ("Grassland Path", [
            "A muddy track between buildings.",
            "Gravel pressed into soft earth.",
            "A well-worn path through the grass.",
        ]),
        _flid: ("Wildflowers", [
            "A patch of small flowers nods in the breeze.",
            "Delicate blooms in faded purple and white.",
            "Low wildflowers cluster between the grass.",
        ]),
        _ftid: ("Tall Grass", [
            "Tall grass sways gently around you.",
            "Dense stalks whisper as you push through.",
            "Knee-high grass brushes against your legs.",
        ]),
        _fsid: ("Low Brush", [
            "A tangle of low green scrub.",
            "Dense groundcover catches at your boots.",
            "Thick brush springs back as you step through.",
        ]),
        _fpid: ("Clover", [
            "A carpet of tiny clover leaves.",
            "Small round leaves crowd the soil.",
            "Soft clover cushions your step.",
        ]),
    },
    "dirt": {
        _gid: ("Bare Ground", [
            "Hard-packed earth, dry and featureless.",
            "Compacted soil crunches underfoot.",
            "Barren ground, grey-brown and lifeless.",
            "A flat expanse of trampled dirt.",
        ]),
        _pid: ("Dirt Path", [
            "A beaten track through the dust.",
            "Paving stones set into packed earth.",
            "A utilitarian walkway, cracked and worn.",
        ]),
        _flid: ("Weeds", [
            "A stubborn patch of weeds pushes through the dirt.",
            "Scraggly plants eke out an existence here.",
            "A few tough weeds refuse to die.",
        ]),
        _fsid: ("Dead Scrub", [
            "Dry, grey scrub litters the ground.",
            "Withered stems poke through the dirt.",
            "A few dead twigs, nothing more.",
        ]),
        _fpid: ("Grit Sprouts", [
            "Tiny pale shoots push through the grit.",
            "Stubborn seedlings barely break the surface.",
        ]),
    },
    "red_earth": {
        _gid: ("Red Earth", [
            "Rust-red soil stains your boots.",
            "Iron-rich earth crunches like gravel.",
            "Crimson dust coats everything here.",
            "The ruddy ground glows faintly in the light.",
        ]),
        _pid: ("Red Earth Path", [
            "Reddish stone slabs, smoothed by traffic.",
            "A gravel path stained ochre by the soil.",
            "Compacted red clay forms a crude walkway.",
        ]),
        _flid: ("Iron Scrub", [
            "Rust-colored brush grows in a tight cluster.",
            "Hardy plants with reddish leaves hug the ground.",
            "Low growth stained ochre by the iron-rich soil.",
        ]),
        _ftid: ("Rusty Stalks", [
            "Stiff, reddish-brown stems rise from the clay.",
            "Wiry stalks the color of old rust.",
        ]),
        _fsid: ("Scrub Brush", [
            "Tough, reddish scrub clings to the clay.",
            "Low brush stained rust-brown by the soil.",
            "Wiry ground cover, dry and coarse.",
        ]),
        _fpid: ("Red Sprouts", [
            "Small ochre shoots push through the clay.",
            "Tiny red-brown seedlings dot the ground.",
        ]),
    },
    "frozen": {
        _gid: ("Frozen Ground", [
            "Permafrost crunches beneath your boots.",
            "A thin crust of ice covers the ground.",
            "Frozen soil, hard as concrete.",
            "Frost crystals crackle with each step.",
        ]),
        _pid: ("Frozen Path", [
            "An icy walkway, treacherous underfoot.",
            "Frost-heaved paving slabs creak and shift.",
            "A salted path, half-frozen over again.",
        ]),
        _flid: ("Frost Lichen", [
            "A pale crust of lichen clings to frozen ground.",
            "Ice-rimed growths spread in slow patterns.",
            "Grey-blue lichen, the only life in the cold.",
        ]),
        _fsid: ("Ice Moss", [
            "A thin mat of frozen moss, stiff and pale.",
            "Crystalline moss crunches under your weight.",
            "Brittle ice-moss clings to the permafrost.",
        ]),
        _fpid: ("Frozen Buds", [
            "Tiny ice-encased buds, suspended in time.",
            "Minuscule frozen shoots glint in the light.",
        ]),
    },
    "alien": {
        _gid: ("Alien Terrain", [
            "Spongy, bioluminescent ground pulses faintly.",
            "Strange fibrous growth carpets the surface.",
            "The ground hums with an alien resonance.",
            "Iridescent spores puff up with each step.",
        ]),
        _pid: ("Alien Path", [
            "A trail of hardened resin between structures.",
            "Smooth chitin plates form a crude walkway.",
            "A path of fused organic material, warm to the touch.",
        ]),
        _flid: ("Spore Cluster", [
            "Luminous spore pods pulse with a faint glow.",
            "A cluster of alien growths, warm to the touch.",
            "Bulbous forms exhale a thin violet mist.",
        ]),
        _ftid: ("Tentacle Stalk", [
            "A rubbery stalk coils slowly as you pass.",
            "Teal tendrils sway without any wind.",
            "A fleshy growth reaches upward, twitching faintly.",
        ]),
        _fsid: ("Fungal Mat", [
            "A spongy carpet of alien fungus, faintly warm.",
            "Violet filaments web across the ground.",
            "Soft, pulsing fungal growth covers the surface.",
        ]),
        _fpid: ("Polyp Buds", [
            "Tiny teal polyps dot the ground, twitching faintly.",
            "Small bioluminescent buds wink on and off.",
            "Gelatinous nodules cluster in the alien soil.",
        ]),
    },
}


def pick_biome(rng: random.Random) -> ColonyPalette:
    return rng.choice(list(BIOMES.values()))


def make_path_tile(palette: ColonyPalette, rng: random.Random) -> np.ndarray:
    mat = rng.choice(palette.path_materials)
    base_tid = int(tile_types.path["tile_id"])
    return tile_types.new_tile(
        walkable=True,
        transparent=True,
        dark=(0xB7, mat.dark_fg, mat.dark_bg),
        light=(0xB7, mat.light_fg, mat.light_bg),
        base_tile_id=base_tid,
    )


def make_ground_tile(palette: ColonyPalette) -> np.ndarray:
    base_tid = int(tile_types.ground["tile_id"])
    # Derive fg from biome bg so the ground glyph picks up the biome tint
    dr, dg, db = palette.ground_dark_bg
    lr, lg, lb = palette.ground_light_bg
    dark_fg = (min(dr * 4, 80), min(dg * 4, 80), min(db * 4, 80))
    light_fg = (min(lr * 4, 160), min(lg * 4, 160), min(lb * 4, 160))
    return tile_types.new_tile(
        walkable=True,
        transparent=True,
        dark=(ord(","), dark_fg, palette.ground_dark_bg),
        light=(ord(","), light_fg, palette.ground_light_bg),
        base_tile_id=base_tid,
    )


def make_flora_tile(entry: FloraEntry, palette: ColonyPalette) -> np.ndarray:
    base_tid = FLORA_CHAR_MAP[entry.char]
    return tile_types.new_tile(
        walkable=True,
        transparent=True,
        dark=(ord(entry.char), entry.dark_fg, palette.ground_dark_bg),
        light=(ord(entry.char), entry.light_fg, palette.ground_light_bg),
        base_tile_id=base_tid,
    )


_fractal_noise = fractal_noise  # backward compat alias


def scatter_flora(
    game_map: "GameMap",
    rng: random.Random,
    palette: ColonyPalette,
    ground_tid: int,
) -> None:
    """Scatter clustered flora tiles over ground tiles.

    Uses fractal noise for a shared vegetation density field that creates
    organic patches, plus per-type zone noise so different flora types
    dominate in different regions. Within vegetation patches, multiple
    flora types can coexist with the dominant type being most common.
    """
    if not palette.flora:
        return
    w, h = game_map.width, game_map.height
    ground_mask = game_map.tiles["tile_id"] == ground_tid
    np_rng = np.random.RandomState(rng.randint(0, 2**31))

    n_types = len(palette.flora)
    flora_tiles = [(entry, make_flora_tile(entry, palette)) for entry in palette.flora]
    total_density = sum(e.density for e in palette.flora)

    # Shared vegetation density field — determines WHERE flora grows at all.
    # Fractal noise gives organic, varied patch shapes and sizes.
    veg_field = _fractal_noise(np_rng, w, h, octaves=3, base_radius=8)

    # Target coverage: fraction of ground tiles that become flora.
    # Sparse biomes ~5-10%, lush biomes ~20-35%.
    target_coverage = min(total_density * 2.5, 0.35)
    target_coverage = max(target_coverage, 0.05)
    # Use quantile of the actual noise field for accurate coverage,
    # since fractal noise isn't uniformly distributed.
    ground_values = veg_field[ground_mask]
    if len(ground_values) == 0:
        return
    veg_threshold = float(np.quantile(ground_values, 1.0 - target_coverage))

    # Per-type zone fields — determines WHICH flora type appears where.
    # Broader scale than veg patches so regions feel coherent.
    zone_fields: list[np.ndarray] = []
    for _ in range(n_types):
        zone_fields.append(_fractal_noise(np_rng, w, h, octaves=2, base_radius=12))

    # Determine where vegetation exists
    veg_mask = ground_mask & (veg_field > veg_threshold)

    if n_types == 1:
        game_map.tiles[veg_mask] = flora_tiles[0][1]
        return

    # For each vegetation cell, pick a flora type.
    # Primary type: whichever zone field is highest (weighted by density).
    # Secondary mixing: 20-30% chance to use a runner-up type instead,
    # so patches contain a natural mix.
    weighted_zones = np.stack([
        zone_fields[i] * palette.flora[i].density
        for i in range(n_types)
    ], axis=-1)  # (w, h, n_types)

    # Primary type at each cell
    primary = np.argmax(weighted_zones, axis=-1)  # (w, h)

    # Mix roll: chance to pick a secondary type instead
    mix_roll = np_rng.uniform(0.0, 1.0, size=(w, h))
    mix_chance = 0.25

    # Secondary type: second-highest weighted zone
    sorted_indices = np.argsort(weighted_zones, axis=-1)
    secondary = sorted_indices[:, :, -2]  # second highest

    chosen = np.where(mix_roll < mix_chance, secondary, primary)

    # Place flora tiles
    for i, (entry, tile) in enumerate(flora_tiles):
        type_mask = veg_mask & (chosen == i)
        game_map.tiles[type_mask] = tile


def make_wall_tile(wall_color: Color) -> np.ndarray:
    base_tid = int(tile_types.structure_wall["tile_id"])
    r, g, b = wall_color
    dark_fg = (r // 2, g // 2, b // 2)
    dark_bg = (r // 12, g // 12, b // 12)
    light_bg = (r // 6, g // 6, b // 6)
    return tile_types.new_tile(
        walkable=False,
        transparent=False,
        dark=(ord("#"), dark_fg, dark_bg),
        light=(ord("#"), wall_color, light_bg),
        base_tile_id=base_tid,
    )


_box_blur = box_blur  # backward compat alias


def apply_ground_noise(
    game_map: "GameMap",
    rng: random.Random,
    ground_tid: int,
    noise_range: int,
    blur_size: int = 5,
    extra_tids: list[int] | None = None,
) -> None:
    """Apply smooth fractal noise to ground/flora bg colors.

    Uses three independent fractal noise channels so color shifts are
    organic — warm areas, cool areas, bright/dark patches — rather than
    a uniform grey offset.
    """
    mask = game_map.tiles["tile_id"] == ground_tid
    for tid in (extra_tids or []):
        mask |= game_map.tiles["tile_id"] == tid
    if not mask.any():
        return
    w, h = game_map.width, game_map.height
    np_rng = np.random.RandomState(rng.randint(0, 2**31))

    # Independent fractal noise per color channel for richer variation.
    # Each channel is [-noise_range, +noise_range].
    noise_channels = []
    for _ in range(3):
        field = _fractal_noise(np_rng, w, h, octaves=3, base_radius=10)
        noise_channels.append(((field * 2 - 1) * noise_range).astype(np.int16))

    for layer in ("dark", "light", "lit"):
        bg = game_map.tiles[layer]["bg"].copy().astype(np.int16)
        for ch in range(3):
            bg[:, :, ch] += noise_channels[ch]
        np.clip(bg, 0, 255, out=bg)
        game_map.tiles[layer]["bg"][mask] = bg[mask].astype(np.uint8)

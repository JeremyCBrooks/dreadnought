"""GameMap: tile grid, FOV, entity management, and rendering."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, List, Optional, Tuple

import numpy as np

from world import tile_types

if TYPE_CHECKING:
    from game.entity import Entity


class GameMap:
    def __init__(self, width: int, height: int, fill_tile: np.ndarray | None = None) -> None:
        self.width = width
        self.height = height
        fv = fill_tile if fill_tile is not None else tile_types.wall
        self.tiles = np.full((width, height), fill_value=fv, order="F")
        self.visible = np.full((width, height), fill_value=False, order="F")
        self.lit = np.full((width, height), fill_value=False, order="F")
        self.explored = np.full((width, height), fill_value=False, order="F")
        self.fully_lit = False
        self.fov_radius = 8
        self.has_space = False
        self.airlocks: list = []
        self.entities: List[Entity] = []
        # Per-tile hazard propagation
        self.hazard_overlays: dict[str, np.ndarray] = {}
        self._hazards_dirty: bool = True
        self.hull_breaches: list[tuple[int, int]] = []
        self._pending_decompression: dict | None = None
        self._pull_directions: dict[tuple[int, int], tuple[int, int]] | None = None
        self._vacuum_baseline_set: bool = False
        self.biome: str | None = None
        # Lighting
        self.light_sources: list = []
        self._light_map: np.ndarray | None = None
        self._light_dirty: bool = True

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        return bool(self.tiles["walkable"][x, y])

    def get_blocking_entity(self, x: int, y: int) -> Optional[Entity]:
        for entity in self.entities:
            if entity.blocks_movement and entity.x == x and entity.y == y:
                return entity
        return None

    def get_items_at(self, x: int, y: int) -> List[Entity]:
        return [
            e for e in self.entities
            if not e.blocks_movement and e.item is not None and e.x == x and e.y == y
        ]

    def get_interactable_at(self, x: int, y: int) -> Optional[Entity]:
        for e in self.entities:
            if getattr(e, "interactable", None) and e.x == x and e.y == y:
                return e
        return None

    def get_non_blocking_entity_at(self, x: int, y: int) -> Optional[Entity]:
        """Return any non-blocking entity (item or interactable) at (x, y)."""
        for e in self.entities:
            if not e.blocks_movement and e.x == x and e.y == y:
                return e
        return None

    def recalculate_hazards(self) -> None:
        """Recompute per-tile hazard overlays if dirty."""
        if not self._hazards_dirty:
            return
        self._hazards_dirty = False

        # Snapshot old vacuum overlay for decompression detection
        old_vacuum = self.hazard_overlays.get("vacuum")

        # Collect vacuum sources: open exterior airlock doors + hull breaches
        vacuum_sources: list[tuple[int, int]] = list(self.hull_breaches)
        ext_open_tid = int(tile_types.airlock_ext_open["tile_id"])
        xs, ys = np.where(self.tiles["tile_id"] == ext_open_tid)
        for i in range(len(xs)):
            vacuum_sources.append((int(xs[i]), int(ys[i])))

        if vacuum_sources:
            from game.environment import _flood_fill_hazard
            new_vacuum = _flood_fill_hazard(self, vacuum_sources)
            self.hazard_overlays["vacuum"] = new_vacuum

            # Detect newly-exposed tiles for explosive decompression
            if self._vacuum_baseline_set:
                if old_vacuum is None:
                    old_vacuum = np.full(
                        (self.width, self.height), fill_value=False, order="F"
                    )
                newly_exposed = new_vacuum & ~old_vacuum
                if np.any(newly_exposed):
                    self._pending_decompression = {
                        "newly_exposed": newly_exposed,
                        "breach_sources": vacuum_sources,
                    }
            self._vacuum_baseline_set = True
        else:
            # No vacuum sources: clear any stale flood-fill overlay
            if "vacuum" in self.hazard_overlays:
                self.hazard_overlays["vacuum"] = np.full(
                    (self.width, self.height), fill_value=False, order="F"
                )
            self._vacuum_baseline_set = True

        # Space tiles always have vacuum — mark them unconditionally
        if self.has_space:
            space_tid = int(tile_types.space["tile_id"])
            space_mask = self.tiles["tile_id"] == space_tid
            if space_mask.any():
                if "vacuum" not in self.hazard_overlays:
                    self.hazard_overlays["vacuum"] = np.full(
                        (self.width, self.height), fill_value=False, order="F"
                    )
                self.hazard_overlays["vacuum"] |= space_mask

    def get_hazards_at(self, x: int, y: int) -> set[str]:
        """Return set of active hazard names at (x, y)."""
        result: set[str] = set()
        for name, overlay in self.hazard_overlays.items():
            if overlay[x, y]:
                result.add(name)
        return result

    def add_light_source(
        self, x: int, y: int, radius: int, color: Tuple[int, int, int], intensity: float = 1.0,
    ) -> None:
        from world.lighting import LightSource
        self.light_sources.append(LightSource(x=x, y=y, radius=radius, color=color, intensity=intensity))
        self._light_dirty = True

    def invalidate_lights(self) -> None:
        self._light_dirty = True
        self._light_map = None

    def get_light_map(self) -> np.ndarray:
        if self._light_map is None or self._light_dirty:
            from world.lighting import compute_light_map
            self._light_map = compute_light_map(self.width, self.height, self.tiles, self.light_sources)
            self._light_dirty = False
        return self._light_map

    def describe_at(
        self, x: int, y: int, *, visible_only: bool = False,
    ) -> List[Tuple[str, Tuple[int, int, int]]]:
        """Return [(text, color), ...] describing a map position."""
        if not self.in_bounds(x, y):
            return [("Nothing there.", (100, 100, 100))]
        if not self.explored[x, y]:
            return [("Unexplored.", (80, 80, 80))]
        if visible_only and not self.visible[x, y]:
            return [("You recall this area dimly.", (90, 90, 110))]

        tid = int(self.tiles["tile_id"][x, y])
        name, flavor = tile_types.describe_tile(tid, biome=self.biome)
        lines: List[Tuple[str, Tuple[int, int, int]]] = [
            (f"{name} \u2014 {flavor}", (170, 170, 190)),
        ]

        for entity in self.entities:
            if entity.x != x or entity.y != y:
                continue
            if not self.visible[entity.x, entity.y] and visible_only:
                continue
            if entity.fighter and entity.blocks_movement:
                lines.append(
                    (f"{entity.name} ({entity.char}) is here.", (255, 180, 180))
                )
            elif entity.item:
                lines.append(
                    (f"You see {entity.name} ({entity.char}) lying here.", (180, 200, 255))
                )
            elif getattr(entity, "interactable", None):
                lines.append(
                    (f"{entity.name} ({entity.char}) — [e] to interact.", (200, 220, 150))
                )
        return lines

    def apply_scan_glow(self, cx: int, cy: int, radius: int) -> None:
        """Mark tiles within Euclidean radius as visible and explored."""
        ix = np.arange(self.width)[:, np.newaxis]
        iy = np.arange(self.height)[np.newaxis, :]
        mask = (ix - cx) ** 2 + (iy - cy) ** 2 <= radius * radius
        self.visible |= mask
        self.explored |= mask

    def update_fov(self, x: int, y: int, radius: int | None = None) -> None:
        import tcod.map

        if radius is None:
            radius = self.fov_radius

        # Infinite-range LOS for visibility (radius=0 means unlimited)
        self.visible[:] = tcod.map.compute_fov(
            self.tiles["transparent"],
            (x, y),
            radius=0,
        )

        # Lit mask: only tiles within fov_radius get bright appearance
        ix = np.arange(self.width)[:, np.newaxis]
        iy = np.arange(self.height)[np.newaxis, :]
        dist_sq = (ix - x) ** 2 + (iy - y) ** 2
        self.lit[:] = self.visible & (dist_sq <= radius * radius)

        self.explored |= self.visible

    SCAN_GLOW_DURATION = 3.0

    def render(
        self,
        console,
        cam_x: int,
        cam_y: int,
        vp_x: int,
        vp_y: int,
        vp_w: int,
        vp_h: int,
        scan_glow: Optional[dict] = None,
    ) -> None:
        cam_x = max(0, min(cam_x, max(0, self.width - vp_w)))
        cam_y = max(0, min(cam_y, max(0, self.height - vp_h)))

        rw = min(vp_w, self.width - cam_x)
        rh = min(vp_h, self.height - cam_y)
        if rw <= 0 or rh <= 0:
            return

        ms = (slice(cam_x, cam_x + rw), slice(cam_y, cam_y + rh))
        cs = (slice(vp_x, vp_x + rw), slice(vp_y, vp_y + rh))

        # Compute scan glow fade alpha and Euclidean mask
        glow_mask = None
        glow_alpha = 0.0
        if scan_glow:
            elapsed = time.time() - scan_glow["start_time"]
            if elapsed < self.SCAN_GLOW_DURATION:
                glow_alpha = 1.0 - elapsed / self.SCAN_GLOW_DURATION
                cx, cy = scan_glow["cx"], scan_glow["cy"]
                radius = scan_glow["radius"]
                ix = np.arange(cam_x, cam_x + rw)[:, np.newaxis]
                iy = np.arange(cam_y, cam_y + rh)[np.newaxis, :]
                glow_mask = (ix - cx) ** 2 + (iy - cy) ** 2 <= radius * radius

        # Tile appearance: lit=bright, visible-but-not-lit=dark, explored=dark/lit, else=shroud
        lit_slice = self.lit[ms]
        vis_slice = self.visible[ms]
        exp_slice = self.explored[ms]
        if self.fully_lit:
            console.rgb[cs] = np.select(
                condlist=[lit_slice, vis_slice, exp_slice],
                choicelist=[self.tiles["light"][ms], self.tiles["dark"][ms], self.tiles["lit"][ms]],
                default=tile_types.SHROUD,
            )
        else:
            console.rgb[cs] = np.select(
                condlist=[lit_slice, vis_slice, exp_slice],
                choicelist=[self.tiles["light"][ms], self.tiles["dark"][ms], self.tiles["dark"][ms]],
                default=tile_types.SHROUD,
            )

        # Apply fading green tint to tiles within scan glow radius
        if glow_mask is not None and glow_alpha > 0:
            fg = console.rgb["fg"][cs]
            bg = console.rgb["bg"][cs]
            dim = 1.0 - 0.5 * glow_alpha
            fg_boost = int(60 * glow_alpha)
            bg_boost = int(25 * glow_alpha)
            fg[glow_mask, 0] = (fg[glow_mask, 0] * dim).astype(np.uint8)
            fg[glow_mask, 1] = np.minimum(
                fg[glow_mask, 1].astype(np.int16) + fg_boost, 255
            ).astype(np.uint8)
            fg[glow_mask, 2] = (fg[glow_mask, 2] * dim).astype(np.uint8)
            bg[glow_mask, 0] = (bg[glow_mask, 0] * dim).astype(np.uint8)
            bg[glow_mask, 1] = np.minimum(
                bg[glow_mask, 1].astype(np.int16) + bg_boost, 255
            ).astype(np.uint8)
            bg[glow_mask, 2] = (bg[glow_mask, 2] * dim).astype(np.uint8)

        # Apply colored light source tinting
        if self.light_sources:
            light_map = self.get_light_map()
            light_slice = light_map[ms]  # (rw, rh, 3)
            fg = console.rgb["fg"][cs]
            bg = console.rgb["bg"][cs]
            vis = self.visible[ms]
            exp = self.explored[ms]
            lit_mask = vis | exp
            # Don't tint space tiles
            if self.has_space:
                space_tid = int(tile_types.space["tile_id"])
                lit_mask = lit_mask & (self.tiles["tile_id"][ms] != space_tid)
            # Reduce intensity for explored-but-not-visible tiles
            strength = np.where(vis[..., np.newaxis], 1.0, 0.5)
            tint = (light_slice * strength * 255).astype(np.int16)
            fg[lit_mask] = np.clip(
                fg[lit_mask].astype(np.int16) + tint[lit_mask], 0, 255
            ).astype(np.uint8)
            bg[lit_mask] = np.clip(
                bg[lit_mask].astype(np.int16) + (tint[lit_mask] // 3), 0, 255
            ).astype(np.uint8)

        # Two-pass: non-blocking (items) first, then blocking entities on top
        for entity in self.entities:
            if entity.blocks_movement:
                continue
            if not self.in_bounds(entity.x, entity.y):
                continue
            if not self.visible[entity.x, entity.y]:
                continue
            sx = vp_x + entity.x - cam_x
            sy = vp_y + entity.y - cam_y
            if vp_x <= sx < vp_x + rw and vp_y <= sy < vp_y + rh:
                color = self._glow_tint_color(entity.color, entity.x, entity.y,
                                              glow_mask, glow_alpha, cam_x, cam_y)
                color = self._light_tint_color(color, entity.x, entity.y)
                console.print(x=sx, y=sy, string=entity.char, fg=color)
        for entity in self.entities:
            if not entity.blocks_movement:
                continue
            if not self.in_bounds(entity.x, entity.y):
                continue
            if not self.visible[entity.x, entity.y]:
                continue
            sx = vp_x + entity.x - cam_x
            sy = vp_y + entity.y - cam_y
            if vp_x <= sx < vp_x + rw and vp_y <= sy < vp_y + rh:
                color = self._glow_tint_color(entity.color, entity.x, entity.y,
                                              glow_mask, glow_alpha, cam_x, cam_y)
                color = self._light_tint_color(color, entity.x, entity.y)
                console.print(x=sx, y=sy, string=entity.char, fg=color)

    @staticmethod
    def _glow_tint_color(color: Tuple[int, int, int], ex: int, ey: int,
                         glow_mask: Optional[np.ndarray], glow_alpha: float,
                         cam_x: int, cam_y: int) -> Tuple[int, int, int]:
        """If entity is within scan glow radius, apply fading green tint."""
        if glow_mask is None or glow_alpha <= 0:
            return color
        lx, ly = ex - cam_x, ey - cam_y
        if glow_mask[lx, ly]:
            dim = 1.0 - 0.5 * glow_alpha
            r = int(color[0] * dim)
            g = min(int(color[1] + 60 * glow_alpha), 255)
            b = int(color[2] * dim)
            return (r, g, b)
        return color

    def _light_tint_color(
        self, color: Tuple[int, int, int], ex: int, ey: int,
    ) -> Tuple[int, int, int]:
        """Apply light source tint to an entity's foreground color."""
        if not self.light_sources:
            return color
        lm = self.get_light_map()
        tint = lm[ex, ey]
        if tint[0] == 0 and tint[1] == 0 and tint[2] == 0:
            return color
        r = min(int(color[0] + tint[0] * 255), 255)
        g = min(int(color[1] + tint[1] * 255), 255)
        b = min(int(color[2] + tint[2] * 255), 255)
        return (r, g, b)

    def animate_space(
        self,
        console,
        cam_x: int,
        cam_y: int,
        vp_x: int,
        vp_y: int,
        vp_w: int,
        vp_h: int,
    ) -> None:
        """Overlay animated starfield on visible space tiles within the viewport."""
        if not self.has_space:
            return

        space_tid = int(tile_types.space["tile_id"])
        rw = min(vp_w, self.width - cam_x)
        rh = min(vp_h, self.height - cam_y)
        if rw <= 0 or rh <= 0:
            return

        ms = (slice(cam_x, cam_x + rw), slice(cam_y, cam_y + rh))
        vis = self.visible[ms]
        is_space = self.tiles["tile_id"][ms] == space_tid
        mask = vis & is_space

        # Exclude space tiles occupied by visible entities
        entity_positions = set()
        for e in self.entities:
            if self.in_bounds(e.x, e.y) and self.visible[e.x, e.y]:
                ex, ey = e.x - cam_x, e.y - cam_y
                if 0 <= ex < rw and 0 <= ey < rh:
                    entity_positions.add((ex, ey))

        xs, ys = np.where(mask)
        if len(xs) == 0:
            return

        t = time.time()

        for i in range(len(xs)):
            mx = xs[i] + cam_x  # map coords
            my = ys[i] + cam_y
            sx = vp_x + xs[i]   # screen coords
            sy = vp_y + ys[i]

            # Skip tiles with entities so they don't flicker
            if (xs[i], ys[i]) in entity_positions:
                continue

            # Deterministic hash for stable star placement
            h = (mx * 7919 + my * 104729) & 0xFFFF
            kind = h % 100

            if kind < 80:
                # Empty void — near-black background
                continue
            elif kind < 93:
                # Dim star — twinkle on/off
                phase = ((h >> 4) & 0xFF) / 256.0
                speed = 0.4 + (h % 13) * 0.02  # 0.40–0.64
                cycle = (t * speed + phase) % 1.0
                if cycle < 0.5:
                    brightness = int(40 + 30 * (h % 7))
                    console.print(
                        x=sx, y=sy, string=".",
                        fg=(brightness, brightness, brightness + 10),
                    )
            elif kind < 98:
                # Bright star — cycle characters
                chars = "*+x*."
                phase = ((h >> 3) & 0xFF) / 64.0
                speed = 0.25 + (h % 11) * 0.01  # 0.25–0.35
                idx = int((t * speed + phase) % len(chars))
                brightness = 140 + (h % 60)
                console.print(
                    x=sx, y=sy, string=chars[idx],
                    fg=(brightness, brightness, brightness + 20),
                )
            else:
                # Nebula — colored background, slow color shift
                phase = ((h >> 5) & 0xFF) / 128.0
                speed = 0.08 + (h % 7) * 0.005  # 0.08–0.11
                shift = (t * speed + phase) % 3.0
                if shift < 1.0:
                    bg = (8, 2, 15)
                elif shift < 2.0:
                    bg = (3, 8, 15)
                else:
                    bg = (12, 4, 8)
                console.rgb[sx, sy]["bg"] = bg

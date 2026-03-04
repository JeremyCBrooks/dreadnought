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
        self.explored = np.full((width, height), fill_value=False, order="F")
        self.fully_lit = False
        self.fov_radius = 8
        self.has_space = False
        self.airlocks: list = []
        self.entities: List[Entity] = []

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
        name, flavor = tile_types.describe_tile(tid)
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

    def update_fov(self, x: int, y: int, radius: int | None = None) -> None:
        import tcod.map

        if radius is None:
            radius = self.fov_radius
        self.visible[:] = tcod.map.compute_fov(
            self.tiles["transparent"],
            (x, y),
            radius=radius,
        )
        # tcod uses Chebyshev distance (square); mask to Euclidean (circle)
        ix = np.arange(self.width)[:, np.newaxis]
        iy = np.arange(self.height)[np.newaxis, :]
        self.visible &= (ix - x) ** 2 + (iy - y) ** 2 <= radius * radius

        # Infinite-range FOV for space tiles (visible through windows, no distance cap)
        if self.has_space:
            space_tid = int(tile_types.space["tile_id"])
            space_mask = self.tiles["tile_id"] == space_tid
            if space_mask.any():
                infinite_fov = tcod.map.compute_fov(
                    self.tiles["transparent"],
                    (x, y),
                    radius=0,
                )
                self.visible |= (infinite_fov & space_mask)

        self.explored |= self.visible

    def render(
        self,
        console,
        cam_x: int,
        cam_y: int,
        vp_x: int,
        vp_y: int,
        vp_w: int,
        vp_h: int,
    ) -> None:
        cam_x = max(0, min(cam_x, max(0, self.width - vp_w)))
        cam_y = max(0, min(cam_y, max(0, self.height - vp_h)))

        rw = min(vp_w, self.width - cam_x)
        rh = min(vp_h, self.height - cam_y)
        if rw <= 0 or rh <= 0:
            return

        ms = (slice(cam_x, cam_x + rw), slice(cam_y, cam_y + rh))
        cs = (slice(vp_x, vp_x + rw), slice(vp_y, vp_y + rh))

        if self.fully_lit:
            console.tiles_rgb[cs] = np.select(
                condlist=[self.visible[ms], self.explored[ms]],
                choicelist=[self.tiles["light"][ms], self.tiles["lit"][ms]],
                default=tile_types.SHROUD,
            )
        else:
            console.tiles_rgb[cs] = np.select(
                condlist=[self.visible[ms], self.explored[ms]],
                choicelist=[self.tiles["light"][ms], self.tiles["dark"][ms]],
                default=tile_types.SHROUD,
            )

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
                console.print(x=sx, y=sy, string=entity.char, fg=entity.color)
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
                console.print(x=sx, y=sy, string=entity.char, fg=entity.color)

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
                console.tiles_rgb[sx, sy]["bg"] = bg

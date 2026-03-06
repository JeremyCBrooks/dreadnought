"""Render a starfield viewport with a procedural star disc for the strategic state."""
from __future__ import annotations

import time

import numpy as np

from data.star_types import STAR_TYPES
from world.noise import fractal_noise


_NEBULA_PALETTES = [
    (20, 5, 35),   # purple
    (6, 18, 35),   # blue
    (28, 10, 18),  # warm
    (8, 22, 28),   # teal
    (24, 6, 28),   # magenta
]


def render_viewport(
    console,
    vp_x: int,
    vp_y: int,
    vp_w: int,
    vp_h: int,
    star_type_key: str,
    system_seed: int,
    time_override: float | None = None,
) -> None:
    """Render starfield background and star disc into the viewport region."""
    st = STAR_TYPES[star_type_key]
    t = time_override if time_override is not None else time.time()

    # Fractal noise fields (seeded per system)
    np_rng = np.random.RandomState(system_seed & 0x7FFFFFFF)
    noise = fractal_noise(np_rng, vp_w, vp_h, octaves=3, base_radius=10)
    nebula_density = fractal_noise(np_rng, vp_w, vp_h, octaves=2, base_radius=14)
    nebula_hue = fractal_noise(np_rng, vp_w, vp_h, octaves=2, base_radius=8)

    # Fill viewport bg with noise-modulated near-black
    bg_slice = console.rgb[vp_x : vp_x + vp_w, vp_y : vp_y + vp_h]
    base_bg = 2 + (noise * 6).astype(np.uint8)
    bg_slice["bg"][..., 0] = base_bg // 2
    bg_slice["bg"][..., 1] = base_bg // 3
    bg_slice["bg"][..., 2] = base_bg

    # Nebula clouds — applied first so star glow blends on top
    # Higher threshold + squared intensity = small dense cores bright, diffuse areas faint
    nebula_threshold = 0.5
    nebula_mask = nebula_density > nebula_threshold
    if np.any(nebula_mask):
        neb_intensity = np.zeros_like(nebula_density)
        neb_intensity[nebula_mask] = (
            (nebula_density[nebula_mask] - nebula_threshold) / (1.0 - nebula_threshold)
        )
        # Square the intensity: diffuse edges stay very faint, only peaks get bright
        neb_intensity *= neb_intensity
        n_pal = len(_NEBULA_PALETTES)
        for ch in range(3):
            idx_f = nebula_hue * (n_pal - 1)
            idx_lo = np.clip(idx_f.astype(int), 0, n_pal - 2)
            idx_hi = idx_lo + 1
            frac = idx_f - idx_lo
            pal_arr = np.array([p[ch] for p in _NEBULA_PALETTES], dtype=np.float64)
            nebula_color = pal_arr[idx_lo] * (1 - frac) + pal_arr[idx_hi] * frac
            addition = (nebula_color * neb_intensity * 3.5).astype(np.int16)
            current = bg_slice["bg"][..., ch].astype(np.int16)
            current[nebula_mask] += addition[nebula_mask]
            np.clip(current, 0, 255, out=current)
            bg_slice["bg"][..., ch] = current.astype(np.uint8)

    # --- Star rendering with smooth glow ---
    cx = vp_x + vp_w - 2
    cy = vp_y + 1

    xs = np.arange(vp_x, vp_x + vp_w)
    ys = np.arange(vp_y, vp_y + vp_h)
    dx = (xs - cx).reshape(-1, 1).astype(np.float64)
    dy = (ys - cy).reshape(1, -1).astype(np.float64) * 2.0
    dist = np.sqrt(dx * dx + dy * dy)

    radius = st.radius * 4
    # Smooth glow: 1.0 inside core, smooth falloff outside
    # Use a power-based falloff for soft blending
    glow = np.zeros_like(dist)

    # Inside disc: full glow with radial color gradient
    disc_mask = dist <= radius
    glow[disc_mask] = 1.0

    # Outside disc: smooth exponential decay — no hard corona edge
    # Glow extends far (4x corona_width) but fades smoothly
    glow_extent = st.corona_width * 6
    outside = dist > radius
    falloff_dist = dist[outside] - radius
    # Smooth exponential falloff: e^(-k*d) where k controls steepness
    decay_k = 3.0 / glow_extent  # ~5% brightness at glow_extent
    glow[outside] = np.exp(-decay_k * falloff_dist)

    # Anything with visible glow (>1% brightness)
    glow_mask = glow > 0.01

    # Apply star color to bg additively, blended by glow intensity
    if np.any(glow_mask):
        # Compute star color per cell based on distance
        norm = np.zeros_like(dist)
        norm[disc_mask] = dist[disc_mask] / max(radius, 1)
        # Outside disc, norm > 1 — use edge/corona colors
        norm[outside] = 1.0 + falloff_dist / max(glow_extent, 1)

        for ch in range(3):
            # Build color field: core -> mid -> edge -> corona
            star_color = np.full_like(dist, float(st.corona_color[ch]))
            # Core zone (0..0.7): core -> mid
            inner = disc_mask & (norm <= 0.7)
            if np.any(inner):
                t_inner = norm[inner] / 0.7
                star_color[inner] = st.core_color[ch] * (1 - t_inner) + st.mid_color[ch] * t_inner
            # Edge zone (0.7..1.0): mid -> edge
            mid_zone = disc_mask & (norm > 0.7)
            if np.any(mid_zone):
                t_mid = (norm[mid_zone] - 0.7) / 0.3
                star_color[mid_zone] = st.mid_color[ch] * (1 - t_mid) + st.edge_color[ch] * t_mid
            # Corona zone (outside disc): edge -> corona, fading
            corona_zone = outside & glow_mask
            if np.any(corona_zone):
                t_cor = np.clip((norm[corona_zone] - 1.0) * 2.0, 0, 1)
                star_color[corona_zone] = st.edge_color[ch] * (1 - t_cor) + st.corona_color[ch] * t_cor

            # Additive blend: existing bg + star_color * glow
            current = bg_slice["bg"][..., ch].astype(np.float64)
            current[glow_mask] += star_color[glow_mask] * glow[glow_mask]
            np.clip(current, 0, 255, out=current)
            bg_slice["bg"][..., ch] = current.astype(np.uint8)

    # Surface char animation on disc cells
    if np.any(disc_mask):
        norm_disc = np.zeros_like(dist)
        norm_disc[disc_mask] = dist[disc_mask] / max(radius, 1)
        disc_xs, disc_ys = np.where(disc_mask)
        for i in range(len(disc_xs)):
            lx, ly = disc_xs[i], disc_ys[i]
            sx, sy = vp_x + lx, vp_y + ly
            n = norm_disc[lx, ly]
            if n < 0.3:
                continue
            h = ((sx + system_seed) * 7919 + sy * 104729) & 0xFFFF
            phase = ((h >> 3) & 0xFF) / 128.0
            speed = 0.15 + (h % 7) * 0.01
            idx = int((t * speed + phase) % len(st.surface_chars))
            char = st.surface_chars[idx]
            bg_r = int(bg_slice["bg"][lx, ly][0])
            bg_g = int(bg_slice["bg"][lx, ly][1])
            bg_b = int(bg_slice["bg"][lx, ly][2])
            fg = (min(bg_r + 30, 255), min(bg_g + 30, 255), min(bg_b + 30, 255))
            console.print(x=sx, y=sy, string=char, fg=fg)

    # Precompute star brightness field: clip to narrow band then cube
    # This gives most stars near-invisible, a few very bright, smooth gradient between
    star_brightness = np.clip((noise - 0.25) / 0.55, 0, 1) ** 3

    # Render background stars
    for lx in range(vp_w):
        for ly in range(vp_h):
            if glow[lx, ly] > 0.05:
                continue
            sx = vp_x + lx
            sy = vp_y + ly

            noise_val = star_brightness[lx, ly]

            h = ((sx + system_seed) * 7919 + sy * 104729) & 0xFFFF
            kind = h % 100

            if kind < 80:
                continue
            elif kind < 93:
                phase = ((h >> 4) & 0xFF) / 256.0
                speed = 0.4 + (h % 13) * 0.02
                cycle = (t * speed + phase) % 1.0
                if cycle < 0.5:
                    brightness = int(10 + 245 * noise_val)
                    console.print(x=sx, y=sy, string=".",
                                  fg=(brightness, brightness, min(brightness + 10, 255)))
            else:
                chars = "*+x*."
                phase = ((h >> 3) & 0xFF) / 64.0
                speed = 0.25 + (h % 11) * 0.01
                idx = int((t * speed + phase) % len(chars))
                brightness = int(20 + 235 * noise_val)
                console.print(x=sx, y=sy, string=chars[idx],
                              fg=(brightness, brightness, min(brightness + 20, 255)))

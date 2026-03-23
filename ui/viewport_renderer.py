"""Render a starfield viewport with a procedural star disc for the strategic state."""

import time

import numpy as np

from data.star_types import STAR_TYPES
from world.noise import coord_fractal_noise

# Background star color tints: (r_mult, g_mult, b_mult)
# Derived from hash bits — most white/blue, some yellow/red
_STAR_TINTS = [
    (1.0, 1.0, 1.0),  # white
    (0.9, 0.9, 1.0),  # blue-white
    (0.85, 0.85, 1.0),  # blue
    (1.0, 1.0, 0.7),  # yellow
    (1.0, 0.8, 0.5),  # orange
    (1.0, 0.6, 0.5),  # red
]
# Lookup: 60% white/blue-white, 20% blue, 12% yellow, 8% red/orange
_TINT_INDEX = [0] * 30 + [1] * 30 + [2] * 20 + [3] * 12 + [4] * 5 + [5] * 3
_TINT_INDEX_ARR = np.array(_TINT_INDEX, dtype=np.int32)
_STAR_TINTS_ARR = np.array(_STAR_TINTS, dtype=np.float64)
_BRIGHT_CHARS = np.array([ord("*"), ord("+"), ord("x"), ord("*"), ord(".")], dtype=np.int32)

# Cache for noise fields that don't change between frames
_noise_cache: dict[tuple, dict[str, np.ndarray]] = {}
_NOISE_CACHE_MAX = 4  # keep a few entries for different views


def _get_cached_noise(seed: int, coord_x: int, coord_y: int, vp_w: int, vp_h: int) -> dict[str, np.ndarray]:
    """Return cached noise fields, computing them if needed."""
    key = (seed, coord_x, coord_y, vp_w, vp_h)
    cached = _noise_cache.get(key)
    if cached is not None:
        return cached

    xs = np.arange(coord_x, coord_x + vp_w)
    ys = np.arange(coord_y, coord_y + vp_h)
    noise = coord_fractal_noise(seed, xs, ys, octaves=3, base_period=10)

    neb_presence = coord_fractal_noise(seed + 1, xs, ys, octaves=2, base_period=60)
    neb_morph = coord_fractal_noise(seed + 4, xs, ys, octaves=2, base_period=40)
    neb_blob = coord_fractal_noise(seed + 5, xs, ys, octaves=3, base_period=18)
    neb_ridge_raw = coord_fractal_noise(seed + 6, xs, ys, octaves=3, base_period=24)
    neb_filament = 1.0 - 2.0 * np.abs(neb_ridge_raw - 0.5)
    neb_filament = np.clip(neb_filament, 0, 1) ** 0.7
    neb_cloud = coord_fractal_noise(seed + 7, xs, ys, octaves=2, base_period=50)
    neb_detail = coord_fractal_noise(seed + 3, xs, ys, octaves=2, base_period=7)

    blob_weight = np.clip(1.0 - 3.0 * neb_morph, 0, 1)
    filament_weight = np.clip(1.0 - np.abs(neb_morph - 0.5) * 4.0, 0, 1)
    cloud_weight = np.clip(3.0 * neb_morph - 2.0, 0, 1)
    total_w = blob_weight + filament_weight + cloud_weight + 1e-8
    nebula_shape = (blob_weight * neb_blob + filament_weight * neb_filament + cloud_weight * neb_cloud) / total_w
    nebula_density = nebula_shape * (0.5 + 0.5 * neb_detail) * neb_presence
    nebula_hue = coord_fractal_noise(seed + 2, xs, ys, octaves=2, base_period=8)
    star_brightness = np.clip((noise - 0.20) / 0.60, 0, 1) ** 5

    result = {
        "noise": noise,
        "nebula_density": nebula_density,
        "nebula_hue": nebula_hue,
        "star_brightness": star_brightness,
    }

    if len(_noise_cache) >= _NOISE_CACHE_MAX:
        _noise_cache.pop(next(iter(_noise_cache)))
    _noise_cache[key] = result
    return result


_NEBULA_PALETTES = [
    (20, 5, 35),  # purple
    (6, 18, 35),  # blue
    (28, 10, 18),  # warm
    (8, 22, 28),  # teal
    (24, 6, 28),  # magenta
]


def render_starfield_bg(
    console,
    vp_x: int,
    vp_y: int,
    vp_w: int,
    vp_h: int,
    seed: int,
    t: float,
    coord_x: int = 0,
    coord_y: int = 0,
    glow: np.ndarray | None = None,
    cell_mask: np.ndarray | None = None,
    skip_positions: set | None = None,
) -> None:
    """Render starfield background: noise bg, nebula clouds, and background stars.

    Uses coordinate-based noise so that the same (seed, coord_x, coord_y)
    always produces the same starfield, regardless of viewport dimensions.

    Args:
        seed: system seed for deterministic noise and star hashing.
        coord_x/y: world-space origin — noise and star hashes are computed
            at (coord_x + lx, coord_y + ly) so overlapping regions match.
        glow: (vp_w, vp_h) star glow intensity to attenuate nebula/stars. None = no glow.
        cell_mask: (vp_w, vp_h) bool mask limiting which cells to render. None = all.
        skip_positions: set of (lx, ly) local coords to skip for star characters.
    """
    cached = _get_cached_noise(seed, coord_x, coord_y, vp_w, vp_h)
    noise = cached["noise"]
    nebula_density = cached["nebula_density"]
    nebula_hue = cached["nebula_hue"]

    bg_slice = console.rgb[vp_x : vp_x + vp_w, vp_y : vp_y + vp_h]

    # Fill bg with noise-modulated near-black
    base_bg = 2 + (noise * 6).astype(np.uint8)
    if cell_mask is not None:
        bg_slice["bg"][..., 0][cell_mask] = (base_bg // 2)[cell_mask]
        bg_slice["bg"][..., 1][cell_mask] = (base_bg // 3)[cell_mask]
        bg_slice["bg"][..., 2][cell_mask] = base_bg[cell_mask]
    else:
        bg_slice["bg"][..., 0] = base_bg // 2
        bg_slice["bg"][..., 1] = base_bg // 3
        bg_slice["bg"][..., 2] = base_bg

    # Nebula clouds — attenuated near star glow if present
    glow_atten = glow if glow is not None else np.zeros((vp_w, vp_h))
    nebula_threshold = 0.18
    nebula_mask = nebula_density > nebula_threshold
    if cell_mask is not None:
        nebula_mask &= cell_mask
    if np.any(nebula_mask):
        neb_intensity = np.zeros_like(nebula_density)
        neb_intensity[nebula_mask] = (nebula_density[nebula_mask] - nebula_threshold) / (1.0 - nebula_threshold)
        neb_intensity *= neb_intensity
        neb_intensity *= 1.0 - glow_atten
        nebula_mask = nebula_mask & (neb_intensity > 0.001)
        n_pal = len(_NEBULA_PALETTES)
        neb_brightness = 1.25 + ((seed * 2654435761) & 0xFFFF) / 0xFFFF * 1.75
        idx_f = nebula_hue * (n_pal - 1)
        idx_lo = np.clip(idx_f.astype(int), 0, n_pal - 2)
        idx_hi = idx_lo + 1
        frac = idx_f - idx_lo
        pal_arr = np.array(_NEBULA_PALETTES, dtype=np.float64)
        for ch in range(3):
            nebula_color = pal_arr[idx_lo, ch] * (1 - frac) + pal_arr[idx_hi, ch] * frac
            addition = (nebula_color * neb_intensity * neb_brightness).astype(np.int16)
            current = bg_slice["bg"][..., ch].astype(np.int16)
            current[nebula_mask] += addition[nebula_mask]
            np.clip(current, 0, 255, out=current)
            bg_slice["bg"][..., ch] = current.astype(np.uint8)

    # Background stars — fully vectorized
    star_brightness = cached["star_brightness"]

    hx_arr = (coord_x + np.arange(vp_w)).reshape(-1, 1)
    hy_arr = (coord_y + np.arange(vp_h)).reshape(1, -1)
    h = ((hx_arr + seed) * 7919 + hy_arr * 104729) & 0xFFFF
    kind = h % 100

    # Star mask: only cells with kind >= 80
    star_mask = kind >= 80
    if cell_mask is not None:
        star_mask = star_mask & cell_mask
    if glow is not None:
        star_mask = star_mask & (glow <= 0.05)
    if skip_positions:
        for slx, sly in skip_positions:
            star_mask[slx, sly] = False

    if not np.any(star_mask):
        return

    # Tint lookup (vectorized)
    tint_select = _TINT_INDEX_ARR[(h >> 8) % 100]
    tint_rgb = _STAR_TINTS_ARR[tint_select]  # (vp_w, vp_h, 3)

    # Per-star animation
    phase = ((h >> 4) & 0xFF) / 256.0
    speed = 0.3 + (h % 13) * 0.015
    fade = 0.5 + 0.5 * np.sin(t * speed + phase * 6.283)

    # Brightness: dim stars (kind 80-92) vs bright stars (kind 93+)
    dim_mask = star_mask & (kind < 93)
    bright_mask = star_mask & (kind >= 93)
    brightness = np.zeros((vp_w, vp_h), dtype=np.float64)
    brightness[dim_mask] = 255.0 * star_brightness[dim_mask] * (0.1 + 0.4 * fade[dim_mask])
    brightness[bright_mask] = 255.0 * star_brightness[bright_mask] * (0.5 + 0.5 * fade[bright_mask])

    # Compute fg colors
    fg_r = np.clip(brightness * tint_rgb[..., 0], 0, 255).astype(np.uint8)
    fg_g = np.clip(brightness * tint_rgb[..., 1], 0, 255).astype(np.uint8)
    fg_b = np.clip(brightness * tint_rgb[..., 2], 0, 255).astype(np.uint8)

    # Skip stars dimmer than bg
    bg_max = np.maximum(
        bg_slice["bg"][..., 0].astype(np.int16),
        np.maximum(bg_slice["bg"][..., 1].astype(np.int16), bg_slice["bg"][..., 2].astype(np.int16)),
    )
    fg_max = np.maximum(fg_r.astype(np.int16), np.maximum(fg_g.astype(np.int16), fg_b.astype(np.int16)))
    star_mask = star_mask & (fg_max >= bg_max)

    if not np.any(star_mask):
        return

    # Character codes: dim='.' bright=animated from "*+x*."
    char_codes = np.full((vp_w, vp_h), ord("."), dtype=np.int32)
    if np.any(bright_mask & star_mask):
        char_phase_b = ((h >> 3) & 0xFF) / 64.0
        char_speed_b = 0.25 + (h % 11) * 0.01
        char_idx = ((t * char_speed_b + char_phase_b) % len(_BRIGHT_CHARS)).astype(np.int32)
        bm = bright_mask & star_mask
        char_codes[bm] = _BRIGHT_CHARS[char_idx[bm]]

    # Apply to console in bulk
    bg_slice["ch"][star_mask] = char_codes[star_mask]
    bg_slice["fg"][..., 0][star_mask] = fg_r[star_mask]
    bg_slice["fg"][..., 1][star_mask] = fg_g[star_mask]
    bg_slice["fg"][..., 2][star_mask] = fg_b[star_mask]


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

    bg_slice = console.rgb[vp_x : vp_x + vp_w, vp_y : vp_y + vp_h]

    # --- Precompute star glow field (needed to attenuate nebula near star) ---
    cx = vp_x + vp_w - 2
    cy = vp_y + 1

    xs = np.arange(vp_x, vp_x + vp_w)
    ys = np.arange(vp_y, vp_y + vp_h)
    dx = (xs - cx).reshape(-1, 1).astype(np.float64)
    dy = (ys - cy).reshape(1, -1).astype(np.float64) * 2.0
    dist = np.sqrt(dx * dx + dy * dy)

    radius = st.radius * 4
    glow = np.zeros_like(dist)

    disc_mask = dist <= radius
    glow[disc_mask] = 1.0

    glow_extent = st.corona_width * 6
    outside = dist > radius
    falloff_dist = dist[outside] - radius
    decay_k = 3.0 / glow_extent  # ~5% brightness at glow_extent
    glow[outside] = np.exp(-decay_k * falloff_dist)
    glow_mask = glow > 0.01

    # Render starfield background (bg fill, nebula clouds, background stars)
    render_starfield_bg(
        console,
        vp_x,
        vp_y,
        vp_w,
        vp_h,
        seed=system_seed,
        t=t,
        glow=glow,
    )

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

    # --- Special rendering for black holes ---
    if st.render_hint == "black_hole":
        # Accretion disc first, then darken center on top — so the
        # darkening smoothly eats into the inner disc edge
        disc_inner = float(radius)
        disc_outer = radius * 3.0
        disc_peak = radius * 1.8
        ring_mask = (dist > disc_inner) & (dist < disc_outer)
        if np.any(ring_mask):
            ring_dist = dist[ring_mask]
            # Asymmetric fade: sharp inner edge, gradual outer fade
            inner_fade = np.clip((ring_dist - disc_inner) / (disc_peak - disc_inner), 0, 1)
            outer_fade = np.clip((disc_outer - ring_dist) / (disc_outer - disc_peak), 0, 1)
            ring_intensity = (inner_fade * outer_fade) ** 1.2
            acc_colors = (255, 180, 80)
            for ch in range(3):
                current = bg_slice["bg"][..., ch].astype(np.float64)
                current[ring_mask] += ring_intensity * acc_colors[ch] * 0.6
                np.clip(current, 0, 255, out=current)
                bg_slice["bg"][..., ch] = current.astype(np.uint8)

        # Darken center — extends into inner disc for smooth blend
        darken_radius = radius * 1.6
        darken_mask = dist <= darken_radius
        for ch in range(3):
            current = bg_slice["bg"][..., ch].astype(np.float64)
            darken_factor = np.zeros_like(dist)
            darken_factor[darken_mask] = (1.0 - dist[darken_mask] / darken_radius) ** 0.7
            current[darken_mask] *= 1.0 - darken_factor[darken_mask] * 0.97
            bg_slice["bg"][..., ch] = np.clip(current, 0, 255).astype(np.uint8)

    # --- Special rendering for pulsars: brightness pulse ---
    if st.render_hint == "pulsar":
        # Smooth sinusoidal pulse: period ~3 seconds, range 0.4–1.0
        pulse = 0.4 + 0.6 * (0.5 + 0.5 * np.sin(t * 2.1))
        pulse_mask = glow > 0.01
        if np.any(pulse_mask):
            for ch in range(3):
                current = bg_slice["bg"][..., ch].astype(np.float64)
                # Scale the glow contribution by pulse factor
                # Brighter cells get more pulse effect
                boost = (pulse - 0.7) * glow[pulse_mask] * st.core_color[ch] * 0.5
                current[pulse_mask] += boost
                np.clip(current, 0, 255, out=current)
                bg_slice["bg"][..., ch] = current.astype(np.uint8)

    # Surface char animation on disc cells (skip for black holes)
    if np.any(disc_mask) and st.render_hint != "black_hole":
        norm_disc = np.zeros_like(dist)
        norm_disc[disc_mask] = dist[disc_mask] / max(radius, 1)
        # Only animate cells past the core (norm >= 0.3)
        surf_mask = disc_mask & (norm_disc >= 0.3)
        if np.any(surf_mask):
            surf_xs = (vp_x + np.arange(vp_w)).reshape(-1, 1)
            surf_ys = (vp_y + np.arange(vp_h)).reshape(1, -1)
            surf_h = ((surf_xs + system_seed) * 7919 + surf_ys * 104729) & 0xFFFF
            surf_phase = ((surf_h >> 3) & 0xFF) / 128.0
            surf_speed = 0.15 + (surf_h % 7) * 0.01
            n_chars = len(st.surface_chars)
            char_arr = np.array([ord(c) for c in st.surface_chars], dtype=np.int32)
            surf_idx = ((t * surf_speed + surf_phase) % n_chars).astype(np.int32)
            surf_codes = char_arr[surf_idx]

            bg_slice["ch"][surf_mask] = surf_codes[surf_mask]
            surf_fg = np.clip(bg_slice["bg"].astype(np.int16) + 30, 0, 255).astype(np.uint8)
            for ch in range(3):
                bg_slice["fg"][..., ch][surf_mask] = surf_fg[..., ch][surf_mask]

    # --- Flares: animated wisps drifting outward from the star ---
    # Scale flare size proportional to star radius
    radius_scale = radius / 24.0  # normalize: yellow_dwarf (r=6*4=24) -> 1.0
    _NUM_FLARES = 0 if st.render_hint == "black_hole" else 5 + (system_seed % 4)
    flare_rng = np.random.default_rng((system_seed * 31337) & 0x7FFFFFFF)
    flare_angles = flare_rng.uniform(0, 2 * np.pi, _NUM_FLARES)
    flare_periods = flare_rng.uniform(12.0, 30.0, _NUM_FLARES)
    flare_offsets = flare_rng.uniform(0, 1.0, _NUM_FLARES)
    # Max drift distance and width scale with star size
    flare_max_dist = flare_rng.uniform(0.5, 1.5, _NUM_FLARES) * radius
    flare_base_widths = flare_rng.uniform(0.8, 1.8, _NUM_FLARES) * radius_scale

    for fi in range(_NUM_FLARES):
        phase = (t / flare_periods[fi] + flare_offsets[fi]) % 1.0
        cur_dist = radius * 0.7 + flare_max_dist[fi] * phase

        # Fade in (first 15%) then fade out (quadratic)
        fade_in = min(1.0, phase / 0.15)  # 0->1 over first 15% of lifecycle
        fade_out = (1.0 - phase) ** 2
        flare_brightness = fade_in * fade_out
        if flare_brightness < 0.02:
            continue

        angle = flare_angles[fi]
        fcx = (cx - vp_x) + np.cos(angle) * cur_dist
        fcy = (cy - vp_y) + np.sin(angle) * cur_dist / 2.0
        # Width scales with star and widens slightly as it drifts
        width = flare_base_widths[fi] + phase * radius_scale * 1.2

        # Render flare as a small gaussian blob, additively blended
        # Only process cells near the flare (bounding box)
        margin = int(width * 3) + 1
        x0 = max(0, int(fcx) - margin)
        x1 = min(vp_w, int(fcx) + margin + 1)
        y0 = max(0, int(fcy) - margin)
        y1 = min(vp_h, int(fcy) + margin + 1)
        if x0 >= x1 or y0 >= y1:
            continue

        fxs = np.arange(x0, x1, dtype=np.float64)
        fys = np.arange(y0, y1, dtype=np.float64)
        fdx = (fxs - fcx).reshape(-1, 1)
        fdy = (fys - fcy).reshape(1, -1) * 2.0  # aspect correction
        fdist2 = fdx * fdx + fdy * fdy
        sigma2 = width * width
        blob = np.exp(-fdist2 / (2.0 * sigma2)) * flare_brightness

        # Flare color: interpolate between edge and corona based on distance
        for ch in range(3):
            fc = st.edge_color[ch] * (1 - phase) + st.corona_color[ch] * phase
            addition = (blob * fc).astype(np.int16)
            region = bg_slice["bg"][x0:x1, y0:y1, ch].astype(np.int16)
            region += addition
            np.clip(region, 0, 255, out=region)
            bg_slice["bg"][x0:x1, y0:y1, ch] = region.astype(np.uint8)

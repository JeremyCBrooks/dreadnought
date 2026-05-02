"""Serialize a tcod Console to a JSON-compatible tile delta for WebSocket streaming."""

from __future__ import annotations

import numpy as np


def serialize_delta(
    console,
    prev_tiles: np.ndarray | None,
) -> tuple[list[list[int]], np.ndarray]:
    """Return (changed_tiles, snapshot) where each tile is [x, y, ch, fr, fg, fb, br, bg, bb].

    On the first call pass prev_tiles=None — all cells are returned.
    On subsequent calls pass the snapshot returned by the previous call — only
    cells that changed since then are returned.
    """
    rgb = console.rgb  # shape (W, H), F-order, fields: ch (int32), fg (rgb uint8), bg (rgb uint8)
    w, h = rgb.shape

    # Flatten to a compact (W*H, 7) uint32 snapshot: ch, fg_r, fg_g, fg_b, bg_r, bg_g, bg_b
    ch = rgb["ch"].ravel(order="F").astype(np.uint32)
    fg = rgb["fg"].reshape(-1, 3, order="F").astype(np.uint32)
    bg = rgb["bg"].reshape(-1, 3, order="F").astype(np.uint32)
    snapshot = np.concatenate([ch[:, None], fg, bg], axis=1)  # (W*H, 7)

    if prev_tiles is None:
        changed_indices = np.arange(w * h)
    else:
        changed_indices = np.where(np.any(snapshot != prev_tiles, axis=1))[0]

    result: list[list[int]] = []
    for idx in changed_indices:
        x = int(idx % w)
        y = int(idx // w)
        row = snapshot[idx]
        result.append([x, y, int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), int(row[5]), int(row[6])])

    return result, snapshot

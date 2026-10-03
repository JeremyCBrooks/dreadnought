"use strict";

// Glyph dimensions matching terminal10x16_gs_ro.png (10px wide, 16px tall, 16x16 grid)
const GLYPH_W = 10;
const GLYPH_H = 16;

const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const status = document.getElementById("status");

let cols = 160;
let rows = 50;

// ── Tileset ───────────────────────────────────────────────────────────────────

// Offscreen canvas used as a scratch buffer for fg-color tinting (one glyph at a time)
const offCanvas = new OffscreenCanvas(GLYPH_W, GLYPH_H);
const offCtx = offCanvas.getContext("2d");

// The preprocessed tileset: black pixels become transparent, white stays white.
// This lets us use destination-in compositing to tint glyphs to any fg color.
let processedTileset = null;

function preprocessTileset(img) {
  const tw = img.naturalWidth;
  const th = img.naturalHeight;
  const tmpCanvas = new OffscreenCanvas(tw, th);
  const tmpCtx = tmpCanvas.getContext("2d");
  tmpCtx.drawImage(img, 0, 0);

  const imageData = tmpCtx.getImageData(0, 0, tw, th);
  const data = imageData.data; // RGBA, 4 bytes per pixel
  for (let i = 0; i < data.length; i += 4) {
    // Luminance of the pixel → alpha channel; set RGB to white so multiply tinting works
    const lum = Math.max(data[i], data[i + 1], data[i + 2]);
    data[i] = 255;
    data[i + 1] = 255;
    data[i + 2] = 255;
    data[i + 3] = lum; // transparent where glyph is black, opaque where white
  }
  tmpCtx.putImageData(imageData, 0, 0);
  processedTileset = tmpCanvas;
}

// The tileset is laid out in code page 437 order, but the server sends Unicode
// codepoints (what tcod stores). CP437[i] is the codepoint drawn by tile i.
const CP437 = [
  0x0000, 0x263a, 0x263b, 0x2665, 0x2666, 0x2663, 0x2660, 0x2022,
  0x25d8, 0x25cb, 0x25d9, 0x2642, 0x2640, 0x266a, 0x266b, 0x263c,
  0x25ba, 0x25c4, 0x2195, 0x203c, 0x00b6, 0x00a7, 0x25ac, 0x21a8,
  0x2191, 0x2193, 0x2192, 0x2190, 0x221f, 0x2194, 0x25b2, 0x25bc,
  0x0020, 0x0021, 0x0022, 0x0023, 0x0024, 0x0025, 0x0026, 0x0027,
  0x0028, 0x0029, 0x002a, 0x002b, 0x002c, 0x002d, 0x002e, 0x002f,
  0x0030, 0x0031, 0x0032, 0x0033, 0x0034, 0x0035, 0x0036, 0x0037,
  0x0038, 0x0039, 0x003a, 0x003b, 0x003c, 0x003d, 0x003e, 0x003f,
  0x0040, 0x0041, 0x0042, 0x0043, 0x0044, 0x0045, 0x0046, 0x0047,
  0x0048, 0x0049, 0x004a, 0x004b, 0x004c, 0x004d, 0x004e, 0x004f,
  0x0050, 0x0051, 0x0052, 0x0053, 0x0054, 0x0055, 0x0056, 0x0057,
  0x0058, 0x0059, 0x005a, 0x005b, 0x005c, 0x005d, 0x005e, 0x005f,
  0x0060, 0x0061, 0x0062, 0x0063, 0x0064, 0x0065, 0x0066, 0x0067,
  0x0068, 0x0069, 0x006a, 0x006b, 0x006c, 0x006d, 0x006e, 0x006f,
  0x0070, 0x0071, 0x0072, 0x0073, 0x0074, 0x0075, 0x0076, 0x0077,
  0x0078, 0x0079, 0x007a, 0x007b, 0x007c, 0x007d, 0x007e, 0x2302,
  0x00c7, 0x00fc, 0x00e9, 0x00e2, 0x00e4, 0x00e0, 0x00e5, 0x00e7,
  0x00ea, 0x00eb, 0x00e8, 0x00ef, 0x00ee, 0x00ec, 0x00c4, 0x00c5,
  0x00c9, 0x00e6, 0x00c6, 0x00f4, 0x00f6, 0x00f2, 0x00fb, 0x00f9,
  0x00ff, 0x00d6, 0x00dc, 0x00a2, 0x00a3, 0x00a5, 0x20a7, 0x0192,
  0x00e1, 0x00ed, 0x00f3, 0x00fa, 0x00f1, 0x00d1, 0x00aa, 0x00ba,
  0x00bf, 0x2310, 0x00ac, 0x00bd, 0x00bc, 0x00a1, 0x00ab, 0x00bb,
  0x2591, 0x2592, 0x2593, 0x2502, 0x2524, 0x2561, 0x2562, 0x2556,
  0x2555, 0x2563, 0x2551, 0x2557, 0x255d, 0x255c, 0x255b, 0x2510,
  0x2514, 0x2534, 0x252c, 0x251c, 0x2500, 0x253c, 0x255e, 0x255f,
  0x255a, 0x2554, 0x2569, 0x2566, 0x2560, 0x2550, 0x256c, 0x2567,
  0x2568, 0x2564, 0x2565, 0x2559, 0x2558, 0x2552, 0x2553, 0x256b,
  0x256a, 0x2518, 0x250c, 0x2588, 0x2584, 0x258c, 0x2590, 0x2580,
  0x03b1, 0x00df, 0x0393, 0x03c0, 0x03a3, 0x03c3, 0x00b5, 0x03c4,
  0x03a6, 0x0398, 0x03a9, 0x03b4, 0x221e, 0x03c6, 0x03b5, 0x2229,
  0x2261, 0x00b1, 0x2265, 0x2264, 0x2320, 0x2321, 0x00f7, 0x2248,
  0x00b0, 0x2219, 0x00b7, 0x221a, 0x207f, 0x00b2, 0x25a0, 0x00a0,
];
const TILE_FOR_CODEPOINT = new Map(CP437.map((codepoint, tile) => [codepoint, tile]));

function loadTileset(onReady) {
  const img = new Image();
  img.onload = () => {
    preprocessTileset(img);
    onReady();
  };
  img.onerror = () => {
    status.textContent = "Failed to load tileset - rendering in fallback mode";
    onReady(); // continue without tileset
  };
  img.src = "/tileset.png";
}

// ── Canvas setup ──────────────────────────────────────────────────────────────

function initCanvas(w, h) {
  cols = w;
  rows = h;
  canvas.width = w * GLYPH_W;
  canvas.height = h * GLYPH_H;
}

initCanvas(160, 50);

// ── Tile rendering ────────────────────────────────────────────────────────────

function drawTile(x, y, ch, fr, fg, fb, br, bg, bb) {
  const px = x * GLYPH_W;
  const py = y * GLYPH_H;

  // Background
  ctx.fillStyle = `rgb(${br},${bg},${bb})`;
  ctx.fillRect(px, py, GLYPH_W, GLYPH_H);

  // Glyph - skip blank/space characters
  if (ch <= 32) return;

  const tile = TILE_FOR_CODEPOINT.get(ch) ?? ch;
  const col = tile % 16;
  const row = Math.floor(tile / 16);
  const sx = col * GLYPH_W;
  const sy = row * GLYPH_H;

  if (processedTileset) {
    // Tileset rendering: tint the white glyph to fg color using destination-in compositing.
    // Step 1: fill offscreen canvas with the desired fg color
    offCtx.clearRect(0, 0, GLYPH_W, GLYPH_H);
    offCtx.fillStyle = `rgb(${fr},${fg},${fb})`;
    offCtx.fillRect(0, 0, GLYPH_W, GLYPH_H);

    // Step 2: destination-in keeps existing (fg color) pixels only where the source
    // (processed glyph) has non-zero alpha, masking the glyph shape.
    offCtx.globalCompositeOperation = "destination-in";
    offCtx.drawImage(processedTileset, sx, sy, GLYPH_W, GLYPH_H, 0, 0, GLYPH_W, GLYPH_H);
    offCtx.globalCompositeOperation = "source-over";

    // Step 3: draw the tinted glyph over the already-filled background
    ctx.drawImage(offCanvas, px, py);
  } else {
    // Fallback: text rendering (blurry for CP437 chars but functional)
    ctx.font = `${GLYPH_H - 2}px "Courier New", monospace`;
    ctx.textBaseline = "top";
    ctx.fillStyle = `rgb(${fr},${fg},${fb})`;
    ctx.fillText(String.fromCodePoint(ch), px, py);
  }
}

function applyTiles(tiles) {
  for (let i = 0; i < tiles.length; i++) {
    const t = tiles[i];
    drawTile(t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], t[8]);
  }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

const _watchMode = (typeof WATCH_MODE !== "undefined" ? WATCH_MODE : false);
const _watchUser = (typeof WATCH_USERNAME !== "undefined" ? WATCH_USERNAME : null);

function _buildWsUrl() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  if (_watchMode && _watchUser) {
    return `${proto}//${location.host}/ws/watch/${encodeURIComponent(_watchUser)}`;
  }
  return `${proto}//${location.host}/ws`;
}

let ws = null;

function connect() {
  ws = new WebSocket(_buildWsUrl());
  status.textContent = "Connecting…";

  ws.onopen = () => {
    status.textContent = "Connected";
    canvas.focus();
  };

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "portal_redirect") {
      location.href = "/portal.html";
      return;
    }
    if (msg.type === "full") {
      initCanvas(msg.w, msg.h);
      if (msg.seed !== undefined) {
        const bar = document.getElementById("seed-bar");
        const val = document.getElementById("seed-value");
        if (bar && val) {
          val.textContent = msg.seed;
          bar.style.display = "block";
          document.getElementById("seed-copy")?.addEventListener("click", () => {
            navigator.clipboard.writeText(String(msg.seed));
          }, { once: true });
        }
      }
    }
    applyTiles(msg.tiles);
  };

  ws.onclose = () => {
    status.textContent = "Disconnected - reload to reconnect";
  };

  ws.onerror = () => {
    status.textContent = "Connection error";
  };
}

// ── Keyboard input ────────────────────────────────────────────────────────────

const SUPPRESS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " ", "Tab"]);

function sendKey(type, e) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type,
    key: e.key,
    code: e.code, // used server-side to distinguish numpad from top-row digits
    shift: e.shiftKey,
    ctrl: e.ctrlKey,
    alt: e.altKey,
  }));
}

document.addEventListener("keydown", (e) => {
  if (SUPPRESS.has(e.key)) e.preventDefault();
  if (!_watchMode) sendKey("keydown", e);
});

document.addEventListener("keyup", (e) => {
  if (!_watchMode) sendKey("keyup", e);
});

// Click canvas to ensure it receives keyboard focus
canvas.setAttribute("tabindex", "0");
canvas.addEventListener("click", () => canvas.focus());

// ── Boot ──────────────────────────────────────────────────────────────────────

loadTileset(() => connect());

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

function loadTileset(onReady) {
  const img = new Image();
  img.onload = () => {
    preprocessTileset(img);
    onReady();
  };
  img.onerror = () => {
    status.textContent = "Failed to load tileset — rendering in fallback mode";
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

  // Glyph — skip blank/space characters
  if (ch <= 32) return;

  const col = ch % 16;
  const row = Math.floor(ch / 16);
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

const _token = (typeof GAME_TOKEN !== "undefined" ? GAME_TOKEN : "");
const _watchMode = (typeof WATCH_MODE !== "undefined" ? WATCH_MODE : false);
const _watchUser = (typeof WATCH_USERNAME !== "undefined" ? WATCH_USERNAME : null);

function _buildWsUrl() {
  const token = encodeURIComponent(_token);
  if (_watchMode && _watchUser) {
    return `ws://${location.host}/ws/watch/${encodeURIComponent(_watchUser)}?token=${token}`;
  }
  return `ws://${location.host}/ws?token=${token}`;
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
    status.textContent = "Disconnected — reload to reconnect";
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

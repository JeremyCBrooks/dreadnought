"use strict";

const gameMsg = document.getElementById("game-msg");

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/"; return null; }
  return r;
}

async function init() {
  const r = await api("GET", "/api/me");
  if (!r || !r.ok) { location.href = "/"; return; }
  const { username } = await r.json();
  document.getElementById("username-display").textContent = username;
  await refreshMyGame();
  await refreshActivePlayers();
  initChat();
  setInterval(() => {
    refreshActivePlayers();
    refreshChat();
  }, 5000);
}

async function refreshMyGame() {
  const r = await api("GET", "/api/my-game");
  if (!r) return;
  const data = await r.json();
  const sec = document.getElementById("my-game-section");
  if (data.exists) {
    const ts = data.updated_at ? new Date(data.updated_at * 1000).toLocaleString() : "";
    sec.innerHTML = `
      <div class="game-box">
        <div class="info">
          <div>Active save</div>
          <small>Last saved: ${ts}</small>
        </div>
        <button onclick="resumeGame()">Resume Game</button>
        <button class="danger" onclick="endGame()">End Game</button>
      </div>`;
  } else {
    sec.innerHTML = `
      <div class="game-box">
        <div class="info">No active game</div>
        <form onsubmit="newGame(event)" style="display:flex;gap:0.5rem;align-items:center">
          <input type="number" id="seed-input" placeholder="Seed (optional)" min="0">
          <button type="submit">New Game</button>
        </form>
      </div>`;
  }
}

async function refreshActivePlayers() {
  const r = await api("GET", "/api/active-games");
  if (!r) return;
  const players = await r.json();
  const tbody = document.getElementById("active-players");
  if (players.length === 0) {
    tbody.innerHTML = "<tr><td colspan='3' style='color:#555'>No active players</td></tr>";
    return;
  }
  tbody.innerHTML = players.map(p => `
    <tr>
      <td>${escHtml(p.username)}</td>
      <td>${p.watching_count}</td>
      <td><a href="/watch.html?u=${encodeURIComponent(p.username)}">Watch</a></td>
    </tr>`).join("");
}

function resumeGame() {
  location.href = "/play.html";
}

async function newGame(e) {
  e.preventDefault();
  gameMsg.textContent = "";
  const seedVal = document.getElementById("seed-input").value.trim();
  const body = seedVal !== "" ? { seed: parseInt(seedVal, 10) } : {};
  const r = await api("POST", "/api/new-game", body);
  if (!r) return;
  if (r.ok) {
    location.href = "/play.html";
  } else {
    const d = await r.json();
    gameMsg.textContent = d.detail || "Failed to create game";
  }
}

async function endGame() {
  if (!confirm("End this game? Your save will be deleted permanently.")) return;
  gameMsg.textContent = "";
  const r = await api("POST", "/api/end-game");
  if (!r) return;
  if (r.ok) {
    await refreshMyGame();
  } else {
    const d = await r.json();
    gameMsg.textContent = d.detail || "Failed to end game";
  }
}

async function logout() {
  await api("POST", "/api/logout");
  location.href = "/";
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Chat ──────────────────────────────────────────────────────────────────────

let chatLatestId = 0;
let chatErrorTimer = null;

function formatChatTime(epochSeconds) {
  const d = new Date(epochSeconds * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function isChatPinnedToBottom(log) {
  return log.scrollHeight - log.scrollTop - log.clientHeight < 30;
}

function renderChatMessages(messages, append) {
  const log = document.getElementById("chat-log");
  if (!append) {
    log.innerHTML = "";
  }
  if (!append && messages.length === 0) {
    log.innerHTML = '<div class="chat-empty">No messages yet</div>';
    return;
  }
  // Remove placeholder if present.
  const empty = log.querySelector(".chat-empty");
  if (empty) empty.remove();

  const wasPinned = append ? isChatPinnedToBottom(log) : true;
  const frag = document.createDocumentFragment();
  for (const m of messages) {
    const row = document.createElement("div");
    row.className = "chat-msg";
    row.innerHTML =
      "<time>" + escHtml(formatChatTime(m.created_at)) + "</time>" +
      "<strong>" + escHtml(m.username) + "</strong>" +
      escHtml(m.body);
    frag.appendChild(row);
  }
  log.appendChild(frag);
  if (wasPinned) log.scrollTop = log.scrollHeight;
}

async function refreshChat() {
  const url = chatLatestId > 0 ? "/api/chat?since=" + chatLatestId : "/api/chat";
  const r = await api("GET", url);
  if (!r || !r.ok) return;
  const data = await r.json();
  const append = chatLatestId > 0;
  if (data.messages.length > 0) {
    renderChatMessages(data.messages, append);
  } else if (!append) {
    renderChatMessages([], false);
  }
  if (data.latest_id > chatLatestId) chatLatestId = data.latest_id;
}

function showChatError(msg) {
  const el = document.getElementById("chat-error");
  el.textContent = msg;
  if (chatErrorTimer) clearTimeout(chatErrorTimer);
  chatErrorTimer = setTimeout(() => { el.textContent = ""; }, 5000);
}

async function sendChat(e) {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const body = input.value;
  if (!body.trim()) return;
  let r;
  try {
    r = await api("POST", "/api/chat", { body });
  } catch (_err) {
    showChatError("Send failed — try again");
    return;
  }
  if (!r) return;  // 401 — api() already redirected
  if (r.ok) {
    input.value = "";
    updateChatCount();
    // Pull immediately so the user sees their own message without waiting up to 5s.
    refreshChat();
  } else {
    const d = await r.json().catch(() => ({}));
    showChatError(d.detail || "Send failed");
  }
}

function updateChatCount() {
  const input = document.getElementById("chat-input");
  const count = document.getElementById("chat-count");
  const len = input.value.length;
  count.textContent = len + "/280";
  count.classList.toggle("warn", len >= 260);
}

function initChat() {
  document.getElementById("chat-input").addEventListener("input", updateChatCount);
  // Submit on Enter; Shift+Enter inserts newline (which the server strips).
  document.getElementById("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      document.getElementById("chat-form").requestSubmit();
    }
  });
  refreshChat();
}

init();

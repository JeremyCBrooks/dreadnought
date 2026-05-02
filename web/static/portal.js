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
  setInterval(refreshActivePlayers, 5000);
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
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

init();

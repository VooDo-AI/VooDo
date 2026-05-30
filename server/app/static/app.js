const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const statusEl = document.getElementById("status");
const sendBtn = form.querySelector(".btn-send");
const stopBtn = document.getElementById("btn-stop");

function setBusy(b) {
  busy = b;
  if (sendBtn) sendBtn.style.display = b ? "none" : "";
  if (stopBtn) stopBtn.style.display = b ? "" : "none";
  if (sendBtn) sendBtn.disabled = b;
  setTyping(b);
  if (!b) hidePermissionPopup();
}

if (stopBtn) {
  stopBtn.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
    stopBtn.disabled = true;  // re-enabled by next render
    stopBtn.title = "Stopping...";
  });
}

// ── Keyboard/mouse permission popup ──────────────────────────────────────
const permOverlay = document.getElementById("permission-overlay");
const permMsg     = document.getElementById("permission-msg");
const btnAllow    = document.getElementById("btn-allow-kb");
const btnDeny     = document.getElementById("btn-deny-kb");

function showPermissionPopup(tool) {
  if (!permOverlay) return;
  if (permMsg) permMsg.textContent =
    `The agent needs to use "${tool}" to continue.\nAllow keyboard and mouse access for the rest of this session?`;
  permOverlay.style.display = "flex";
}
function hidePermissionPopup() {
  if (permOverlay) permOverlay.style.display = "none";
}

if (btnAllow) {
  btnAllow.addEventListener("click", () => {
    hidePermissionPopup();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "approve_keyboard" }));
    }
  });
}
if (btnDeny) {
  btnDeny.addEventListener("click", () => {
    hidePermissionPopup();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "stop" }));
    }
    if (stopBtn) { stopBtn.disabled = false; stopBtn.title = "Stop agent"; }
  });
}
// ─────────────────────────────────────────────────────────────────────────
const typingIndicator = document.getElementById("typing-indicator");

let ws = null;
let busy = false;

function setTyping(on) {
  typingIndicator.style.display = on ? "flex" : "none";
  if (on) chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

// ── Conversation Storage ──────────────────────────────────────────
const S_CONVS  = "voodo-convs";
const S_ACTIVE = "voodo-active-id";
let activeId = null;

function genId() {
  return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

function loadConvs() {
  try { return JSON.parse(localStorage.getItem(S_CONVS)) || []; }
  catch { return []; }
}

function saveConvs(convs) {
  try { localStorage.setItem(S_CONVS, JSON.stringify(convs)); } catch {}
}

function getConv(id) {
  return loadConvs().find(c => c.id === id) || null;
}

function createConv() {
  const conv = { id: genId(), title: "New Chat", messages: [] };
  const convs = loadConvs();
  convs.unshift(conv);
  saveConvs(convs);
  return conv;
}

function ensureActive() {
  const saved = localStorage.getItem(S_ACTIVE);
  if (saved && getConv(saved)) {
    activeId = saved;
  } else {
    const convs = loadConvs();
    activeId = convs.length > 0 ? convs[0].id : createConv().id;
    localStorage.setItem(S_ACTIVE, activeId);
  }
}

function setActive(id) {
  activeId = id;
  localStorage.setItem(S_ACTIVE, id);
}

function updateTitle(id, text) {
  const convs = loadConvs();
  const conv = convs.find(c => c.id === id);
  if (conv && conv.title === "New Chat") {
    conv.title = text.length > 28 ? text.slice(0, 28) + "…" : text;
    saveConvs(convs);
    renderConvList();
  }
}

function saveMsg(id, msg) {
  const convs = loadConvs();
  const conv = convs.find(c => c.id === id);
  if (!conv) return;
  const stored = { ...msg };
  if (stored.image && stored.image.length > 200000) stored.image = "[image]";
  conv.messages.push(stored);
  saveConvs(convs);
}

function deleteConv(id) {
  const all = loadConvs();
  const deleted = all.find(c => c.id === id);
  if (!deleted) return;
  let convs = all.filter(c => c.id !== id);
  saveConvs(convs);
  if (activeId === id) {
    if (convs.length === 0) convs = [createConv()];
    setActive(convs[0].id);
    renderChat(convs[0].id);
  }
  renderConvList();
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Intro HTML ────────────────────────────────────────────────────
const INTRO_HTML = `
  <div class="msg intro">
    <div class="intro-content">
      <svg class="robot-logo intro-robot" viewBox="0 0 40 44" width="72" height="72" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <radialGradient id="rHead2" cx="38%" cy="28%" r="72%">
            <stop offset="0%" stop-color="#e8eef8"/>
            <stop offset="60%" stop-color="#b8c8df"/>
            <stop offset="100%" stop-color="#7a95b8"/>
          </radialGradient>
          <radialGradient id="rEar2" cx="30%" cy="30%" r="70%">
            <stop offset="0%" stop-color="#c5d3e8"/>
            <stop offset="100%" stop-color="#8099b8"/>
          </radialGradient>
          <radialGradient id="rEye2" cx="38%" cy="32%" r="62%">
            <stop offset="0%" stop-color="#d0f8ff"/>
            <stop offset="35%" stop-color="#40d8f8"/>
            <stop offset="100%" stop-color="#0088bb"/>
          </radialGradient>
          <filter id="eyeBloom2" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2.2" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="headShadow2" x="-10%" y="-5%" width="120%" height="120%">
            <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#4a6a9a" flood-opacity="0.35"/>
          </filter>
        </defs>
        <rect x="0" y="17" width="7" height="11" rx="3.5" fill="url(#rEar2)"/>
        <rect x="1.5" y="19.5" width="3" height="6" rx="1.5" fill="#1a2030" opacity="0.4"/>
        <rect x="33" y="17" width="7" height="11" rx="3.5" fill="url(#rEar2)"/>
        <rect x="35.5" y="19.5" width="3" height="6" rx="1.5" fill="#1a2030" opacity="0.4"/>
        <rect x="6" y="5" width="28" height="35" rx="10" fill="url(#rHead2)" filter="url(#headShadow2)"/>
        <rect x="16" y="2" width="8" height="7" rx="3.5" fill="#b8c8df"/>
        <rect x="18" y="1" width="4" height="4" rx="2" fill="#9aafc8"/>
        <rect x="9" y="12" width="22" height="22" rx="6" fill="#0d1825"/>
        <rect x="10" y="13" width="10" height="4" rx="2" fill="white" opacity="0.04"/>
        <ellipse class="r-eye r-eye-left" cx="15.5" cy="23" rx="4.5" ry="5.8" fill="url(#rEye2)" filter="url(#eyeBloom2)"/>
        <ellipse class="r-eye r-eye-right" cx="24.5" cy="23" rx="4.5" ry="5.8" fill="url(#rEye2)" filter="url(#eyeBloom2)"/>
        <circle cx="13.8" cy="20.5" r="1.1" fill="white" opacity="0.55"/>
        <circle cx="22.8" cy="20.5" r="1.1" fill="white" opacity="0.55"/>
        <circle cx="15" cy="19.5" r="0.5" fill="white" opacity="0.3"/>
        <circle cx="24" cy="19.5" r="0.5" fill="white" opacity="0.3"/>
      </svg>
      <h2>How can I fix your system today?</h2>
      <p>Describe your issue or pick a suggestion below</p>
      <div class="suggestion-chips">
        <button class="chip" data-text="My audio isn't working on Zoom">Zoom audio broken</button>
        <button class="chip" data-text="My computer is running very slow">Slow computer</button>
        <button class="chip" data-text="My WiFi keeps disconnecting">WiFi issues</button>
        <button class="chip" data-text="I can't connect to my printer">Printer not working</button>
      </div>
    </div>
  </div>`;

// ── Chat Rendering ────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen  = () => setStatus("connected", "connected");
  ws.onclose = () => { setStatus("reconnecting…", "disconnected"); setTimeout(connect, 1500); };
  ws.onerror = () => setStatus("error", "disconnected");
  ws.onmessage = (e) => { renderEvent(JSON.parse(e.data)); };
}

function attachFeedbackRow(parentEl, success, summary) {
  // Append a 👍 / 👎 row to a result/error message. Clicking sends a
  // {type:"feedback"} WS frame to the backend and locks the row with
  // a "Thanks!" confirmation so it can't be submitted twice.
  const row = document.createElement("div");
  row.className = "feedback-row";
  const ask = document.createElement("span");
  ask.className = "feedback-ask";
  ask.textContent = "Was this helpful?";
  const like = document.createElement("button");
  like.type = "button"; like.className = "feedback-btn"; like.textContent = "👍";
  like.title = "Yes, this helped";
  const dis = document.createElement("button");
  dis.type = "button"; dis.className = "feedback-btn"; dis.textContent = "👎";
  dis.title = "No, it didn't help";
  function send(rating) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "feedback", rating, success, summary,
      }));
    }
    row.innerHTML = "";
    const thanks = document.createElement("span");
    thanks.className = "feedback-thanks";
    thanks.textContent = rating === "like" ? "Thanks for the 👍" : "Thanks — we'll do better 👎";
    row.appendChild(thanks);
  }
  like.addEventListener("click", () => send("like"));
  dis.addEventListener("click", () => send("dislike"));
  row.appendChild(ask);
  row.appendChild(like);
  row.appendChild(dis);
  parentEl.appendChild(row);
}

function makeThoughtBubble(text) {
  // Collapsed by default — header is the click target; body holds the
  // full thought text and is also the streaming target for thought_delta.
  // We keep the bubble in a single .msg.thought wrapper so external
  // selectors (e.g. data-stream='1') still resolve to the bubble itself.
  const intro = chat.querySelector(".intro");
  if (intro) intro.remove();
  const d = document.createElement("div");
  d.className = "msg thought collapsed";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "thought-toggle";
  toggle.innerHTML =
    '<svg class="thought-chevron" viewBox="0 0 12 12" width="10" height="10"' +
    ' aria-hidden="true">' +
    '<polyline points="3 5 6 8 9 5" fill="none" stroke="currentColor"' +
    ' stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
    '</svg><span class="thought-label">💭 Thinking</span>';
  toggle.addEventListener("click", () => d.classList.toggle("collapsed"));

  const body = document.createElement("div");
  body.className = "thought-body";
  body.textContent = text || "";

  d.appendChild(toggle);
  d.appendChild(body);
  chat.appendChild(d);
  chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
  return d;
}

function el(cls, text) {
  const intro = chat.querySelector(".intro");
  if (intro) intro.remove();
  const d = document.createElement("div");
  d.className = "msg " + cls;
  if (text !== undefined) d.textContent = text;
  chat.appendChild(d);
  chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
  return d;
}

function renderEvent(event) {
  const { kind, payload } = event;
  switch (kind) {
    case "thought": {
      const d = makeThoughtBubble(payload.text || "");
      if (payload.stream) {
        d.dataset.stream = "1";  // mark as the live target for thought_delta
        // Clear any previous streaming target.
        chat.querySelectorAll(".msg.thought[data-stream]").forEach(prev => {
          if (prev !== d) delete prev.dataset.stream;
        });
      } else {
        saveMsg(activeId, { kind: "thought", text: payload.text });
      }
      break;
    }
    case "thought_delta": {
      const liveMsg = chat.querySelector(".msg.thought[data-stream='1']");
      if (liveMsg) {
        const target = liveMsg.querySelector(".thought-body") || liveMsg;
        target.textContent = (target.textContent || "") + (payload.text || "");
        chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
      }
      // Persist incrementally so reload shows the final text.
      const convs = loadConvs();
      const conv = convs.find(c => c.id === activeId);
      if (conv) {
        const last = conv.messages[conv.messages.length - 1];
        if (last && last.kind === "thought") {
          last.text = (last.text || "") + (payload.text || "");
        } else {
          conv.messages.push({ kind: "thought", text: payload.text || "" });
        }
        saveConvs(convs);
      }
      break;
    }
    case "tool_call": {
      // Just the tool name — arguments (often noisy: long strings,
      // coordinates, base64 chunks) stay out of the user-facing chat.
      // Persisted msg still carries args so they're not lost from the
      // DB / debugging path.
      const d = el("tool");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = payload.name;
      d.appendChild(name);
      saveMsg(activeId, { kind: "tool", name: payload.name, args: payload.args });
      break;
    }
    case "observation": {
      const full = JSON.stringify(payload, null, 2);
      const summary = payload.ok === false
        ? `error: ${(payload.error || "unknown").toString().slice(0, 120)}`
        : (payload.result ? `ok — ${JSON.stringify(payload.result).slice(0, 80)}` : "ok");
      const d = el("observation", summary);
      d.dataset.full = full;
      d.addEventListener("click", () => {
        d.classList.toggle("expanded");
        d.textContent = d.classList.contains("expanded") ? d.dataset.full : summary;
      });
      saveMsg(activeId, { kind: "observation", text: summary });
      break;
    }
    case "result": {
      const ok = payload.success;
      const intro = chat.querySelector(".intro");
      if (intro) intro.remove();
      if (ok) {
        const card = document.createElement("div");
        card.className = "msg resolution-card";
        card.innerHTML = `
          <h4>Issue Resolved</h4>
          <p>${esc(payload.summary || "Task completed successfully.")}</p>
          <button class="btn-confirm">Done</button>`;
        card.style.cursor = 'pointer';
        card.title = 'Click to see details';
        card.addEventListener('click', (ev) => {
          if (ev.target.classList.contains('btn-confirm') || ev.target.classList.contains('btn-new-issue')) return;
          if (ev.target.closest('.feedback-row')) return;
          card.classList.toggle('expanded');
          card.title = card.classList.contains('expanded') ? '' : 'Click to see details';
        });
        chat.appendChild(card);
        attachFeedbackRow(card, ok, payload.summary || "");
        chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
      } else {
        const err = el("error", "Failed: " + (payload.summary || "Unknown error occurred"));
        attachFeedbackRow(err, ok, payload.summary || "");
      }
      saveMsg(activeId, { kind: "result", success: ok, summary: payload.summary || "" });
      setBusy(false); if (stopBtn) { stopBtn.disabled = false; stopBtn.title = "Stop agent"; }
      break;
    }
    case "error":
      el("error", "error: " + (payload.msg || JSON.stringify(payload)));
      saveMsg(activeId, { kind: "error", text: payload.msg || JSON.stringify(payload) });
      setBusy(false); if (stopBtn) { stopBtn.disabled = false; stopBtn.title = "Stop agent"; }
      break;
    case "status":
      el("status", payload.msg || JSON.stringify(payload));
      saveMsg(activeId, { kind: "agent", text: payload.msg || JSON.stringify(payload) });
      if (payload.permission === "keyboard") showPermissionPopup(payload.tool || "keyboard/mouse");
      break;
    default:
      el("thought", `[${kind}] ${JSON.stringify(payload)}`);
  }
}

function renderStoredMsg(msg) {
  switch (msg.kind) {
    case "user": {
      const d = document.createElement("div");
      d.className = "msg user";
      if (msg.image && msg.image !== "[image]") {
        const img = document.createElement("img");
        img.src = msg.image; img.className = "chat-img";
        d.appendChild(img);
      } else if (msg.image === "[image]") {
        const note = document.createElement("em");
        note.textContent = "[image]"; note.style.opacity = "0.5";
        d.appendChild(note);
      }
      if (msg.text) d.appendChild(document.createTextNode(msg.text));
      chat.appendChild(d);
      break;
    }
    case "agent":      el("agent", msg.text); break;
    case "thought":    makeThoughtBubble(msg.text); break;
    case "tool": {
      const d = el("tool");
      const n = document.createElement("span"); n.className = "name"; n.textContent = msg.name; d.appendChild(n);
      // Replayed history mirrors the live render: tool name only.
      break;
    }
    case "observation": el("observation", msg.text); break;
    case "result": {
      if (msg.success) {
        const card = document.createElement("div");
        card.className = "msg resolution-card";
        card.innerHTML = `
          <div class="resolution-icon">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
          <h4>System Resolved</h4>
          <p>${esc(msg.summary || "Task completed successfully.")}</p>
          <button class="btn-confirm" disabled style="opacity:0.5;">Confirmed</button>`;
        chat.appendChild(card);
      } else {
        el("error", "Failed: " + (msg.summary || "Unknown error"));
      }
      break;
    }
    case "error": el("error", msg.text); break;
  }
}

function renderChat(id) {
  chat.innerHTML = "";
  setTyping(false);
  const conv = getConv(id);
  if (!conv || conv.messages.length === 0) {
    chat.innerHTML = INTRO_HTML;
    return;
  }
  for (const msg of conv.messages) renderStoredMsg(msg);
  chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
}

// ── Conversation List UI ──────────────────────────────────────────
function renderConvList() {
  const convs = loadConvs();
  const list = document.getElementById("conv-list");
  if (!list) return;
  list.innerHTML = convs.map(conv => `
    <div class="conv-item${conv.id === activeId ? " active" : ""}" data-id="${conv.id}">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;opacity:0.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
      <span class="conv-title">${esc(conv.title)}</span>
      <button class="conv-del" data-id="${conv.id}" title="Delete">
        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>`).join("");
}

document.addEventListener("click", (e) => {
  // Switch conversation
  const item = e.target.closest(".conv-item");
  const del  = e.target.closest(".conv-del");
  if (del) {
    e.stopPropagation();
    deleteConv(del.dataset.id);
    return;
  }
  if (item && item.dataset.id !== activeId) {
    setActive(item.dataset.id);
    renderChat(item.dataset.id);
    renderConvList();
    setBusy(false); if (stopBtn) { stopBtn.disabled = false; stopBtn.title = "Stop agent"; }
  }
  // New chat button
  if (e.target.closest("#btn-new-chat")) {
    const conv = createConv();
    setActive(conv.id);
    renderChat(conv.id);
    renderConvList();
    setBusy(false); if (stopBtn) { stopBtn.disabled = false; stopBtn.title = "Stop agent"; }
    input.focus();
  }
  // Suggestion chips
  if (e.target.classList.contains("chip")) {
    input.value = e.target.dataset.text;
    input.focus();
  }
  // Confirmed button
  if (e.target.classList.contains("btn-confirm") && !e.target.disabled) {
    e.target.disabled = true;
    e.target.textContent = "✓ Confirmed";
    e.target.style.background  = "rgba(74,222,128,0.15)";
    e.target.style.color       = "var(--ok)";
    e.target.style.borderColor = "rgba(74,222,128,0.4)";
    const newBtn = document.createElement("button");
    newBtn.className = "btn-new-issue";
    newBtn.textContent = "+ Start New Issue";
    newBtn.addEventListener("click", () => {
      const conv = createConv();
      setActive(conv.id);
      renderChat(conv.id);
      renderConvList();
      busy = false; sendBtn.disabled = false; setTyping(false);
      input.focus();
    });
    e.target.parentElement.appendChild(newBtn);
  }
});

// ── Image Upload ──────────────────────────────────────────────────
let pendingImage = null;
const imgBtn       = document.getElementById("img-btn");
const imgInput     = document.getElementById("img-input");
const imgPreviewBar   = document.getElementById("img-preview-bar");
const imgPreviewThumb = document.getElementById("img-preview-thumb");
const imgRemoveBtn    = document.getElementById("img-remove-btn");

imgBtn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); imgInput.click(); });

imgInput.addEventListener("change", () => {
  const file = imgInput.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    pendingImage = ev.target.result;
    imgPreviewThumb.src = pendingImage;
    imgPreviewBar.style.display = "block";
    imgInput.value = "";
  };
  reader.onerror = () => { imgInput.value = ""; };
  reader.readAsDataURL(file);
});

imgRemoveBtn.addEventListener("click", () => {
  pendingImage = null;
  imgPreviewBar.style.display = "none";
  imgPreviewThumb.src = "";
});

// ── Form Submit ───────────────────────────────────────────────────
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text && !pendingImage) return;
  if (busy) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    el("error", "Not connected — please wait a moment and try again.");
    return;
  }

  const intro = chat.querySelector(".intro");
  if (intro) intro.remove();

  const userMsg = document.createElement("div");
  userMsg.className = "msg user";
  if (pendingImage) {
    const img = document.createElement("img");
    img.src = pendingImage; img.className = "chat-img";
    userMsg.appendChild(img);
  }
  if (text) userMsg.appendChild(document.createTextNode(text));
  chat.appendChild(userMsg);
  chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });

  saveMsg(activeId, { kind: "user", text, image: pendingImage || null });
  if (text) updateTitle(activeId, text);

  // Read the current mode from the dropdown ("control" = voodo clicks,
  // "guide" = voodo only highlights where to click).
  const activeOpt = document.querySelector(".model-option.active");
  const mode = (activeOpt && activeOpt.dataset.value) === "guide" ? "guide" : "control";
  ws.send(JSON.stringify({ type: "message", text, image: pendingImage || null, mode }));

  input.value = "";
  pendingImage = null;
  imgPreviewBar.style.display = "none";
  imgPreviewThumb.src = "";
  setTyping(true);
  setBusy(true);
});

// ── Drag & Drop ───────────────────────────────────────────────────
const inputWrapper = document.querySelector(".input-wrapper");

inputWrapper.addEventListener("dragover",  (e) => { e.preventDefault(); inputWrapper.classList.add("drag-over"); });
inputWrapper.addEventListener("dragleave", ()  => { inputWrapper.classList.remove("drag-over"); });
inputWrapper.addEventListener("drop", (e) => {
  e.preventDefault();
  inputWrapper.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (!file || !file.type.startsWith("image/")) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    pendingImage = ev.target.result;
    imgPreviewThumb.src = pendingImage;
    imgPreviewBar.style.display = "block";
  };
  reader.readAsDataURL(file);
});

// ── Init ──────────────────────────────────────────────────────────
// `?new=1` (used by client/scripts/dev_all.ps1 when it opens the browser
// after a fresh executor launch) forces a new conversation so the
// user lands on a blank feed instead of seeing the previous chat.
// Strip the param from the URL after consuming it so a refresh
// doesn't keep spawning new conversations.
const _params = new URLSearchParams(window.location.search);
if (_params.get("new") === "1") {
  setActive(createConv().id);
  const clean = window.location.pathname + window.location.hash;
  window.history.replaceState({}, document.title, clean);
}
ensureActive();
renderConvList();
renderChat(activeId);
connect();

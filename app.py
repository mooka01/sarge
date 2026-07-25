"""M1083A1 Service Bay — web front end.

Home is a diagnostic chat grounded in the Tier 1 index: each turn retrieves
manual pages (hybrid keyword+semantic), Claude answers with [[MANUAL|PAGE]]
citations rendered as links to the page-image viewer, and a validation pass
flags fabricated citations / ungrounded numbers. Search and structured intake
remain as secondary views. No external assets — works offline except the
chat itself.

Run:  python app.py   →  http://127.0.0.1:8383
"""

import html
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path

from flask import (Flask, Response, abort, redirect, render_template_string,
                   request, send_file, url_for)

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "ingest"))
from render_page import render as render_page_image  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "corpus" / "index.sqlite"
SESSIONS_DIR = REPO_ROOT / "sessions"
AS_BUILT = REPO_ROOT / "AS_BUILT_CONFIGURATION.md"

app = Flask(__name__)

# ---------------------------------------------------------------- templates

BASE = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — SARGE</title>
<style>
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #1a1d21; --muted: #5f6b7a;
  --line: #dde3ea; --accent: #b45f2a; --accent-ink: #fff;
  --user-bubble: #2f5d8a; --warn-bg: #fdf3e4; --warn-line: #e2b06a;
  --ok: #2e7d4f; --mono: ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171b; --panel: #1d2126; --ink: #e6e9ed; --muted: #98a3b0;
    --line: #313842; --accent: #d07a3f; --user-bubble: #2b5379;
    --warn-bg: #2a2416; --warn-line: #8a6a35; --ok: #58b384;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 system-ui, "Segoe UI", sans-serif; }
header { position: sticky; top: 0; z-index: 5; background: var(--panel);
  border-bottom: 1px solid var(--line); }
.hwrap { max-width: 62rem; margin: 0 auto; padding: .55rem 1rem;
  display: flex; align-items: center; gap: 1rem; flex-wrap: nowrap; }
.brand { font-weight: 700; letter-spacing: .02em; text-decoration: none;
  color: var(--ink); white-space: nowrap; flex: none; }
.brand span { color: var(--accent); }
nav { display: flex; overflow-x: auto; scrollbar-width: none; min-width: 0; }
nav a { color: var(--muted); text-decoration: none; margin-right: 1rem;
  padding: .3rem 0; border-bottom: 2px solid transparent; flex: none; }
nav a.active { color: var(--ink); border-bottom-color: var(--accent); }
nav a:hover { color: var(--ink); }
@media (max-width: 560px) {
  .brand { font-size: .85rem; }
  .brand span { display: none; }
  nav a { font-size: .9rem; margin-right: .8rem; }
}
main { max-width: 62rem; margin: 0 auto; padding: 1.2rem 1rem 4rem; }
a { color: var(--accent); }
.card { background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 1rem 1.2rem; margin: .9rem 0; }
.authority { background: var(--warn-bg); border: 1px solid var(--warn-line);
  border-radius: 10px; padding: .6rem .9rem; font-size: .85rem;
  color: var(--ink); margin: .8rem 0; }
button, .btn { background: var(--accent); color: var(--accent-ink);
  border: 0; border-radius: 8px; padding: .55rem 1.1rem; font-size: .95rem;
  cursor: pointer; }
button:hover { filter: brightness(1.08); }
input[type=text], textarea, select { width: 100%; background: var(--bg);
  color: var(--ink); border: 1px solid var(--line); border-radius: 8px;
  padding: .55rem .7rem; font: inherit; }
label { display: block; margin: .8rem 0 .2rem; font-weight: 600;
  font-size: .88rem; }
.hit { border-left: 3px solid var(--accent); padding: .5rem .9rem;
  margin: .7rem 0; background: var(--panel); border-radius: 0 10px 10px 0;
  border-top: 1px solid var(--line); border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line); }
.hit .loc { font-weight: 600; font-size: .92rem; }
.hit .snip { color: var(--muted); font-size: .9rem; }
mark { background: color-mix(in srgb, var(--accent) 30%, transparent);
  color: inherit; border-radius: 3px; padding: 0 2px; }
img.page { max-width: 100%; border: 1px solid var(--line); border-radius: 8px; }
/* chat layout: left drawer + chat column */
main.chat { max-width: 100rem; padding: 0 1rem; }
#chatwrap { display: flex; gap: 1rem; height: calc(100vh - 3.6rem); }
#drawer { flex: 0 0 17rem; display: flex; flex-direction: column;
  gap: .5rem; padding: 1rem 0; overflow: hidden; }
#convList { flex: 1 1 auto; overflow-y: auto; min-height: 5rem;
  border-bottom: 1px solid var(--line); padding-bottom: .4rem; }
#drawer .dhead { font-size: .78rem; font-weight: 700; color: var(--muted);
  text-transform: uppercase; letter-spacing: .06em; margin-top: .6rem; }
.conv { padding: .5rem .7rem; border-radius: 8px; cursor: pointer;
  border: 1px solid transparent; }
.conv:hover { background: var(--panel); border-color: var(--line); }
.conv.active { background: var(--panel); border-color: var(--accent); }
.conv .t { font-size: .88rem; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }
.conv .d { font-size: .75rem; color: var(--muted); }
.btn-ghost { background: transparent; color: var(--accent);
  border: 1px solid var(--accent); }
#chatcol { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#chatlog { flex: 1; overflow-y: auto; display: flex; flex-direction: column;
  gap: .8rem; padding: 1rem .2rem; }
.msg { max-width: 88%; padding: .7rem 1rem; border-radius: 14px;
  white-space: pre-wrap; overflow-wrap: break-word; }
.msg.user { align-self: flex-end; background: var(--user-bubble);
  color: #fff; border-bottom-right-radius: 4px; }
.msg.ai { align-self: flex-start; background: var(--panel);
  border: 1px solid var(--line); border-bottom-left-radius: 4px; }
.msg.ai .val { margin-top: .6rem; padding-top: .5rem;
  border-top: 1px dashed var(--line); font-size: .82rem; color: var(--muted); }
.msg.ai .val .bad { color: #c0392b; }
.msg.ai .val .good { color: var(--ok); }
#composer { border-top: 1px solid var(--line); background: var(--panel);
  border-radius: 12px 12px 0 0; padding: .6rem .8rem; }
#composer .row { display: flex; gap: .6rem; }
#composer input[type=text] { flex: 1 1 0; width: auto; min-width: 0;
  font-size: 1rem; }
#composer .row button { flex: none; }
#composer .tools { flex-wrap: wrap; }
#chatwrap, #chatcol, #composer { max-width: 100%; min-width: 0; }
#composer .tools { display: flex; gap: .5rem; align-items: center;
  margin-bottom: .45rem; }
#composer .tools select { width: auto; max-width: 22rem; font-size: .82rem;
  padding: .3rem .5rem; }
#menuBtn { display: none; padding: .25rem .6rem; flex: none; }
@media (max-width: 820px) {
  #menuBtn { display: inline-block; }
  #drawer { position: fixed; left: 0; top: 0; bottom: 0; z-index: 20;
    background: var(--bg); padding: 1rem; width: 17rem;
    border-right: 1px solid var(--line); transform: translateX(-100%);
    transition: transform .18s ease; }
  #drawer.open { transform: none; box-shadow: 0 0 40px rgba(0,0,0,.4); }
}
.hint { color: var(--muted); font-size: .85rem; }
.spin { display: inline-block; width: 1em; height: 1em; vertical-align: -2px;
  border: 2px solid var(--muted); border-top-color: transparent;
  border-radius: 50%; animation: r 0.8s linear infinite; }
@keyframes r { to { transform: rotate(360deg); } }
h2 { font-size: 1.15rem; }
table { border-collapse: collapse; }
td, th { padding: .3rem .6rem; border-bottom: 1px solid var(--line); }
fieldset.group { border: 1px solid var(--line); border-radius: 10px;
  margin: 1rem 0; padding: .4rem 1rem .9rem; }
fieldset.group legend { font-weight: 700; font-size: .82rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: .06em; padding: 0 .4rem; }
</style></head><body>
<header><div class="hwrap">
  {% if active == 'chat' %}<button id="menuBtn" class="btn-ghost" title="Conversations">☰</button>{% endif %}
  <a class="brand" href="/">SARGE&nbsp;<span>SERVICE&nbsp;BAY</span></a>
  <nav>
    <a href="/" class="{{ 'active' if active == 'chat' else '' }}">Diagnose</a>
    <a href="/search" class="{{ 'active' if active == 'search' else '' }}">Search</a>
    <a href="/intake" class="{{ 'active' if active == 'intake' else '' }}">Intake</a>
    <a href="/knowledge" class="{{ 'active' if active == 'knowledge' else '' }}">Knowledge</a>
    <a href="/config" class="{{ 'active' if active == 'config' else '' }}">My truck</a>
  </nav>
</div></header>
<main class="{{ mainclass }}">{{ body|safe }}</main>
</body></html>
"""

CHAT_BODY = """
<div id="chatwrap">
<aside id="drawer">
  <button id="newChat" style="width:100%">＋ New conversation</button>
  <div class="dhead">Conversations</div>
  <div id="convList"></div>
  <div class="dhead">Scope</div>
  <select id="scopeSel" title="Which side of the truck to search: chassis manuals, habitat/RV manuals, or both">
    <option value="both">Chassis + habitat</option>
    <option value="chassis">Chassis only</option>
    <option value="habitat">Habitat (RV box) only</option>
  </select>
  <div class="dhead">Field reports</div>
  <label style="font-weight:400;font-size:.85rem;display:flex;gap:.4rem;align-items:center">
    <input type="checkbox" id="forumsChk" style="width:auto">
    live-search Steel Soldiers (Tier 2, anecdotal)
  </label>
  <div class="dhead">Model</div>
  <select id="backendSel" title="Claude needs connectivity; the local model works offline but is much weaker — validation flags matter more there">
    <option value="claude">Claude (online, best)</option>
    <option value="ollama">Local / offline (Ollama)</option>
  </select>
  <div class="dhead">Attach intake to next message</div>
  <select id="intakeSel" title="Attach a filed intake to your next message">
    <option value="">no intake attached</option>
  </select>
  <button id="helpPost" class="btn-ghost" style="width:100%"
    title="Draft a structured post for a forum or group from this conversation">📢 Draft help post</button>
</aside>
<section id="chatcol">
  <div id="chatlog"></div>
  <div id="composer">
    <div class="tools">
      <span id="attachNote" class="hint" style="display:none"></span>
      <span class="hint">page-image citations are the authority — verify [A] specs before wrenching</span>
    </div>
    <div class="row">
      <button id="photoBtn" class="btn-ghost" title="Attach photos (gauge faces, leaks, parts)">📷</button>
      <input type="file" id="photoInput" accept="image/*" multiple hidden>
      <input id="box" type="text" placeholder="What's the issue? (e.g. slow air buildup, 8 minutes to 120 psi, no audible leaks)" autofocus>
      <button id="send">Send</button>
    </div>
  </div>
</section>
</div>
<script>
const log = document.getElementById("chatlog");
const box = document.getElementById("box");
const send = document.getElementById("send");
const drawer = document.getElementById("drawer");
const convList = document.getElementById("convList");
const intakeSel = document.getElementById("intakeSel");
let chatId = sessionStorage.getItem("chatId") ||
  (sessionStorage.setItem("chatId", crypto.randomUUID()), sessionStorage.getItem("chatId"));

function cite(text) {
  let esc = text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  esc = esc.replace(/\\*\\*([^*\\n]+)\\*\\*/g, "<b>$1</b>");
  return esc.replace(/\\[\\[([A-Za-z0-9._-]+)\\|(\\d+)\\]\\]/g,
    (_, m, p) => `<a href="/page/${m}/${p}" target="_blank">[${m.replace("TM-9-2320-366-","TM ")} p.${p}]</a>`);
}
function bubble(cls, html) {
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = html;
  log.appendChild(d);
  d.scrollIntoView({behavior: "smooth", block: "end"});
  return d;
}

function loadChatList() {
  fetch("/api/chats").then(r => r.json()).then(list => {
    convList.innerHTML = "";
    for (const ch of list) {
      const d = document.createElement("div");
      d.className = "conv" + (ch.id === chatId ? " active" : "");
      d.innerHTML = `<div class="t"></div><div class="d">${ch.date} · ${ch.turns} turn${ch.turns == 1 ? "" : "s"}</div>`;
      d.querySelector(".t").textContent = ch.title || "(untitled)";
      d.title = ch.title || "";
      d.onclick = () => { openChat(ch.id); drawer.classList.remove("open"); };
      convList.appendChild(d);
    }
  });
}
async function openChat(id) {
  chatId = id;
  sessionStorage.setItem("chatId", id);
  log.innerHTML = "";
  const msgs = await (await fetch(`/api/chats/${id}/history`)).json();
  for (const m of msgs)
    bubble(m.role === "user" ? "user" : "ai", cite(m.content));
  if (log.lastChild) log.lastChild.scrollIntoView({block: "end"});
  loadChatList();
}
document.getElementById("newChat").onclick = () => {
  chatId = crypto.randomUUID();
  sessionStorage.setItem("chatId", chatId);
  log.innerHTML = "";
  drawer.classList.remove("open");
  loadChatList();
  box.focus();
};
document.getElementById("menuBtn").onclick = () =>
  drawer.classList.toggle("open");

document.getElementById("helpPost").onclick = async () => {
  drawer.classList.remove("open");
  const ai = bubble("ai", '<span class="spin"></span> drafting help post…');
  try {
    const r = await fetch("/api/helppost", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({chat_id: chatId, intake: intakeSel.value}),
    });
    if (!r.ok) { ai.innerHTML = "Error: " + (await r.text()); return; }
    const text = await r.text();
    ai.innerHTML = "<b>Draft help post — review before posting:</b>" +
      '<textarea style="width:100%;height:16rem;margin-top:.5rem;font-family:var(--mono);font-size:.82rem">' +
      text.replace(/&/g,"&amp;").replace(/</g,"&lt;") + "</textarea>" +
      '<button onclick="navigator.clipboard.writeText(this.previousElementSibling.value);this.textContent=\\'copied ✓\\'">copy</button>';
    ai.scrollIntoView({block: "end"});
  } catch (e) { ai.innerHTML = "Error: " + e; }
};

const backendSel = document.getElementById("backendSel");
backendSel.value = localStorage.getItem("backend") || "claude";
backendSel.addEventListener("change", () =>
  localStorage.setItem("backend", backendSel.value));

const attachNote = document.getElementById("attachNote");
const photoInput = document.getElementById("photoInput");
let photos = [];
document.getElementById("photoBtn").onclick = () => photoInput.click();
photoInput.addEventListener("change", async () => {
  for (const f of photoInput.files) {
    if (photos.length >= 4) break;
    photos.push(await downscale(f));
  }
  photoInput.value = "";
  showAttach();
});
function downscale(file) {
  return new Promise(res => {
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, 1600 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      res(c.toDataURL("image/jpeg", 0.85));
    };
    img.src = URL.createObjectURL(file);
  });
}
function showAttach() {
  const bits = [];
  if (intakeSel.value) bits.push("📋 intake " + intakeSel.value);
  if (photos.length) bits.push("📷 " + photos.length + " photo(s)");
  attachNote.style.display = bits.length ? "" : "none";
  attachNote.textContent = bits.length ? "next message includes: " + bits.join(", ") : "";
}
intakeSel.addEventListener("change", showAttach);

fetch("/api/intakes").then(r => r.json()).then(list => {
  for (const it of list) {
    const o = document.createElement("option");
    o.value = it.file;
    o.textContent = `${it.date} — ${it.category}: ${it.symptom}`;
    intakeSel.appendChild(o);
  }
  const params = new URLSearchParams(location.search);
  const shareChat = params.get("chat");
  if (shareChat && /^[0-9a-f-]{36}$/.test(shareChat)) openChat(shareChat);
  const want = params.get("intake");
  if (want) { intakeSel.value = want; showAttach(); }
  if (want && params.get("auto") === "1") {
    history.replaceState(null, "", "/");   // don't re-fire on refresh
    chatId = crypto.randomUUID();          // fresh conversation per intake
    sessionStorage.setItem("chatId", chatId);
    log.innerHTML = "";
    intakeSel.value = want;
    box.value = "Analyze this intake: rank the likely causes and give me " +
                "the first test to run.";
    ask();
  }
});

async function ask() {
  const q = box.value.trim();
  if (!q) return;
  box.value = ""; box.disabled = send.disabled = true;
  const attach = intakeSel.value;
  const sendPhotos = photos; photos = [];
  if (attach) bubble("user", "📋 attached intake: " + attach);
  if (sendPhotos.length) {
    const pb = bubble("user", "");
    pb.innerHTML = sendPhotos.map(d => `<img src="${d}" style="max-width:9rem;border-radius:8px;margin:.15rem">`).join("");
  }
  bubble("user", cite(q));
  intakeSel.value = "";
  showAttach();
  const ai = bubble("ai", '<span class="spin"></span> retrieving manual pages…');
  let raw = "";
  try {
    const r = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({chat_id: chatId, message: q, intake: attach,
                            backend: backendSel.value, photos: sendPhotos,
                            forums: document.getElementById("forumsChk").checked,
                            scope: document.getElementById("scopeSel").value}),
    });
    if (!r.ok) { ai.innerHTML = "Error: " + (await r.text()); return; }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      raw += dec.decode(value, {stream: true});
      const parts = raw.split("\\u241E");   // answer ␞ validation-json
      ai.innerHTML = cite(parts[0]);
      if (parts.length > 1 && parts[1].trim()) {
        try {
          const v = JSON.parse(parts[1]);
          ai.innerHTML = cite(parts[0]) + '<div class="val">' + (
            v.problems.length
              ? v.problems.map(p => '<div class="bad">⚠ ' + p + "</div>").join("")
              : '<div class="good">✓ citations verified against index; numbers grounded in cited pages</div>'
          ) + "</div>";
        } catch (e) {}
      }
      log.lastChild.scrollIntoView({block: "end"});
    }
  } catch (e) { ai.innerHTML = "Connection error: " + e; }
  finally {
    box.disabled = send.disabled = false; box.focus();
    loadChatList();
  }
}
send.onclick = ask;
box.addEventListener("keydown", e => { if (e.key === "Enter") ask(); });

loadChatList();
// restore this tab's conversation on load (unless auto-analysis replaces it)
if (!new URLSearchParams(location.search).get("auto"))
  fetch(`/api/chats/${chatId}/history`).then(r => r.json()).then(msgs => {
    if (log.children.length === 0)
      for (const m of msgs)
        bubble(m.role === "user" ? "user" : "ai", cite(m.content));
  });
</script>
"""


def page(title: str, body: str, active: str = "", mainclass: str = "") -> str:
    return render_template_string(BASE, title=title, body=body, active=active,
                                  mainclass=mainclass)


def db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


@app.after_request
def no_cache_html(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _model() -> str:
    from backends import get_config
    return get_config()["claude_model"]


AUTHORITY_NOTE = (
    '<div class="authority"><b>Governing rule:</b> the page image is the '
    'authority. Verify every numeric value against the image before acting '
    'on it. Extracted text and search snippets are advisory.</div>'
)

# ---------------------------------------------------------------- chat


@app.route("/")
def home():
    return page("Diagnose", CHAT_BODY, active="chat", mainclass="chat")


@app.route("/api/chats")
def api_chats():
    out = []
    for f in sorted(SESSIONS_DIR.glob("chat-*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)[:60]:
        try:
            msgs = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        first = next((m["content"] for m in msgs if m["role"] == "user"), "")
        # skip the intake dump if that's how the chat started
        title = re.sub(r"^STRUCTURED INTAKE.*?:\n(- .+\n?)*\n*", "", first,
                       flags=re.S).strip() or first.strip()
        out.append({
            "id": f.stem.replace("chat-", ""),
            "date": time.strftime("%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
            "title": title[:70],
            "turns": sum(1 for m in msgs if m["role"] == "user"),
        })
    return json.dumps(out), 200, {"Content-Type": "application/json"}


@app.route("/api/chats/<chat_id>/history")
def api_chat_history(chat_id):
    if not re.fullmatch(r"[0-9a-f-]{36}", chat_id):
        abort(400)
    f = SESSIONS_DIR / f"chat-{chat_id}.json"
    if not f.exists():
        return "[]", 200, {"Content-Type": "application/json"}
    return f.read_text(encoding="utf-8"), 200, {"Content-Type": "application/json"}


@app.route("/api/intakes")
def api_intakes():
    out = []
    for f in sorted(SESSIONS_DIR.glob("intake-*.json"), reverse=True)[:25]:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        fields = rec.get("fields", {})
        out.append({
            "file": f.name,
            "date": rec.get("filed_utc", "")[:16].replace("T", " "),
            "category": rec.get("category", fields.get("complaint", "?")),
            "symptom": (fields.get("symptom") or "")[:60],
        })
    return json.dumps(out), 200, {"Content-Type": "application/json"}


def _load_intake_text(name: str) -> str:
    if not re.fullmatch(r"intake-[\d-]+\.json", name):
        abort(400)
    path = SESSIONS_DIR / name
    if not path.exists():
        abort(404)
    rec = json.loads(path.read_text(encoding="utf-8"))
    fields = {k: v for k, v in rec.get("fields", {}).items() if v}
    lines = [f"- {k}: {v}" for k, v in fields.items()]
    return (f"STRUCTURED INTAKE (filed {rec.get('filed_utc', '?')}, "
            f"category: {rec.get('category', '?')}):\n" + "\n".join(lines))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    import diagnose as dx
    import anthropic

    data = request.get_json(force=True)
    chat_id = data.get("chat_id", "")
    message = (data.get("message") or "").strip()
    if not message or not re.fullmatch(r"[0-9a-f-]{36}", chat_id):
        abort(400)
    intake_name = (data.get("intake") or "").strip()
    if intake_name:
        message = _load_intake_text(intake_name) + "\n\n" + message
    # photos: data URLs from the composer (client already downscaled)
    photo_blocks = []
    for durl in (data.get("photos") or [])[:4]:
        m = re.match(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$",
                     durl)
        if m:
            photo_blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": m.group(1),
                "data": m.group(2)}})
    use_forums = bool(data.get("forums"))

    SESSIONS_DIR.mkdir(exist_ok=True)
    hist_file = SESSIONS_DIR / f"chat-{chat_id}.json"
    history = (json.loads(hist_file.read_text(encoding="utf-8"))
               if hist_file.exists() else [])

    # retrieve on the new message plus a little recent context
    scope = data.get("scope", "both")
    domains = None if scope == "both" else [scope, "shared"]
    from retrieval import hybrid_search
    recent = " ".join(m["content"][-500:] for m in history[-2:] if m["role"] == "user")
    pages_used = hybrid_search((recent + " " + message).strip(), 8, domains)

    turn = (
        "RETRIEVED TIER 1 SOURCE PAGES for this turn (your ONLY permitted "
        "source for specs and procedures):\n\n" + dx.build_context(pages_used)
        + "\n\n=====\n\n" + message
    )
    turn_content = (photo_blocks + [{"type": "text", "text": turn}]
                    if photo_blocks else turn)
    system = [
        {"type": "text",
         "text": dx.SYSTEM
         + (dx.TIER2_ADDENDUM if use_forums else "")
         + "\nThis is an ongoing chat with the owner at the truck. Be "
           "conversational and brief; give ONE next test at a time and ask "
           "for its result. Full test-card formality only when concluding."
           "\nIf the owner attached photos, read them carefully (gauges, "
           "labels, part markings, leak evidence) and treat what you see "
           "as measured evidence [B]."
         + "\n\nAS-BUILT CONFIGURATION (canonical dossier):\n"
         + as_built_text(),
         "cache_control": {"type": "ephemeral"}},
    ]
    messages = history + [{"role": "user", "content": turn_content}]
    tools = ([{"type": "web_search_20260209", "name": "web_search",
               "max_uses": 5, "allowed_domains": ["steelsoldiers.com"]}]
             if use_forums else [])

    backend = data.get("backend", "claude")

    def generate():
        answer = []
        try:
            if backend == "ollama":
                import backends
                yield ("⚠ OFFLINE MODE (local model) — weaker reasoning; "
                       "expect validation flags; treat everything as [C] "
                       "at best.\n\n")
                sys_text = "".join(b["text"] for b in system)
                for piece in backends.ollama_stream(sys_text, messages):
                    answer.append(piece)
                    yield piece
            else:
                client = anthropic.Anthropic()
                convo = list(messages)
                for _ in range(4):   # pause_turn continuations (web search)
                    with client.messages.stream(
                        model=_model(),
                        max_tokens=8000,
                        thinking={"type": "adaptive"},
                        system=system,
                        tools=tools,
                        messages=convo,
                    ) as stream:
                        for text in stream.text_stream:
                            answer.append(text)
                            yield text
                        resp = stream.get_final_message()
                    if resp.stop_reason != "pause_turn":
                        break
                    convo = convo + [{"role": "assistant", "content": resp.content}]
        except Exception as e:
            yield f"\n[error: {e}]"
            return
        full = "".join(answer)
        problems = dx.validate(full, pages_used)
        # persist history (text only; photos noted, saved alongside)
        note = message
        if photo_blocks:
            import base64 as _b64
            pdir = SESSIONS_DIR / "photos"
            pdir.mkdir(exist_ok=True)
            for i, blk in enumerate(photo_blocks):
                (pdir / f"{chat_id}-{int(time.time())}-{i}.jpg").write_bytes(
                    _b64.b64decode(blk["source"]["data"]))
            note += f"\n[{len(photo_blocks)} photo(s) attached]"
        history.append({"role": "user", "content": note})
        history.append({"role": "assistant", "content": full})
        hist_file.write_text(json.dumps(history, indent=1), encoding="utf-8")
        yield "␞" + json.dumps({"problems": problems})

    return Response(generate(), mimetype="text/plain")


HELP_POST_SYSTEM = """\
You draft a "call for help" post for a military-vehicle forum or owners group,
on behalf of the owner of a 2003 M1083A1 FMTV. Input: the diagnostic chat so
far and possibly a structured intake. Write a post another owner or mechanic
can act on in one read:

**Title line** — vehicle + symptom in under 12 words.
**Vehicle** — model/year/engine/trans + ONLY the as-built deviations relevant
to this problem (e.g. eco-hub conversion, aux flat-tow brake module).
**Symptom** — what happens, when, conditions. Measurements with numbers.
**What I've checked so far** — each test done, how, and its result. Include
TM references as plain text (e.g. "per TM 9-2320-366-20-2 air system
troubleshooting") — no [[...]] markup, forums can't render it.
**Current leads** — ranked hypotheses, honestly labeled as unconfirmed.
**Questions** — 2-4 specific questions for the group.

Plain text with simple bold headings. First person, concise, no fluff, no
AI-isms. Do not invent tests or measurements not present in the input; if
little has been tested, say so honestly."""


@app.route("/api/helppost", methods=["POST"])
def api_helppost():
    import anthropic
    data = request.get_json(force=True)
    chat_id = data.get("chat_id", "")
    if not re.fullmatch(r"[0-9a-f-]{36}", chat_id):
        abort(400)
    hist_file = SESSIONS_DIR / f"chat-{chat_id}.json"
    history = (json.loads(hist_file.read_text(encoding="utf-8"))
               if hist_file.exists() else [])
    intake_name = (data.get("intake") or "").strip()
    parts = []
    if intake_name:
        parts.append(_load_intake_text(intake_name))
    if history:
        convo = "\n\n".join(
            f"{'OWNER' if m['role'] == 'user' else 'DIAGNOSTIC AI'}: {m['content']}"
            for m in history)
        parts.append("DIAGNOSTIC CHAT SO FAR:\n" + convo)
    if not parts:
        return ("Nothing to summarize yet — describe the issue in chat or "
                "attach an intake first."), 400
    parts.append("AS-BUILT DOSSIER:\n" + as_built_text())

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=_model(),
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=HELP_POST_SYSTEM,
        messages=[{"role": "user", "content": "\n\n=====\n\n".join(parts)}],
    ) as stream:
        response = stream.get_final_message()
    text = "".join(b.text for b in response.content if b.type == "text")
    return Response(text, mimetype="text/plain")


# ---------------------------------------------------------------- search


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    body = [
        '<form action="/search" style="display:flex;gap:.6rem;margin:.4rem 0 1rem">'
        f'<input type="text" name="q" value="{html.escape(q)}" '
        'placeholder="e.g. governor cutout pressure, slack adjuster, flash code 25">'
        "<button>Search</button></form>"
    ]
    if q:
        from retrieval import fts_query
        con = db()
        sql = """SELECT p.manual, p.pdf_page, p.printed_page, p.paragraph,
                        p.paragraph_title,
                        snippet(pages_fts, 0, '<mark>', '</mark>', ' … ', 28)
                 FROM pages_fts f JOIN pages p ON p.id = f.rowid
                 WHERE pages_fts MATCH ? AND p.kind = 'content'
                 ORDER BY rank LIMIT 20"""
        rows = con.execute(sql, (fts_query(q),)).fetchall()
        if not rows:
            rows = con.execute(sql, (fts_query(q, any_word=True),)).fetchall()
            if rows:
                body.append("<p class='hint'>No page matched every term; "
                            "best partial matches:</p>")
        con.close()
        body.append(AUTHORITY_NOTE)
        if not rows:
            body.append("<p>No hits.</p>")
        for manual, pdf_page, printed, para, title, snip in rows:
            href = url_for("view_page", manual=manual, pdf_page=pdf_page)
            paras = f" &nbsp;·&nbsp; ¶ {para} {title or ''}" if para else ""
            body.append(
                f'<div class="hit"><div class="loc"><a href="{href}">{manual}'
                f' — printed p.{printed or "?"}</a>{paras}</div>'
                f'<div class="snip">{snip}</div></div>'
            )
    return page("Search", "\n".join(body), active="search")


# ---------------------------------------------------------------- page viewer


@app.route("/page/<manual>/<int:pdf_page>")
def view_page(manual, pdf_page):
    con = db()
    row = con.execute(
        "SELECT printed_page, paragraph, paragraph_title,"
        " (SELECT MAX(pdf_page) FROM pages WHERE manual = ?)"
        " FROM pages WHERE manual = ? AND pdf_page = ?",
        (manual, manual, pdf_page),
    ).fetchone()
    con.close()
    if not row:
        abort(404)
    printed, para, title, last = row
    img = url_for("page_image", manual=manual, pdf_page=pdf_page)
    nav = []
    if pdf_page > 0:
        nav.append(f'<a href="{url_for("view_page", manual=manual, pdf_page=pdf_page-1)}">&larr; prev</a>')
    if pdf_page < last:
        nav.append(f'<a href="{url_for("view_page", manual=manual, pdf_page=pdf_page+1)}">next &rarr;</a>')
    body = (
        f"<p><b>{manual}</b> — printed page <b>{printed or '?'}</b>"
        + (f" — ¶ {para} {title or ''}" if para else "")
        + f" (pdf page {pdf_page}) &nbsp; {' '.join(nav)}</p>"
        + AUTHORITY_NOTE
        + f'<img class="page" src="{img}" alt="{manual} page {printed or pdf_page}">'
    )
    return page(f"{manual} p.{printed or pdf_page}", body)


@app.route("/image/<manual>/<int:pdf_page>.png")
def page_image(manual, pdf_page):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", manual):
        abort(400)
    try:
        return send_file(render_page_image(manual, pdf_page))
    except (FileNotFoundError, RuntimeError, SystemExit):
        return Response(
            f"Page image unavailable: the PDF for {manual} is not in "
            "corpus/raw. Run  python bootstrap_fmtv.py  (or upload it on the "
            "Knowledge page) to enable the page-image authority layer.",
            status=404, mimetype="text/plain")


# ---------------------------------------------------------------- intake

# One adaptive intake (brief §3.1): the complaint category surfaces the
# measurement fields relevant to that system. Common fields always show.
INTAKE_COMMON_TOP = [
    ("symptom", "Symptom description (what, when, how bad)", "textarea"),
    ("onset", "Onset", ["Sudden", "Gradual", "After recent work", "Unknown"]),
    ("frequency", "Constant or intermittent?", ["Constant", "Intermittent"]),
    ("ambient", "Ambient temperature", "text"),
]
INTAKE_COMMON_BOTTOM = [
    ("warnings", "Warning lights / buzzer / codes displayed", "text"),
    ("recent_work", "Recent work done on the truck", "textarea"),
    ("still_works", "What still works normally", "textarea"),
    ("measurements", "Other measurements (instrument, lead/tap location, conditions, value)", "textarea"),
]
INTAKE_CATEGORIES = {
    "Air system / brakes": [
        ("primary_psi", "Primary gauge reading (psi)", "text"),
        ("secondary_psi", "Secondary gauge reading (psi)", "text"),
        ("buildup_time", "Time to build 0→governor cutout (min:sec, ~1500 RPM)", "text"),
        ("leakdown", "Leak-down rate, engine off, brakes released (psi/min)", "text"),
        ("leakdown_applied", "Leak-down rate, brakes applied (psi/min)", "text"),
        ("cut_in", "Observed governor cut-in (psi)", "text"),
        ("cut_out", "Observed governor cut-out (psi)", "text"),
        ("abs_light", "ABS lamp behavior (on/off/blink pattern)", "text"),
    ],
    "Engine (Cat 3126E)": [
        ("codes", "Flash codes / Cat ET codes (e.g. 25, 164-02)", "text"),
        ("starts", "Cranks? Starts? Cranking speed sound", "text"),
        ("oil_psi", "Oil pressure (idle / operating rpm)", "text"),
        ("coolant_temp", "Coolant temp when symptom occurs", "text"),
        ("boost", "Boost reading under load (if known)", "text"),
        ("smoke", "Exhaust smoke (color, when)", "text"),
        ("fuel", "Fuel level/filters age, any recent fuel work", "text"),
        ("engine_rpm", "RPM where symptom occurs", "text"),
    ],
    "Transmission (Allison MD3070PT)": [
        ("trans_codes", "Shift selector codes (d1/d2 display)", "text"),
        ("fluid", "Fluid level and condition (checked how?)", "text"),
        ("trans_temp", "Transmission temp when symptom occurs", "text"),
        ("ranges", "Which ranges work / don't (R, N, D, low)", "text"),
        ("shift_quality", "Shift quality (flare, slip, harsh, hunting)", "text"),
    ],
    "CTIS": [
        ("ctis_lights", "ECU indicator lights (how many, flash pattern)", "text"),
        ("ctis_mode", "Mode selected (highway/cross-country/mud-sand/emergency)", "text"),
        ("axle_behavior", "Per-axle behavior (which inflate/deflate, which don't)", "text"),
        ("tire_psi", "Actual tire pressures if measured", "text"),
    ],
    "Electrical (24V system, 24→12V converter)": [
        ("bus_affected", "Which side is affected?", ["24V side", "12V side (fed by converter)", "Both", "Unknown"]),
        ("batt_v_off", "Battery voltage, key off (measured at batteries, V)", "text"),
        ("batt_v_crank", "Battery voltage while cranking (V)", "text"),
        ("batt_v_run", "Voltage engine running — 24V bus (V)", "text"),
        ("conv_12v_out", "24→12V converter output, engine running (V)", "text"),
        ("gauge_v", "Dash voltmeter/gauge reading vs meter reading", "text"),
        ("alt_output", "Alternator output if measured (V / A)", "text"),
        ("circuits", "Which circuits dead or misbehaving", "text"),
        ("fuses", "Fuses/breakers checked (which, result)", "text"),
        ("batt_age", "Battery age/condition, terminals & grounds checked?", "text"),
    ],
    "Cooling": [
        ("temp_gauge", "Temp gauge reading and conditions", "text"),
        ("fan", "Fan clutch engaging? (audible roar at temp)", "text"),
        ("coolant_loss", "Coolant loss rate / where", "text"),
    ],
    "Driveline / axles / hubs": [
        ("noise", "Noise or vibration (describe, speed/load dependence)", "text"),
        ("when_occurs", "Accel / coast / turning / constant?", "text"),
        ("hub_temp", "Hub temperatures after driving (hand check per wheel)", "text"),
        ("lube", "Gear lube levels/condition last checked", "text"),
    ],
    "RV habitat box": [
        ("rv_system", "Which habitat system?", ["12V DC", "120V AC / inverter / shore power", "Plumbing / water", "Propane", "Appliance", "HVAC", "Structure / seal", "Other"]),
        ("rv_power_state", "Power state when observed (shore / inverter / batteries, voltages if known)", "text"),
        ("rv_component", "Component make/model if known", "text"),
        ("rv_detail", "What works / what doesn't on the same circuit or line", "textarea"),
    ],
    "Steering / suspension": [
        ("steer_symptom", "Wander, pull, play, noise? At what speed", "text"),
        ("tire_wear", "Tire wear pattern", "text"),
    ],
    "Other": [],
}


def _field_html(name, label, kind):
    out = [f'<label for="{name}">{label}</label>']
    if kind == "textarea":
        out.append(f'<textarea id="{name}" name="{name}" rows="3"></textarea>')
    elif kind == "text":
        out.append(f'<input type="text" id="{name}" name="{name}">')
    else:
        opts = "".join(f"<option>{o}</option>" for o in kind)
        out.append(f'<select id="{name}" name="{name}">{opts}</select>')
    return "\n".join(out)


@app.route("/intake", methods=["GET", "POST"])
def intake():
    if request.method == "POST":
        category = request.form.get("category", "Other")
        cat_fields = INTAKE_CATEGORIES.get(category, [])
        names = ([n for n, _, _ in INTAKE_COMMON_TOP]
                 + [n for n, _, _ in cat_fields]
                 + [n for n, _, _ in INTAKE_COMMON_BOTTOM])
        record = {
            "schema": "intake-v2",
            "filed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "category": category,
            "as_built_snapshot": as_built_text(),
            "fields": {n: request.form.get(n, "").strip() for n in names},
        }
        record["fields"]["complaint"] = category
        SESSIONS_DIR.mkdir(exist_ok=True)
        fname = SESSIONS_DIR / f"intake-{time.strftime('%Y%m%d-%H%M%S')}.json"
        fname.write_text(json.dumps(record, indent=2), encoding="utf-8")
        # straight into chat: intake attached, analysis auto-submitted
        return redirect(url_for("home", intake=fname.name, auto=1))

    cat_opts = "".join(f"<option>{c}</option>" for c in INTAKE_CATEGORIES)
    blocks = []
    for cat, fields in INTAKE_CATEGORIES.items():
        inner = "\n".join(_field_html(*f) for f in fields) or \
            "<p class='hint'>No category-specific measurements — describe " \
            "everything in the other sections.</p>"
        blocks.append(
            f'<fieldset class="group catblock" data-cat="{html.escape(cat)}" '
            f'style="display:none"><legend>Measurements — {html.escape(cat)}'
            f'</legend>{inner}</fieldset>')
    body = (
        '<div class="card"><h2>Diagnostic intake</h2>'
        "<p class='hint'>One form for any system — pick the category and the "
        "relevant measurement fields appear. Measurements beat adjectives. "
        "The as-built profile is stamped onto the session automatically.</p>"
        '<form method="post">'
        '<fieldset class="group"><legend>The complaint</legend>'
        '<label for="category">Complaint category</label>'
        f'<select id="category" name="category">{cat_opts}</select>'
        + "\n".join(_field_html(*f) for f in INTAKE_COMMON_TOP)
        + "</fieldset>"
        + "\n".join(blocks)
        + '<fieldset class="group"><legend>History &amp; context</legend>'
        + "\n".join(_field_html(*f) for f in INTAKE_COMMON_BOTTOM)
        + "</fieldset>"
        + '<p style="margin-top:1rem"><button>File intake</button></p></form></div>'
        + """
<script>
const sel = document.getElementById("category");
function swap() {
  document.querySelectorAll(".catblock").forEach(b =>
    b.style.display = b.dataset.cat === sel.value ? "" : "none");
}
sel.addEventListener("change", swap);
swap();
</script>"""
    )
    return page("Intake", body, active="intake")


# ---------------------------------------------------------------- my truck


TRUCK_JSON = REPO_ROOT / "truck.json"

VARIANTS = ["M1083A1 (MTV 6x6 cargo)", "M1083 (MTV 6x6 cargo, A0)",
            "M1084A1 (MTV w/ MHC)", "M1085A1 (MTV long bed)",
            "M1086A1", "M1088A1 (tractor)", "M1089A1 (wrecker)",
            "M1090A1 (dump)", "M1078A1 (LMTV 4x4 cargo)", "M1078 (LMTV A0)",
            "M1079A1 (LMTV van)", "Other FMTV variant"]
ENGINES = ["Cat 3126E", "Cat 3126B", "Cat 3116", "Other"]
TRANSMISSIONS = ["Allison MD3070PT (7-speed)", "Allison MD3070T",
                 "Allison 3700SP", "Other"]
ELEC_OPTIONS = ["Stock (24V system)",
                "24V alternator + 24V to 12V converter for 12V side",
                "Other / modified (describe in details)"]


def load_truck() -> dict:
    try:
        return json.loads(TRUCK_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {"variant": VARIANTS[0], "year": "", "engine": ENGINES[0],
                "engine_serial": "", "engine_hp": "",
                "transmission": TRANSMISSIONS[0], "trans_serial": "",
                "axle_ratio": "", "odometer": "",
                "tires": "", "ctis_pressures": "",
                "electrical": ELEC_OPTIONS[0], "electrical_details": "",
                "deviations": [], "rv_equipment": [], "notes": ""}


def build_dossier(tr: dict) -> str:
    """Generate the canonical as-built markdown from structured data."""
    nl = chr(10)
    dev_lines = []
    for d in tr.get("deviations", []):
        if d.get("title"):
            dev_lines.append("### " + d["title"] + nl + d.get("details", "")
                             + nl + "- **Implications:** stock TM procedures/"
                             "figures touching this system may not apply as "
                             "printed.")
    rv_lines = []
    for r in tr.get("rv_equipment", []):
        if r.get("name"):
            line = "- **" + r["name"] + "**"
            if r.get("model"):
                line += " (model " + r["model"] + ")"
            if r.get("ingested"):
                line += " - manual indexed"
            rv_lines.append(line)
    elec = tr.get("electrical", "")
    elec_block = "- **Charging/electrical:** " + elec
    if tr.get("electrical_details"):
        elec_block += nl + "  - " + tr["electrical_details"]
    if "converter" in elec.lower():
        elec_block += (nl + "  - Any charging/voltage diagnosis must account "
                       "for this - stock TM alternator procedures do NOT "
                       "apply as printed.")
    parts = [
        "# AS-BUILT CONFIGURATION - " + tr.get("variant", "FMTV"), "",
        "> Canonical dossier, generated from the My Truck page. "
        "Edit there, not here.", "",
        "## Identity",
        "- **Variant:** " + tr.get("variant", ""),
        "- **Model year:** " + tr.get("year", ""),
        "- **Odometer:** " + tr.get("odometer", ""), "",
        "## Powertrain",
        "- **Engine:** " + tr.get("engine", "") + " (serial: "
        + (tr.get("engine_serial") or "unknown") + ", "
        + (tr.get("engine_hp") or "?") + " HP)",
        "- **Transmission:** " + tr.get("transmission", "") + " (serial: "
        + (tr.get("trans_serial") or "unknown") + ")",
        "- **Axle ratio:** " + (tr.get("axle_ratio") or "unknown"), "",
        "## \u26a0 Deviations from stock",
        nl.join(dev_lines) if dev_lines else "(none recorded - assumed stock)",
        "",
        "## Electrical", elec_block, "",
        "## Tires / CTIS",
        "- Tires: " + (tr.get("tires") or "unknown"),
        "- CTIS pressures in use: " + (tr.get("ctis_pressures") or "unknown"),
        "",
        "## Habitat / RV equipment",
        nl.join(rv_lines) if rv_lines else "(none - no habitat box recorded)",
        "",
        "## Notes", tr.get("notes", ""), "",
    ]
    return nl.join(parts)


def as_built_text() -> str:
    """The dossier; generated blank from truck.json defaults if absent
    (fresh installs — AS_BUILT is user data and not shipped)."""
    if not AS_BUILT.exists():
        AS_BUILT.write_text(build_dossier(load_truck()), encoding="utf-8")
    return AS_BUILT.read_text(encoding="utf-8")


def _rv_ingest_job(name: str, url: str):
    """Download an RV equipment manual and index it (habitat domain)."""
    import subprocess
    import urllib.request
    job = {"file": name + " manual", "state": "downloading", "detail": ""}
    KNOWLEDGE_JOBS.append(job)
    try:
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", name)[:60] or "rv-doc"
        dest = REPO_ROOT / "corpus" / "raw" / ("RV-" + safe + ".pdf")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
            f.write(r.read())
        if dest.stat().st_size < 10_000 or not dest.read_bytes()[:5].startswith(b"%PDF"):
            dest.unlink(missing_ok=True)
            job.update(state="failed", detail="link did not return a PDF")
            return
        job.update(state="ingesting")
        r1 = subprocess.run([sys.executable,
                             str(REPO_ROOT / "ingest" / "ingest_tm.py"),
                             "--domain", "habitat", str(dest)],
                            capture_output=True, text=True, timeout=1800)
        if r1.returncode != 0:
            job.update(state="failed", detail=r1.stderr[-200:])
            return
        job.update(state="embedding")
        r2 = subprocess.run([sys.executable,
                             str(REPO_ROOT / "ingest" / "embed_index.py")],
                            capture_output=True, text=True, timeout=3600)
        job.update(state="done" if r2.returncode == 0 else "failed")
        tr = load_truck()
        for item in tr.get("rv_equipment", []):
            if item.get("name") == name:
                item["ingested"] = True
        TRUCK_JSON.write_text(json.dumps(tr, indent=1), encoding="utf-8")
        AS_BUILT.write_text(build_dossier(tr), encoding="utf-8")
    except Exception as e:
        job.update(state="failed", detail=str(e)[:200])


def _sel(name, options, current):
    opts = "".join(
        "<option" + (" selected" if o == current else "") + ">"
        + html.escape(o) + "</option>" for o in options)
    return '<select name="' + name + '">' + opts + "</select>"


def _txt(name, label, value, ph=""):
    return ('<label for="' + name + '">' + label + "</label>"
            '<input type="text" id="' + name + '" name="' + name + '" '
            'value="' + html.escape(value or "") + '" placeholder="' + ph + '">')


CONFIG_SCRIPT = """
<script>
function addDev() {
  const d = document.createElement("div");
  d.className = "devrow";
  d.innerHTML = '<input type="text" name="dev_title" placeholder="What changed">' +
    '<textarea name="dev_details" rows="2" placeholder="Vendor, part numbers, date, details"></textarea>';
  document.getElementById("devlist").appendChild(d);
}
function addRv() {
  const d = document.createElement("div");
  d.className = "rvrow";
  d.innerHTML = '<input type="text" name="rv_name" placeholder="Item (e.g. water pump)">' +
    '<input type="text" name="rv_model" placeholder="Model number">' +
    '<input type="text" name="rv_url" placeholder="Link to PDF manual (auto-indexed)">';
  document.getElementById("rvlist").appendChild(d);
}
</script>
<style>
.devrow, .rvrow { border-left: 3px solid var(--line); padding-left: .8rem;
  margin: .7rem 0; }
.devrow input, .rvrow input { margin-bottom: .3rem; }
</style>
"""


@app.route("/config", methods=["GET", "POST"])
def config():
    import threading
    from backends import get_config
    saved = ""
    if request.method == "POST" and request.form.get("form") == "settings":
        cfg = {
            "backend": request.form.get("backend", "claude"),
            "claude_model": request.form.get("claude_model", "claude-opus-5"),
            "ollama_url": request.form.get("ollama_url", "").strip()
                          or "http://127.0.0.1:11434",
            "ollama_model": request.form.get("ollama_model", "").strip()
                            or "qwen2.5:7b-instruct",
        }
        (REPO_ROOT / "config.json").write_text(json.dumps(cfg, indent=1),
                                               encoding="utf-8")
        saved = "settings"
    elif request.method == "POST":
        tr = load_truck()
        for k in ["variant", "year", "odometer", "engine", "engine_serial",
                  "engine_hp", "transmission", "trans_serial", "axle_ratio",
                  "tires", "ctis_pressures", "electrical",
                  "electrical_details", "notes"]:
            tr[k] = request.form.get(k, "").strip()
        tr["deviations"] = [
            {"title": ti.strip(), "details": de.strip()}
            for ti, de in zip(request.form.getlist("dev_title"),
                              request.form.getlist("dev_details"))
            if ti.strip()]
        old_rv = {r.get("name"): r
                  for r in load_truck().get("rv_equipment", [])}
        new_rv = []
        for n, m, u in zip(request.form.getlist("rv_name"),
                           request.form.getlist("rv_model"),
                           request.form.getlist("rv_url")):
            if not n.strip():
                continue
            item = {"name": n.strip(), "model": m.strip(),
                    "doc_url": u.strip(),
                    "ingested": old_rv.get(n.strip(), {}).get("ingested",
                                                              False)}
            new_rv.append(item)
            if item["doc_url"] and not item["ingested"]:
                threading.Thread(target=_rv_ingest_job,
                                 args=(item["name"], item["doc_url"]),
                                 daemon=True).start()
        tr["rv_equipment"] = new_rv
        TRUCK_JSON.write_text(json.dumps(tr, indent=1), encoding="utf-8")
        AS_BUILT.write_text(build_dossier(tr), encoding="utf-8")
        saved = "truck"

    tr = load_truck()
    cfg = get_config()
    dev_rows = "".join(
        '<div class="devrow"><input type="text" name="dev_title" value="'
        + html.escape(d.get("title", ""))
        + '" placeholder="What changed (e.g. Eco-Hub conversion)">'
        + '<textarea name="dev_details" rows="2" placeholder="Vendor, part '
        'numbers, date, details">' + html.escape(d.get("details", ""))
        + "</textarea></div>"
        for d in tr.get("deviations", []))
    rv_rows = "".join(
        '<div class="rvrow"><input type="text" name="rv_name" value="'
        + html.escape(r.get("name", "")) + '" placeholder="Item">'
        + '<input type="text" name="rv_model" value="'
        + html.escape(r.get("model", "")) + '" placeholder="Model number">'
        + '<input type="text" name="rv_url" value="'
        + html.escape(r.get("doc_url", ""))
        + '" placeholder="Link to PDF manual (auto-indexed)">'
        + ('<span class="hint">manual indexed \u2713</span>'
           if r.get("ingested") else "")
        + "</div>"
        for r in tr.get("rv_equipment", []))

    ok = ('<p class="hint" style="color:var(--ok)">\u2713 saved - takes '
          'effect immediately</p>') if saved else ""
    body = (
        ok
        + '<div class="card"><h2>My truck</h2>'
        '<p class="hint">This builds the as-built dossier injected into every '
        'diagnosis. The AI can only account for what you record here - '
        'especially deviations from stock.</p>'
        '<form method="post">'
        '<fieldset class="group"><legend>Identity</legend>'
        '<label>Variant</label>' + _sel("variant", VARIANTS, tr.get("variant"))
        + _txt("year", "Model year", tr.get("year"), "e.g. 2003")
        + _txt("odometer", "Odometer (mi)", tr.get("odometer"))
        + "</fieldset>"
        '<fieldset class="group"><legend>Powertrain</legend>'
        "<label>Engine</label>" + _sel("engine", ENGINES, tr.get("engine"))
        + _txt("engine_serial", "Engine serial (prefix matters, e.g. 9SZ...)",
               tr.get("engine_serial"))
        + _txt("engine_hp", "Rated HP", tr.get("engine_hp"), "e.g. 330")
        + "<label>Transmission</label>"
        + _sel("transmission", TRANSMISSIONS, tr.get("transmission"))
        + _txt("trans_serial", "Transmission serial", tr.get("trans_serial"))
        + _txt("axle_ratio", "Axle ratio", tr.get("axle_ratio"), "e.g. 2.97:1")
        + "</fieldset>"
        '<fieldset class="group"><legend>\u26a0 Deviations from stock</legend>'
        '<p class="hint">Anything not factory: hub conversions, added '
        'modules, deleted equipment. Each changes how the TM applies.</p>'
        '<div id="devlist">' + dev_rows + "</div>"
        '<button type="button" class="btn-ghost" onclick="addDev()">'
        "\uff0b Add deviation</button></fieldset>"
        '<fieldset class="group"><legend>Electrical</legend>'
        "<label>Charging system</label>"
        + _sel("electrical", ELEC_OPTIONS, tr.get("electrical"))
        + _txt("electrical_details",
               "Details (alternator/converter models, amp ratings)",
               tr.get("electrical_details"))
        + "</fieldset>"
        '<fieldset class="group"><legend>Tires / CTIS</legend>'
        + _txt("tires", "Tires", tr.get("tires"), "e.g. Goodyear 395/85R20")
        + _txt("ctis_pressures", "CTIS pressures in use",
               tr.get("ctis_pressures"))
        + "</fieldset>"
        '<fieldset class="group"><legend>Habitat / RV equipment</legend>'
        '<p class="hint">Add each appliance/system in your box. Paste a link '
        "to its PDF manual and SARGE downloads and indexes it (habitat "
        "domain) automatically.</p>"
        '<div id="rvlist">' + rv_rows + "</div>"
        '<button type="button" class="btn-ghost" onclick="addRv()">'
        "\uff0b Add item</button></fieldset>"
        "<label>Anything else the AI should know</label>"
        '<textarea name="notes" rows="3">' + html.escape(tr.get("notes", ""))
        + "</textarea>"
        '<p style="margin-top:1rem"><button>Save truck profile</button></p>'
        "</form></div>"
        '<div class="card"><h2>AI settings</h2>'
        '<form method="post"><input type="hidden" name="form" value="settings">'
        "<label>Default provider</label>"
        '<select name="backend">'
        '<option value="claude"'
        + (" selected" if cfg["backend"] == "claude" else "")
        + ">Claude API (online, best)</option>"
        '<option value="ollama"'
        + (" selected" if cfg["backend"] == "ollama" else "")
        + ">Local / Ollama (offline)</option></select>"
        "<label>Claude model</label>"
        '<select name="claude_model">'
        '<option value="claude-opus-5"'
        + (" selected" if cfg["claude_model"] == "claude-opus-5" else "")
        + ">Claude Opus 5 - newest flagship (recommended)</option>"
        '<option value="claude-opus-4-8"'
        + (" selected" if cfg["claude_model"] == "claude-opus-4-8" else "")
        + ">Claude Opus 4.8 - previous flagship ($5/$25 per Mtok)</option>"
        '<option value="claude-fable-5"'
        + (" selected" if cfg["claude_model"] == "claude-fable-5" else "")
        + ">Claude Fable 5 - most capable, 2x price ($10/$50)</option>"
        '<option value="claude-sonnet-5"'
        + (" selected" if cfg["claude_model"] == "claude-sonnet-5" else "")
        + ">Claude Sonnet 5 - cheaper ($3/$15)</option></select>"
        + _txt("ollama_url", "Ollama server URL (local model)",
               cfg["ollama_url"])
        + _txt("ollama_model", "Ollama model name", cfg["ollama_model"])
        + '<p style="margin-top:1rem"><button>Save settings</button></p>'
        "</form></div>" + CONFIG_SCRIPT
    )
    return page("My truck", body, active="config")


# ---------------------------------------------------------------- knowledge

KNOWLEDGE_JOBS: list[dict] = []   # {"file", "state", "detail"}


def _ingest_job(pdf_path: Path, domain: str = "chassis"):
    import subprocess
    job = {"file": pdf_path.name, "state": "ingesting", "detail": ""}
    KNOWLEDGE_JOBS.append(job)
    try:
        r = subprocess.run(
            [sys.executable, str(REPO_ROOT / "ingest" / "ingest_tm.py"),
             "--domain", domain, str(pdf_path)],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            job.update(state="failed", detail=r.stderr[-300:])
            return
        job.update(state="embedding")
        r = subprocess.run(
            [sys.executable, str(REPO_ROOT / "ingest" / "embed_index.py")],
            capture_output=True, text=True, timeout=3600)
        job.update(state="done" if r.returncode == 0 else "failed",
                   detail="" if r.returncode == 0 else r.stderr[-300:])
    except Exception as e:
        job.update(state="failed", detail=str(e)[:300])


@app.route("/knowledge", methods=["GET"])
def knowledge():
    con = db()
    rows = con.execute(
        "SELECT manual, COUNT(*), SUM(kind='content'), MAX(domain)"
        " FROM pages GROUP BY manual ORDER BY manual").fetchall()
    con.close()
    jobs = "".join(
        f'<li><code>{html.escape(j["file"])}</code> — {j["state"]}'
        + (f' <span class="hint">{html.escape(j["detail"])}</span>'
           if j["detail"] else "") + "</li>"
        for j in reversed(KNOWLEDGE_JOBS[-8:]))
    table = "".join(
        f"<tr><td>{m}</td><td>{n}</td><td>{c}</td><td>{d}</td>"
        f'<td><form method="post" action="/knowledge/remove" '
        f'style="display:inline" onsubmit="return confirm(\'Remove {m} from '
        f"the search index? The PDF stays in corpus/raw.')\">"
        f'<input type="hidden" name="manual" value="{m}">'
        f'<button class="btn-ghost" style="padding:.15rem .6rem">remove</button>'
        f"</form></td></tr>"
        for m, n, c, d in rows)
    body = (
        '<div class="card"><h2>Add knowledge</h2>'
        "<p class='hint'>Upload a PDF manual for your equipment. It is "
        "ingested (per-page text + page images) and embedded for semantic "
        "search — a large TM takes a few minutes. Only index documents that "
        "apply to YOUR equipment: irrelevant manuals actively compete with "
        "the right answer in retrieval.</p>"
        '<form method="post" action="/knowledge/upload" '
        'enctype="multipart/form-data">'
        '<input type="file" name="pdf" accept=".pdf" required> '
        '<select name="domain" style="width:auto">'
        '<option value="chassis">chassis (truck)</option>'
        '<option value="habitat">habitat (RV box)</option>'
        '<option value="shared">shared / other</option></select> '
        "<button>Upload &amp; index</button></form>"
        + (f"<h3>Recent jobs</h3><ul>{jobs}</ul>" if jobs else "")
        + "</div>"
        '<div class="card"><h2>Indexed manuals</h2>'
        '<div style="overflow-x:auto"><table><tr><th>Manual</th><th>Pages</th>'
        "<th>Content pages</th><th>Domain</th><th></th></tr>" + table + "</table></div>"
        "<p class='hint'>Removing only clears the search index — the PDF "
        "remains in corpus/raw for re-ingest.</p></div>"
    )
    return page("Knowledge", body, active="knowledge")


@app.route("/knowledge/upload", methods=["POST"])
def knowledge_upload():
    import threading
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        abort(400)
    name = re.sub(r"[^A-Za-z0-9._-]", "-", f.filename)
    dest = REPO_ROOT / "corpus" / "raw" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    f.save(dest)
    domain = request.form.get("domain", "chassis")
    if domain not in ("chassis", "habitat", "shared"):
        domain = "chassis"
    threading.Thread(target=_ingest_job, args=(dest, domain),
                     daemon=True).start()
    return redirect(url_for("knowledge"))


@app.route("/knowledge/remove", methods=["POST"])
def knowledge_remove():
    manual = request.form.get("manual", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", manual):
        abort(400)
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("DELETE FROM page_vecs WHERE id IN "
                "(SELECT id FROM pages WHERE manual = ?)", (manual,))
    con.execute("DELETE FROM pages WHERE manual = ?", (manual,))
    con.commit()
    con.close()
    return redirect(url_for("knowledge"))


# ------------------------------------------------------- one-shot diagnosis


def _linkify_citations(escaped_text: str) -> str:
    def repl(m):
        manual, pg = m.group(1), int(m.group(2))
        href = url_for("view_page", manual=manual, pdf_page=pg)
        return f'<a href="{href}">[{manual} pdf p.{pg}]</a>'
    return re.sub(r"\[\[([A-Za-z0-9._-]+)\|(\d+)\]\]", repl, escaped_text)


@app.route("/diagnose", methods=["GET", "POST"])
def diagnose_page():
    session_name = request.values.get("session", "")
    if session_name and not re.fullmatch(r"intake-[\d-]+\.json", session_name):
        abort(400)

    if request.method == "GET":
        body = (
            '<div class="card"><h2>Run AI diagnosis on intake '
            f"<code>{session_name}</code></h2>"
            "<p>Sends the retrieved manual pages and as-built profile to the "
            "Claude API (a few cents, 1–3 minutes) and returns a "
            "stop-and-report test card.</p>"
            '<form method="post">'
            f'<input type="hidden" name="session" value="{session_name}">'
            "<button>Run diagnosis</button> &nbsp; "
            f'<a href="{url_for("home")}?intake={session_name}">'
            "or discuss it in chat instead</a>"
            "</form></div>"
        )
        return page("Diagnose intake", body)

    import diagnose as dx
    import anthropic
    problem = dx.load_intake(str(dx.SESSIONS_DIR / session_name))
    pages_used = dx.retrieve(problem, 10)
    user_msg = (
        "AS-BUILT CONFIGURATION (canonical dossier):\n"
        + as_built_text()
        + "\n\n=====\n\nRETRIEVED TIER 1 SOURCE PAGES (your ONLY permitted "
        "source for specs and procedures):\n\n" + dx.build_context(pages_used)
        + "\n\n=====\n\n" + problem
    )
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=_model(), max_tokens=16000, thinking={"type": "adaptive"},
        system=[{"type": "text", "text": dx.SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        response = stream.get_final_message()
    if response.stop_reason == "refusal":
        return page("Diagnosis", "<p>The model declined this request.</p>")
    answer = "".join(b.text for b in response.content if b.type == "text")
    problems = dx.validate(answer, pages_used)
    rendered = _linkify_citations(html.escape(answer))
    val = ("".join(f"<li>⚠ {html.escape(p)}</li>" for p in problems)
           or "<li>✓ all citations exist and all unit-bearing numbers appear "
              "in cited pages</li>")
    body = (
        AUTHORITY_NOTE
        + f'<div class="card" style="white-space:pre-wrap">{rendered}</div>'
        + f"<h2>Validation</h2><ul>{val}</ul>"
    )
    return page("Diagnosis", body)

if __name__ == "__main__":
    # 0.0.0.0: reachable from phone via LAN/Tailscale. No auth — do NOT
    # port-forward this to the internet.
    app.run(host="0.0.0.0", port=8383, debug=False, threaded=True)

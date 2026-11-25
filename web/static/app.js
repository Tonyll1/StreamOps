// Panel de StreamOps: navegación por vistas, estado en vivo y edición de configuración.
const $ = (id) => document.getElementById(id);
const { esc, fmt } = StreamOps;
const icon = (name) => `<svg class="ic"><use href="#i-${name}"/></svg>`;
let config = {}, rules = [], media = [], voices = [], openRules = new Set(), voiceFilter = "all";

function toast(text, error = false) {
  const el = document.createElement("div");
  el.className = "toast" + (error ? " err" : "");
  el.textContent = text;
  $("toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, 2400);
}
async function api(method, path, body) {
  const res = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) { const msg = await res.text(); toast("Error: " + msg.slice(0, 140), true); throw new Error(msg); }
  return res.json();
}

// ---- navegación ---------------------------------------------------------
const VIEWS = {
  inicio: ["Inicio", "Resumen de tu directo en tiempo real"],
  conexiones: ["Conexiones", "Conecta tus canales de TikTok, Twitch y Kick"],
  voz: ["Voz (TTS)", "Voces, lectura del chat y volumen"],
  alertas: ["Alertas y acciones", "Qué pasa cuando alguien dona, sigue o escribe"],
  overlays: ["Overlays", "Fuentes de navegador para tu escena"],
  medios: ["Medios", "Sonidos, imágenes y videos de tus alertas"],
  pulso: ["Pulsómetro", "Muestra tu ritmo cardíaco en pantalla"],
  ajustes: ["Ajustes", "Atajos de teclado, OBS y datos"],
};
function show(view) {
  if (!VIEWS[view]) view = "inicio";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  [$("viewTitle").textContent, $("viewSub").textContent] = VIEWS[view];
  if (location.hash.slice(1) !== view) history.replaceState(null, "", "#" + view);
  if (view === "overlays") renderOverlays();
  $("views").scrollTop = 0;
}
$("nav").addEventListener("click", (e) => { const a = e.target.closest("a"); if (a) show(a.dataset.view); });
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

// ---- campos simples: id = seccion_clave ---------------------------------
const FIELDS = ["tiktok_username","tiktok_autoconnect","twitch_channel","twitch_autoconnect","kick_channel","kick_chatroom_id","kick_autoconnect",
  "tts_enabled","tts_read_chat","tts_say_username","tts_allow_voice_command","tts_chat_prefix","tts_volume","tts_max_chars","audio_alert_volume",
  "heartrate_source","heartrate_pulsoid_token","heartrate_ble_address","hotkeys_mute_toggle","hotkeys_skip_tts","hotkeys_stop_all","obs_host","obs_port","obs_password"];
const split = (id) => { const i = id.indexOf("_"); return [id.slice(0, i), id.slice(i + 1)]; };
function showRange(el) { const out = $("o_" + el.id); if (out) out.textContent = Math.round(el.value * 100) + "%"; }
function fillFields() {
  for (const id of FIELDS) {
    const [s, k] = split(id), el = $(id), v = config[s][k];
    if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
    if (el.type === "range") showRange(el);
  }
  $("tts_blocked_words").value = (config.tts.blocked_words || []).join(", ");
}
async function saveField(el) {
  const [s, k] = split(el.id);
  let v = el.type === "checkbox" ? el.checked : el.value;
  if (el.type === "number" || el.type === "range") v = Number(v);
  config = await api("PUT", "/api/config", { [s]: { [k]: v } });
  toast("Guardado");
}
FIELDS.forEach((id) => {
  $(id).addEventListener("change", (e) => saveField(e.target));
  if ($(id).type === "range") $(id).addEventListener("input", (e) => showRange(e.target));
});
$("tts_blocked_words").addEventListener("change", async (e) => {
  config = await api("PUT", "/api/config", { tts: { blocked_words: e.target.value.split(",").map((w) => w.trim()).filter(Boolean) } });
  toast("Guardado");
});

// ---- controles ----------------------------------------------------------
document.querySelectorAll("[data-connect]").forEach((b) => b.onclick = () => api("POST", "/api/connect/" + b.dataset.connect));
document.querySelectorAll("[data-disconnect]").forEach((b) => b.onclick = () => api("POST", "/api/disconnect/" + b.dataset.disconnect));
$("btnMute").onclick = () => api("POST", "/api/mute", {});
$("btnSkip").onclick = () => api("POST", "/api/skip");
$("btnStop").onclick = () => api("POST", "/api/stop").then(() => toast("Todo detenido"));
const resetSession = () => { if (confirm("¿Reiniciar los tops de la sesión actual?")) api("POST", "/api/session/reset", {}).then(() => toast("Sesión reiniciada")); };
$("btnResetSession").onclick = resetSession;
$("btnResetSession2").onclick = resetSession;
$("btnResetAll").onclick = () => { if (confirm("¿Borrar TODO el histórico de tops? No se puede deshacer.")) api("POST", "/api/session/reset", { all: true }).then(() => toast("Histórico borrado")); };
$("btnSim").onclick = () => api("POST", "/api/simulate", { type: $("sim_type").value, user: $("sim_user").value, gift: $("sim_gift").value,
  count: Number($("sim_count").value), value: Number($("sim_value").value) * Number($("sim_count").value), text: $("sim_text").value });
$("btnScan").onclick = async () => {
  toast("Buscando bandas…");
  const r = await fetch("/api/heartrate/scan").then((x) => x.json());
  $("dt_heartrate").textContent = r.error ? "Error: " + r.error : (r.length ? r.map((d) => `${d.name} → ${d.address}`).join(" · ") : "No se encontraron bandas");
};

// ---- estado en vivo -----------------------------------------------------
function setMuted(muted) {
  $("btnMute").classList.toggle("off", muted);
  $("muteLabel").textContent = muted ? "SILENCIADO" : "Sonido activo";
  $("muteIcon").setAttribute("href", muted ? "#i-mute" : "#i-vol");
}
function setStatus(connectors) {
  for (const [name, c] of Object.entries(connectors || {})) {
    const pill = $("st_" + name);
    if (pill) { pill.textContent = c.status; pill.className = "pill " + c.status; }
    const dot = $("dot_" + name);
    if (dot) dot.className = "dot " + c.status;
    const card = document.querySelector(`.plat[data-plat="${name}"]`);
    if (card) card.classList.toggle("live", c.status === "conectado");
    const d = $("dt_" + name);
    if (d && (name !== "heartrate" || c.status === "error")) d.textContent = c.detail || "";
  }
}
const shown = {};
function countUp(id, target) {
  const el = $(id), from = shown[id] || 0;
  if (from === target) return;
  shown[id] = target;
  const tile = el.closest(".tile");
  if (tile && target > from) { tile.classList.remove("bump"); void tile.offsetWidth; tile.classList.add("bump"); }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / 600), eased = 1 - Math.pow(1 - t, 3);
    el.textContent = fmt(from + (target - from) * eased);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function setBpm(bpm) {
  if (!bpm) return;
  $("bpm_now").textContent = bpm;
  const card = document.querySelector(".hrcard");
  card.classList.remove("stale");
  card.style.setProperty("--beat", (60 / Math.max(bpm, 30)).toFixed(2) + "s");
}
function renderMiniTop(rows) {
  rows = (rows || []).slice(0, 5);
  const max = rows.length ? rows[0].value : 1;
  $("miniTop").innerHTML = rows.map((r, i) => `<div class="mt" style="animation-delay:${i * 40}ms"><span class="pos">${i + 1}</span><span class="nm">${esc(r.name)}</span>
    <span class="barx"><i style="transform:scaleX(${(r.value / max).toFixed(3)})"></i></span><span class="vl">${fmt(r.value)}</span></div>`).join("") || '<div class="empty">Aún sin donaciones en esta sesión</div>';
}
const LABEL = {
  chat: (e) => `<b>${esc(e.user)}</b> ${esc(e.text)}`,
  gift: (e) => `<b>${esc(e.user)}</b> envió ${e.count}× ${esc(e.gift)} · ${fmt(e.value)} monedas`,
  like: (e) => `<b>${esc(e.user)}</b> dio ${e.count} like(s)`,
  follow: (e) => `<b>${esc(e.user)}</b> te siguió`,
  share: (e) => `<b>${esc(e.user)}</b> compartió el directo`,
  sub: (e) => `<b>${esc(e.user)}</b> ${esc(e.gift)} ×${e.count}`,
  raid: (e) => `<b>${esc(e.user)}</b> hizo raid con ${e.count}`,
};
let feedEmpty = true;
function addEvent(e) {
  if (!LABEL[e.type]) return;
  const feed = $("feed");
  if (feedEmpty) { feed.innerHTML = ""; feedEmpty = false; }
  const div = document.createElement("div");
  div.className = "ev " + e.type;
  const initial = esc((e.user || "?").trim().charAt(0).toUpperCase() || "?");
  const avatar = e.avatar ? `<img src="${esc(e.avatar)}" referrerpolicy="no-referrer" onerror="this.remove()">` : initial;
  div.innerHTML = `<span class="av">${avatar}</span><span class="tx">${LABEL[e.type](e)}</span><span class="pf">${esc(e.platform)}</span>`;
  const stick = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 40;
  feed.appendChild(div);
  while (feed.children.length > 300) feed.firstChild.remove();
  if (stick) feed.scrollTop = feed.scrollHeight;
}
StreamOps.connect((msg) => {
  if (msg.type === "state") {
    setMuted(msg.muted); setStatus(msg.connectors); setBpm(msg.bpm);
    const c = msg.counters || {};
    countUp("stat_coins", c.coins || 0); countUp("stat_likes", c.likes || 0); countUp("stat_follows", c.follows || 0); countUp("stat_shares", c.shares || 0);
    renderMiniTop(msg.session && msg.session.coins);
  } else if (msg.type === "status") setStatus(msg.connectors);
  else if (msg.type === "mute") setMuted(msg.muted);
  else if (msg.type === "hr") setBpm(msg.bpm);
  else if (msg.type === "event") addEvent(msg.event);
  else if (msg.type === "history" && msg.events.length) { $("feed").innerHTML = ""; feedEmpty = false; msg.events.forEach(addEvent); }
});
setTimeout(() => { if (feedEmpty) $("feed").innerHTML = '<div class="empty">Esperando eventos… usa el simulador para probar.</div>'; }, 2500);

// ---- voces --------------------------------------------------------------
function renderVoices() {
  const q = $("voiceSearch").value.trim().toLowerCase();
  const list = voices.filter((v) => (voiceFilter === "all" || v.kind === voiceFilter) && v.name.toLowerCase().includes(q));
  $("voiceGrid").innerHTML = list.map((v, i) => `<div class="voice ${v.kind} ${v.name === config.tts.voice ? "sel" : ""}" data-voice="${esc(v.name)}" style="animation-delay:${Math.min(i, 24) * 14}ms" title="${esc(v.name)}">
    <span class="va">${esc(v.name.replace(/^es_[A-Z]{2}-/, "").slice(0, 2))}</span><span>${esc(v.name.replace(/^es_([A-Z]{2})-(.*?)-(?:x_low|low|medium|high)$/, "$2 ($1)"))}</span>
    ${v.kind === "rvc" ? '<svg class="star" viewBox="0 0 24 24"><use href="#i-star"/></svg>' : ""}<button class="play" data-play="${esc(v.name)}" title="Escuchar">${icon("play")}</button></div>`).join("")
    || '<div class="empty">Ninguna voz coincide. Instala más con tools\\voces.py</div>';
}
$("voiceSearch").addEventListener("input", renderVoices);
$("voiceFilter").addEventListener("click", (e) => {
  if (!e.target.dataset.f) return;
  voiceFilter = e.target.dataset.f;
  $("voiceFilter").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.target));
  renderVoices();
});
async function testVoice(name) {
  const r = await api("POST", "/api/tts/test", { text: $("tts_test_text").value, voice: name });
  toast(r.ok ? `Probando "${name}"…` : "No se pudo: revisa que el TTS esté activo y sin silenciar", !r.ok);
}
$("voiceGrid").addEventListener("click", async (e) => {
  const play = e.target.closest("[data-play]");
  if (play) { e.stopPropagation(); return testVoice(play.dataset.play); }
  const chip = e.target.closest("[data-voice]");
  if (!chip) return;
  config = await api("PUT", "/api/config", { tts: { voice: chip.dataset.voice } });
  renderVoices();
  toast(`Voz predeterminada: ${chip.dataset.voice}`);
});
$("btnTtsTest").onclick = () => testVoice(config.tts.voice || (voices[0] && voices[0].name) || "");

// ---- overlays -----------------------------------------------------------
const OVERLAYS = [["Alertas", "/overlay/alerts"], ["Top donador", "/overlay/leaderboard?metric=coins&limit=1&title=Top%20donador"],
  ["Top donadores (sesión)", "/overlay/leaderboard?metric=coins&limit=5"], ["Top donadores general", "/overlay/leaderboard?metric=coins&scope=all&limit=5"],
  ["Top likes", "/overlay/leaderboard?metric=likes&limit=5"], ["Top compartidos", "/overlay/leaderboard?metric=shares&limit=5"], ["Pulsómetro", "/overlay/heartrate"]];
let overlaysDrawn = false;
function renderOverlays() {
  if (overlaysDrawn) return;
  overlaysDrawn = true;
  $("overlays").innerHTML = OVERLAYS.map(([name, path]) => `<div class="card ov"><h2>${name}</h2>
    <div class="frame"><iframe src="${path}" loading="lazy" tabindex="-1"></iframe></div>
    <input readonly value="${location.origin}${path}" onclick="this.select()">
    <div class="actions"><button class="btn tiny" data-copy="${location.origin}${path}">${icon("copy")}Copiar URL</button><button class="btn tiny ghost" data-open="${path}">${icon("ext")}Abrir</button></div></div>`).join("");
}
$("overlays").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.copy) { navigator.clipboard.writeText(b.dataset.copy); toast("URL copiada"); }
  if (b.dataset.open) window.open(b.dataset.open, "_blank");
});

// ---- reglas -------------------------------------------------------------
const EVENTS = [["gift", "Regalo / bits"], ["chat", "Chat / comando"], ["like", "Like"], ["follow", "Follow"], ["share", "Compartir"], ["sub", "Suscripción"], ["raid", "Raid"], ["join", "Entrada"]];
const ACTION_TYPES = { alert: "Alerta en pantalla", sound: "Sonido", tts: "Voz (TTS)", key: "Pulsar tecla", obs_scene: "Escena de OBS", webhook: "Webhook" };
const opt = (value, label, current) => `<option value="${esc(value)}" ${value === (current ?? "") ? "selected" : ""}>${esc(label)}</option>`;
const mediaOptions = (kinds, current) => opt("", "(ninguno)", current) + media.filter((m) => kinds.includes(m.kind)).map((m) => opt(m.name, m.name, current)).join("");
const voiceOptions = (current) => opt("", "(predeterminada)", current) + voices.map((v) => opt(v.name, v.name + (v.kind === "rvc" ? " ★" : ""), current)).join("");
function actionFields(a, ri, ai) {
  const at = `data-r="${ri}" data-a="${ai}"`;
  const text = (key, label, ph = "") => `<label>${label}<input ${at} data-k="${key}" value="${esc(a[key] ?? "")}" placeholder="${ph}"></label>`;
  const num = (key, label, def, extra = "") => `<label>${label}<input type="number" ${extra} ${at} data-k="${key}" value="${a[key] ?? def}"></label>`;
  const sel = (key, label, options) => `<label>${label}<select ${at} data-k="${key}">${options}</select></label>`;
  if (a.type === "alert") return text("text", "Texto", "{user} envió {gift}") + sel("media", "Imagen o video", mediaOptions(["image", "video"], a.media)) + sel("sound", "Sonido", mediaOptions(["audio"], a.sound)) + num("duration", "Segundos", 5, 'min="1"');
  if (a.type === "sound") return sel("file", "Archivo", mediaOptions(["audio"], a.file)) + num("volume", "Volumen (0-2)", "", 'step="0.1" min="0" max="2"');
  if (a.type === "tts") return text("text", "Texto a leer", "Gracias {user}") + sel("voice", "Voz", voiceOptions(a.voice));
  if (a.type === "key") return text("keys", "Teclas", "ctrl+shift+f1") + num("hold_ms", "Mantener (ms)", 100, 'min="10"');
  if (a.type === "obs_scene") return text("scene", "Nombre de la escena");
  if (a.type === "webhook") return text("url", "URL", "https://");
  return "";
}
function renderRules() {
  $("navRules").textContent = rules.length || "";
  $("rules").innerHTML = rules.map((r, ri) => {
    const evLabel = (EVENTS.find((e) => e[0] === r.event) || ["", r.event])[1];
    return `<div class="rule ${openRules.has(ri) ? "open" : ""} ${r.enabled === false ? "off" : ""}" style="animation-delay:${ri * 50}ms">
    <div class="rule-h" data-toggle="${ri}"><span class="tag ${esc(r.event)}">${esc(evLabel)}</span><span class="rn">${esc(r.name)}</span>
      <span class="flow"><span class="arrow">→</span>${(r.actions || []).map((a) => `<span class="achip">${esc(ACTION_TYPES[a.type] || a.type)}</span>`).join("") || '<span class="achip">sin acciones</span>'}</span>
      <svg class="ic chev"><use href="#i-chev"/></svg></div>
    <div class="rule-b"><div><div class="rule-in">
      <div class="cond">
        <label>Nombre<input data-r="${ri}" data-k="name" value="${esc(r.name)}"></label>
        <label>Evento<select data-r="${ri}" data-k="event">${EVENTS.map(([v, l]) => opt(v, l, r.event)).join("")}</select></label>
        <label>Plataforma<select data-r="${ri}" data-k="platform">${[["any", "Todas"], ["tiktok", "TikTok"], ["twitch", "Twitch"], ["kick", "Kick"]].map(([v, l]) => opt(v, l, r.platform)).join("")}</select></label>
        <label>Mínimo<input type="number" min="0" data-r="${ri}" data-k="min_value" value="${r.min_value ?? 0}"></label>
        <label>${r.event === "chat" ? "Comando" : "Regalo contiene"}<input data-r="${ri}" data-k="match" value="${esc(r.match ?? "")}" placeholder="${r.event === "chat" ? "!comando" : "rosa"}"></label>
        <label>Espera (s)<input type="number" min="0" data-r="${ri}" data-k="cooldown" value="${r.cooldown ?? 0}"></label>
      </div>
      ${(r.actions || []).map((a, ai) => `<div class="action"><label class="t">Acción<select data-r="${ri}" data-a="${ai}" data-k="type">${Object.entries(ACTION_TYPES).map(([v, l]) => opt(v, l, a.type)).join("")}</select></label>
        ${actionFields(a, ri, ai)}<button class="btn icon ghost danger" data-del-action="${ri}:${ai}" title="Quitar acción">${icon("x")}</button></div>`).join("")}
      <div class="rule-f"><label class="sw"><input type="checkbox" data-r="${ri}" data-k="enabled" ${r.enabled !== false ? "checked" : ""}><i></i>Regla activa</label>
        <button class="btn tiny" data-add-action="${ri}">${icon("plus")}Acción</button><button class="btn tiny" data-test="${ri}">${icon("play")}Probar</button><button class="btn tiny ghost danger" data-del-rule="${ri}">Eliminar</button></div>
    </div></div></div></div>`;
  }).join("") || '<div class="card empty">No hay reglas todavía. Crea la primera con "Nueva regla".</div>';
}
const NUMERIC = new Set(["min_value", "cooldown", "duration", "hold_ms", "volume"]);
$("rules").addEventListener("change", (e) => {
  const el = e.target, k = el.dataset.k;
  if (!k) return;
  const rule = rules[el.dataset.r], target = el.dataset.a !== undefined ? rule.actions[el.dataset.a] : rule;
  let v = el.type === "checkbox" ? el.checked : el.value;
  if (NUMERIC.has(k)) v = v === "" ? "" : Number(v);
  target[k] = v;
  if (["type", "event", "name", "enabled"].includes(k)) renderRules();
});
$("rules").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-add-action],[data-del-action],[data-del-rule],[data-test]");
  if (b) {
    const d = b.dataset;
    if (d.addAction !== undefined) { rules[d.addAction].actions.push({ type: "alert", text: "{user}", duration: 5 }); renderRules(); }
    else if (d.delAction) { const [r, a] = d.delAction.split(":"); rules[r].actions.splice(a, 1); renderRules(); }
    else if (d.delRule !== undefined) { if (confirm("¿Eliminar esta regla?")) { rules.splice(d.delRule, 1); openRules.clear(); renderRules(); } }
    else if (d.test !== undefined) { await api("POST", "/api/rule/test", rules[d.test]); toast("Regla disparada"); }
    return;
  }
  const head = e.target.closest("[data-toggle]");
  if (head) {
    const i = Number(head.dataset.toggle);
    openRules.has(i) ? openRules.delete(i) : openRules.add(i);
    head.parentElement.classList.toggle("open");
  }
});
$("btnAddRule").onclick = () => {
  rules.push({ id: "r" + Date.now(), name: "Nueva regla", enabled: true, platform: "any", event: "gift", min_value: 0, match: "", cooldown: 0, actions: [{ type: "alert", text: "{user} envió {count}x {gift}", duration: 5 }] });
  openRules.add(rules.length - 1);
  renderRules();
  $("rules").lastElementChild.scrollIntoView({ behavior: "smooth", block: "center" });
};
$("btnSaveRules").onclick = async () => { config = await api("PUT", "/api/config", { rules }); rules = config.rules; toast("Reglas guardadas"); };

// ---- medios -------------------------------------------------------------
async function loadMedia() {
  media = await api("GET", "/api/media");
  $("navMedia").textContent = media.length || "";
  $("media").innerHTML = media.map((m, i) => {
    const src = "/media/" + encodeURIComponent(m.name);
    const thumb = m.kind === "image" ? `<img src="${src}" loading="lazy">` : m.kind === "video" ? `<video src="${src}#t=0.5" muted preload="metadata"></video>` : `<svg class="ic xl"><use href="#i-vol"/></svg>`;
    return `<div class="mtile" style="animation-delay:${Math.min(i, 20) * 25}ms"><div class="th">${thumb}</div><span class="kd">${m.kind}</span>
      ${m.kind === "audio" ? `<button class="btn icon tiny ply" data-play="${esc(m.name)}" title="Escuchar">${icon("play")}</button>` : ""}
      <button class="btn icon tiny danger del" data-del="${esc(m.name)}" title="Eliminar">${icon("x")}</button>
      <div class="inf"><b title="${esc(m.name)}">${esc(m.name)}</b><small>${(m.size / 1048576).toFixed(1)} MB</small></div></div>`;
  }).join("") || '<div class="empty">Aún no hay archivos.</div>';
  renderRules();
}
$("media").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.play) return api("POST", "/api/rule/test", { event: "gift", actions: [{ type: "sound", file: b.dataset.play }] });
  if (b.dataset.del && confirm("¿Eliminar " + b.dataset.del + "?")) { await api("DELETE", "/api/media/" + encodeURIComponent(b.dataset.del)); loadMedia(); }
});
async function upload(files) {
  if (!files.length) return;
  const form = new FormData();
  for (const f of files) form.append("file", f, f.name);
  toast(`Subiendo ${files.length} archivo(s)…`);
  const res = await fetch("/api/media", { method: "POST", body: form });
  if (!res.ok) return toast("Error: " + (await res.text()).slice(0, 140), true);
  toast("Archivos subidos");
  loadMedia();
}
$("mediaFile").addEventListener("change", (e) => { upload(e.target.files); e.target.value = ""; });
const drop = $("drop");
["dragenter", "dragover"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));

// ---- inicio -------------------------------------------------------------
(async () => {
  [config, voices] = await Promise.all([api("GET", "/api/config"), api("GET", "/api/voices")]);
  const chars = voices.filter((v) => v.kind === "rvc").length;
  $("voice_hint").textContent = voices.length ? `${voices.length} instaladas · ${chars} personajes` : "sin voces instaladas";
  fillFields();
  rules = config.rules;
  renderVoices();
  await loadMedia();
  show(location.hash.slice(1) || "inicio");
})();

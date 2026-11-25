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
  // Las vistas previas son páginas vivas: solo existen mientras se ve la sección.
  if (view === "voz" && config.tts) api("GET", "/api/config").then((c) => { config = c; renderUserVoices(); });
  if (view === "overlays") renderOverlays(); else if (overlaysDrawn) { $("overlays").innerHTML = ""; overlaysDrawn = false; }
  $("views").scrollTop = 0;
}
$("nav").addEventListener("click", (e) => { const a = e.target.closest("a"); if (a) show(a.dataset.view); });
window.addEventListener("hashchange", () => show(location.hash.slice(1)));

// ---- campos simples: id = seccion_clave ---------------------------------
const FIELDS = ["tiktok_username","tiktok_autoconnect","twitch_channel","twitch_autoconnect","kick_channel","kick_chatroom_id","kick_autoconnect",
  "tts_enabled","tts_read_chat","tts_allow_voice_command","tts_chat_prefix","tts_volume","tts_max_chars","audio_alert_volume",
  "tts_voice_command","tts_chat_min_chars","tts_user_cooldown","tts_skip_links","tts_skip_emoji_only","tts_skip_repeats",
  "heartrate_source","heartrate_pulsoid_token","heartrate_ble_address","hotkeys_mute_toggle","hotkeys_skip_tts","hotkeys_stop_all","obs_host","obs_port","obs_password"];
const split = (id) => { const i = id.indexOf("_"); return [id.slice(0, i), id.slice(i + 1)]; };
function showRange(el) { const out = $("o_" + el.id); if (out) out.textContent = Math.round(el.value * 100) + "%"; }
function fillFields() {
  for (const id of FIELDS) {
    const [s, k] = split(id), el = $(id), v = config[s][k];
    if (el.type === "checkbox") el.checked = !!v; else el.value = v ?? "";
    if (el.type === "range") showRange(el);
  }
  fillReader();
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
// ---- lectura: qué se lee y voces por usuario ------------------------------
const LISTS = ["tts_blocked_words", "tts_ignored_users", "tts_only_users"];
const READ = [["chat", "Mensajes del chat"], ["gift", "Regalos"], ["follow", "Seguidores"], ["share", "Compartidos"], ["like", "Likes"], ["sub", "Suscripciones"], ["raid", "Raids"], ["join", "Entradas al directo"]];
const voiceSelect = (sel, empty = "Voz por defecto") => `<option value="">${empty}</option>` + voices.map((v) => `<option value="${esc(v.name)}" ${v.name === sel ? "selected" : ""}>${esc(v.name)}</option>`).join("");
function fillReader() {
  const t = config.tts;
  LISTS.forEach((id) => { $(id).value = (t[id.slice(4)] || []).join(", "); });
  document.querySelectorAll("#ttsPlatforms input").forEach((el) => { el.checked = (t.platforms || {})[el.dataset.plat] !== false; });
  $("tts_random_voices_mode").value = t.random_voices ? t.random_pool || "all" : "off";
  $("uvVoice").innerHTML = voiceSelect("", "Elige una voz");
  $("readRows").innerHTML = READ.map(([type, label]) => {
    const r = t.read[type] || {}, at = `data-read="${type}"`, chat = type === "chat";
    return `<div class="readrow ${chat ? (t.read_chat ? "" : "off") : r.enabled ? "" : "off"}">
      <label class="sw"><input type="checkbox" ${at} data-k="enabled" ${chat ? (t.read_chat ? "checked" : "") : r.enabled ? "checked" : ""}><i></i>${label}</label>
      <input ${at} data-k="template" value="${esc(r.template || "")}" title="Frase que se lee">
      ${chat ? `<span class="rr-note">Cada persona usa su voz asignada (abajo) o la voz por defecto.</span>` : `<div class="rr-opts">
        <label>Voz<select ${at} data-k="voice">${voiceSelect(r.voice)}</select></label>
        <label>Espera (s)<input type="number" ${at} data-k="cooldown" value="${r.cooldown || 0}" min="0"></label>
        ${"min" in r ? `<label>${type === "gift" ? "Mín. monedas" : "Mín. likes"}<input type="number" ${at} data-k="min" value="${r.min || 0}" min="0"></label>` : ""}
        ${type === "gift" ? `<label class="grow">Solo estos regalos<input ${at} data-k="gifts" value="${esc(r.gifts || "")}" placeholder="rosa, león (vacío = todos)"></label>` : ""}</div>`}
    </div>`;
  }).join("");
  renderUserVoices();
}
function renderUserVoices() {
  const entries = Object.entries(config.tts.user_voices || {});
  $("uvCount").textContent = entries.length ? entries.length + " asignadas" : "";
  $("uvList").innerHTML = entries.map(([key, voice]) => {
    const [plat, ...rest] = key.startsWith("@") ? ["", key.slice(1)] : key.split(":");
    return `<div class="uv"><span class="pchip ${plat}">${plat ? plat.slice(0, 2).toUpperCase() : "@"}</span><b>${esc(rest.join(":"))}</b>
      <select data-uv="${esc(key)}">${voiceSelect(voice, "—")}</select><button class="btn icon tiny danger" data-uvdel="${esc(key)}" title="Quitar">${icon("x")}</button></div>`;
  }).join("") || '<div class="empty">Nadie tiene una voz asignada todavía.</div>';
}
async function saveUserVoices(map) { config = await api("PUT", "/api/config", { tts: { user_voices: map } }); renderUserVoices(); toast("Guardado"); }
$("uvAdd").onclick = () => {
  const user = $("uvUser").value.trim().replace(/^@/, ""), voice = $("uvVoice").value, plat = $("uvPlat").value;
  if (!user || !voice) return toast("Escribe el usuario y elige una voz", true);
  $("uvUser").value = "";
  saveUserVoices({ ...config.tts.user_voices, [plat === "@" ? "@" + user.toLowerCase() : plat + ":" + user]: voice });
};
$("uvList").addEventListener("change", (e) => { if (e.target.dataset.uv && e.target.value) saveUserVoices({ ...config.tts.user_voices, [e.target.dataset.uv]: e.target.value }); });
$("uvList").addEventListener("click", (e) => {
  const b = e.target.closest("[data-uvdel]");
  if (!b) return;
  const map = { ...config.tts.user_voices }; delete map[b.dataset.uvdel]; saveUserVoices(map);
});
$("readRows").addEventListener("change", async (e) => {
  const el = e.target, type = el.dataset.read, key = el.dataset.k;
  if (!type) return;
  const value = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
  if (key === "enabled") el.closest(".readrow").classList.toggle("off", !value);
  config = await api("PUT", "/api/config", type === "chat" && key === "enabled" ? { tts: { read_chat: value } } : { tts: { read: { [type]: { [key]: value } } } });
  if (type === "chat" && key === "enabled") $("tts_read_chat").checked = value;
  toast("Guardado");
});
$("tts_read_chat").addEventListener("change", () => setTimeout(fillReader, 300));
LISTS.forEach((id) => $(id).addEventListener("change", async (e) => {
  config = await api("PUT", "/api/config", { tts: { [id.slice(4)]: e.target.value.split(",").map((w) => w.trim()).filter(Boolean) } });
  toast("Guardado");
}));
$("ttsPlatforms").addEventListener("change", async (e) => {
  config = await api("PUT", "/api/config", { tts: { platforms: { [e.target.dataset.plat]: e.target.checked } } });
  toast("Guardado");
});
$("tts_random_voices_mode").addEventListener("change", async (e) => {
  const mode = e.target.value;
  config = await api("PUT", "/api/config", { tts: mode === "off" ? { random_voices: false } : { random_voices: true, random_pool: mode } });
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
  if (!el) return;
  if (from === target) return;
  shown[id] = target;
  const tile = el.closest(".tile");
  if (tile && target > from) { tile.classList.remove("bump"); void tile.offsetWidth; tile.classList.add("bump"); }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / 350), eased = 1 - Math.pow(1 - t, 3);
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
  $("miniTop").innerHTML = rows.map((r, i) => `<div class="mt"><span class="pos">${i + 1}</span><span class="nm">${esc(r.name)}</span>
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
  $("voiceGrid").innerHTML = list.map((v, i) => `<div class="voice ${v.kind} ${v.name === config.tts.voice ? "sel" : ""}" data-voice="${esc(v.name)}" title="${esc(v.name)}">
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
// ---- afinador de voces de personaje ----------------------------------------
let tuneVoice = "";
function showTune() {
  $("o_tunePitch").textContent = ($("tunePitch").value > 0 ? "+" : "") + $("tunePitch").value + " semitonos";
  $("o_tuneSpeed").textContent = Math.round($("tuneSpeed").value * 100) + "%";
  $("o_tuneIndex").textContent = Math.round($("tuneIndex").value * 100) + "%";
}
async function loadTuner(name) {
  const voice = voices.find((v) => v.name === name);
  if (!voice || voice.kind !== "rvc") { $("tuner").hidden = true; tuneVoice = ""; return; }
  const spec = await api("GET", "/api/voice/" + encodeURIComponent(name));
  tuneVoice = name;
  $("tuneName").textContent = name;
  $("tunePitch").value = (spec.rvc && spec.rvc.pitch) || 0;
  $("tuneSpeed").value = (1 / (spec.length_scale || 1)).toFixed(2);
  $("tuneIndex").value = spec.rvc && spec.rvc.index_influence !== undefined ? spec.rvc.index_influence : 0.66;
  $("tuneBase").innerHTML = voices.filter((v) => v.kind === "piper").map((v) => `<option ${v.name === spec.piper ? "selected" : ""}>${esc(v.name)}</option>`).join("");
  showTune();
  $("tuner").hidden = false;
}
async function saveTune() {
  if (!tuneVoice) return;
  await api("PUT", "/api/voice/" + encodeURIComponent(tuneVoice), { pitch: Number($("tunePitch").value), length_scale: Number((1 / $("tuneSpeed").value).toFixed(3)), index_influence: Number($("tuneIndex").value), piper: $("tuneBase").value });
  toast("Voz afinada");
}
["tunePitch", "tuneSpeed", "tuneIndex"].forEach((id) => { $(id).addEventListener("input", showTune); $(id).addEventListener("change", saveTune); });
$("tuneBase").addEventListener("change", saveTune);
$("tunePlay").onclick = () => tuneVoice && testVoice(tuneVoice);

async function testVoice(name) {
  const r = await api("POST", "/api/tts/test", { text: $("tts_test_text").value, voice: name });
  toast(r.ok ? `Probando "${name}"…` : "No se pudo: revisa que el TTS esté activo y sin silenciar", !r.ok);
}
$("voiceGrid").addEventListener("click", async (e) => {
  const play = e.target.closest("[data-play]");
  if (play) { e.stopPropagation(); loadTuner(play.dataset.play); return testVoice(play.dataset.play); }
  if (e.target.closest("[data-voice]")) loadTuner(e.target.closest("[data-voice]").dataset.voice);
  const chip = e.target.closest("[data-voice]");
  if (!chip) return;
  config = await api("PUT", "/api/config", { tts: { voice: chip.dataset.voice } });
  renderVoices();
  toast(`Voz predeterminada: ${chip.dataset.voice}`);
});
$("btnTtsTest").onclick = () => testVoice(config.tts.voice || (voices[0] && voices[0].name) || "");

// ---- overlays -----------------------------------------------------------
// Catálogo: cada overlay declara sus opciones; el panel arma la URL con ellas.
const EV = [["gift", "Regalo"], ["follow", "Seguidor"], ["like", "Like"], ["share", "Compartido"], ["chat", "Mensaje"], ["sub", "Suscripción"]];
const MET = [["coins", "Monedas"], ["likes", "Likes"], ["shares", "Compartidos"], ["comments", "Mensajes"]];
const SCOPE = [["session", "Esta sesión"], ["all", "Histórico"]];
const P = {
  title: (def = "") => ({ k: "title", l: "Título", t: "text", d: def }),
  type: (def, list = EV) => ({ k: "type", l: "Evento", t: "select", o: list, d: def }),
  gif: (l = "Tu GIF o imagen") => ({ k: "gif", l, t: "image", d: "" }),
  sound: (l = "Tu sonido") => ({ k: "sound", l, t: "audio", d: "" }),
};
const OVERLAYS = [
  { id: "alerts", name: "Alertas", desc: "Imagen, GIF, video y texto de tus reglas", path: "alerts", test: "gift", params: [] },
  { id: "top1", name: "Top donador", desc: "El mayor donador de la sesión", path: "leaderboard", test: "gift", preset: { limit: 1, title: "Top donador" },
    params: [{ k: "metric", l: "Métrica", t: "select", o: MET, d: "coins" }, { k: "scope", l: "Periodo", t: "select", o: SCOPE, d: "session" }, { k: "limit", l: "Puestos", t: "number", d: 5 }, P.title()] },
  { id: "top5", name: "Top donadores", desc: "Ranking de monedas de la sesión", path: "leaderboard", test: "gift", sameAs: "top1", preset: {} },
  { id: "topall", name: "Top donadores general", desc: "Ranking histórico de todos tus directos", path: "leaderboard", test: "gift", sameAs: "top1", preset: { scope: "all" } },
  { id: "toplikes", name: "Top likes", desc: "Quién ha dado más likes", path: "leaderboard", test: "like", sameAs: "top1", preset: { metric: "likes" } },
  { id: "topshares", name: "Top compartidos", desc: "Quién ha compartido más", path: "leaderboard", test: "share", sameAs: "top1", preset: { metric: "shares" } },
  { id: "rotator", name: "Tops rotativos", desc: "Un solo espacio que alterna entre varios tops", path: "rotator", test: "gift",
    params: [{ k: "metrics", l: "Tops (separados por coma)", t: "text", d: "coins,likes,shares" }, { k: "scope", l: "Periodo", t: "select", o: SCOPE, d: "session" }, { k: "limit", l: "Puestos", t: "number", d: 3 }, { k: "seconds", l: "Segundos por top", t: "number", d: 8 }] },
  { id: "goal", name: "Meta", desc: "Barra de progreso hacia un objetivo", path: "goal", test: "gift",
    params: [{ k: "metric", l: "Métrica", t: "select", o: [["coins", "Monedas"], ["likes", "Likes"], ["follows", "Seguidores"], ["shares", "Compartidos"]], d: "coins" }, { k: "goal", l: "Objetivo", t: "number", d: 1000 },
      { k: "start", l: "Empezar en", t: "number", d: 0 }, P.title(), { k: "style", l: "Forma", t: "select", o: [["", "Barra"], ["ring", "Anillo"]], d: "" }, P.gif("GIF al cumplirla"), P.sound("Sonido al cumplirla")] },
  { id: "chat", name: "Chat · burbujas", desc: "Mensajes de TikTok, Twitch y Kick juntos", path: "chat", test: "chat",
    params: [{ k: "style", l: "Estilo", t: "select", o: [["bubble", "Burbujas"], ["plain", "Solo texto"], ["outline", "Texto con contorno"], ["card", "Tarjetas"], ["compact", "Compacto"], ["tag", "Etiqueta de nombre"], ["bar", "Franja de color"],
        ["split", "Mensajería"], ["neon", "Neón"], ["terminal", "Terminal"], ["comic", "Cómic"], ["pixel", "Pixel retro"]], d: "bubble" },
      { k: "names", l: "Color de nombres", t: "select", o: [["platform", "Por plataforma"], ["user", "Uno por usuario"], ["accent", "Color de acento"]], d: "platform" },
      { k: "anim", l: "Entrada", t: "select", o: [["slide", "Deslizar"], ["fade", "Aparecer"], ["pop", "Rebote"], ["up", "Subir"]], d: "slide" },
      { k: "from", l: "Crece desde", t: "select", o: [["", "Abajo"], ["top", "Arriba"]], d: "" }, { k: "align", l: "Lado", t: "select", o: [["", "Izquierda"], ["right", "Derecha"]], d: "" },
      { k: "size", l: "Tamaño de letra", t: "number", d: 16 }, { k: "width", l: "Ancho (px)", t: "number", d: 460 }, { k: "max", l: "Mensajes visibles", t: "number", d: 8 },
      { k: "fade", l: "Ocultar tras (s, 0 = nunca)", t: "number", d: 0 }, { k: "minlen", l: "Letras mínimas", t: "number", d: 0 },
      { k: "avatars", l: "Avatares", t: "check", d: true }, { k: "badges", l: "Insignia de plataforma", t: "check", d: false },
      { k: "events", l: "Incluir regalos y follows", t: "check", d: false }, { k: "hidecmd", l: "Ocultar comandos (!)", t: "check", d: true }] },
  { id: "chat_plain", name: "Chat · solo texto", desc: "Sin fondo, con sombra para leerse sobre el juego", path: "chat", test: "chat", sameAs: "chat", preset: { style: "plain", avatars: false, names: "user" } },
  { id: "chat_outline", name: "Chat · contorno grueso", desc: "Letras con borde negro, muy legible", path: "chat", test: "chat", sameAs: "chat", preset: { style: "outline", avatars: false, names: "user", size: 20 } },
  { id: "chat_card", name: "Chat · tarjetas", desc: "Nombre arriba y franja de color por usuario", path: "chat", test: "chat", sameAs: "chat", preset: { style: "card", names: "user" } },
  { id: "chat_tag", name: "Chat · etiqueta", desc: "El nombre en una etiqueta de color", path: "chat", test: "chat", sameAs: "chat", preset: { style: "tag", names: "user", avatars: false } },
  { id: "chat_compact", name: "Chat · compacto", desc: "Una línea por mensaje, ocupa poco", path: "chat", test: "chat", sameAs: "chat", preset: { style: "compact", max: 14, size: 14 } },
  { id: "chat_split", name: "Chat · mensajería", desc: "Globos alternados como en un chat de móvil", path: "chat", test: "chat", sameAs: "chat", preset: { style: "split", avatars: false, anim: "pop" } },
  { id: "chat_neon", name: "Chat · neón", desc: "Borde luminoso del color de cada usuario", path: "chat", test: "chat", sameAs: "chat", preset: { style: "neon", names: "user" } },
  { id: "chat_terminal", name: "Chat · terminal", desc: "Estilo consola verde", path: "chat", test: "chat", sameAs: "chat", preset: { style: "terminal", anim: "fade" } },
  { id: "chat_comic", name: "Chat · cómic", desc: "Globos blancos con trazo grueso", path: "chat", test: "chat", sameAs: "chat", preset: { style: "comic", anim: "pop" } },
  { id: "chat_pixel", name: "Chat · pixel retro", desc: "Cajas de diálogo de videojuego clásico", path: "chat", test: "chat", sameAs: "chat", preset: { style: "pixel", max: 5 } },
  { id: "chat_events", name: "Chat + eventos", desc: "Mensajes, regalos y follows en la misma lista", path: "chat", test: "gift", sameAs: "chat", preset: { style: "bar", events: true, badges: true, names: "user" } },
  { id: "chatline", name: "Chat en una línea", desc: "Franja horizontal; lo nuevo entra por la derecha", path: "chatline", test: "chat",
    params: [{ k: "label", l: "Etiqueta", t: "text", d: "Chat" }, { k: "size", l: "Tamaño de letra", t: "number", d: 17 }, { k: "max", l: "Mensajes", t: "number", d: 12 }] },
  { id: "danmaku", name: "Chat volador", desc: "Los mensajes cruzan la pantalla de lado a lado", path: "danmaku", test: "chat",
    params: [{ k: "size", l: "Tamaño de letra", t: "number", d: 26 }, { k: "speed", l: "Velocidad", t: "number", d: 1 }, { k: "area", l: "Zona usada (% de alto)", t: "number", d: 100 }, { k: "name", l: "Mostrar nombre", t: "check", d: true }] },
  { id: "chatpop", name: "Burbujas flotantes", desc: "Cada mensaje es un globo que aparece y se va", path: "chatpop", test: "chat",
    params: [{ k: "style", l: "Color", t: "select", o: [["", "Blanco"], ["dark", "Oscuro"]], d: "" }, { k: "seconds", l: "Duración (s)", t: "number", d: 6 }, { k: "size", l: "Tamaño de letra", t: "number", d: 16 }, { k: "max", l: "A la vez", t: "number", d: 10 }] },
  { id: "spotlight", name: "Mensaje destacado", desc: "Un mensaje a la vez, en grande y letra por letra", path: "spotlight", test: "chat", say: "!destacar ¡Este mensaje sale en grande!",
    params: [{ k: "mode", l: "Qué mensajes", t: "select", o: [["all", "Todos"], ["cmd", "Solo con comando"], ["donors", "Solo de quien regaló"]], d: "all" }, { k: "cmd", l: "Comando", t: "text", d: "!destacar" },
      { k: "seconds", l: "Segundos en pantalla", t: "number", d: 7 }, { k: "size", l: "Tamaño de letra", t: "number", d: 26 }, { k: "type", l: "Escribir letra por letra", t: "check", d: true }, P.sound()] },
  { id: "questions", name: "Preguntas del chat", desc: "Lista de preguntas para responder en orden", path: "questions", test: "chat", say: "¿A qué hora empiezas mañana?",
    params: [P.title("Preguntas del chat"), { k: "cmd", l: "Comando (vacío = mensajes con ?)", t: "text", d: "" }, { k: "done", l: "Comando para marcar respondida", t: "text", d: "!respondida" },
      { k: "owner", l: "Quién puede marcar (tu usuario)", t: "text", d: "" }, { k: "max", l: "Preguntas visibles", t: "number", d: 5 }, { k: "reset", l: "Vaciar al cargar", t: "check", d: false }] },
  { id: "pinned", name: "Mensaje fijado", desc: "Un aviso fijo que cambias desde el chat", path: "pinned", test: "chat", say: "!fijar Hoy: torneo a las 9 pm",
    params: [P.title("Fijado"), { k: "text", l: "Texto inicial", t: "text", d: "" }, { k: "cmd", l: "Comando para fijar", t: "text", d: "!fijar" }, { k: "clear", l: "Comando para quitar", t: "text", d: "!quitar" },
      { k: "owner", l: "Quién puede fijar (tu usuario)", t: "text", d: "" }, { k: "size", l: "Tamaño de letra", t: "number", d: 19 }, P.sound()] },
  { id: "emotes", name: "Muro de emojis", desc: "Los emojis del chat vuelan por la pantalla", path: "emotes", test: "chat", say: "😂🔥❤️👏🎉",
    params: [{ k: "mode", l: "Movimiento", t: "select", o: [["rise", "Suben"], ["fall", "Caen"], ["burst", "Aparecen"]], d: "rise" }, { k: "size", l: "Tamaño (px)", t: "number", d: 40 }, { k: "each", l: "Máximo por mensaje", t: "number", d: 6 }] },
  { id: "feed", name: "Actividad reciente", desc: "Lista de regalos, follows y compartidos", path: "feed", test: "follow",
    params: [P.title("Actividad"), { k: "types", l: "Eventos (separados por coma)", t: "text", d: "gift,follow,share,sub,raid" }, { k: "max", l: "Filas", t: "number", d: 6 }] },
  { id: "lastevent", name: "Último seguidor / regalo", desc: "Tarjeta con el evento más reciente", path: "lastevent", test: "$type",
    params: [P.type("follow", EV.filter((e) => e[0] !== "chat")), P.title()] },
  { id: "stats", name: "Contadores", desc: "Monedas, likes, seguidores y compartidos", path: "stats", test: "like",
    params: [{ k: "show", l: "Mostrar (separados por coma)", t: "text", d: "coins,likes,follows,shares" }, { k: "layout", l: "Dirección", t: "select", o: [["", "Horizontal"], ["col", "Vertical"]], d: "" }] },
  { id: "sticker", name: "Stickers con tus GIFs", desc: "Tu GIF aparece en pantalla con cada evento", path: "sticker", test: "$type",
    params: [P.type("follow"), P.gif(), P.sound(), { k: "match", l: "Solo si empieza con / regalo contiene", t: "text", d: "" }, { k: "min", l: "Mínimo (monedas o likes)", t: "number", d: 0 },
      { k: "seconds", l: "Duración (s)", t: "number", d: 4 }, { k: "size", l: "Tamaño (px)", t: "number", d: 220 }, { k: "pos", l: "Posición", t: "select", o: [["random", "Al azar"], ["center", "Centro"]], d: "random" }, { k: "name", l: "Mostrar nombre", t: "check", d: true }] },
  { id: "fountain", name: "Lluvia de corazones", desc: "Partículas que suben con likes, o tu propio GIF", path: "fountain", test: "$type",
    params: [P.type("like"), { k: "emoji", l: "Emoji", t: "text", d: "" }, P.gif("O tu GIF/imagen"), { k: "dir", l: "Dirección", t: "select", o: [["", "Sube"], ["down", "Cae"]], d: "" }, { k: "size", l: "Tamaño (px)", t: "number", d: 34 }] },
  { id: "confetti", name: "Celebración", desc: "Confeti o fuegos artificiales en regalos grandes", path: "confetti", test: "$type",
    params: [P.type("gift"), { k: "min", l: "Mínimo (monedas o likes)", t: "number", d: 100 }, { k: "style", l: "Efecto", t: "select", o: [["confetti", "Confeti"], ["fireworks", "Fuegos artificiales"]], d: "confetti" }, P.sound()] },
  { id: "timer", name: "Temporizador / subathon", desc: "Cuenta regresiva que el chat alarga", path: "timer", test: "gift",
    params: [P.title("Tiempo restante"), { k: "minutes", l: "Minutos iniciales", t: "number", d: 10 }, { k: "coin", l: "Segundos por moneda", t: "number", d: 1 }, { k: "follow", l: "Segundos por seguidor", t: "number", d: 30 },
      { k: "share", l: "Segundos por compartido", t: "number", d: 15 }, { k: "like", l: "Segundos por like", t: "number", d: 0 }, { k: "cap", l: "Tope (min, 0 = sin tope)", t: "number", d: 0 }, P.sound("Sonido al terminar"), { k: "reset", l: "Reiniciar al cargar", t: "check", d: false }] },
  { id: "ticker", name: "Cinta de texto", desc: "Mensajes que se desplazan, estilo noticiero", path: "ticker", test: "follow",
    params: [{ k: "text", l: "Mensajes (separados por |)", t: "text", d: "" }, { k: "label", l: "Etiqueta", t: "text", d: "" }, { k: "events", l: "Incluir últimos eventos", t: "check", d: false }, { k: "speed", l: "Velocidad", t: "number", d: 1 }] },
  { id: "subtitle", name: "Subtítulos de la voz", desc: "Muestra lo que el bot está leyendo", path: "subtitle", test: "tts", params: [{ k: "voice", l: "Mostrar nombre de la voz", t: "check", d: true }] },
  { id: "hype", name: "Medidor de hype", desc: "Sube con la actividad y baja con el tiempo", path: "hype", test: "gift",
    params: [P.title("Nivel de hype"), { k: "full", l: "Puntos para llenarlo", t: "number", d: 100 }, { k: "decay", l: "Puntos que pierde por segundo", t: "number", d: 4 }, P.sound("Sonido al llenarse")] },
  { id: "podium", name: "Podio", desc: "Los tres primeros en un podio con avatares", path: "podium", test: "gift",
    params: [{ k: "metric", l: "Métrica", t: "select", o: MET, d: "coins" }, { k: "scope", l: "Periodo", t: "select", o: SCOPE, d: "session" }, P.title()] },
  { id: "combo", name: "Combos de regalos", desc: "Contador que crece con regalos seguidos", path: "combo", test: "gift",
    params: [{ k: "seconds", l: "Segundos visible", t: "number", d: 6 }, { k: "max", l: "Combos a la vez", t: "number", d: 4 }, { k: "min", l: "Mínimo de monedas", t: "number", d: 0 }, P.sound()] },
  { id: "welcome", name: "Bienvenidas", desc: "Saluda a quien entra o te sigue", path: "welcome", test: "$type",
    params: [P.type("join", [["join", "Entra al directo"], ["follow", "Seguidor"], ["share", "Compartido"], ["sub", "Suscripción"]]), { k: "text", l: "Frase ({user})", t: "text", d: "" }, P.gif(), P.sound(),
      { k: "seconds", l: "Duración (s)", t: "number", d: 4 }, { k: "gap", l: "Espera entre saludos (s)", t: "number", d: 2 }] },
  { id: "poll", name: "Encuesta", desc: "El chat vota escribiendo un número", path: "poll", test: "poll",
    params: [{ k: "q", l: "Pregunta", t: "text", d: "" }, { k: "options", l: "Opciones (separadas por |)", t: "text", d: "Sí|No" }, { k: "seconds", l: "Cerrar tras (s, 0 = abierta)", t: "number", d: 0 }, { k: "id", l: "Nº de encuesta (cámbialo para empezar otra)", t: "text", d: "1" }] },
  { id: "wheel", name: "Ruleta", desc: "Gira con un regalo o con un comando del chat", path: "wheel", test: "$type",
    params: [{ k: "options", l: "Premios (separados por |)", t: "text", d: "" }, P.type("gift", [["gift", "Regalo"], ["chat", "Comando del chat"], ["follow", "Seguidor"], ["share", "Compartido"]]),
      { k: "match", l: "Comando o nombre del regalo", t: "text", d: "" }, { k: "min", l: "Mínimo de monedas", t: "number", d: 0 }, P.sound("Sonido al girar"), { k: "winsound", l: "Sonido del resultado", t: "audio", d: "" }, { k: "always", l: "Siempre visible", t: "check", d: false }] },
  { id: "battle", name: "Batalla de equipos", desc: "Dos bandos compiten con palabras o regalos", path: "battle", test: "battle",
    params: [P.title(), { k: "a", l: "Equipo A", t: "text", d: "Equipo rojo" }, { k: "b", l: "Equipo B", t: "text", d: "Equipo azul" }, { k: "ka", l: "Palabra de A", t: "text", d: "#rojo" }, { k: "kb", l: "Palabra de B", t: "text", d: "#azul" },
      { k: "ga", l: "Regalo de A", t: "text", d: "" }, { k: "gb", l: "Regalo de B", t: "text", d: "" }, { k: "reset", l: "Reiniciar al cargar", t: "check", d: false }] },
  { id: "queue", name: "Fila para jugar", desc: "Los espectadores entran con un comando", path: "queue", test: "queue",
    params: [P.title("Fila para jugar"), { k: "join", l: "Comando para entrar", t: "text", d: "!unirme" }, { k: "leave", l: "Comando para salir", t: "text", d: "!salir" }, { k: "next", l: "Comando para avanzar", t: "text", d: "!siguiente" },
      { k: "owner", l: "Quién puede avanzar (tu usuario)", t: "text", d: "" }, { k: "max", l: "Cupo", t: "number", d: 8 }, { k: "reset", l: "Vaciar al cargar", t: "check", d: false }] },
  { id: "words", name: "Nube de palabras", desc: "Lo que más se repite en el chat", path: "words", test: "words",
    params: [P.title("El chat dice"), { k: "max", l: "Palabras", t: "number", d: 18 }, { k: "minlen", l: "Letras mínimas", t: "number", d: 4 }, { k: "minutes", l: "Minutos que duran", t: "number", d: 5 }] },
  { id: "starting", name: "Pantalla de espera", desc: "Empezamos pronto, ya vuelvo o fin del directo", path: "starting",
    params: [P.title("Empezamos pronto"), { k: "sub", l: "Subtítulo", t: "text", d: "" }, { k: "minutes", l: "Cuenta regresiva (min, 0 = sin)", t: "number", d: 5 }, P.gif(), { k: "bg", l: "Tu fondo", t: "image", d: "" }, P.sound("Sonido al terminar"), { k: "clear", l: "Fondo transparente", t: "check", d: false }] },
  { id: "image", name: "Tu GIF o logo", desc: "Imagen fija con efecto de movimiento", path: "image",
    params: [P.gif(), { k: "size", l: "Ancho (px)", t: "number", d: 300 }, { k: "effect", l: "Efecto", t: "select", o: [["", "Ninguno"], ["float", "Flotar"], ["pulse", "Latir"], ["spin", "Girar"], ["shake", "Temblar"]], d: "" }, { k: "text", l: "Texto debajo", t: "text", d: "" }] },
  { id: "socials", name: "Tus redes", desc: "Tarjeta que rota entre tus cuentas", path: "socials",
    params: [{ k: "items", l: "Redes (Red:usuario separadas por |)", t: "text", d: "" }, { k: "layout", l: "Formato", t: "select", o: [["", "Rotar"], ["row", "Todas en fila"]], d: "" }, { k: "seconds", l: "Segundos por red", t: "number", d: 6 }] },
  { id: "clock", name: "Reloj / tiempo en vivo", desc: "Hora local o cuánto llevas en directo", path: "clock",
    params: [{ k: "mode", l: "Modo", t: "select", o: [["clock", "Hora"], ["uptime", "Tiempo en directo"]], d: "clock" }, P.title(), { k: "seconds", l: "Mostrar segundos", t: "check", d: false }, { k: "h12", l: "Formato 12 h", t: "check", d: false }, { k: "date", l: "Mostrar fecha", t: "check", d: true }] },
  { id: "hrgraph", name: "Gráfica de pulso", desc: "Tus pulsaciones de los últimos minutos", path: "hrgraph", test: "hr", params: [{ k: "minutes", l: "Minutos de historial", t: "number", d: 3 }] },
  { id: "heartrate", name: "Pulsómetro", desc: "Tus pulsaciones en vivo", path: "heartrate", test: "hr", params: [] },
];
const COMMON = [{ k: "accent", l: "Color de acento", t: "color", d: "#ff6b35" }, { k: "scale", l: "Escala", t: "number", d: 1 }];
const ovDef = (id) => OVERLAYS.find((o) => o.id === id);
const ovParams = (o) => (o.sameAs ? ovDef(o.sameAs).params : o.params).concat(COMMON);
let overlaysDrawn = false, ovValues = {};
try { ovValues = JSON.parse(localStorage.getItem("streamops_overlays") || "{}"); } catch (err) { ovValues = {}; }
function ovStore() { try { localStorage.setItem("streamops_overlays", JSON.stringify(ovValues)); } catch (err) { /* sin almacenamiento */ } }
function ovGet(o, p) { const v = (ovValues[o.id] || {})[p.k]; return v !== undefined ? v : o.preset && o.preset[p.k] !== undefined ? o.preset[p.k] : p.d; }
function ovUrl(o) {
  const q = new URLSearchParams();
  for (const p of ovParams(o)) {
    const v = ovGet(o, p);
    if (p.t === "check") { if (!!v !== !!p.d) q.set(p.k, v ? "1" : "0"); }
    else if (String(v) !== String(p.d) && v !== "") q.set(p.k, p.t === "color" ? String(v).replace("#", "") : v);
  }
  const qs = q.toString();
  return "/overlay/" + o.path + (qs ? "?" + qs : "");
}
function ovField(o, p) {
  const v = ovGet(o, p), at = `data-ov="${o.id}" data-k="${p.k}"`;
  if (p.t === "check") return `<label class="sw"><input type="checkbox" ${at} ${v ? "checked" : ""}><i></i>${p.l}</label>`;
  if (p.t === "select") return `<label>${p.l}<select ${at}>${p.o.map(([val, lab]) => `<option value="${val}" ${String(v) === val ? "selected" : ""}>${lab}</option>`).join("")}</select></label>`;
  if (p.t === "image" || p.t === "audio") {
    const files = media.filter((m) => (p.t === "audio" ? m.kind === "audio" : m.kind === "image"));
    return `<label>${p.l}<select ${at} data-pick="${p.t}"><option value="">— ninguno —</option>${files.map((m) => `<option value="${esc(m.name)}" ${v === m.name ? "selected" : ""}>${esc(m.name)}</option>`).join("")}<option value="__upload">Subir archivo…</option></select></label>`;
  }
  if (p.t === "color") return `<label>${p.l}<input type="color" ${at} value="${esc(v)}"></label>`;
  return `<label>${p.l}<input type="${p.t === "number" ? "number" : "text"}" step="any" ${at} value="${esc(v)}"></label>`;
}
const OV_GROUPS = [["all", "Todos"], ["chat", "Chat"], ["top", "Tops y metas"], ["alert", "Alertas y efectos"], ["game", "Juegos con el chat"], ["info", "Información"]];
const OV_GROUP_OF = { chat: /^(chat|danmaku|spotlight|questions|pinned|emotes|words|subtitle)/, top: /^(top|rotator|podium|goal|stats|hype|lastevent|feed|combo)/, alert: /^(alerts|sticker|fountain|confetti|welcome|image)/,
  game: /^(poll|wheel|battle|queue|timer)/ };
const ovGroup = (o) => (Object.entries(OV_GROUP_OF).find(([, re]) => re.test(o.id)) || ["info"])[0];
let ovFilter = "all";
function ovVisible() {
  const q = $("ovSearch").value.trim().toLowerCase();
  return OVERLAYS.filter((o) => (ovFilter === "all" || ovGroup(o) === ovFilter) && (!q || (o.name + " " + o.desc).toLowerCase().includes(q)));
}
function renderOverlays() {
  if (overlaysDrawn) return;
  overlaysDrawn = true;
  $("ovFilter").innerHTML = OV_GROUPS.map(([id, label]) => `<button class="${id === ovFilter ? "on" : ""}" data-g="${id}">${label} <small>${id === "all" ? OVERLAYS.length : OVERLAYS.filter((o) => ovGroup(o) === id).length}</small></button>`).join("");
  $("overlays").innerHTML = ovVisible().map((o) => { const path = ovUrl(o); return `<div class="card ov" id="ov_${o.id}"><div><h2>${o.name}</h2><p class="ovd">${o.desc}</p></div>
    <div class="frame"><iframe src="${path}" loading="lazy" tabindex="-1" allow="autoplay"></iframe></div>
    <input readonly class="url" value="${location.origin}${path}" onclick="this.select()">
    <div class="actions"><button class="btn tiny" data-act="copy">${icon("copy")}Copiar</button>${o.test ? `<button class="btn tiny ghost" data-act="test">${icon("zap")}Probar</button>` : ""}
      <button class="btn tiny ghost" data-act="edit">${icon("cog")}Personalizar</button><button class="btn tiny ghost icon" data-act="open" title="Abrir">${icon("ext")}</button></div>
    <div class="ovform" hidden>${ovParams(o).map((p) => ovField(o, p)).join("")}<button class="btn tiny ghost danger" data-act="reset">Restablecer</button></div></div>`; }).join("") || '<div class="empty">Ningún overlay coincide.</div>';
}
$("ovSearch").addEventListener("input", () => { overlaysDrawn = false; renderOverlays(); });
$("ovFilter").addEventListener("click", (e) => { const b = e.target.closest("[data-g]"); if (!b) return; ovFilter = b.dataset.g; overlaysDrawn = false; renderOverlays(); });
function ovRefresh(o) {
  const card = $("ov_" + o.id), path = ovUrl(o);
  card.querySelector(".url").value = location.origin + path;
  clearTimeout(card._t);
  card._t = setTimeout(() => { card.querySelector("iframe").src = path; }, 450);
}
function redrawOverlays(keepOpen) {
  if (!overlaysDrawn) return;
  const open = [...document.querySelectorAll(".ovform:not([hidden])")].map((f) => f.parentElement.id.slice(3));
  if (keepOpen && !open.includes(keepOpen)) open.push(keepOpen);
  overlaysDrawn = false; renderOverlays();
  open.forEach((id) => { const card = $("ov_" + id); if (card) card.querySelector(".ovform").hidden = false; });
}
let ovPickTarget = null;
$("overlays").addEventListener("input", (e) => {
  const el = e.target, o = ovDef(el.dataset.ov);
  if (!o) return;
  if (el.value === "__upload") { ovPickTarget = { ov: o.id, k: el.dataset.k }; el.value = ""; $("ovFile").accept = el.dataset.pick === "audio" ? "audio/*" : "image/*"; $("ovFile").click(); return; }
  (ovValues[o.id] = ovValues[o.id] || {})[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value;
  ovStore(); ovRefresh(o);
});
$("ovFile").addEventListener("change", async (e) => {
  const file = e.target.files[0], target = ovPickTarget;
  e.target.value = "";
  if (!file || !target) return;
  const saved = await upload([file]);
  if (saved && saved[0]) { (ovValues[target.ov] = ovValues[target.ov] || {})[target.k] = saved[0]; ovStore(); redrawOverlays(target.ov); }
});
$("overlays").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-act]");
  if (!b) return;
  const card = b.closest(".ov"), o = ovDef(card.id.slice(3)), act = b.dataset.act;
  if (act === "copy") { navigator.clipboard.writeText(location.origin + ovUrl(o)); toast("URL copiada"); }
  else if (act === "open") window.open(ovUrl(o), "_blank");
  else if (act === "edit") card.querySelector(".ovform").hidden = !card.querySelector(".ovform").hidden;
  else if (act === "reset") { delete ovValues[o.id]; ovStore(); redrawOverlays(o.id); }
  else if (act === "test") {
    b.disabled = true;
    try { await ovTest(card, o); } finally { b.disabled = false; }
  }
});
// La vista previa debe estar cargada y conectada antes de enviarle la prueba.
$("overlays").addEventListener("load", (e) => { if (e.target.tagName === "IFRAME") e.target.dataset.ready = Date.now(); }, true);
async function ovReady(card) {
  const frame = card.querySelector("iframe");
  if (card._t) { clearTimeout(card._t); card._t = null; delete frame.dataset.ready; frame.src = ovUrl(ovDef(card.id.slice(3))); }
  for (let i = 0; i < 50; i++) {
    const ready = Number(frame.dataset.ready || 0);
    if (ready && Date.now() - ready > 600) return;
    await new Promise((r) => setTimeout(r, 100));
  }
}
async function ovTest(card, o) {
  await ovReady(card);
  const direct = { alerts: "alert", subtitle: "tts", heartrate: "hr", hrgraph: "hr" }[o.id];
  if (direct) return api("POST", "/api/overlay/test", { kind: direct });
  const val = (k) => { const p = ovParams(o).find((x) => x.k === k); return p ? ovGet(o, p) : ""; };
  const sim = (body) => api("POST", "/api/simulate", { quiet: true, user: "Prueba", ...body });
  const type = o.test === "$type" ? val("type") : o.test, match = val("match");
  const chats = { poll: ["1", "2", "1"], battle: [val("ka"), val("kb"), val("ka")], queue: [val("join")], words: ["qué buen directo amigos", "directo increíble saludos", "saludos amigos del directo"] }[o.test];
  if (chats) { for (const text of chats) await sim({ type: "chat", user: "Prueba" + Math.floor(Math.random() * 900 + 100), text }); return; }
  if (o.id === "ticker" && !val("events")) toast("Activa «Incluir últimos eventos» en Personalizar para ver la prueba");
  const min = Number(val("min")) || 0;
  await sim({ type, gift: (type === "gift" && match) || "Rosa", count: type === "like" ? Math.max(30, min) : 1, value: type === "gift" ? Math.max(150, min) : 0,
    text: type === "chat" ? o.say || (match || (o.id === "wheel" ? "!girar" : "")) + " hola desde la prueba" : "" });
}

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
    return `<div class="rule ${openRules.has(ri) ? "open" : ""} ${r.enabled === false ? "off" : ""}">
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
    return `<div class="mtile"><div class="th">${thumb}</div><span class="kd">${m.kind}</span>
      ${m.kind === "audio" ? `<button class="btn icon tiny ply" data-play="${esc(m.name)}" title="Escuchar">${icon("play")}</button>` : ""}
      <button class="btn icon tiny danger del" data-del="${esc(m.name)}" title="Eliminar">${icon("x")}</button>
      <div class="inf"><b title="${esc(m.name)}">${esc(m.name)}</b><small>${(m.size / 1048576).toFixed(1)} MB</small></div></div>`;
  }).join("") || '<div class="empty">Aún no hay archivos.</div>';
  renderRules();
  redrawOverlays();
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
  const saved = (await res.json()).saved;
  await loadMedia();
  return saved;
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

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
  if (view === "overlays") renderOverlays(); else if (overlaysDrawn) { $("overlays").innerHTML = ""; overlaysDrawn = false; }
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
  { id: "chat", name: "Chat", desc: "Mensajes de TikTok, Twitch y Kick juntos", path: "chat", test: "chat",
    params: [{ k: "style", l: "Estilo", t: "select", o: [["bubble", "Burbujas"], ["plain", "Solo texto"]], d: "bubble" }, { k: "max", l: "Mensajes visibles", t: "number", d: 8 }, { k: "fade", l: "Ocultar tras (s, 0 = nunca)", t: "number", d: 0 }, { k: "avatars", l: "Mostrar avatares", t: "check", d: true }] },
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
  { id: "heartrate", name: "Pulsómetro", desc: "Tus pulsaciones en vivo", path: "heartrate", params: [] },
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
function renderOverlays() {
  if (overlaysDrawn) return;
  overlaysDrawn = true;
  $("overlays").innerHTML = OVERLAYS.map((o) => { const path = ovUrl(o); return `<div class="card ov" id="ov_${o.id}"><div><h2>${o.name}</h2><p class="ovd">${o.desc}</p></div>
    <div class="frame"><iframe src="${path}" loading="lazy" tabindex="-1"></iframe></div>
    <input readonly class="url" value="${location.origin}${path}" onclick="this.select()">
    <div class="actions"><button class="btn tiny" data-act="copy">${icon("copy")}Copiar</button>${o.test ? `<button class="btn tiny ghost" data-act="test">${icon("zap")}Probar</button>` : ""}
      <button class="btn tiny ghost" data-act="edit">${icon("cog")}Personalizar</button><button class="btn tiny ghost icon" data-act="open" title="Abrir">${icon("ext")}</button></div>
    <div class="ovform" hidden>${ovParams(o).map((p) => ovField(o, p)).join("")}<button class="btn tiny ghost danger" data-act="reset">Restablecer</button></div></div>`; }).join("");
}
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
  open.forEach((id) => { $("ov_" + id).querySelector(".ovform").hidden = false; });
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
    if (o.test === "tts") return api("POST", "/api/tts/test", { text: "Así se ven los subtítulos de la voz." });
    const type = o.test === "$type" ? ovGet(o, ovParams(o).find((p) => p.k === "type")) : o.test;
    const match = (ovValues[o.id] || {}).match || "";
    await api("POST", "/api/simulate", { type, user: "Prueba", gift: match || "Rosa", count: type === "like" ? 30 : 1, value: type === "gift" ? 150 : 0, text: (match ? match + " " : "") + "hola desde la prueba" });
  }
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

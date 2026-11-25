// Utilidades compartidas por panel y overlays.
window.StreamOps = {
  params: new URLSearchParams(location.search),
  muted: false,
  // Lee un parámetro de la URL con valor por defecto.
  p(key, def = "") { const v = this.params.get(key); return v === null || v === "" ? def : v; },
  num(key, def = 0) { const v = parseFloat(this.params.get(key)); return Number.isFinite(v) ? v : def; },
  flag(key, def = false) { const v = this.params.get(key); return v === null ? def : v !== "0" && v !== "false"; },
  media(name) { return name ? "/media/" + encodeURIComponent(name) : ""; },
  // Reproduce un sonido de la biblioteca, respetando el silencio global.
  sound(name, volume = 1) {
    if (!name || this.muted) return;
    const audio = new Audio(this.media(name));
    audio.volume = Math.max(0, Math.min(1, volume));
    audio.play().catch(() => {});
  },
  connect(onMessage) {
    const open = () => {
      const ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch (err) { return; }
        if (msg.type === "state" || msg.type === "mute") StreamOps.muted = !!msg.muted;
        try { onMessage(msg); } catch (err) { console.error(err); }
      };
      ws.onclose = () => setTimeout(open, 2000);
      ws.onerror = () => ws.close();
    };
    open();
  },
  fmt(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return Math.round(n).toLocaleString("es-MX");
  },
  esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  },
  // Cantidad que aporta un evento a una métrica (coins, likes, follows, shares, comments, subs).
  amount(event, metric) {
    const map = { coins: "gift", likes: "like", follows: "follow", shares: "share", comments: "chat", subs: "sub" };
    if (event.type !== map[metric]) return 0;
    if (metric === "coins") return Number(event.value) || 0;
    if (metric === "likes") return Number(event.count) || 1;
    return 1;
  },
  describe(e) {
    const u = `<b>${this.esc(e.user)}</b>`;
    switch (e.type) {
      case "chat": return `${u} ${this.esc(e.text)}`;
      case "gift": return `${u} envió ${e.count}× ${this.esc(e.gift)}`;
      case "like": return `${u} dio ${e.count} like(s)`;
      case "follow": return `${u} te siguió`;
      case "share": return `${u} compartió el directo`;
      case "sub": return `${u} se suscribió`;
      case "raid": return `${u} llegó con ${e.count} personas`;
      default: return "";
    }
  },
  // Aplica ?accent=hex y ?scale=1.2 comunes a todos los overlays.
  applyTheme() {
    const accent = this.params.get("accent");
    if (accent) document.documentElement.style.setProperty("--accent", "#" + accent.replace("#", ""));
    const scale = this.num("scale", 1);
    if (scale !== 1) document.documentElement.style.zoom = scale;
  },
};
if (document.documentElement.classList.contains("overlay")) StreamOps.applyTheme();

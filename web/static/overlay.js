// Utilidades compartidas por panel y overlays: WebSocket con reconexión.
window.StreamOps = {
  params: new URLSearchParams(location.search),
  connect(onMessage) {
    const open = () => {
      const ws = new WebSocket(`ws://${location.host}/ws`);
      ws.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data)); } catch (err) { console.error(err); }
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
};

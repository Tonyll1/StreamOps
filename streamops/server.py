"""Servidor HTTP/WebSocket local: panel, API y overlays para OBS."""

from __future__ import annotations

import asyncio
import json
import random
import time
import copy
import logging
import os
import re
import threading

from aiohttp import web

from .app import App
from .bus import Event
from . import engine, voces
from .config import DATA, FROZEN, VOICES, MEDIA, WEB
from .descargas import ENGINE_JOB
from .connectors.heartrate import scan_ble
from .rules import media_kind

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_UPLOAD = 200 * 1024 * 1024
_LOCAL_HOSTS = ("127.0.0.1", "localhost")


def build_web_app(app: App) -> web.Application:
    routes = web.RouteTableDef()

    def config_json() -> web.Response:
        return web.json_response(copy.deepcopy(app.config.data))

    @routes.get("/")
    async def index(_request: web.Request) -> web.FileResponse:
        return web.FileResponse(WEB / "dashboard.html")

    @routes.get("/overlay/{name}")
    async def overlay(request: web.Request) -> web.StreamResponse:
        name = _SAFE_NAME.sub("", request.match_info["name"])
        path = WEB / "overlays" / f"{name}.html"
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    @routes.get("/ws")
    async def websocket(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        app.sockets.add(ws)
        try:
            await ws.send_json(app.state())
            await ws.send_json({"type": "history", "events": list(app.recent)})
            async for _msg in ws:
                pass
        finally:
            app.sockets.discard(ws)
        return ws

    @routes.get("/api/state")
    async def state(_request: web.Request) -> web.Response:
        return web.json_response(app.state())

    @routes.get("/api/config")
    async def get_config(_request: web.Request) -> web.Response:
        return config_json()

    @routes.put("/api/config")
    async def put_config(request: web.Request) -> web.Response:
        patch = await request.json()
        if not isinstance(patch, dict):
            raise web.HTTPBadRequest(text="Se esperaba un objeto JSON")
        old_hr = dict(app.config["heartrate"])
        touched_hotkeys = "hotkeys" in patch
        app.config.update(patch)
        if touched_hotkeys:
            app.bind_hotkeys()
        if dict(app.config["heartrate"]) != old_hr:
            await app.connectors["heartrate"].stop()
            if app.config["heartrate"]["source"] != "off":
                app.connectors["heartrate"].start()
        return config_json()

    @routes.post("/api/connect/{name}")
    async def connect(request: web.Request) -> web.Response:
        connector = app.connectors.get(request.match_info["name"])
        if connector is None:
            raise web.HTTPNotFound()
        await connector.stop()
        connector.start()
        return web.json_response({"ok": True})

    @routes.post("/api/disconnect/{name}")
    async def disconnect(request: web.Request) -> web.Response:
        connector = app.connectors.get(request.match_info["name"])
        if connector is None:
            raise web.HTTPNotFound()
        await connector.stop()
        return web.json_response({"ok": True})

    @routes.post("/api/simulate")
    async def simulate(request: web.Request) -> web.Response:
        await app.simulate(await request.json())
        return web.json_response({"ok": True})

    @routes.post("/api/mute")
    async def mute(request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else {}
        return web.json_response({"muted": app.toggle_mute(body.get("muted"))})

    @routes.post("/api/skip")
    async def skip(_request: web.Request) -> web.Response:
        app.tts.skip()
        return web.json_response({"ok": True})

    @routes.post("/api/stop")
    async def stop(_request: web.Request) -> web.Response:
        app.stop_all()
        return web.json_response({"ok": True})

    @routes.post("/api/session/reset")
    async def reset(request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else {}
        if body.get("all"):
            app.store.reset_all()
        else:
            app.store.reset_session()
        await app.broadcast(app.state())
        return web.json_response({"ok": True})

    @routes.get("/api/voices")
    async def voices(_request: web.Request) -> web.Response:
        return web.json_response(app.tts.voices())

    def _voice_file(request: web.Request):
        name = request.match_info["name"]
        path = (VOICES / f"{name}.voice.json").resolve()
        if path.parent != VOICES.resolve() or not path.is_file():
            raise web.HTTPNotFound(text="Esa voz no es de personaje o no existe")
        return path

    @routes.get("/api/voice/{name}")
    async def voice_get(request: web.Request) -> web.Response:
        return web.json_response(json.loads(_voice_file(request).read_text(encoding="utf-8")))

    @routes.put("/api/voice/{name}")
    async def voice_put(request: web.Request) -> web.Response:
        """Afinación de una voz de personaje: tono, velocidad, voz base y fuerza del timbre."""
        path = _voice_file(request)
        body = await request.json()
        spec = json.loads(path.read_text(encoding="utf-8"))
        rvc = spec.setdefault("rvc", {})
        if "pitch" in body:
            rvc["pitch"] = max(-24, min(24, int(body["pitch"])))
        if "index_influence" in body:
            rvc["index_influence"] = max(0.0, min(1.0, float(body["index_influence"])))
        if "length_scale" in body:
            spec["length_scale"] = max(0.5, min(2.0, float(body["length_scale"])))
        if body.get("piper") and (VOICES / f"{body['piper']}.onnx").is_file():
            spec["piper"] = str(body["piper"])
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        return web.json_response(spec)

    @routes.post("/api/tts/test")
    async def tts_test(request: web.Request) -> web.Response:
        body = await request.json()
        app.tts.clear()  # una prueba no espera a que termine lo que esté sonando
        queued = app.tts.say(body.get("text") or "Hola, esta es una prueba de voz.", voice=body.get("voice") or None)
        return web.json_response({"ok": queued})

    @routes.post("/api/rule/test")
    async def rule_test(request: web.Request) -> web.Response:
        """Ejecuta las acciones de una regla con un evento de prueba."""
        rule = await request.json()
        event = Event(
            platform="sim", type=rule.get("event", "gift"), user_id="tester", user="Tester",
            gift="Rosa", count=5, value=5, text="hola",
        )
        for action in rule.get("actions", []):
            await app.rules.run_action(action, event)
        return web.json_response({"ok": True})

    @routes.post("/api/overlay/test")
    async def overlay_test(request: web.Request) -> web.Response:
        """Envía a los overlays un mensaje de muestra (alerta, subtítulo o pulso) sin sonido."""
        kind = (await request.json()).get("kind")
        samples = {
            "alert": {"type": "alert", "text": "Prueba envió 5x Rosa", "media": "", "media_kind": "", "duration": 4, "avatar": "", "muted": True},
            "tts": {"type": "tts", "text": "Así se ven los subtítulos de la voz.", "voice": app.config["tts"].get("voice", ""), "seconds": 4},
            "hr": {"type": "hr", "bpm": random.randint(72, 148), "ts": time.time()},
        }
        if kind not in samples:
            raise web.HTTPBadRequest(text="Prueba desconocida")
        await app.broadcast(samples[kind])
        return web.json_response({"ok": True})

    @routes.get("/api/media")
    async def media_list(_request: web.Request) -> web.Response:
        files = [
            {"name": p.name, "kind": media_kind(p.name), "size": p.stat().st_size}
            for p in sorted(MEDIA.iterdir())
            if p.is_file() and media_kind(p.name)
        ]
        return web.json_response(files)

    @routes.post("/api/media")
    async def media_upload(request: web.Request) -> web.Response:
        reader = await request.multipart()
        saved = []
        async for part in reader:
            if not part.filename:
                continue
            name = _SAFE_NAME.sub("_", part.filename.replace("\\", "/").rsplit("/", 1)[-1]).lstrip(".")
            if not name or not media_kind(name):
                raise web.HTTPBadRequest(text=f"Tipo de archivo no permitido: {part.filename}")
            target = MEDIA / name
            size = 0
            too_big = False
            with open(target, "wb") as fh:
                while chunk := await part.read_chunk(1 << 16):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        too_big = True
                        break
                    fh.write(chunk)
            if too_big:
                target.unlink(missing_ok=True)
                raise web.HTTPRequestEntityTooLarge(max_size=MAX_UPLOAD, actual_size=size)
            saved.append(name)
        return web.json_response({"saved": saved})

    @routes.delete("/api/media/{name}")
    async def media_delete(request: web.Request) -> web.Response:
        target = MEDIA / _SAFE_NAME.sub("_", request.match_info["name"])
        if target.is_file():
            target.unlink()
        return web.json_response({"ok": True})

    @routes.get("/api/heartrate/scan")
    async def hr_scan(_request: web.Request) -> web.Response:
        try:
            return web.json_response(await asyncio.wait_for(scan_ble(), timeout=15))
        except Exception as exc:
            return web.json_response({"error": str(exc) or type(exc).__name__}, status=500)

    # ---- catálogo de voces y motor de personajes ---------------------------
    @routes.get("/api/catalog")
    async def catalog(_request: web.Request) -> web.Response:
        data = await asyncio.to_thread(app.downloads.catalog)
        return web.json_response({**data, "app": {"frozen": FROZEN, "data": str(DATA)}})

    @routes.post("/api/catalog/install")
    async def catalog_install(request: web.Request) -> web.Response:
        names = [str(n) for n in (await request.json()).get("names", [])][:400]
        app.downloads.request(names)
        return web.json_response({"ok": True})

    @routes.delete("/api/catalog/{name}")
    async def catalog_delete(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in voces.CATALOG:
            raise web.HTTPNotFound()
        users = voces.used_by(name)
        if users:
            raise web.HTTPConflict(text="La usan como voz base: " + ", ".join(users[:6]) + ("…" if len(users) > 6 else ""))
        app.tts.forget(name)
        voces.remove(name)
        await app.broadcast({"type": "catalog"})
        return web.json_response({"ok": True})

    @routes.post("/api/engine/install")
    async def engine_install(_request: web.Request) -> web.Response:
        if not FROZEN:
            raise web.HTTPBadRequest(text="Desde el código fuente el motor se instala con tools\\instalar_rvc.bat")
        app.downloads.request([ENGINE_JOB])
        return web.json_response({"ok": True})

    @routes.post("/api/quit")
    async def quit_app(_request: web.Request) -> web.Response:
        def leave() -> None:
            raise web.GracefulExit()

        asyncio.get_running_loop().call_later(0.4, leave)
        # Si el cierre ordenado se atasca (audio, atajos o bibliotecas de voz), se termina igual.
        killer = threading.Timer(3.0, os._exit, [0])
        killer.daemon = True
        killer.start()
        return web.json_response({"ok": True})

    @web.middleware
    async def local_only(request: web.Request, handler):
        # Bloquea peticiones lanzadas desde otras webs abiertas en el navegador.
        if request.host.split(":")[0] not in _LOCAL_HOSTS:
            raise web.HTTPForbidden()
        origin = request.headers.get("Origin")
        if origin and origin.split("://")[-1].split(":")[0] not in _LOCAL_HOSTS:
            raise web.HTTPForbidden()
        return await handler(request)

    web_app = web.Application(middlewares=[local_only], client_max_size=MAX_UPLOAD)
    web_app.add_routes(routes)
    web_app.router.add_static("/media/", MEDIA)
    web_app.router.add_static("/static/", WEB / "static")

    async def on_startup(_app: web.Application) -> None:
        await app.start()

    async def on_cleanup(_app: web.Application) -> None:
        await app.stop()

    web_app.on_startup.append(on_startup)
    web_app.on_cleanup.append(on_cleanup)
    return web_app

"""Servidor HTTP/WebSocket local: panel, API y overlays para OBS."""

from __future__ import annotations

import asyncio
import copy
import logging
import re

from aiohttp import web

from .app import App
from .bus import Event
from .config import MEDIA, WEB
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

    @routes.post("/api/tts/test")
    async def tts_test(request: web.Request) -> web.Response:
        body = await request.json()
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

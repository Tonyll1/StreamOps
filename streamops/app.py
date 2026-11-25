"""Núcleo: une bus, reglas, TTS, audio, conectores y el servidor web."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import aiohttp
from aiohttp import web

from .reader import Reader
from .audio import Mixer
from .bus import Event, EventBus
from .config import Config
from .connectors.heartrate import HeartRateConnector
from .connectors.kick import KickConnector
from .connectors.tiktok import TikTokConnector
from .connectors.twitch import TwitchConnector
from .hotkeys import Hotkeys
from .rules import RuleEngine
from .store import Store
from .tts import TTS

logger = logging.getLogger(__name__)


QUIET_USER = "__prueba__"
TEST_LINGER = 25  # segundos que los datos de prueba siguen visibles

class App:
    def __init__(self) -> None:
        self.config = Config()
        self.bus = EventBus()
        self.store = Store()
        self.mixer = Mixer(self.config["audio"].get("device", ""))
        self.tts = TTS(self)
        self.reader = Reader(self)
        self.rules = RuleEngine(self)
        self.hotkeys = Hotkeys()
        self.connectors = {
            "tiktok": TikTokConnector(self),
            "twitch": TwitchConnector(self),
            "kick": KickConnector(self),
            "heartrate": HeartRateConnector(self),
        }
        self.sockets: set[web.WebSocketResponse] = set()
        self.recent: deque[dict] = deque(maxlen=100)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._purge_timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task] = set()
        self._dirty = False
        self.bus.subscribe(self.on_event)

    # ---- ciclo de vida --------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.bus.bind_loop(self.loop)
        self.mixer.start()
        self.bind_hotkeys()
        for name in ("tiktok", "twitch", "kick"):
            if self.config[name].get("autoconnect"):
                self.connectors[name].start()
        if self.config["heartrate"]["source"] != "off":
            self.connectors["heartrate"].start()
        self.spawn(self._state_loop())

    async def stop(self) -> None:
        self.hotkeys.stop()
        for connector in self.connectors.values():
            await connector.stop()
        self.mixer.stop()

    def spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def notify(self, message: dict) -> None:
        """Difunde un mensaje desde cualquier hilo (voz, atajos)."""
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: self.spawn(self.broadcast(message)))

    # ---- atajos ---------------------------------------------------------
    def bind_hotkeys(self) -> None:
        keys = self.config["hotkeys"]

        def threadsafe(fn):
            return lambda: self.loop.call_soon_threadsafe(fn) if self.loop else None

        self.hotkeys.bind(
            {
                keys.get("mute_toggle", ""): threadsafe(self.toggle_mute),
                keys.get("skip_tts", ""): threadsafe(self.tts.skip),
                keys.get("stop_all", ""): threadsafe(self.stop_all),
            }
        )

    def toggle_mute(self, value: bool | None = None) -> bool:
        self.mixer.muted = (not self.mixer.muted) if value is None else bool(value)
        if self.mixer.muted:
            self.tts.clear()
            self.mixer.clear()
        logger.info("[Mute] %s", "SILENCIADO" if self.mixer.muted else "activo")
        self.spawn(self.broadcast({"type": "mute", "muted": self.mixer.muted}))
        return self.mixer.muted

    def stop_all(self) -> None:
        self.tts.clear()
        self.mixer.clear()
        self.spawn(self.broadcast({"type": "stop"}))

    # ---- eventos --------------------------------------------------------
    async def on_event(self, event: Event) -> None:
        self.store.record(event)
        self._dirty = True
        payload = event.to_dict()
        if event.type != "join":
            self.recent.append(payload)
        await self.broadcast({"type": "event", "event": payload})
        if event.user_id.startswith(QUIET_USER):
            # Prueba de overlay: no dispara voz ni reglas, y sus datos se retiran al rato.
            if self._purge_timer:
                self._purge_timer.cancel()
            self._purge_timer = self.loop.call_later(TEST_LINGER, self._purge_tests)
            return
        self.reader.handle(event)
        await self.rules.handle(event)

    def _purge_tests(self) -> None:
        self._purge_timer = None
        if self.store.purge_tests():
            self.recent = type(self.recent)((e for e in self.recent if not str(e.get("user_id", "")).startswith(QUIET_USER)), self.recent.maxlen)
            self._dirty = True

    async def simulate(self, data: dict) -> None:
        event = Event(
            platform=data.get("platform") or "sim",
            type=data.get("type", "chat"),
            user_id=(QUIET_USER + str(data.get("user") or "") if data.get("quiet") else "") or str(data.get("user_id") or data.get("user") or "tester"),
            user=data.get("user") or "Tester",
            text=data.get("text", ""),
            gift=data.get("gift", ""),
            count=int(data.get("count") or 1),
            value=float(data.get("value") or 0),
        )
        await self.bus.publish(event)

    # ---- difusión a panel y overlays -----------------------------------
    def connector_status(self) -> dict:
        return {name: {"status": c.status, "detail": c.detail} for name, c in self.connectors.items()}

    def state(self) -> dict:
        return {
            "type": "state",
            "muted": self.mixer.muted,
            "connectors": self.connector_status(),
            "bpm": self.connectors["heartrate"].bpm,
            "tts_queue": self.tts._queue.qsize(),
            "ts": time.time(),
            **self.store.snapshot(),
        }

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in list(self.sockets):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)

    async def _state_loop(self) -> None:
        """Envía tops y contadores poco después de cada cambio (como máximo 5 veces por segundo)."""
        while True:
            await asyncio.sleep(0.2)
            if self._dirty and self.sockets:
                self._dirty = False
                await self.broadcast(self.state())

    async def post_webhook(self, url: str, payload: dict) -> None:
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    logger.info("[Webhook] %s -> %s", url, resp.status)
        except Exception as exc:
            logger.warning("[Webhook] %s falló: %s", url, exc)

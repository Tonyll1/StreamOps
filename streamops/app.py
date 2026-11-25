"""Núcleo: une bus, reglas, TTS, audio, conectores y el servidor web."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

import aiohttp
from aiohttp import web

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


class App:
    def __init__(self) -> None:
        self.config = Config()
        self.bus = EventBus()
        self.store = Store()
        self.mixer = Mixer(self.config["audio"].get("device", ""))
        self.tts = TTS(self)
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
        if event.type == "chat":
            self._handle_chat_tts(event)
        await self.rules.handle(event)

    def _handle_chat_tts(self, event: Event) -> bool:
        cfg = self.config["tts"]
        text = event.text.strip()
        lowered = text.lower()
        if cfg.get("allow_voice_command") and lowered.startswith("!voz"):
            wanted = self.tts.find_voice(text[4:])
            if wanted:
                cfg["user_voices"][f"{event.platform}:{event.user_id}"] = wanted
                self.config.save()
            return True
        if not cfg["read_chat"] or text.startswith("!") and not cfg["chat_prefix"]:
            return False
        prefix = cfg["chat_prefix"].strip().lower()
        if prefix:
            if not lowered.startswith(prefix):
                return False
            text = text[len(prefix) :].strip()
        if not text:
            return False
        voice = cfg["user_voices"].get(f"{event.platform}:{event.user_id}")
        spoken = f"{event.user} dice: {text}" if cfg["say_username"] else text
        return self.tts.say(spoken, voice=voice)

    async def simulate(self, data: dict) -> None:
        event = Event(
            platform=data.get("platform") or "sim",
            type=data.get("type", "chat"),
            user_id=str(data.get("user_id") or data.get("user") or "tester"),
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
        """Envía los tops como máximo una vez por segundo y solo si cambiaron."""
        while True:
            await asyncio.sleep(1)
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

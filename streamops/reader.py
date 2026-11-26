"""Decide qué eventos se leen en voz alta, con qué texto y con qué voz."""

from __future__ import annotations

import dataclasses
import hashlib
import re
import time
from typing import TYPE_CHECKING

from .bus import Event
from .rules import render

if TYPE_CHECKING:
    from .app import App

_LINK = re.compile(r"(https?://|www\.)\S+|\b\S+\.(com|net|org|gg|tv|io|mx|ly)\b\S*", re.IGNORECASE)
_HAS_WORD = re.compile(r"[^\W_]", re.UNICODE)


class Reader:
    def __init__(self, app: "App") -> None:
        self.app = app
        self._last_text: dict[str, str] = {}
        self._last_time: dict[str, float] = {}
        cfg = app.config["tts"]
        # Ajuste antiguo: "decir el nombre" ahora es la plantilla del chat.
        if cfg.get("say_username") is False:
            cfg["read"]["chat"]["template"] = "{text}"
            cfg["say_username"] = True
            app.config.save()

    # ---- voces ----------------------------------------------------------
    def voice_for(self, event: Event) -> str | None:
        """Voz asignada al usuario: fija, elegida con el comando, o al azar estable."""
        cfg = self.app.config["tts"]
        voices = cfg["user_voices"]
        assigned = voices.get(f"{event.platform}:{event.user_id}") or voices.get("@" + event.user.strip().lower())
        if assigned:
            return assigned
        if cfg.get("random_voices"):
            pool = [v["name"] for v in self.app.tts.voices() if cfg.get("random_pool", "all") in ("all", v.get("kind"))]
            if pool:
                digest = hashlib.sha1(f"{event.platform}:{event.user_id}".encode()).digest()
                return pool[int.from_bytes(digest[:4], "big") % len(pool)]
        return None

    def _voice_command(self, event: Event, text: str) -> bool:
        cfg = self.app.config["tts"]
        command = (cfg.get("voice_command") or "!voz").strip().lower()
        if not cfg.get("allow_voice_command") or not text.lower().startswith(command):
            return False
        wanted = text[len(command):].strip()
        key = f"{event.platform}:{event.user_id}"
        if wanted.lower() in ("reset", "quitar", "normal"):
            cfg["user_voices"].pop(key, None)
        else:
            found = self.app.tts.find_voice(wanted)
            if not found:
                return True
            cfg["user_voices"][key] = found
        self.app.config.save()
        return True

    # ---- filtros --------------------------------------------------------
    def _listed(self, names: list, event: Event) -> bool:
        wanted = {str(n).strip().lstrip("@").lower() for n in names if str(n).strip()}
        return event.user.strip().lower() in wanted or str(event.user_id).lower() in wanted

    def _chat_text(self, event: Event) -> str:
        """Devuelve el texto a leer de un mensaje, o '' si los filtros lo descartan."""
        cfg = self.app.config["tts"]
        text = event.text.strip()
        if self._voice_command(event, text) or not cfg["read_chat"]:
            return ""
        if event.platform != "sim" and not cfg.get("platforms", {}).get(event.platform, True):
            return ""
        if self._listed(cfg.get("ignored_users", []), event):
            return ""
        only = cfg.get("only_users", [])
        if only and not self._listed(only, event):
            return ""
        prefix = cfg["chat_prefix"].strip().lower()
        if prefix:
            if not text.lower().startswith(prefix):
                return ""
            text = text[len(prefix):].strip()
        elif text.startswith("!"):
            return ""
        if cfg.get("skip_links") and _LINK.search(text):
            return ""
        if cfg.get("skip_emoji_only") and not _HAS_WORD.search(text):
            return ""
        if len(text) < int(cfg.get("chat_min_chars") or 1):
            return ""
        key = f"{event.platform}:{event.user_id}"
        now = time.monotonic()
        if cfg.get("skip_repeats") and self._last_text.get(key) == text.lower():
            return ""
        cooldown = float(cfg.get("user_cooldown") or 0)
        if cooldown > 0 and now - self._last_time.get(key, -1e9) < cooldown:
            return ""
        self._last_text[key] = text.lower()
        self._last_time[key] = now
        if len(self._last_text) > 5000:
            self._last_text.clear()
            self._last_time.clear()
        return text

    # ---- entrada --------------------------------------------------------
    def handle(self, event: Event) -> bool:
        cfg = self.app.config["tts"]
        spec = cfg["read"].get(event.type)
        if not spec:
            return False
        if event.type == "chat":
            text = self._chat_text(event)
            if not text:
                return False
            event = dataclasses.replace(event, text=text)
            return self.app.tts.say(render(spec.get("template") or "{text}", event), voice=self.voice_for(event), kind="chat")
        if not spec.get("enabled"):
            return False
        amount = event.value if event.type == "gift" else event.count
        if amount < float(spec.get("min") or 0):
            return False
        gifts = [g.strip().lower() for g in str(spec.get("gifts") or "").split(",") if g.strip()]
        if event.type == "gift" and gifts and not any(g in event.gift.lower() for g in gifts):
            return False
        cooldown = float(spec.get("cooldown") or 0)
        now = time.monotonic()
        if cooldown > 0 and now - self._last_time.get("#" + event.type, -1e9) < cooldown:
            return False
        self._last_time["#" + event.type] = now
        voice = spec.get("voice") or (self.voice_for(event) if spec.get("user_voice") else None)
        return self.app.tts.say(render(spec.get("template") or "{user}", event), voice=voice)

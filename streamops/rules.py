"""Motor de reglas: evento -> acciones (alerta, sonido, TTS, tecla, OBS, webhook)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from . import actions
from .bus import Event
from .config import MEDIA

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac"}


def render(template: str, event: Event) -> str:
    values = {
        "user": event.user,
        "gift": event.gift,
        "count": event.count,
        "value": int(event.value) if float(event.value).is_integer() else event.value,
        "text": event.text,
        "platform": event.platform,
    }
    out = template or ""
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def media_kind(name: str) -> str:
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in VIDEO_EXT:
        return "video"
    if suffix in AUDIO_EXT:
        return "audio"
    return ""


class RuleEngine:
    def __init__(self, app: "App") -> None:
        self.app = app
        self._last_fired: dict[str, float] = {}

    def _matches(self, rule: dict, event: Event) -> bool:
        if not rule.get("enabled", True) or rule.get("event") != event.type:
            return False
        platform = rule.get("platform", "any")
        if platform not in ("any", "", event.platform) and event.platform != "sim":
            return False
        min_value = float(rule.get("min_value") or 0)
        if min_value > 0:
            amount = event.value if event.type == "gift" else event.count
            if amount < min_value:
                return False
        match = (rule.get("match") or "").strip().lower()
        if match:
            if event.type == "chat":
                # Comando: el mensaje debe empezar con el texto indicado.
                if not event.text.strip().lower().startswith(match):
                    return False
            elif match not in event.gift.lower():
                return False
        cooldown = float(rule.get("cooldown") or 0)
        if cooldown > 0:
            now = time.monotonic()
            rule_id = rule.get("id", rule.get("name", ""))
            if now - self._last_fired.get(rule_id, -1e9) < cooldown:
                return False
            self._last_fired[rule_id] = now
        return True

    async def handle(self, event: Event) -> None:
        for rule in self.app.config["rules"]:
            if self._matches(rule, event):
                for action in rule.get("actions", []):
                    try:
                        await self.run_action(action, event)
                    except Exception:
                        logger.exception("[Reglas] Acción %s falló", action.get("type"))

    async def run_action(self, action: dict, event: Event) -> None:
        app = self.app
        kind = action.get("type")
        if kind == "alert":
            # Imagen / video / texto van al overlay; el sonido sale por el mezclador.
            media = action.get("media") or ""
            await app.broadcast(
                {
                    "type": "alert",
                    "text": render(action.get("text", ""), event),
                    "media": f"/media/{media}" if media else "",
                    "media_kind": media_kind(media),
                    "duration": float(action.get("duration") or 5),
                    "avatar": event.avatar,
                    "muted": app.mixer.muted,
                }
            )
            self._play_sound(action.get("sound") or "", action.get("volume"))
        elif kind == "sound":
            self._play_sound(action.get("file") or action.get("sound") or "", action.get("volume"))
        elif kind == "tts":
            text = render(action.get("text", ""), event)
            app.tts.say(text, voice=action.get("voice") or None)
        elif kind == "key":
            actions.run_in_thread(actions.press_keys, action.get("keys", ""), int(action.get("hold_ms") or 100))
        elif kind == "obs_scene":
            actions.run_in_thread(actions.obs_set_scene, app.config["obs"], action.get("scene", ""))
        elif kind == "webhook":
            url = action.get("url", "")
            if url.startswith(("http://", "https://")):
                app.spawn(app.post_webhook(url, event.to_dict()))
        else:
            logger.warning("[Reglas] Tipo de acción desconocido: %s", kind)

    def _play_sound(self, name: str, volume) -> None:
        if not name:
            return
        path = (MEDIA / name).resolve()
        if MEDIA.resolve() not in path.parents or not path.is_file():
            logger.warning("[Reglas] Sonido no encontrado: %s", name)
            return
        vol = float(volume) if volume not in (None, "") else float(self.app.config["audio"]["alert_volume"])
        actions.run_in_thread(self.app.mixer.play_file, path, "alert", vol)

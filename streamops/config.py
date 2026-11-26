"""Configuración persistente en data/config.json."""

from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))  # True dentro de StreamOps.exe
# BUNDLE: archivos de solo lectura que vienen con la app (panel, overlays, afinación).
BUNDLE = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    """Carpeta de datos: junto al programa; si no se puede escribir ahí, en AppData."""
    if not FROZEN:
        return BUNDLE / "data"
    beside = Path(sys.executable).resolve().parent / "StreamOps-datos"
    try:
        beside.mkdir(parents=True, exist_ok=True)
        probe = beside / ".escritura"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return beside
    except OSError:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "StreamOps"


DATA = _data_dir()
MEDIA = DATA / "media"
VOICES = DATA / "voices"
WEB = BUNDLE / "web"
CONFIG_FILE = DATA / "config.json"

DEFAULTS: dict = {
    "server": {"host": "127.0.0.1", "port": 8765},
    "tiktok": {"username": "", "autoconnect": False},
    "twitch": {"channel": "", "autoconnect": False},
    "kick": {
        "channel": "",
        "chatroom_id": "",
        "channel_id": "",
        "autoconnect": False,
        # Clave pública del chat de Kick; reportada por la comunidad tras la rotación de oct-2026.
        "pusher_key": "34bf7a0ff419a2a775b9",
        "pusher_cluster": "us2",
    },
    "heartrate": {
        # source: off | pulsoid | ble | sim
        "source": "off",
        "pulsoid_token": "",
        "ble_address": "",
    },
    "tts": {
        "enabled": True,
        "voice": "",
        "volume": 1.0,
        "read_chat": True,
        # Si no está vacío, solo se leen mensajes que empiecen con este prefijo.
        "chat_prefix": "",
        "say_username": True,
        "max_chars": 200,
        "max_queue": 20,
        # Los espectadores eligen voz con "!voz nombre".
        "allow_voice_command": True,
        "user_voices": {},
        "blocked_words": [],
        "voice_command": "!voz",
        # Filtros del chat.
        "chat_min_chars": 1,
        "skip_links": True,
        "skip_emoji_only": True,
        "skip_repeats": True,
        "user_cooldown": 0,
        "ignored_users": [],
        "only_users": [],
        "platforms": {"tiktok": True, "twitch": True, "kick": True},
        # Dónde se usan las voces de personaje (RVC, pesadas sin GPU):
        #   auto = en todo con tarjeta NVIDIA, solo en alertas sin ella
        #   all = en todo · alerts = solo alertas (el chat usa la voz base) · off = nunca
        "character_mode": "auto",
        # Si las voces de personaje van lentas, el chat cambia solo a la voz base.
        "fast_fallback": True,
        "fallback_queue": 3,      # frases esperando a partir de las cuales el chat usa la voz base
        "fallback_seconds": 6,    # una conversión más lenta que esto activa el modo rápido 2 min
        # Voz al azar (siempre la misma) para quien no tenga una asignada.
        "random_voices": False,
        "random_pool": "all",
        # Qué eventos se leen, con qué frase, mínimo y voz.
        "read": {
            "chat": {"template": "{user} dice: {text}"},
            "gift": {"enabled": False, "template": "{user} envió {count} {gift}", "min": 0, "gifts": "", "voice": "", "cooldown": 0},
            "follow": {"enabled": False, "template": "{user} te siguió", "voice": "", "cooldown": 0},
            "share": {"enabled": False, "template": "{user} compartió el directo", "voice": "", "cooldown": 0},
            "like": {"enabled": False, "template": "{user} dio {count} likes", "min": 15, "voice": "", "cooldown": 10},
            "sub": {"enabled": False, "template": "{user} se suscribió", "voice": "", "cooldown": 0},
            "raid": {"enabled": False, "template": "{user} llegó con {count} personas", "voice": "", "cooldown": 0},
            "join": {"enabled": False, "template": "Bienvenido {user}", "voice": "", "cooldown": 5},
        },
    },
    "audio": {"alert_volume": 0.8, "device": ""},
    "hotkeys": {
        "mute_toggle": "<ctrl>+<alt>+m",
        "skip_tts": "<ctrl>+<alt>+s",
        "stop_all": "<ctrl>+<alt>+x",
    },
    "obs": {"host": "127.0.0.1", "port": 4455, "password": ""},
    "rules": [
        {
            "id": "ejemplo-regalo",
            "name": "Regalo: voz de agradecimiento",
            "enabled": True,
            "platform": "any",
            "event": "gift",
            "min_value": 1,
            "match": "",
            "cooldown": 0,
            "actions": [
                {"type": "alert", "text": "{user} envió {count}x {gift}", "media": "", "sound": "", "duration": 6},
                {"type": "tts", "text": "Gracias {user} por {count} {gift}", "voice": ""},
            ],
        },
        {
            "id": "ejemplo-follow",
            "name": "Nuevo seguidor",
            "enabled": True,
            "platform": "any",
            "event": "follow",
            "min_value": 0,
            "match": "",
            "cooldown": 0,
            "actions": [
                {"type": "alert", "text": "{user} ahora te sigue", "media": "", "sound": "", "duration": 5},
            ],
        },
    ],
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        for folder in (DATA, MEDIA, VOICES):
            folder.mkdir(parents=True, exist_ok=True)
        self.data = copy.deepcopy(DEFAULTS)
        if CONFIG_FILE.is_file():
            try:
                self.data = _merge(DEFAULTS, json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        else:
            self.save()

    def __getitem__(self, key: str):
        return self.data[key]

    def update(self, patch: dict) -> None:
        with self._lock:
            # Las reglas y user_voices se reemplazan completas, no se mezclan.
            rules = patch.pop("rules", None) if isinstance(patch, dict) else None
            tts = patch.get("tts") if isinstance(patch, dict) else None
            user_voices = tts.pop("user_voices", None) if isinstance(tts, dict) else None
            self.data = _merge(self.data, patch)
            if rules is not None:
                self.data["rules"] = rules
            if isinstance(user_voices, dict):
                self.data["tts"]["user_voices"] = user_voices
        self.save()

    def save(self) -> None:
        with self._lock:
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CONFIG_FILE)

"""Configuración persistente en data/config.json."""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MEDIA = DATA / "media"
VOICES = DATA / "voices"
WEB = ROOT / "web"
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
            self.data = _merge(self.data, patch)
            if rules is not None:
                self.data["rules"] = rules
        self.save()

    def save(self) -> None:
        with self._lock:
            tmp = CONFIG_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CONFIG_FILE)

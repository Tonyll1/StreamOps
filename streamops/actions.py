"""Acciones de escritorio: teclas, escena de OBS y webhooks."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_key_lock = threading.Lock()


def _parse_key(name: str):
    from pynput.keyboard import Key

    name = name.strip().lower()
    aliases = {"control": "ctrl", "win": "cmd", "return": "enter", "escape": "esc", "espacio": "space"}
    name = aliases.get(name, name)
    if len(name) == 1:
        return name
    return getattr(Key, name)  # AttributeError si no existe


def press_keys(combo: str, hold_ms: int = 100) -> None:
    """Pulsa una combinación tipo 'ctrl+shift+f1' o una tecla 'space'."""
    from pynput.keyboard import Controller

    keys = [_parse_key(part) for part in combo.split("+") if part.strip()]
    if not keys:
        return
    controller = Controller()
    with _key_lock:
        for key in keys:
            controller.press(key)
        time.sleep(max(hold_ms, 10) / 1000)
        for key in reversed(keys):
            controller.release(key)


def obs_set_scene(obs_cfg: dict, scene: str) -> None:
    import obsws_python as obs

    client = obs.ReqClient(
        host=obs_cfg.get("host", "127.0.0.1"),
        port=int(obs_cfg.get("port", 4455)),
        password=obs_cfg.get("password", ""),
        timeout=3,
    )
    try:
        client.set_current_program_scene(scene)
    finally:
        client.disconnect()


def run_in_thread(fn, *args) -> None:
    def runner() -> None:
        try:
            fn(*args)
        except Exception as exc:
            logger.warning("[Acción] %s falló: %s", getattr(fn, "__name__", fn), exc)

    threading.Thread(target=runner, daemon=True).start()

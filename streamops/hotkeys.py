"""Atajos de teclado globales (funcionan aunque la app no tenga el foco)."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class Hotkeys:
    def __init__(self) -> None:
        self._listener = None

    def bind(self, mapping: dict[str, Callable[[], None]]) -> None:
        """mapping: combinación estilo pynput ('<ctrl>+<alt>+m') -> función."""
        self.stop()
        valid = {combo: fn for combo, fn in mapping.items() if combo}
        if not valid:
            return
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys(valid)
            self._listener.daemon = True
            self._listener.start()
            logger.info("[Hotkeys] Activos: %s", ", ".join(valid))
        except Exception:
            logger.exception("[Hotkeys] Combinación inválida o teclado no disponible")
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

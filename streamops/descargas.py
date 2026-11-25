"""Cola de descargas del panel: voces del catálogo y motor de personajes, una a la vez."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

from . import engine, voces

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

ENGINE_JOB = "__motor__"
DEFAULT_VOICE = "es_MX-laura-high"


class Downloads:
    def __init__(self, app: "App") -> None:
        self.app = app
        self.jobs: dict[str, dict] = {}  # nombre -> {"status": cola|descargando|error, "text": …}
        self._queue: queue.Queue[str] = queue.Queue()
        self._last = 0.0
        threading.Thread(target=self._worker, name="descargas", daemon=True).start()

    def request(self, names: list[str]) -> None:
        for name in names:
            if name != ENGINE_JOB and name not in voces.CATALOG:
                continue
            if self.jobs.get(name, {}).get("status") in ("cola", "descargando"):
                continue
            self.jobs[name] = {"status": "cola", "text": "En cola"}
            self._queue.put(name)
        self.app.notify({"type": "catalog"})

    def first_run(self) -> None:
        """Sin ninguna voz instalada la app no puede hablar: baja la voz por defecto."""
        if not any(voces.VOICES.glob("*.onnx")):
            self.request([DEFAULT_VOICE])

    def catalog(self) -> dict:
        items = []
        for name, entry in voces.CATALOG.items():
            items.append({"name": name, "kind": entry[0], "installed": voces.installed(name), "job": self.jobs.get(name)})
        return {"voices": items, "engine": {**engine.info(), "job": self.jobs.get(ENGINE_JOB)}}

    def _progress(self, name: str, done: int, total: int, label: str = "Descargando") -> None:
        now = time.monotonic()
        if now - self._last < 0.4:
            return
        self._last = now
        if label.startswith("Instalando"):
            text = f"{label} {done * 100 // max(1, total)}%"
        elif total:
            text = f"{label} {done / 1048576:.0f} de {total / 1048576:.0f} MB"
        else:
            text = f"{label} {done / 1048576:.0f} MB"
        self.jobs[name] = {"status": "descargando", "text": text}
        self.app.notify({"type": "download", "name": name, "text": text})

    def _worker(self) -> None:
        while True:
            name = self._queue.get()
            self.jobs[name] = {"status": "descargando", "text": "Empezando…"}
            self.app.notify({"type": "download", "name": name, "text": "Empezando…"})
            try:
                if name == ENGINE_JOB:
                    engine.install(lambda done, total, label: self._progress(name, done, total, label))
                else:
                    voces.on_progress = lambda done, total: self._progress(name, done, total)
                    voces.install(name)
                self.jobs.pop(name, None)
                logger.info("[Descargas] %s lista", name)
            except Exception as exc:
                logger.exception("[Descargas] Falló %s", name)
                self.jobs[name] = {"status": "error", "text": str(exc)[:160] or type(exc).__name__}
            finally:
                voces.on_progress = None
            self.app.notify({"type": "catalog"})

"""Conectores de plataforma. Cada uno publica eventos normalizados en el bus."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import App

logger = logging.getLogger(__name__)


class Connector:
    """Base: ciclo de reconexión y estado visible en el panel."""

    name = "base"

    def __init__(self, app: "App") -> None:
        self.app = app
        self.status = "desconectado"
        self.detail = ""
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def set_status(self, status: str, detail: str = "") -> None:
        self.status, self.detail = status, detail
        logger.info("[%s] %s %s", self.name, status, detail)
        await self.app.broadcast({"type": "status", "connectors": self.app.connector_status()})

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        await self.set_status("desconectado")

    async def _supervise(self) -> None:
        delay = 5
        while True:
            try:
                await self.set_status("conectando")
                await self.run()
                delay = 5
                await self.set_status("reconectando", "conexión cerrada")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[%s] error: %s", self.name, exc)
                await self.set_status("error", str(exc)[:200])
                delay = min(delay * 2, 60)
            await asyncio.sleep(delay)

    async def run(self) -> None:
        raise NotImplementedError

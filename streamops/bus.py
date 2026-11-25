"""Evento normalizado y bus de eventos compartido por todos los conectores."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

# Tipos de evento: chat, gift, like, follow, share, sub, join, raid
EVENT_TYPES = ("chat", "gift", "like", "follow", "share", "sub", "join", "raid")


@dataclass
class Event:
    platform: str  # tiktok | twitch | kick | sim
    type: str
    user_id: str = ""
    user: str = ""  # nombre visible
    avatar: str = ""
    text: str = ""  # mensaje de chat
    gift: str = ""  # nombre del regalo / "bits" / "sub"
    count: int = 1  # cantidad (regalos, likes, meses)
    value: float = 0.0  # valor total en monedas (diamantes, bits, kicks)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: Event) -> None:
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Fallo en handler de evento %s", event.type)

    def publish_threadsafe(self, event: Event) -> None:
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self.publish(event), self._loop)

"""Twitch por IRC anónimo (sin credenciales): chat, bits, subs y raids.

Los follows no viajan por IRC; requieren EventSub con una app registrada.
"""

from __future__ import annotations

import random

import aiohttp

from ..bus import Event
from . import Connector

IRC_URL = "wss://irc-ws.chat.twitch.tv:443"


def parse_irc(line: str) -> tuple[dict, str, str, list[str]]:
    """Devuelve (tags, prefijo, comando, parámetros) de una línea IRCv3."""
    tags: dict[str, str] = {}
    prefix = ""
    if line.startswith("@"):
        raw, line = line[1:].split(" ", 1)
        for pair in raw.split(";"):
            key, _, value = pair.partition("=")
            tags[key] = value.replace("\\s", " ").replace("\\:", ";")
    if line.startswith(":"):
        prefix, line = line[1:].split(" ", 1)
    trailing = None
    if " :" in line:
        line, trailing = line.split(" :", 1)
    parts = line.split()
    if trailing is not None:
        parts.append(trailing)
    return tags, prefix, (parts[0] if parts else ""), parts[1:]


class TwitchConnector(Connector):
    name = "twitch"

    async def run(self) -> None:
        channel = self.app.config["twitch"]["channel"].strip().lstrip("#@").lower()
        if not channel:
            raise RuntimeError("Falta el canal de Twitch")
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(IRC_URL, heartbeat=None) as ws:
                await ws.send_str("CAP REQ :twitch.tv/tags twitch.tv/commands")
                await ws.send_str(f"NICK justinfan{random.randint(10000, 99999)}")
                await ws.send_str(f"JOIN #{channel}")
                await self.set_status("conectado", f"#{channel}")
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    for line in msg.data.split("\r\n"):
                        if not line:
                            continue
                        if line.startswith("PING"):
                            await ws.send_str("PONG :tmi.twitch.tv")
                            continue
                        await self._handle(line)

    async def _handle(self, line: str) -> None:
        tags, prefix, command, params = parse_irc(line)
        user_id = tags.get("user-id") or prefix.split("!")[0]
        name = tags.get("display-name") or tags.get("login") or prefix.split("!")[0]
        base = {"platform": "twitch", "user_id": user_id, "user": name}
        bus = self.app.bus
        if command == "PRIVMSG" and len(params) >= 2:
            text = params[1]
            bits = int(tags.get("bits") or 0)
            if bits > 0:
                await bus.publish(Event(type="gift", gift="bits", count=bits, value=bits, text=text, **base))
            await bus.publish(Event(type="chat", text=text, **base))
        elif command == "USERNOTICE":
            kind = tags.get("msg-id", "")
            text = params[1] if len(params) >= 2 else ""
            if kind in ("sub", "resub"):
                months = int(tags.get("msg-param-cumulative-months") or 1)
                await bus.publish(Event(type="sub", gift="sub", count=months, text=text, **base))
            elif kind in ("subgift", "submysterygift"):
                count = int(tags.get("msg-param-mass-gift-count") or 1)
                await bus.publish(Event(type="sub", gift="sub regalada", count=count, text=text, **base))
            elif kind == "raid":
                viewers = int(tags.get("msg-param-viewerCount") or 0)
                await bus.publish(Event(type="raid", count=viewers, **base))

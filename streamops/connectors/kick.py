"""Kick por su WebSocket público (Pusher): chat, follows, subs y regalos.

Kick rota la clave pública de Pusher de vez en cuando; se configura en
kick.pusher_key / kick.pusher_cluster. El id de la sala se obtiene de kick.com/api/v2/channels/<canal>. Cloudflare a
veces bloquea esa consulta; en ese caso se puede escribir chatroom_id a mano en
la configuración.
"""

from __future__ import annotations

import json
import logging

import aiohttp

from ..bus import Event
from . import Connector

logger = logging.getLogger(__name__)

PUSHER_URL = "wss://ws-{cluster}.pusher.com/app/{key}?protocol=7&client=js&version=8.4.0&flash=false"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class KickConnector(Connector):
    name = "kick"

    async def _resolve_ids(self, session: aiohttp.ClientSession) -> tuple[str, str]:
        cfg = self.app.config["kick"]
        chatroom, channel_id = str(cfg.get("chatroom_id") or ""), str(cfg.get("channel_id") or "")
        if chatroom:
            return chatroom, channel_id
        slug = cfg["channel"].strip().lstrip("@").lower()
        if not slug:
            raise RuntimeError("Falta el canal de Kick")
        async with session.get(f"https://kick.com/api/v2/channels/{slug}", headers=BROWSER_HEADERS) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Kick respondió {resp.status} al buscar el canal; escribe chatroom_id manualmente"
                )
            data = await resp.json(content_type=None)
        return str(data["chatroom"]["id"]), str(data.get("id") or "")

    async def run(self) -> None:
        async with aiohttp.ClientSession() as session:
            chatroom, channel_id = await self._resolve_ids(session)
            cfg = self.app.config["kick"]
            url = PUSHER_URL.format(cluster=cfg.get("pusher_cluster") or "us2", key=cfg.get("pusher_key") or "")
            async with session.ws_connect(url, heartbeat=None) as ws:
                channels = [f"chatrooms.{chatroom}.v2", f"chatrooms.{chatroom}", f"chatroom_{chatroom}"]
                if channel_id:
                    channels += [f"channel.{channel_id}", f"channel_{channel_id}"]
                for channel in channels:
                    await ws.send_json({"event": "pusher:subscribe", "data": {"auth": "", "channel": channel}})
                await self.set_status("conectado", f"sala {chatroom}")
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    frame = json.loads(msg.data)
                    name = frame.get("event", "")
                    if name == "pusher:error":
                        # Kick rota esta clave cada cierto tiempo (la última vez en octubre de 2026).
                        raise RuntimeError(
                            "Kick rechazó la clave de chat (pusher_key en data/config.json está desactualizada)"
                        )
                    if name == "pusher:ping":
                        await ws.send_json({"event": "pusher:pong", "data": {}})
                        continue
                    raw = frame.get("data")
                    try:
                        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    except ValueError:
                        continue
                    await self._handle(name.rsplit("\\", 1)[-1], data)

    async def _handle(self, name: str, data: dict) -> None:
        bus = self.app.bus

        def who(obj: dict | None, fallback: str = "") -> dict:
            obj = obj or {}
            username = obj.get("username") or obj.get("slug") or fallback
            return {"platform": "kick", "user_id": str(obj.get("id") or username), "user": username}

        if name == "ChatMessageEvent":
            await bus.publish(Event(type="chat", text=data.get("content", ""), **who(data.get("sender"))))
        elif name in ("FollowersUpdated", "FollowersUpdatedForChannelOwner"):
            # Kick solo envía el contador, no quién siguió.
            if data.get("followed", True):
                await bus.publish(Event(type="follow", platform="kick", user="Alguien"))
        elif name in ("SubscriptionEvent", "ChannelSubscriptionEvent"):
            username = data.get("username") or (data.get("user") or {}).get("username", "")
            await bus.publish(
                Event(type="sub", gift="sub", count=int(data.get("months") or 1), **who({"username": username}))
            )
        elif name == "GiftedSubscriptionsEvent":
            count = len(data.get("gifted_usernames") or []) or 1
            await bus.publish(
                Event(type="sub", gift="sub regalada", count=count, **who({"username": data.get("gifter_username", "")}))
            )
        elif name in ("KicksGifted", "KicksGiftedEvent"):
            gift = data.get("gift") or {}
            amount = float(gift.get("amount") or data.get("amount") or 0)
            await bus.publish(
                Event(
                    type="gift",
                    gift=gift.get("name") or "kicks",
                    count=1,
                    value=amount,
                    text=data.get("message") or "",
                    **who(data.get("sender")),
                )
            )
        elif name == "StreamHostEvent":
            await bus.publish(
                Event(type="raid", count=int(data.get("number_viewers") or 0), **who({"username": data.get("host_username", "")}))
            )

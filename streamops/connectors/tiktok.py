"""TikTok LIVE mediante la librería no oficial TikTokLive."""

from __future__ import annotations

import asyncio
import logging

from ..bus import Event
from . import Connector

logger = logging.getLogger(__name__)


def _avatar(user) -> str:
    thumb = getattr(user, "avatar_thumb", None)
    for attr in ("m_urls", "url_list", "urls"):
        urls = getattr(thumb, attr, None)
        if urls:
            return str(urls[0])
    return ""


def _who(user) -> dict:
    if user is None:
        return {"platform": "tiktok", "user_id": "", "user": "Alguien", "avatar": ""}
    unique_id = getattr(user, "unique_id", "") or getattr(user, "display_id", "") or ""
    nickname = getattr(user, "nickname", "") or getattr(user, "nick_name", "") or unique_id
    return {
        "platform": "tiktok",
        "user_id": str(unique_id or getattr(user, "id", "")),
        "user": nickname,
        "avatar": _avatar(user),
    }


class TikTokConnector(Connector):
    name = "tiktok"

    async def run(self) -> None:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import (
            CommentEvent,
            ConnectEvent,
            FollowEvent,
            GiftEvent,
            JoinEvent,
            LikeEvent,
            ShareEvent,
            SubNotifyEvent,
        )

        username = self.app.config["tiktok"]["username"].strip().lstrip("@")
        if not username:
            raise RuntimeError("Falta el usuario de TikTok")
        client = TikTokLiveClient(unique_id=f"@{username}")
        bus = self.app.bus

        @client.on(ConnectEvent)
        async def on_connect(_event) -> None:
            await self.set_status("conectado", f"@{username}")

        @client.on(CommentEvent)
        async def on_comment(event) -> None:
            await bus.publish(Event(type="chat", text=event.comment or "", **_who(event.user)))

        @client.on(GiftEvent)
        async def on_gift(event) -> None:
            gift = event.gift
            # Los regalos en racha llegan repetidos; solo cuenta el último de la racha.
            if gift is None or event.streaking:
                return
            count = int(getattr(event, "repeat_count", 1) or 1)
            diamonds = int(getattr(gift, "diamond_count", 0) or 0)
            await bus.publish(
                Event(
                    type="gift",
                    gift=getattr(gift, "name", "") or "regalo",
                    count=count,
                    value=diamonds * count,
                    **_who(event.user),
                )
            )

        @client.on(LikeEvent)
        async def on_like(event) -> None:
            await bus.publish(Event(type="like", count=int(getattr(event, "count", 1) or 1), **_who(event.user)))

        @client.on(FollowEvent)
        async def on_follow(event) -> None:
            await bus.publish(Event(type="follow", **_who(event.user)))

        @client.on(ShareEvent)
        async def on_share(event) -> None:
            await bus.publish(Event(type="share", **_who(event.user)))

        @client.on(SubNotifyEvent)
        async def on_sub(event) -> None:
            await bus.publish(Event(type="sub", gift="sub", **_who(event.user)))

        @client.on(JoinEvent)
        async def on_join(event) -> None:
            await bus.publish(Event(type="join", **_who(event.user)))

        try:
            # Espera a que empiece el directo sin tratarlo como error.
            while not await client.is_live():
                if self.status != "esperando":
                    await self.set_status("esperando", f"@{username} no está en vivo; se conectará al empezar")
                await asyncio.sleep(15)
            await self.set_status("conectando", f"@{username}")
            await client.connect()
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

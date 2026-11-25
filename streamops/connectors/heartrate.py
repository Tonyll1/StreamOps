"""Pulsómetro: Pulsoid (token), banda Bluetooth LE directa, o simulado."""

from __future__ import annotations

import asyncio
import json
import math
import random
import time

import aiohttp

from . import Connector

HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"


def parse_hr_measurement(data: bytes) -> int:
    """Característica BLE 0x2A37: el bit 0 indica si el valor es de 16 bits."""
    if len(data) < 2:
        return 0
    if data[0] & 0x01:
        return int.from_bytes(data[1:3], "little")
    return data[1]


class HeartRateConnector(Connector):
    name = "heartrate"

    def __init__(self, app) -> None:
        super().__init__(app)
        self.bpm = 0

    async def _emit(self, bpm: int) -> None:
        if bpm <= 0:
            return
        self.bpm = bpm
        await self.app.broadcast({"type": "hr", "bpm": bpm, "ts": time.time()})

    async def run(self) -> None:
        cfg = self.app.config["heartrate"]
        source = cfg.get("source", "off")
        if source == "pulsoid":
            await self._run_pulsoid(cfg.get("pulsoid_token", "").strip())
        elif source == "ble":
            await self._run_ble(cfg.get("ble_address", "").strip())
        elif source == "sim":
            await self._run_sim()
        else:
            raise RuntimeError("Fuente de pulso apagada")

    async def _run_pulsoid(self, token: str) -> None:
        if not token:
            raise RuntimeError("Falta el token de Pulsoid")
        url = f"wss://dev.pulsoid.net/api/v1/data/real_time?access_token={token}"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=30) as ws:
                await self.set_status("conectado", "Pulsoid")
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    data = json.loads(msg.data).get("data") or {}
                    await self._emit(int(data.get("heart_rate") or 0))

    async def _run_ble(self, address: str) -> None:
        from bleak import BleakClient, BleakScanner

        if not address:
            await self.set_status("conectando", "buscando banda Bluetooth")
            devices = await BleakScanner.discover(timeout=8.0, service_uuids=[HR_SERVICE])
            if not devices:
                raise RuntimeError("No se encontró ninguna banda de pulso Bluetooth")
            address = devices[0].address
        loop = asyncio.get_running_loop()
        disconnected = asyncio.Event()

        def on_data(_char, data: bytearray) -> None:
            loop.create_task(self._emit(parse_hr_measurement(bytes(data))))

        async with BleakClient(address, disconnected_callback=lambda _c: disconnected.set()) as client:
            await client.start_notify(HR_MEASUREMENT, on_data)
            await self.set_status("conectado", f"BLE {address}")
            await disconnected.wait()

    async def _run_sim(self) -> None:
        await self.set_status("conectado", "simulado")
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            await self._emit(int(95 + 25 * math.sin(t / 20) + random.randint(-3, 3)))
            await asyncio.sleep(1)


async def scan_ble() -> list[dict]:
    from bleak import BleakScanner

    devices = await BleakScanner.discover(timeout=6.0, service_uuids=[HR_SERVICE])
    return [{"address": d.address, "name": d.name or "(sin nombre)"} for d in devices]

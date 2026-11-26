"""Pulsómetro: Pulsoid (token), banda Bluetooth LE directa, o simulado."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import math
import random
import threading
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


async def in_ble_thread(make_coro):
    """Ejecuta una corrutina de Bluetooth en un hilo propio con su propio bucle asyncio.

    En Windows, bleak exige que el hilo use COM en modo MTA. El hilo principal de la
    app ya queda en modo STA (lo inicializan el audio o los atajos de teclado), y ahí
    bleak falla con «Thread is configured for Windows GUI but callbacks are not
    working». Un hilo nuevo no tiene COM inicializado y WinRT lo pone en MTA.
    Si la tarea de fuera se cancela, también se cancela la de Bluetooth.
    """
    done: concurrent.futures.Future = concurrent.futures.Future()
    holder: dict = {}

    async def main():
        holder["loop"] = asyncio.get_running_loop()
        holder["task"] = asyncio.current_task()
        return await make_coro()

    def runner() -> None:
        try:
            from bleak.backends.winrt.util import uninitialize_sta

            uninitialize_sta()  # por si alguna biblioteca ya puso este hilo en STA
        except Exception:
            pass
        try:
            result = asyncio.run(main())
        except BaseException as exc:  # noqa: BLE001 - se reenvía tal cual al hilo principal
            if not done.done():
                done.set_exception(exc)
        else:
            if not done.done():
                done.set_result(result)

    threading.Thread(target=runner, name="bluetooth", daemon=True).start()
    try:
        return await asyncio.wrap_future(done)
    except asyncio.CancelledError:
        loop, task = holder.get("loop"), holder.get("task")
        if loop is not None and task is not None and not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)
        raise


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
        if not address:
            await self.set_status("conectando", "buscando banda Bluetooth")
        main_loop = asyncio.get_running_loop()

        def on_main(coro) -> None:
            asyncio.run_coroutine_threadsafe(coro, main_loop)

        async def session(address: str) -> None:  # corre en el hilo de Bluetooth
            from bleak import BleakClient, BleakScanner

            if not address:
                devices = await BleakScanner.discover(timeout=8.0, service_uuids=[HR_SERVICE])
                if not devices:
                    raise RuntimeError("No se encontró ninguna banda de pulso Bluetooth")
                address = devices[0].address
            disconnected = asyncio.Event()

            def on_data(_char, data: bytearray) -> None:
                on_main(self._emit(parse_hr_measurement(bytes(data))))

            async with BleakClient(address, disconnected_callback=lambda _c: disconnected.set()) as client:
                await client.start_notify(HR_MEASUREMENT, on_data)
                on_main(self.set_status("conectado", f"BLE {address}"))
                await disconnected.wait()

        await in_ble_thread(lambda: session(address))

    async def _run_sim(self) -> None:
        await self.set_status("conectado", "simulado")
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            await self._emit(int(95 + 25 * math.sin(t / 20) + random.randint(-3, 3)))
            await asyncio.sleep(1)


async def scan_ble() -> list[dict]:
    async def scan() -> list[dict]:
        from bleak import BleakScanner

        devices = await BleakScanner.discover(timeout=6.0, service_uuids=[HR_SERVICE])
        return [{"address": d.address, "name": d.name or "(sin nombre)"} for d in devices]

    return await in_ble_thread(scan)

"""Punto de entrada: python -m streamops (o StreamOps.exe)"""

from __future__ import annotations

import logging
import os
import socket
import sys
import webbrowser

from aiohttp import web

from .config import DATA, FROZEN, Config


def _running(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def main() -> None:
    probe = Config()
    host, port = probe["server"]["host"], int(probe["server"]["port"])
    url = f"http://{host}:{port}/"
    browser = "--no-browser" not in sys.argv
    if FROZEN and _running(host, port):
        # Ya hay un StreamOps abierto: basta con mostrar su panel.
        if browser:
            webbrowser.open(url)
        return
    if FROZEN:
        # El .exe no tiene consola: todo lo que se imprima va al registro.
        log = open(DATA / "streamops.log", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = sys.stderr = log
        os.chdir(DATA)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from .app import App
    from .server import build_web_app

    app = App()
    print(f"\n  StreamOps listo en {url}\n")
    if browser:
        webbrowser.open(url)
    web.run_app(build_web_app(app), host=host, port=port, print=None)


if __name__ == "__main__":
    main()

"""Punto de entrada: python -m streamops"""

from __future__ import annotations

import logging
import sys
import webbrowser

from aiohttp import web

from .app import App
from .server import build_web_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = App()
    host, port = app.config["server"]["host"], int(app.config["server"]["port"])
    url = f"http://{host}:{port}/"
    print(f"\n  StreamOps listo en {url}\n")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    web.run_app(build_web_app(app), host=host, port=port, print=None)


if __name__ == "__main__":
    main()

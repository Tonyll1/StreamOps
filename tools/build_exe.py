"""Genera dist/StreamOps.exe.

    .venv\\Scripts\\python.exe tools\\build_exe.py            compila el programa
    .venv\\Scripts\\python.exe tools\\build_exe.py --motor    antes actualiza la lista de bibliotecas del motor

StreamOps.exe lleva la app completa (panel, overlays, conexiones, voces Piper).
El motor de voces de personaje no va dentro: el programa lo descarga cuando se le pide,
las bibliotecas desde PyPI (lista fijada en tools/motor.json) y PyTorch desde su web.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(TOOLS))


def build_exe() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.10"])
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", str(TOOLS / "StreamOps.spec"), "--noconfirm",
        "--distpath", str(DIST), "--workpath", str(ROOT / "build"),
    ])
    print(f"StreamOps.exe: {(DIST / 'StreamOps.exe').stat().st_size / 1048576:.0f} MB")


def build_lock() -> None:
    """Escribe tools/motor.json: el paquete exacto de PyPI para cada biblioteca del motor."""
    import concurrent.futures
    import json
    import urllib.request

    from packaging.tags import sys_tags
    from packaging.utils import parse_wheel_filename
    from particion import partition

    tags = set(sys_tags())
    _core, pack = partition()

    def find(item):
        name, dist = item
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{dist.version}/json", timeout=60) as resp:
            files = json.load(resp)["urls"]
        for file in files:
            if file["filename"].endswith(".whl") and parse_wheel_filename(file["filename"])[3] & tags:
                return {"name": name, "version": dist.version, "url": file["url"], "sha256": file["digests"]["sha256"], "size": file["size"]}
        raise SystemExit(f"{name} {dist.version} no tiene paquete compatible en PyPI")

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        wheels = list(pool.map(find, sorted(pack.items())))
    (TOOLS / "motor.json").write_text(json.dumps(wheels, indent=1), encoding="utf-8")
    print(f"motor.json: {len(wheels)} bibliotecas, {sum(w['size'] for w in wheels) / 1048576:.0f} MB")


if __name__ == "__main__":
    if "--motor" in sys.argv or not (TOOLS / "motor.json").is_file():
        build_lock()
    build_exe()

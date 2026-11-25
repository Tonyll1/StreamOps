"""Reparte los paquetes instalados entre StreamOps.exe y el motor de personajes.

- núcleo: lo que pide requirements.txt y sus dependencias -> va completo dentro del .exe
- motor:  todo lo demás (bibliotecas de RVC) -> tools/motor.json, el programa las baja de PyPI
- PyTorch no va en ninguno: el programa lo baja de la web oficial de PyTorch.
"""

from __future__ import annotations

import re
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_ONLY = {"pip", "wheel", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes"}
TORCH = {"torch", "torchaudio"}
STDLIB_SKIP = {"test", "tkinter", "idlelib", "lib2to3", "turtledemo", "ensurepip", "venv", "site-packages", "__pycache__", "turtle.py", "antigravity.py", "this.py"}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requires(dist: metadata.Distribution) -> list[str]:
    from packaging.requirements import Requirement

    names = []
    for line in dist.requires or []:
        req = Requirement(line)
        if req.marker is None or req.marker.evaluate({"extra": ""}):
            names.append(norm(req.name))
    return names


def partition() -> tuple[dict[str, metadata.Distribution], dict[str, metadata.Distribution]]:
    dists = {norm(d.metadata["Name"]): d for d in metadata.distributions() if d.metadata["Name"]}
    pending = [norm(re.split(r"[<>=!~ ]", line.strip())[0]) for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip()]
    core: dict[str, metadata.Distribution] = {}
    while pending:
        name = pending.pop()
        if name in core or name not in dists:
            continue
        core[name] = dists[name]
        pending.extend(_requires(dists[name]))
    pack = {n: d for n, d in dists.items() if n not in core and n not in BUILD_ONLY and n not in TORCH}
    return core, pack


def top_levels(dist: metadata.Distribution) -> set[str]:
    """Nombres importables que instala una distribución."""
    names = set()
    for file in dist.files or []:
        first = file.parts[0]
        if first.startswith("..") or first.endswith((".dist-info", ".data", ".libs")) or first == "__pycache__":
            continue
        if len(file.parts) == 1:
            if not first.endswith((".py", ".pyd")):
                continue
            first = first.split(".")[0]
        if first.isidentifier():
            names.add(first)
    return names


def stdlib_modules() -> list[str]:
    """Toda la biblioteca estándar: el motor descargado la necesita aunque la app no la use."""
    lib = Path(sysconfig.get_path("stdlib"))
    found = set(sys.stdlib_module_names) - {"tkinter", "_tkinter", "turtle", "turtledemo", "idlelib", "lib2to3", "test", "ensurepip", "venv", "antigravity", "this"}
    for path in lib.rglob("*.py"):
        rel = path.relative_to(lib)
        if any(part in STDLIB_SKIP or part in ("tests", "idle_test") for part in rel.parts):
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts and all(p.isidentifier() for p in parts) and not parts[0].startswith("__"):
            found.add(".".join(parts))
    return sorted(found)


if __name__ == "__main__":
    core, pack = partition()
    print("núcleo:", " ".join(sorted(core)))
    print("motor: ", " ".join(sorted(pack)))

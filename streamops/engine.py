"""Motor de voces de personaje (PyTorch + RVC).

Pesa varios GB, así que StreamOps.exe no lo incluye: se descarga una sola vez desde el
panel y queda en la carpeta de datos. Al ejecutar desde el código fuente se usa el que
esté instalado en el entorno de Python (tools\\instalar_rvc.bat).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from .config import BUNDLE, DATA, FROZEN

logger = logging.getLogger(__name__)

ENGINE = DATA / "motor"
READY = ENGINE / "listo.txt"
VERSION = "1"
TORCH, TORCHAUDIO = "2.6.0", "2.6.0"
# Bibliotecas de apoyo (todo menos PyTorch): lista fijada que genera tools/build_exe.py.
LOCK = BUNDLE / "tools" / "motor.json"
WHEELS = "https://download.pytorch.org/whl/{variant}/{name}-{version}%2B{variant}-cp311-cp311-win_amd64.whl"


def has_nvidia() -> bool:
    return (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvcuda.dll").is_file()


def available() -> bool:
    if FROZEN:
        return READY.is_file() and READY.read_text(encoding="utf-8").strip() == VERSION
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("infer_rvc_python") is not None


def activate() -> None:
    """Hace importables las bibliotecas del motor descargado."""
    if FROZEN and str(ENGINE) not in sys.path:
        sys.path.append(str(ENGINE))
        importlib.invalidate_caches()


def info() -> dict:
    gpu = has_nvidia()
    return {
        "installed": available(),
        "gpu": gpu,
        "size": "unos 2.8 GB de descarga" if gpu else "unos 0.5 GB de descarga",
        "note": "" if gpu else "Sin tarjeta NVIDIA las voces de personaje tardan varios segundos por frase.",
    }


def _download(url: str, target: Path, progress, label: str) -> None:
    """Descarga a un archivo; si quedó a medias de un intento anterior, continúa."""
    part = target.with_name(target.name + ".part")
    done = part.stat().st_size if part.is_file() else 0
    headers = {"User-Agent": "streamops/1.0"}
    if done:
        headers["Range"] = f"bytes={done}-"
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)
    except urllib.error.HTTPError as exc:
        if exc.code != 416:  # 416: el archivo parcial ya estaba completo
            raise
        part.replace(target)
        return
    with resp:
        if done and resp.status != 206:
            done = 0
        total = done + int(resp.headers.get("Content-Length") or 0)
        with open(part, "ab" if done else "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                progress(done, total, label)
    part.replace(target)


def _unpack(archive: Path, progress, label: str) -> None:
    with zipfile.ZipFile(archive) as zf:
        members = zf.infolist()
        for i, member in enumerate(members):
            zf.extract(member, ENGINE)  # zipfile descarta rutas absolutas y «..»
            if i % 200 == 0:
                progress(i, len(members), label)
    # Un .whl puede traer carpetas «nombre.data/purelib|platlib» que van a la raíz.
    for data_dir in ENGINE.glob("*.data"):
        for kind in ("purelib", "platlib"):
            for item in (data_dir / kind).glob("*"):
                if not (ENGINE / item.name).exists():
                    shutil.move(str(item), str(ENGINE / item.name))
        shutil.rmtree(data_dir, ignore_errors=True)
    archive.unlink(missing_ok=True)


def install(progress) -> None:
    """Descarga e instala el motor. progress(hecho, total, etiqueta)."""
    if not FROZEN:
        raise RuntimeError("Al ejecutar desde el código fuente, instala el motor con tools\\instalar_rvc.bat")
    variant = "cu124" if has_nvidia() else "cpu"
    READY.unlink(missing_ok=True)
    ENGINE.mkdir(parents=True, exist_ok=True)
    # 1) Bibliotecas de apoyo: versiones exactas publicadas en PyPI, con suma de comprobación.
    wheels = json.loads(LOCK.read_text(encoding="utf-8"))
    total, base = sum(w["size"] for w in wheels), 0
    for wheel in wheels:
        archive = ENGINE / "_paquete.zip"
        archive.with_name(archive.name + ".part").unlink(missing_ok=True)
        _download(wheel["url"], archive, lambda done, _t, label, base=base: progress(base + done, total, label), "Descargando bibliotecas")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != wheel["sha256"]:
            archive.unlink(missing_ok=True)
            raise RuntimeError(f"La descarga de {wheel['name']} llegó dañada; inténtalo de nuevo")
        _unpack(archive, lambda *_: None, "")
        base += wheel["size"]
    # 2) PyTorch, de su web oficial (con o sin soporte de tarjeta NVIDIA).
    for label, name, version in (("PyTorch", "torch", TORCH), ("audio", "torchaudio", TORCHAUDIO)):
        archive = ENGINE / f"_{name}.zip"
        _download(WHEELS.format(variant=variant, name=name, version=version), archive, progress, f"Descargando {label}")
        _unpack(archive, progress, f"Instalando {label}")
    READY.write_text(VERSION, encoding="utf-8")
    logger.info("[Motor] Instalado (%s)", variant)


def remove() -> None:
    shutil.rmtree(ENGINE, ignore_errors=True)

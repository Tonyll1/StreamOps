"""Publica dist/ en GitHub Releases usando la credencial que ya usa git.

    python tools/publicar.py v1.0.0            sube StreamOps.exe a la versión indicada
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "Tonyll1/StreamOps"
API = f"https://api.github.com/repos/{REPO}"


def token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("git no tiene una credencial de GitHub guardada")


def call(method: str, url: str, tok: str, data: bytes | None = None, content_type: str = "application/json"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "Content-Type": content_type, "User-Agent": "streamops-publicar",
    })
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GitHub respondió {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")


def main(tag: str) -> None:
    tok = token()
    asset = ROOT / "dist" / "StreamOps.exe"
    name, notes = f"StreamOps {tag}", (
        "Descarga **StreamOps.exe** y ábrelo: no necesita instalación.\n\n"
        "- Las voces se descargan desde el panel (Voz > Catálogo de voces).\n"
        "- Las voces de personaje piden instalar el motor de voces, una sola vez, desde el mismo panel.\n"
        "- Windows puede mostrar un aviso de SmartScreen porque el programa no está firmado: «Más información» > «Ejecutar de todas formas»."
    )
    releases = call("GET", f"{API}/releases?per_page=100", tok)
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if release is None:
        release = call("POST", f"{API}/releases", tok, json.dumps({"tag_name": tag, "target_commitish": "main", "name": name, "body": notes}).encode())
    for old in release.get("assets", []):
        if old["name"] == asset.name:
            call("DELETE", f"{API}/releases/assets/{old['id']}", tok)
    upload = release["upload_url"].split("{")[0] + f"?name={asset.name}"
    print(f"subiendo {asset.name} ({asset.stat().st_size / 1048576:.0f} MB)…", flush=True)
    done = call("POST", upload, tok, asset.read_bytes(), "application/octet-stream")
    print("publicado:", done.get("browser_download_url"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

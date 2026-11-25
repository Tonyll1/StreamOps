"""Descarga voces para StreamOps desde la terminal (el panel hace lo mismo en Voz > Catálogo).

    python tools/voces.py lista
    python tools/voces.py instalar miku teto
    python tools/voces.py instalar todas
    python tools/voces.py url nombre https://…/modelo.zip [--base es_MX-ald-medium] [--pitch 0]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamops.voces import CATALOG, main  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main(sys.argv))

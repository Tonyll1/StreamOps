"""Afina las voces de personaje: elige voz base, tono y velocidad a partir del tono esperado.

    python tools/afinar_voces.py            aplica la tabla a las voces instaladas
    python tools/afinar_voces.py --buscar duende-verde yoda
                                            prueba tonos cercanos y se queda con el más limpio

El tono esperado (Hz) es una estimación del registro del personaje, no una medición de
su audio original: sirve para dejar cada voz en su zona y luego ajustar de oído en el panel.
El resultado se guarda en tools/afinacion.json, que el instalador de voces aplica.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES = ROOT / "data" / "voices"
TABLE = Path(__file__).with_name("afinacion.json")
BASES = {"es_MX-ald-medium": 142.7, "es_MX-claude-high": 192.6}  # tono medido de cada voz base

# personaje: (tono esperado en Hz, velocidad; 1 = normal, más = más rápido)
TARGETS: dict[str, tuple[float, float]] = {
    "miku": (300, 1.03), "miku-jp": (310, 1.03), "teto": (280, 1.03), "rin": (320, 1.03), "len": (250, 1.0), "luka": (220, 0.97),
    "bob-esponja": (250, 1.06), "patricio": (125, 0.9), "calamardo": (150, 0.97), "don-cangrejo": (150, 1.0), "plankton": (180, 1.03), "arenita": (240, 1.03),
    "homero": (135, 0.97), "bart": (250, 1.05), "lisa": (280, 1.03), "ralph": (270, 0.93), "moe": (115, 1.0),
    "shrek": (120, 0.97), "burro": (185, 1.1), "goku": (150, 1.0), "vegeta": (135, 1.0), "naruto": (230, 1.05),
    "loquendo-jorge": (115, 1.0), "loquendo-juan": (120, 1.0), "dross": (105, 0.97),
    "chavo": (210, 1.0), "don-ramon": (150, 1.03), "jirafales": (115, 0.95), "senor-barriga": (125, 0.97),
    "duende-verde": (140, 1.0), "peter-griffin": (150, 1.0), "rick": (130, 1.03), "morty": (200, 1.05), "oogway": (105, 0.83),
    "deadpool": (130, 1.08), "harley-quinn": (240, 1.05), "woody": (145, 1.03), "buzz": (115, 0.97), "gru": (125, 0.97), "skipper": (120, 1.03),
    "rey-julien": (160, 1.05), "mojo-jojo": (150, 1.0), "shaggy": (180, 1.03), "po": (140, 1.03),
    "crash": (180, 1.05), "optimus": (90, 0.88), "doraemon": (290, 1.0), "shin-chan": (270, 1.03), "wario": (140, 1.0),
    "glados": (210, 0.95), "darth-vader": (85, 0.87), "mario": (240, 1.05), "luigi": (210, 1.03), "sonic": (180, 1.1), "mickey": (320, 1.0),
    # anime
    "teto-jp": (280, 1.03), "gojo": (125, 1.0), "sukuna": (105, 0.95), "toji": (105, 0.97), "geto": (115, 0.97), "nobara": (230, 1.05), "itadori": (150, 1.05), "megumi": (120, 0.97), "sasuke": (120, 0.97), "madara": (95, 0.92), "goku-jp": (290, 1.05), "luffy": (260, 1.08), "levi": (115, 0.97), "zenitsu": (190, 1.08), "nezuko": (290, 1.0), "anya": (330, 1.0), "light-yagami": (130, 1.0), "saitama": (125, 0.97), "zero-two": (240, 1.0), "frieren": (230, 0.93), "rei": (230, 0.93), "asuka": (260, 1.05), "killua": (250, 1.03), "nagatoro": (260, 1.05), "todoroki": (125, 0.97), "aizen": (110, 0.93), "jotaro": (100, 0.95), "giorno": (130, 1.0), "raiden-shogun": (220, 0.95), "hinata": (250, 0.97),
    "makima": (215, 0.95), "zundamon": (330, 1.05), "vegeta-jp": (135, 1.0), "deku": (230, 1.05), "naruto-jp": (250, 1.05),
    "pato-donald": (270, 1.0), "kermit": (190, 1.0), "yoda": (150, 0.9), "kratos": (90, 0.9), "master-chief": (100, 0.95), "cartman": (240, 1.0),
}


def plan(name: str) -> dict:
    """Voz base y semitonos que dejan la voz más cerca del tono esperado con el menor cambio."""
    target, speed = TARGETS[name]
    options = [(abs(12 * math.log2(target / hz)), base, round(12 * math.log2(target / hz))) for base, hz in BASES.items()]
    _, base, pitch = min(options)
    return {"piper": base, "pitch": int(pitch), "length_scale": round(1 / speed, 3)}


def apply(name: str, tune: dict) -> bool:
    path = VOICES / f"{name}.voice.json"
    if not path.is_file() or not (VOICES / f"{tune['piper']}.onnx").is_file():
        return False
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["piper"] = tune["piper"]
    spec["length_scale"] = tune["length_scale"]
    spec.setdefault("rvc", {})["pitch"] = tune["pitch"]
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def search(names: list[str], table: dict) -> None:
    """Para voces que salen sucias: prueba tonos vecinos y elige el que da más voz limpia."""
    import numpy as np
    from piper import PiperVoice, SynthesisConfig

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).parent))
    from medir_voces import TEXT, f0_stats
    from streamops.rvc import RvcConverter

    rvc, pipers = RvcConverter(), {}
    for name in names:
        spec = json.loads((VOICES / f"{name}.voice.json").read_text(encoding="utf-8"))
        best = None
        for base in BASES:
            if base not in pipers:
                pipers[base] = PiperVoice.load(str(VOICES / f"{base}.onnx"))
            chunks = list(pipers[base].synthesize(TEXT, syn_config=SynthesisConfig(length_scale=table[name]["length_scale"])))
            audio, rate = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32), chunks[0].sample_rate
            center = round(12 * math.log2(TARGETS[name][0] / BASES[base]))
            for pitch in range(center - 4, center + 5, 2):
                out, out_rate = rvc.convert(audio, rate, {**spec["rvc"], "pitch": pitch})
                stats = f0_stats(out, out_rate)
                # Más voz limpia es mejor; se penaliza alejarse del tono esperado.
                score = stats["voiced"] - 0.02 * abs(pitch - center)
                print(f"  {name:14} {base[6:12]:7} {pitch:+3d} -> {stats['hz']:6} Hz voz={stats['voiced']} punt={score:.2f}", flush=True)
                if best is None or score > best[0]:
                    best = (score, base, pitch, stats)
        table[name].update(piper=best[1], pitch=best[2])
        print(f"{name}: queda {best[1]} {best[2]:+d} ({best[3]['hz']} Hz, voz {best[3]['voiced']})", flush=True)


def main(argv: list[str]) -> int:
    table = json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.is_file() else {}
    for name in TARGETS:
        table.setdefault(name, plan(name))
    if argv[:1] == ["--buscar"]:
        search([n for n in argv[1:] if n in TARGETS and (VOICES / f"{n}.voice.json").is_file()], table)
    done = [name for name, tune in table.items() if apply(name, tune)]
    TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"afinadas {len(done)} voces; tabla en {TABLE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

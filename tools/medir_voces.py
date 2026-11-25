"""Mide el tono (F0) real de cada voz instalada para detectar las que están mal afinadas.

    python tools/medir_voces.py [voz ...]      sin argumentos mide todas las de personaje

Escribe data/voices/medicion.json con: tono medio en Hz, proporción de audio con voz,
pico de volumen y duración. Sirve para comparar contra el tono esperado del personaje.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
VOICES = ROOT / "data" / "voices"
TEXT = "Hola chat, muchas gracias por el regalo. Hoy vamos a jugar un rato y a leer sus mensajes."


def f0_stats(samples: np.ndarray, rate: int) -> dict:
    import librosa

    y = librosa.resample(samples.astype(np.float32), orig_sr=rate, target_sr=16000) if rate != 16000 else samples
    f0, voiced, _ = librosa.pyin(y, fmin=55, fmax=800, sr=16000, frame_length=1024)
    good = f0[voiced & ~np.isnan(f0)]
    return {
        "hz": round(float(np.median(good)), 1) if good.size else 0.0,
        "voiced": round(float(voiced.mean()), 2),
        "peak": round(float(np.abs(samples).max()), 2),
        "seconds": round(len(samples) / rate, 2),
    }


def main(names: list[str]) -> int:
    from piper import PiperVoice, SynthesisConfig

    from streamops.rvc import RvcConverter

    specs = {p.name[: -len(".voice.json")]: json.loads(p.read_text(encoding="utf-8")) for p in sorted(VOICES.glob("*.voice.json"))}
    if names:
        specs = {n: specs[n] for n in names if n in specs}
    out_file = VOICES / "medicion.json"
    results = json.loads(out_file.read_text(encoding="utf-8")) if out_file.is_file() else {}
    pipers, bases, rvc = {}, {}, RvcConverter()
    for name, spec in specs.items():
        base = spec["piper"]
        scale = float(spec.get("length_scale") or 1.0)
        key = (base, scale)
        if key not in bases:
            if base not in pipers:
                pipers[base] = PiperVoice.load(str(VOICES / f"{base}.onnx"))
            chunks = list(pipers[base].synthesize(TEXT, syn_config=SynthesisConfig(length_scale=scale)))
            audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
            bases[key] = (audio, chunks[0].sample_rate)
            results["@" + base] = f0_stats(audio, chunks[0].sample_rate)
        audio, rate = bases[key]
        started = time.perf_counter()
        try:
            converted, out_rate = rvc.convert(audio, rate, spec["rvc"])
            stats = f0_stats(converted, out_rate)
            stats.update(pitch=int(spec["rvc"].get("pitch", 0)), base=base, index=bool(spec["rvc"].get("index")), rate=out_rate,
                         took=round(time.perf_counter() - started, 1))
        except Exception as exc:  # modelo roto o incompatible
            stats = {"error": f"{type(exc).__name__}: {exc}"[:160], "base": base}
        results[name] = stats
        print(f"{name:18} {stats}", flush=True)
        out_file.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

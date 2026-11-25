"""Calibra la entonación de las voces de personaje.

    python tools/calibrar_voces.py [voz ...]     sin argumentos calibra todas las instaladas

Para cada personaje prueba las voces base en español de México y mide qué tan fielmente
el resultado sigue la melodía de la frase (sin saltos de tono ni tramos sin voz). Se queda
con la base de entonación más estable salvo que otra salga claramente más limpia.
Guarda el resultado en tools/afinacion.json y en cada data/voices/<voz>.voice.json.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from afinar_voces import TABLE, TARGETS, VOICES, apply  # noqa: E402

# De más a menos estable al entonar (rango de tono medido: laura 6 st, claude 12 st, ald 21 st).
PREFERRED = ["es_MX-laura-high", "es_MX-claude-high", "es_MX-ald-medium"]
MARGIN = 0.08  # ventaja que necesita una base menos estable para ganar
TEXT = "Hola chat, muchas gracias por el regalo. ¿Cómo están hoy? ¡No puede ser, qué locura!"
HOP = 320


def contour(samples: np.ndarray, rate: int):
    import librosa

    y = librosa.resample(samples.astype(np.float32), orig_sr=rate, target_sr=16000) if rate != 16000 else samples
    f0, voiced, _ = librosa.pyin(y, fmin=55, fmax=900, sr=16000, frame_length=1024, hop_length=HOP)
    return np.nan_to_num(f0), voiced


def main(names: list[str]) -> int:
    from piper import PiperVoice, SynthesisConfig

    from streamops.rvc import RvcConverter

    table = json.loads(TABLE.read_text(encoding="utf-8")) if TABLE.is_file() else {}
    bases = [b for b in PREFERRED if (VOICES / f"{b}.onnx").is_file()]
    pipers = {b: PiperVoice.load(str(VOICES / f"{b}.onnx")) for b in bases}
    rvc, cache = RvcConverter(), {}
    todo = [n for n in (names or TARGETS) if n in TARGETS and (VOICES / f"{n}.voice.json").is_file()]
    for name in todo:
        target, speed = TARGETS[name]
        scale = round(1 / speed, 3)
        spec = json.loads((VOICES / f"{name}.voice.json").read_text(encoding="utf-8"))
        results = []
        for base in bases:
            if (base, scale) not in cache:
                chunks = list(pipers[base].synthesize(TEXT, syn_config=SynthesisConfig(length_scale=scale)))
                audio = np.concatenate([c.audio_float_array for c in chunks]).astype(np.float32)
                f0, voiced = contour(audio, chunks[0].sample_rate)
                cache[(base, scale)] = (audio, chunks[0].sample_rate, f0, voiced, float(np.median(f0[voiced])))
            audio, rate, f0b, vb, median = cache[(base, scale)]
            pitch = round(12 * math.log2(target / median))
            try:
                out, out_rate = rvc.convert(audio, rate, {**spec["rvc"], "pitch": pitch})
            except Exception as exc:
                print(f"{name}: no carga ({type(exc).__name__})", flush=True)
                results = []
                break
            f0o, vo = contour(out, out_rate)
            n = min(len(f0b), len(f0o))
            both = vb[:n] & vo[:n]
            lost = 1 - both.sum() / max(1, vb[:n].sum())  # tramos donde se pierde la voz
            dev = 12 * np.log2(f0o[:n][both] / (f0b[:n][both] * 2 ** (pitch / 12))) if both.any() else np.array([9.0])
            jumps = float((np.abs(dev) > 2).mean())  # saltos de tono que no estaban en la frase
            results.append({"base": base, "pitch": int(pitch), "error": round(jumps * (1 - lost) + lost, 3), "saltos": round(jumps, 2), "sin_voz": round(lost, 2)})
        if not results:
            continue
        best = results[0]
        for r in results[1:]:
            if r["error"] < best["error"] - MARGIN:
                best = r
        table[name] = {"piper": best["base"], "pitch": best["pitch"], "length_scale": scale, "error": best["error"]}
        apply(name, table[name])
        TABLE.write_text(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        shown = "  ".join(f"{r['base'][6:11]}{r['pitch']:+d}:{r['error']:.2f}" for r in results)
        print(f"{name:15} -> {best['base'][6:12]:7} {best['pitch']:+3d}  error {best['error']:.2f}   [{shown}]", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

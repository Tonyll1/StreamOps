"""TTS local con Piper, cola serial y conversión opcional de voz (RVC).

Voces disponibles en data/voices:
  - nombre.onnx + nombre.onnx.json       -> voz Piper directa
  - nombre.voice.json                    -> voz compuesta, por ejemplo:
        {"piper": "es_MX-claude-high", "length_scale": 1.0, "speaker": 0,
         "rvc": {"model": "miku.pth", "index": "miku.index", "pitch": 12}}
    Piper genera el habla y RVC la convierte al timbre del personaje.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
from typing import TYPE_CHECKING

import numpy as np

from . import engine
from .audio import resample, to_stereo
from .config import VOICES

if TYPE_CHECKING:
    from .app import App

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_REPEAT_RE = re.compile(r"(.)\1{4,}")


def clean_text(text: str, max_chars: int, blocked: list[str]) -> str:
    text = _URL_RE.sub("enlace", text or "")
    text = _REPEAT_RE.sub(r"\1\1\1", text)
    for word in blocked:
        if word:
            text = re.sub(re.escape(word), "", text, flags=re.IGNORECASE)
    return " ".join(text.split())[:max_chars].strip()


class TTS:
    def __init__(self, app: "App") -> None:
        self.app = app
        self._queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._piper_cache: dict[str, object] = {}
        self._current: threading.Event | None = None
        self._rvc = None
        self._rvc_lock = threading.Lock()
        threading.Thread(target=self._worker, name="tts", daemon=True).start()
        threading.Thread(target=self._warm_up, name="tts-precarga", daemon=True).start()

    # ---- catálogo -------------------------------------------------------
    def voices(self) -> list[dict]:
        found = []
        for path in sorted(VOICES.glob("*.voice.json")):
            name = path.name[: -len(".voice.json")]
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            found.append({"name": name, "kind": "rvc" if spec.get("rvc") else "piper", "base": spec.get("piper", "")})
        for path in sorted(VOICES.glob("*.onnx")):
            if path.with_suffix(".onnx.json").is_file():
                found.append({"name": path.stem, "kind": "piper", "base": ""})
        return found

    def _resolve(self, name: str | None) -> dict | None:
        """Devuelve la especificación de una voz, o la primera disponible."""
        names = [name, self.app.config["tts"]["voice"]]
        for candidate in names:
            if not candidate:
                continue
            composite = VOICES / f"{candidate}.voice.json"
            if composite.is_file():
                try:
                    spec = json.loads(composite.read_text(encoding="utf-8"))
                    if (VOICES / f"{spec.get('piper', '')}.onnx").is_file():
                        return spec
                except ValueError:
                    pass
            if (VOICES / f"{candidate}.onnx").is_file():
                return {"piper": candidate}
        for path in sorted(VOICES.glob("*.onnx")):
            return {"piper": path.stem}
        return None

    def find_voice(self, query: str) -> str | None:
        """Busca una voz por nombre parcial (para el comando !voz)."""
        query = query.strip().lower()
        if not query:
            return None
        names = [v["name"] for v in self.voices()]
        for name in names:
            if name.lower() == query:
                return name
        for name in names:
            if query in name.lower():
                return name
        return None

    # ---- cola -----------------------------------------------------------
    def say(self, text: str, voice: str | None = None) -> bool:
        cfg = self.app.config["tts"]
        if not cfg["enabled"] or self.app.mixer.muted:
            return False
        text = clean_text(text, int(cfg["max_chars"]), cfg.get("blocked_words", []))
        if not text or self._queue.qsize() >= int(cfg["max_queue"]):
            return False
        self._queue.put((text, voice))
        return True

    def forget(self, name: str) -> None:
        """Suelta una voz Piper cargada (se va a borrar su archivo)."""
        self._piper_cache.pop(name, None)

    def skip(self) -> None:
        """Corta la frase que está sonando."""
        self.app.mixer.clear("tts")

    def clear(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        self.skip()

    def _worker(self) -> None:
        playing: threading.Event | None = None
        while True:
            text, voice = self._queue.get()
            if self.app.mixer.muted:
                continue
            # La frase se genera mientras aún suena la anterior, para que no haya huecos.
            try:
                samples, rate = self.synthesize(text, voice)
            except Exception:
                logger.exception("[TTS] No se pudo sintetizar")
                continue
            if samples is None:
                continue
            if playing is not None:
                playing.wait(timeout=60)
                self.app.notify({"type": "tts_end"})
            if self.app.mixer.muted:
                playing = None
                continue
            # Avisa a los overlays (subtítulos) de lo que se va a leer.
            shown = self.find_voice(voice) if voice else None
            self.app.notify({
                "type": "tts", "text": text, "seconds": round(len(samples) / rate, 2),
                "voice": shown or self.app.config["tts"].get("voice", ""),
            })
            playing = self.app.mixer.play(
                resample(to_stereo(samples), rate), kind="tts", volume=float(self.app.config["tts"]["volume"])
            )

    # ---- síntesis -------------------------------------------------------
    def _piper(self, name: str):
        voice = self._piper_cache.get(name)
        if voice is None:
            from piper import PiperVoice

            voice = PiperVoice.load(str(VOICES / f"{name}.onnx"))
            self._piper_cache[name] = voice
            logger.info("[TTS] Voz Piper cargada: %s", name)
        return voice

    def synthesize(self, text: str, voice_name: str | None = None) -> tuple[np.ndarray | None, int]:
        spec = self._resolve(voice_name)
        if spec is None:
            logger.warning("[TTS] No hay voces en %s", VOICES)
            return None, 0
        voice = self._piper(spec["piper"])
        from piper import SynthesisConfig

        syn = SynthesisConfig(
            length_scale=float(spec["length_scale"]) if spec.get("length_scale") else None,
            speaker_id=int(spec["speaker"]) if spec.get("speaker") is not None else None,
        )
        chunks, rate = [], 22050
        for chunk in voice.synthesize(text, syn_config=syn):
            chunks.append(chunk.audio_float_array)
            rate = chunk.sample_rate
        if not chunks:
            return None, 0
        samples = np.concatenate(chunks).astype(np.float32)
        if spec.get("rvc") and engine.available():  # sin el motor suena la voz base
            try:
                samples, rate = self._convert(samples, rate, spec["rvc"])
            except Exception:
                logger.exception("[TTS] RVC falló; se usa la voz base")
        return samples, rate

    def _convert(self, samples: np.ndarray, rate: int, rvc_spec: dict) -> tuple[np.ndarray, int]:
        with self._rvc_lock:
            if self._rvc is None:
                from .rvc import RvcConverter

                self._rvc = RvcConverter()
            return self._rvc.convert(samples, rate, rvc_spec)

    def _warm_up(self) -> None:
        """Carga en segundo plano el motor de personajes y la voz por defecto, para que la primera frase no tarde."""
        try:
            spec = self._resolve(None)
            if spec is None:
                return
            self._piper(spec["piper"])
            if engine.available() and (spec.get("rvc") or any(VOICES.glob("*.voice.json"))):
                silence = (np.random.default_rng(0).standard_normal(8000) * 0.01).astype(np.float32)
                if spec.get("rvc"):
                    self._convert(silence, 16000, spec["rvc"])
                else:
                    with self._rvc_lock:
                        if self._rvc is None:
                            from .rvc import RvcConverter

                            self._rvc = RvcConverter()
            logger.info("[TTS] Voces precargadas")
        except Exception:
            logger.warning("[TTS] No se pudo precargar la voz", exc_info=True)

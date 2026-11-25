"""Mezclador con un único stream de salida (48 kHz estéreo).

Un solo stream siempre abierto hace que la app aparezca como una fuente fija en
el mezclador de Windows, así OBS / TikTok LIVE Studio pueden capturarla por app.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

RATE = 48000
CHANNELS = 2


def resample(samples: np.ndarray, src_rate: int, dst_rate: int = RATE) -> np.ndarray:
    """Remuestreo lineal de un arreglo (n, canales) float32."""
    if src_rate == dst_rate or len(samples) == 0:
        return samples
    n_out = int(round(len(samples) * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.stack(
        [np.interp(x_new, x_old, samples[:, ch]) for ch in range(samples.shape[1])], axis=1
    ).astype(np.float32)


def to_stereo(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        samples = samples[:, None]
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    elif samples.shape[1] > 2:
        samples = samples[:, :2]
    return samples.astype(np.float32, copy=False)


def load_file(path: Path) -> np.ndarray:
    """Decodifica WAV/MP3/OGG/FLAC a float32 estéreo 48 kHz."""
    import soundfile as sf

    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return resample(to_stereo(data), rate)


class _Voice:
    __slots__ = ("samples", "pos", "kind", "volume", "done")

    def __init__(self, samples: np.ndarray, kind: str, volume: float) -> None:
        self.samples = samples
        self.pos = 0
        self.kind = kind
        self.volume = volume
        self.done = threading.Event()


class Mixer:
    def __init__(self, device: str = "") -> None:
        self._lock = threading.Lock()
        self._voices: list[_Voice] = []
        self.muted = False
        self._stream = None
        self._device = device or None
        self._cache: dict[str, tuple[float, np.ndarray]] = {}

    def start(self) -> None:
        try:
            import sounddevice as sd

            self._stream = sd.OutputStream(
                samplerate=RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=960,
                device=self._device,
                callback=self._callback,
            )
            self._stream.start()
            logger.info("[Audio] Salida abierta: %s", sd.query_devices(self._stream.device)["name"])
        except Exception:
            logger.exception("[Audio] No se pudo abrir la salida de audio")
            self._stream = None

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, outdata, frames, _time, _status) -> None:
        outdata.fill(0.0)
        with self._lock:
            alive = []
            for voice in self._voices:
                chunk = voice.samples[voice.pos : voice.pos + frames]
                if len(chunk) and not self.muted:
                    outdata[: len(chunk)] += chunk * voice.volume
                voice.pos += frames
                if voice.pos >= len(voice.samples):
                    voice.done.set()
                else:
                    alive.append(voice)
            self._voices = alive
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def play(self, samples: np.ndarray, kind: str = "alert", volume: float = 1.0) -> threading.Event:
        """Agrega un clip a la mezcla. Devuelve un Event que se activa al terminar."""
        voice = _Voice(to_stereo(samples), kind, max(0.0, min(float(volume), 2.0)))
        if self._stream is None or len(voice.samples) == 0:
            voice.done.set()
            return voice.done
        with self._lock:
            self._voices.append(voice)
        return voice.done

    def play_file(self, path: Path, kind: str = "alert", volume: float = 1.0) -> threading.Event:
        key = str(path)
        mtime = path.stat().st_mtime
        cached = self._cache.get(key)
        if cached is None or cached[0] != mtime:
            if len(self._cache) > 64:
                self._cache.clear()
            cached = (mtime, load_file(path))
            self._cache[key] = cached
        return self.play(cached[1], kind, volume)

    def clear(self, kind: str | None = None) -> int:
        with self._lock:
            dropped = [v for v in self._voices if kind is None or v.kind == kind]
            self._voices = [v for v in self._voices if v not in dropped]
        for voice in dropped:
            voice.done.set()
        return len(dropped)

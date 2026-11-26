"""Mezclador con un único stream de salida (48 kHz estéreo).

Un solo stream siempre abierto hace que la app aparezca como una fuente fija en
el mezclador de Windows, así OBS / TikTok LIVE Studio pueden capturarla por app.
"""

from __future__ import annotations

import logging
import threading
import time
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


def sd_abort() -> Exception:
    """Excepción que detiene el stream de forma ordenada (el vigilante lo reabre)."""
    import sounddevice as sd

    return sd.CallbackAbort()


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
    """Mezcla todo en un stream de salida y lo vuelve a abrir si se cae.

    Un vigilante revisa que el callback de audio siga avanzando. Si el stream se
    detiene (error en el callback, dispositivo reiniciado, audífonos desconectados,
    FxSound reiniciado…), lo reabre. Los clips en curso siguen donde iban.
    """

    STALL_SECONDS = 2.0  # sin llamadas al callback por este tiempo = stream colgado
    CHECK_SECONDS = 1.0

    def __init__(self, device: str = "") -> None:
        self._lock = threading.Lock()
        self._open_lock = threading.Lock()
        self._voices: list[_Voice] = []
        self.muted = False
        self._stream = None
        self._device = device or None
        self._cache: dict[str, tuple[float, np.ndarray]] = {}
        self._last_tick = 0.0
        self._callback_error: str | None = None
        self._running = False
        self._failing = False
        self.device_name = ""
        self.reopens = 0

    def start(self) -> None:
        self._running = True
        self._open()
        threading.Thread(target=self._watchdog, name="audio-vigilante", daemon=True).start()

    def stop(self) -> None:
        self._running = False
        with self._open_lock:
            self._close()

    # ---- stream ---------------------------------------------------------
    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def _open(self, refresh: bool = False) -> bool:
        """Abre (o reabre) la salida. Con refresh relee la lista de dispositivos de Windows."""
        import sounddevice as sd

        with self._open_lock:
            self._close()
            if refresh:
                try:  # PortAudio guarda la lista de dispositivos; hay que reiniciarlo para ver cambios
                    sd._terminate()
                    sd._initialize()
                except Exception:
                    logger.debug("[Audio] No se pudo reiniciar PortAudio", exc_info=True)
            device = self._device
            if device is not None:
                try:
                    sd.query_devices(device, kind="output")
                except Exception:
                    if not self._failing:
                        logger.warning("[Audio] No se encontró el dispositivo «%s»; se usa el predeterminado", device)
                    device = None
            try:
                stream = sd.OutputStream(
                    samplerate=RATE,
                    channels=CHANNELS,
                    dtype="float32",
                    blocksize=960,
                    device=device,
                    callback=self._callback,
                )
                self._callback_error = None
                self._last_tick = time.monotonic()
                stream.start()
            except Exception:
                if not self._failing:
                    logger.exception("[Audio] No se pudo abrir la salida de audio; se reintentará")
                self._failing = True
                return False
            self._stream = stream
            self._failing = False
            self.device_name = sd.query_devices(stream.device)["name"]
            logger.info("[Audio] Salida abierta: %s", self.device_name)
            return True

    def _watchdog(self) -> None:
        while self._running:
            time.sleep(self.CHECK_SECONDS)
            if not self._running:
                break
            stream = self._stream
            reason = None
            if stream is None:
                reason = "sin salida"
            elif self._callback_error:
                reason = f"error en el audio: {self._callback_error}"
            elif not stream.active:
                reason = "la salida se detuvo"
            elif time.monotonic() - self._last_tick > self.STALL_SECONDS:
                reason = "la salida dejó de avanzar"
            if reason is None:
                continue
            if not self._failing:
                logger.warning("[Audio] %s; reabriendo la salida", reason)
            if self._open(refresh=True):
                self.reopens += 1
            else:
                self.clear()  # sin salida no se acumulan clips que nunca van a sonar

    def _callback(self, outdata, frames, _time, _status) -> None:
        self._last_tick = time.monotonic()
        try:
            self._mix(outdata, frames)
        except Exception as exc:  # un error aquí mataría el stream sin avisar
            outdata.fill(0.0)
            if self._callback_error is None:
                self._callback_error = repr(exc)
                logger.exception("[Audio] Error al mezclar")
            raise sd_abort() from exc

    def _mix(self, outdata, frames) -> None:
        outdata.fill(0.0)
        with self._lock:
            alive = []
            for voice in self._voices:
                try:
                    chunk = voice.samples[voice.pos : voice.pos + frames]
                    if len(chunk) and not self.muted:
                        outdata[: len(chunk)] += chunk * voice.volume
                except Exception:
                    logger.exception("[Audio] Clip inválido descartado")
                    voice.done.set()
                    continue
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
        if (self._stream is None and not self._running) or len(voice.samples) == 0:
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

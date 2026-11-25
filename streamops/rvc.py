"""Conversión de voz RVC (opcional): convierte el habla de Piper al timbre de un personaje.

Requiere la instalación extra de tools/instalar_rvc.bat (PyTorch + infer_rvc_python).
Los modelos (.pth y, si existe, .index) van en data/voices/rvc/.
"""

from __future__ import annotations

import logging

import numpy as np

from .config import VOICES

logger = logging.getLogger(__name__)

RVC_DIR = VOICES / "rvc"


class RvcConverter:
    def __init__(self) -> None:
        import torch
        from infer_rvc_python import BaseLoader

        self._gpu = torch.cuda.is_available()
        self._loader = BaseLoader(only_cpu=not self._gpu, hubert_path=None, rmvpe_path=None)
        self._configured: dict[str, tuple] = {}
        logger.info("[RVC] Listo (%s)", "GPU" if self._gpu else "CPU, será lento")

    def convert(self, samples: np.ndarray, rate: int, spec: dict) -> tuple[np.ndarray, int]:
        model = RVC_DIR / spec["model"]
        if not model.is_file():
            raise FileNotFoundError(f"No existe el modelo RVC {model}")
        index = RVC_DIR / spec["index"] if spec.get("index") else None
        tag = model.stem
        settings = (
            int(spec.get("pitch", 0)),
            str(index) if index and index.is_file() else "",
            float(spec.get("index_influence", 0.66)),
        )
        if self._configured.get(tag) != settings:
            self._loader.apply_conf(
                tag=tag,
                file_model=str(model),
                pitch_algo=spec.get("pitch_algo", "rmvpe+"),
                pitch_lvl=settings[0],
                file_index=settings[1],
                index_influence=settings[2],
                respiration_median_filtering=3,
                envelope_ratio=0.25,
                consonant_breath_protection=0.5,
            )
            self._configured[tag] = settings
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        out, out_rate = self._loader.generate_from_cache(audio_data=(pcm, rate), tag=tag)
        out = np.asarray(out)
        if out.dtype.kind == "i":
            out = out.astype(np.float32) / 32768.0
        return out.astype(np.float32), int(out_rate)

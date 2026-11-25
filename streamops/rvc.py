"""Conversión de voz RVC (opcional): convierte el habla de Piper al timbre de un personaje.

Requiere el motor de personajes (ver engine.py): PyTorch + infer_rvc_python.
Los modelos (.pth y, si existe, .index) van en data/voices/rvc/.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

import numpy as np

from . import engine
from .config import VOICES

logger = logging.getLogger(__name__)

RVC_DIR = VOICES / "rvc"
MAX_LOADED = 8  # personajes que se mantienen cargados a la vez


class RvcConverter:
    def __init__(self) -> None:
        engine.activate()
        import torch
        from infer_rvc_python import BaseLoader

        self._gpu = torch.cuda.is_available()
        self._loader = BaseLoader(only_cpu=not self._gpu, hubert_path=None, rmvpe_path=None, preload_models=True)
        self._configured: dict[str, tuple] = {}
        # La biblioteca solo recuerda un modelo y lo recarga al cambiar de voz;
        # aquí se guardan los últimos usados para que alternar personajes sea inmediato.
        self._loaded: OrderedDict[str, tuple] = OrderedDict()
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
            spec.get("pitch_algo", "rmvpe+"),
        )
        if self._configured.get(tag) != settings:
            self._loader.apply_conf(
                tag=tag,
                file_model=str(model),
                pitch_algo=settings[3],
                pitch_lvl=settings[0],
                file_index=settings[1],
                index_influence=settings[2],
                respiration_median_filtering=3,
                envelope_ratio=0.25,
                consonant_breath_protection=0.5,
            )
            self._configured[tag] = settings
        self._activate(tag)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        out, out_rate = self._loader.generate_from_cache(audio_data=(pcm, rate), tag=tag)
        out = np.asarray(out)
        if out.dtype.kind == "i":
            out = out.astype(np.float32) / 32768.0
        return out.astype(np.float32), int(out_rate)

    def _activate(self, tag: str) -> None:
        """Guarda el modelo que estaba activo y recupera el pedido si ya se había cargado."""
        loader = self._loader
        current = loader.cache_model.get("tag") if loader.cache_model else None
        if current == tag:
            return
        if current and loader.model_vc:
            self._loaded[current] = (loader.model_vc, loader.cache_model)
            self._loaded.move_to_end(current)
            while len(self._loaded) > MAX_LOADED:
                self._loaded.popitem(last=False)
        if tag in self._loaded:
            loader.model_vc, loader.cache_model = self._loaded.pop(tag)

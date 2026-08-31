"""Adaptador hosted, via la API de Anthropic.

Alternativa conmutable con INFERENCE_PROVIDER=hosted. Procesar las secciones de
prosa de 450 contratos cuesta unos pocos dolares, contra las mas de 60 horas de
CPU que costaria en local.

Se mantiene porque la interfaz de dos adaptadores es el argumento arquitectonico
del proyecto, no porque este caso lo necesite: estos datos son publicos.
"""

from __future__ import annotations

import logging

import httpx

from contratos.config import Config, cargar
from contratos.inferencia.interfaz import ModeloNoDisponible

log = logging.getLogger(__name__)

URL = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"


class ModeloHosted:
    """Claude via la API de Anthropic."""

    def __init__(self, config: Config | None = None) -> None:
        cfg = config or cargar()
        self.nombre = cfg.hosted_inference_model
        self._clave = cfg.hosted_inference_api_key
        self._timeout = cfg.inference_timeout_seconds
        self._max_tokens = cfg.inference_max_tokens

    def responder(self, prompt: str) -> str:
        if not self._clave:
            raise ModeloNoDisponible(
                "falta HOSTED_INFERENCE_API_KEY en el .env. "
                "Con INFERENCE_PROVIDER=local no hace falta."
            )
        try:
            r = httpx.post(
                URL,
                headers={
                    "x-api-key": self._clave,
                    "anthropic-version": VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.nombre,
                    "max_tokens": self._max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self._timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ModeloNoDisponible(f"la API hosted no respondio: {e}") from e

        bloques = r.json().get("content") or []
        texto: str = bloques[0].get("text", "") if bloques else ""
        return texto

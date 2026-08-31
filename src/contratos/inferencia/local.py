"""Adaptador local, via Ollama.

Medido en el Spike 0 sobre esta maquina: **7,34 GB de RAM y ~3,4 minutos por
documento** con el filtro de pasajes puesto. Por eso esta capa corre en lote,
offline, y NUNCA en la ruta de un request.
"""

from __future__ import annotations

import logging

import httpx

from contratos.config import Config, cargar
from contratos.inferencia.interfaz import ModeloNoDisponible

log = logging.getLogger(__name__)


class ModeloLocal:
    """Ollama en localhost."""

    def __init__(self, config: Config | None = None) -> None:
        cfg = config or cargar()
        self.nombre = cfg.ollama_model
        self._url = f"{cfg.ollama_base_url}/api/generate"
        self._timeout = cfg.inference_timeout_seconds
        self._temperatura = cfg.inference_temperature

    def responder(self, prompt: str) -> str:
        try:
            r = httpx.post(
                self._url,
                json={
                    "model": self.nombre,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": self._temperatura,
                        # Explicito a proposito: el default de Ollama es 2048
                        # tokens y recortaria el 92% de un documento largo SIN
                        # avisar. Ese fallo casi arruina el Spike 0.
                        "num_ctx": 4096,
                    },
                },
                timeout=self._timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ModeloNoDisponible(
                f"Ollama no respondio en {self._url}: {e}. "
                "Verifica que este corriendo y que el modelo este descargado."
            ) from e

        texto: str = r.json().get("response", "")
        return texto

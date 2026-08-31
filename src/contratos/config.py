"""Configuración del proyecto, cargada y validada desde el entorno.

Un valor mal puesto tiene que fallar acá, al arrancar, con un mensaje que nombre
la variable. No dentro del pipeline, tres fuentes más adelante.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

RAIZ = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    """Espejo tipado de .env.example. Ver ese archivo para el porqué de cada valor."""

    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- API de Mercado Público -------------------------------------------
    # Única variable sin valor por defecto: es un secreto y no puede inventarse.
    mp_api_ticket: str = Field(min_length=1)
    mp_api_base_url: str = "https://api.mercadopublico.cl/servicios/v1/publico"
    mp_web_base_url: str = "https://www.mercadopublico.cl"
    ocds_base_url: str = "https://apis.mercadopublico.cl/OCDS/data"

    # --- Identificación honesta -------------------------------------------
    user_agent: str = "demo-scrap/0.1 (+contacto)"
    contact_email: str = ""

    # --- Throttling y reintentos ------------------------------------------
    request_delay_seconds: float = 2.0
    request_timeout_seconds: int = 30
    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 2.0
    retry_http_codes: Annotated[list[int], NoDecode] = [429, 500, 502, 503, 504]
    # Cortafuegos: el ticket tiene tope de 10.000 requests diarios.
    max_requests_per_run: int = 2000

    # --- Caché de respuestas ----------------------------------------------
    http_cache_enabled: bool = True
    http_cache_dir: Path = Path("data/raw")

    # --- Muestra -----------------------------------------------------------
    # Tres fechas elegidas midiendo el volumen de cada una. Ver docs/02-diseno.md.
    fechas_oc: Annotated[list[date], NoDecode] = [
        date(2025, 1, 15),
        date(2025, 5, 15),
        date(2025, 10, 15),
    ]
    oc_con_proceso_por_fecha: int = 100
    oc_sin_proceso_por_fecha: int = 50
    tipos_oc_con_licitacion: Annotated[list[str], NoDecode] = ["SE", "CC"]
    tipos_oc_sin_licitacion: Annotated[list[str], NoDecode] = [
        "AG",
        "CM",
        "TD",
        "CT",
    ]

    # Estados de orden de compra. "Gasto" son dos cosas distintas y se separan.
    estados_comprometido: Annotated[list[int], NoDecode] = [4, 5, 6, 12]
    estados_ejecutado: Annotated[list[int], NoDecode] = [6, 12]

    # --- Capa de inferencia -----------------------------------------------
    # local por defecto: el argumento arquitectonico es que un CLM enterprise
    # procesa contratos confidenciales. Estos datos son publicos, asi que la
    # decision es de diseno, no una necesidad de este caso.
    inference_provider: str = "local"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    hosted_inference_api_key: str = ""
    hosted_inference_model: str = "claude-sonnet-5"
    inference_temperature: float = 0.0
    inference_max_tokens: int = 2048
    inference_timeout_seconds: int = 1200

    # --- Umbrales de calidad que hacen fallar la corrida -------------------
    max_quarantine_rate: float = 0.05
    min_cobertura_garantias: float = 0.90

    # --- Operación ---------------------------------------------------------
    log_level: str = "INFO"
    database_url: str = "sqlite:///data/contratos.db"

    @field_validator(
        "retry_http_codes",
        "fechas_oc",
        "tipos_oc_con_licitacion",
        "tipos_oc_sin_licitacion",
        "estados_comprometido",
        "estados_ejecutado",
        mode="before",
    )
    @classmethod
    def _lista_separada_por_comas(cls, v: object) -> object:
        """Acepta `429,500,502` ademas de JSON.

        pydantic-settings espera JSON para tipos complejos, pero un .env que
        obliga a escribir ["SE","CC"] es hostil para quien lo edita a mano. El
        formato legible manda; el codigo se adapta.
        """
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("tipos_oc_con_licitacion", "tipos_oc_sin_licitacion", mode="after")
    @classmethod
    def _en_mayusculas(cls, v: list[str]) -> list[str]:
        return [x.strip().upper() for x in v]

    @field_validator("max_quarantine_rate", "min_cobertura_garantias", mode="after")
    @classmethod
    def _es_proporcion(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("debe estar entre 0 y 1, es una proporción")
        return v


@lru_cache(maxsize=1)
def cargar() -> Config:
    """Devuelve la configuración, cacheada.

    Se cachea para que importar config desde varios módulos no relea el .env ni
    repita la validación.
    """
    return Config()  # type: ignore[call-arg]

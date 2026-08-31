"""Configuración del proyecto, cargada y validada desde el entorno.

Un valor mal puesto tiene que fallar acá, al arrancar, con un mensaje que nombre
la variable. No dentro del pipeline, tres fuentes más adelante.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    retry_http_codes: list[int] = [429, 500, 502, 503, 504]
    # Cortafuegos: el ticket tiene tope de 10.000 requests diarios.
    max_requests_per_run: int = 2000

    # --- Caché de respuestas ----------------------------------------------
    http_cache_enabled: bool = True
    http_cache_dir: Path = Path("data/raw")

    # --- Muestra -----------------------------------------------------------
    # Tres fechas elegidas midiendo el volumen de cada una. Ver docs/02-diseno.md.
    fechas_oc: list[date] = [
        date(2025, 1, 15),
        date(2025, 5, 15),
        date(2025, 10, 15),
    ]
    oc_con_proceso_por_fecha: int = 100
    oc_sin_proceso_por_fecha: int = 50
    tipos_oc_con_licitacion: list[str] = ["SE", "CC"]
    tipos_oc_sin_licitacion: list[str] = ["AG", "CM", "TD"]

    # Estados de orden de compra. "Gasto" son dos cosas distintas y se separan.
    estados_comprometido: list[int] = [4, 5, 6, 12]
    estados_ejecutado: list[int] = [6, 12]

    # --- Umbrales de calidad que hacen fallar la corrida -------------------
    max_quarantine_rate: float = 0.05
    min_cobertura_garantias: float = 0.90

    # --- Operación ---------------------------------------------------------
    log_level: str = "INFO"
    database_url: str = "sqlite:///data/contratos.db"

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

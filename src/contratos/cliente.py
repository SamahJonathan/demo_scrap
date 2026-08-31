"""Cliente HTTP con caché en disco, throttling y reintentos.

Es el incremento que acelera a todos los demás. Sin la caché, cada iteración
sobre el parseo consume cupo del ticket —tope de 10.000 diarios— y espera a la
red. Con ella, corregir un selector y revalidar 450 contratos toma segundos.

El cliente es genérico a propósito: no sabe qué endpoint es cuál. Eso vive en
`fuentes/`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from contratos.config import Config, cargar

log = logging.getLogger(__name__)

# httpx registra la URL completa en INFO, y el ticket viaja como parametro. Eso
# lo dejaria en cualquier consola, log o captura de pantalla. Se sube su umbral
# a WARNING: los errores siguen visibles, la URL con el secreto no.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class LimiteDeRequests(RuntimeError):
    """Se alcanzó `MAX_REQUESTS_PER_RUN`.

    Es un cortafuegos: el ticket tiene tope diario y una corrida descontrolada
    lo quema. Aborta en vez de seguir.
    """


class RespuestaTransitoria(RuntimeError):
    """Fallo que vale la pena reintentar: 429 o 5xx."""


class RespuestaDefinitiva(RuntimeError):
    """Fallo que NO se reintenta: 4xx distinto de 429.

    Reintentar un 404 solo gasta cupo. Se registra y se levanta.
    """


class ErrorDeLaFuente(RuntimeError):
    """La API respondio 2xx pero el cuerpo trae un error.

    Mercado Publico devuelve **HTTP 203** con {"Codigo":203,"Mensaje":"Ticket no
    valido."} cuando el ticket vencio. 203 es un codigo de exito, asi que un
    cliente ingenuo lo cachearia como dato bueno y la corrida terminaria con
    cero registros sin avisar de nada.

    El ticket se renueva a diario, o sea que esto pasa todos los dias.
    """


def _error_en_el_cuerpo(texto: str) -> str | None:
    """Devuelve el mensaje de error si el cuerpo es un sobre de error.

    Una respuesta buena trae Cantidad, FechaCreacion, Version y Listado. Una
    mala trae Codigo y Mensaje. No se adivina por el codigo HTTP: se mira el
    cuerpo.
    """
    try:
        datos = json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        return None  # HTML, por ejemplo la ficha web: no aplica
    if isinstance(datos, dict) and "Mensaje" in datos and "Listado" not in datos:
        return f"{datos.get('Codigo')}: {datos['Mensaje']}"
    return None


def _clave(url: str, params: dict[str, Any] | None) -> str:
    """Hash estable de la petición, para nombrar su archivo de caché.

    El ticket se excluye a propósito: es un secreto y además cambiaría la clave
    si algún día se renueva, invalidando una caché que sigue siendo válida.
    """
    limpios = {k: v for k, v in (params or {}).items() if k != "ticket"}
    crudo = url + "?" + "&".join(f"{k}={limpios[k]}" for k in sorted(limpios))
    return hashlib.sha256(crudo.encode()).hexdigest()[:24]


def _avisar_reintento(estado: RetryCallState) -> None:
    espera = getattr(estado.next_action, "sleep", 0.0)
    log.warning(
        "reintento %d tras fallo transitorio, esperando %.1fs",
        estado.attempt_number,
        espera,
    )


class Cliente:
    """Cliente HTTP con caché, throttling y tope de gasto."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or cargar()
        self.cache_dir = Path(self.config.http_cache_dir)
        self.emitidos = 0
        self.aciertos_cache = 0
        self._ultimo_request = 0.0
        self._http = httpx.Client(
            timeout=self.config.request_timeout_seconds,
            headers={"User-Agent": self.config.user_agent},
            follow_redirects=True,
        )

    def __enter__(self) -> Cliente:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        self._http.close()

    # -- caché --------------------------------------------------------------

    def _ruta(self, url: str, params: dict[str, Any] | None, sufijo: str) -> Path:
        return self.cache_dir / f"{_clave(url, params)}{sufijo}"

    # -- throttling ---------------------------------------------------------

    def _esperar_turno(self) -> None:
        """Respeta `REQUEST_DELAY_SECONDS` entre peticiones reales."""
        transcurrido = time.monotonic() - self._ultimo_request
        pendiente = self.config.request_delay_seconds - transcurrido
        if self._ultimo_request and pendiente > 0:
            time.sleep(pendiente)
        self._ultimo_request = time.monotonic()

    # -- petición -----------------------------------------------------------

    def obtener(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        sufijo: str = ".json",
    ) -> str:
        """Devuelve el cuerpo crudo, desde caché si existe.

        El crudo se escribe a disco ANTES de parsear: si el parseo falla, el
        dato ya está a salvo y se reprocesa sin volver a la fuente.
        """
        ruta = self._ruta(url, params, sufijo)
        if self.config.http_cache_enabled and ruta.exists():
            self.aciertos_cache += 1
            log.debug("caché: %s", ruta.name)
            return ruta.read_text(encoding="utf-8")

        cuerpo = self._pedir_con_reintentos(url, params)

        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(cuerpo, encoding="utf-8")
        return cuerpo

    def obtener_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        datos: dict[str, Any] = json.loads(self.obtener(url, params))
        return datos

    @retry(
        retry=retry_if_exception_type(RespuestaTransitoria),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=_avisar_reintento,
        reraise=True,
    )
    def _pedir_con_reintentos(self, url: str, params: dict[str, Any] | None) -> str:
        if self.emitidos >= self.config.max_requests_per_run:
            raise LimiteDeRequests(
                f"alcanzado MAX_REQUESTS_PER_RUN={self.config.max_requests_per_run}. "
                "Se aborta para no quemar el cupo diario del ticket."
            )

        self._esperar_turno()
        self.emitidos += 1
        respuesta = self._http.get(url, params=params)

        if respuesta.status_code in self.config.retry_http_codes:
            raise RespuestaTransitoria(
                f"HTTP {respuesta.status_code} en {url} — reintentable"
            )
        if respuesta.status_code >= 400:
            # Nada de except silencioso: se registra y se levanta.
            log.error("HTTP %d en %s — no se reintenta", respuesta.status_code, url)
            raise RespuestaDefinitiva(f"HTTP {respuesta.status_code} en {url}")

        # Un 2xx no garantiza un cuerpo util. Se revisa ANTES de cachear, para
        # no envenenar la cache con un mensaje de error.
        problema = _error_en_el_cuerpo(respuesta.text)
        if problema is not None:
            log.error(
                "la fuente respondio HTTP %d con un error en el cuerpo: %s",
                respuesta.status_code,
                problema,
            )
            raise ErrorDeLaFuente(
                f"{problema} (HTTP {respuesta.status_code}). "
                "Si dice 'Ticket no valido', renueva MP_API_TICKET en el .env."
            )

        return respuesta.text

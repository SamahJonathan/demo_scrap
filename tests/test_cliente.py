"""Criterios de aceptación del Incremento 1.

Ningún test toca la red: `respx` intercepta las peticiones de httpx.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from contratos.cliente import (
    Cliente,
    LimiteDeRequests,
    RespuestaDefinitiva,
    RespuestaTransitoria,
)
from contratos.config import Config

URL = "https://api.ejemplo.cl/ordenesdecompra.json"
CUERPO = {"Cantidad": 2, "Listado": [{"Codigo": "1002-183-SE25"}]}


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """Config aislada: caché en un directorio temporal y sin esperas."""
    return Config(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_ticket="ticket-de-prueba",
        http_cache_dir=tmp_path / "raw",
        request_delay_seconds=0.0,
        retry_backoff_base_seconds=0.0,
    )


@respx.mock
def test_escribe_el_crudo_en_disco_antes_de_parsear(config: Config) -> None:
    ruta = respx.get(URL).mock(return_value=httpx.Response(200, json=CUERPO))

    with Cliente(config) as c:
        datos = c.obtener_json(URL, {"fecha": "15052025"})

    assert datos["Cantidad"] == 2
    assert ruta.call_count == 1

    archivos = list(config.http_cache_dir.glob("*.json"))
    assert len(archivos) == 1, "el crudo debe quedar en disco"
    # Es el cuerpo tal como llegó, no una versión ya procesada.
    assert json.loads(archivos[0].read_text(encoding="utf-8")) == CUERPO


@respx.mock
def test_la_segunda_vez_sale_de_cache_y_no_emite_request(config: Config) -> None:
    ruta = respx.get(URL).mock(return_value=httpx.Response(200, json=CUERPO))

    with Cliente(config) as c:
        c.obtener_json(URL, {"fecha": "15052025"})
        c.obtener_json(URL, {"fecha": "15052025"})

        assert c.emitidos == 1, "el segundo pedido no debe salir a la red"
        assert c.aciertos_cache == 1

    assert ruta.call_count == 1


@respx.mock
def test_reintenta_los_transitorios_con_tope_de_tres(config: Config) -> None:
    ruta = respx.get(URL).mock(return_value=httpx.Response(503))

    with Cliente(config) as c, pytest.raises(RespuestaTransitoria):
        c.obtener(URL)

    assert ruta.call_count == 3, "tope de 3 intentos, ni más ni menos"


@respx.mock
def test_un_404_falla_de_inmediato_sin_reintentar(
    config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    ruta = respx.get(URL).mock(return_value=httpx.Response(404))

    with Cliente(config) as c, pytest.raises(RespuestaDefinitiva):
        c.obtener(URL)

    assert ruta.call_count == 1, "reintentar un 404 solo gasta cupo"
    # Nada de except silencioso: el fallo queda registrado.
    assert any("404" in r.getMessage() for r in caplog.records)


@respx.mock
def test_aborta_al_alcanzar_el_tope_de_requests(tmp_path: Path) -> None:
    config = Config(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_ticket="ticket-de-prueba",
        http_cache_dir=tmp_path / "raw",
        request_delay_seconds=0.0,
        max_requests_per_run=2,
    )
    respx.get(URL).mock(return_value=httpx.Response(200, json=CUERPO))

    with Cliente(config) as c:
        c.obtener(URL, {"n": 1})
        c.obtener(URL, {"n": 2})

        with pytest.raises(LimiteDeRequests) as e:
            c.obtener(URL, {"n": 3})

    assert "MAX_REQUESTS_PER_RUN" in str(e.value)


@respx.mock
def test_el_ticket_no_entra_en_la_clave_de_cache(config: Config) -> None:
    """Un ticket renovado no debe invalidar una caché que sigue siendo válida."""
    respx.get(URL).mock(return_value=httpx.Response(200, json=CUERPO))

    with Cliente(config) as c:
        c.obtener(URL, {"fecha": "15052025", "ticket": "viejo"})
        c.obtener(URL, {"fecha": "15052025", "ticket": "nuevo"})

        assert c.emitidos == 1
        assert c.aciertos_cache == 1


@respx.mock
def test_el_ticket_no_aparece_en_los_logs(
    config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    """httpx registra la URL completa en INFO, y el ticket viaja ahi.

    Una captura de pantalla en una entrevista, o un log en el servidor, dejaria
    el ticket personal a la vista.
    """
    import logging

    respx.get(URL).mock(return_value=httpx.Response(200, json=CUERPO))
    secreto = "TICKET-SECRETO-QUE-NO-DEBE-SALIR"

    with caplog.at_level(logging.DEBUG), Cliente(config) as c:
        c.obtener(URL, {"fecha": "15052025", "ticket": secreto})

    for r in caplog.records:
        assert secreto not in r.getMessage()

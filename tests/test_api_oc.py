"""Criterios de aceptación del Incremento 2.

La clasificación se prueba contra el listado REAL de un día completo, guardado en
`data/samples/`. Nada de datos inventados: los conteos son los que trae la
fuente.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from contratos.cliente import Cliente
from contratos.config import Config
from contratos.fuentes.api_oc import (
    OrdenResumen,
    clasificar,
    descubrir,
    listar,
    parsear_listado,
)

RAIZ = Path(__file__).resolve().parents[1]
MUESTRA = RAIZ / "data" / "samples" / "oc_listado_20250515.json"


@pytest.fixture(scope="module")
def listado_real() -> list[OrdenResumen]:
    datos = json.loads(MUESTRA.read_text(encoding="utf-8"))
    return parsear_listado(datos)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_ticket="ticket-de-prueba",
        http_cache_dir=tmp_path / "raw",
        request_delay_seconds=0.0,
    )


def test_el_listado_trae_codigo_nombre_y_estado(
    listado_real: list[OrdenResumen],
) -> None:
    assert len(listado_real) == 9206
    o = listado_real[0]
    assert o.codigo and o.nombre is not None and o.codigo_estado


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("1002-183-SE25", "SE"),
        ("1057492-1433-CC23", "CC"),
        ("1002-182-AG25", "AG"),
        ("1006-135-CM25", "CM"),
        ("1057049-947-TD25", "TD"),
        ("codigo-raro", ""),
    ],
)
def test_el_tipo_sale_del_sufijo_del_codigo(codigo: str, esperado: str) -> None:
    assert OrdenResumen(codigo=codigo, nombre="", codigo_estado=1).tipo == esperado


def test_clasifica_el_dia_completo_con_los_conteos_reales(
    listado_real: list[OrdenResumen], config: Config
) -> None:
    """Los números son los medidos contra la fuente, no inventados."""
    c = clasificar(listado_real, config)

    assert len(c.con_proceso) == 4047, "SE (3968) + CC (79)"
    assert len(c.sin_proceso) == 5159, "AG 3473 + CM 1021 + TD 664 + CT 1"
    assert len(c.otros) == 0, "los 6 tipos del dia quedan clasificados"
    assert c.total == 9206
    # El 56% no nace de una licitación. No es un descarte: es el hallazgo.
    assert len(c.sin_proceso) / c.total == pytest.approx(0.56, abs=0.01)


def test_clasificar_no_emite_ningun_request(
    listado_real: list[OrdenResumen], config: Config
) -> None:
    """Clasificar es texto: el sufijo del código basta."""
    with respx.mock:
        ruta = respx.get(url__regex=r".*").mock(return_value=httpx.Response(500))
        clasificar(listado_real, config)
        assert ruta.call_count == 0


def test_un_tipo_desconocido_se_aparta_y_no_se_adivina(config: Config) -> None:
    ordenes = [
        OrdenResumen(codigo="1-1-SE25", nombre="", codigo_estado=12),
        OrdenResumen(codigo="1-2-XX25", nombre="", codigo_estado=12),
    ]
    c = clasificar(ordenes, config)
    assert len(c.con_proceso) == 1
    assert len(c.otros) == 1, "un tipo nuevo no se mete a la fuerza en un grupo"


@respx.mock
def test_descubrir_respeta_los_limites_de_ambos_grupos(config: Config) -> None:
    datos = json.loads(MUESTRA.read_text(encoding="utf-8"))
    respx.get(url__regex=r".*ordenesdecompra.*").mock(
        return_value=httpx.Response(200, json=datos)
    )

    with Cliente(config) as c:
        r = descubrir(c, __import__("datetime").date(2025, 5, 15), 100, 50)
        assert len(r.con_proceso) == 100
        assert len(r.sin_proceso) == 50
        assert c.emitidos == 1, "un solo request para todo el dia"


@respx.mock
def test_listar_pide_la_fecha_en_el_formato_de_la_api(config: Config) -> None:
    """La API espera ddmmaaaa, no ISO."""
    ruta = respx.get(url__regex=r".*ordenesdecompra.*").mock(
        return_value=httpx.Response(200, json={"Listado": []})
    )
    with Cliente(config) as c:
        listar(c, __import__("datetime").date(2025, 5, 15))

    assert ruta.calls[0].request.url.params["fecha"] == "15052025"

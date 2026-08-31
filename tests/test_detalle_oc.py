"""Criterios de aceptación del Incremento 3.

Las fixtures son respuestas reales de la API, guardadas tal como llegaron: una
orden con licitación, una sin ella, y una cancelada con monto distinto de cero.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from contratos.cliente import Cliente
from contratos.config import Config
from contratos.fuentes.api_oc import detallar, detalle
from contratos.modelos import EstadoNoConocido, EstadoOC, OrdenCompra

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _crudo(nombre: str) -> dict[str, Any]:
    datos = json.loads((FIXTURES / f"oc_{nombre}.json").read_text(encoding="utf-8"))
    listado: list[dict[str, Any]] = datos["Listado"]
    return listado[0]


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_ticket="ticket-de-prueba",
        http_cache_dir=tmp_path / "raw",
        request_delay_seconds=0.0,
    )


def test_el_detalle_trae_los_campos_del_contrato() -> None:
    o = OrdenCompra.desde_api(_crudo("se_con_licitacion"))

    assert o.codigo == "1002772-10006-SE25"
    assert o.monto_total == Decimal("975800.0")
    assert o.organismo and o.organismo_rut
    assert o.proveedor and o.proveedor_rut
    assert o.fecha_envio is not None


def test_una_orden_se_trae_su_licitacion() -> None:
    o = OrdenCompra.desde_api(_crudo("se_con_licitacion"))
    assert o.codigo_licitacion == "1002772-78-LR24"
    assert o.tiene_proceso is True


def test_una_orden_ag_sin_licitacion_es_valida_no_un_error() -> None:
    """El 56% de las órdenes no nace de una licitación. Es un caso válido."""
    o = OrdenCompra.desde_api(_crudo("ag_sin_licitacion"))

    assert o.codigo_licitacion is None, "la API manda cadena vacía, no null"
    assert o.tiene_proceso is False
    assert o.monto_total > 0, "sigue siendo un contrato con dinero real"


def test_una_cancelada_se_ingesta_pero_no_cuenta_como_gasto() -> None:
    """Medida en la fuente: $1.346.366. Sumarla al gasto lo inflaría."""
    o = OrdenCompra.desde_api(_crudo("se_cancelada"))

    assert o.codigo_estado is EstadoOC.CANCELADA
    assert o.monto_total == Decimal("1346366.0")
    assert o.es_comprometido is False
    assert o.es_ejecutado is False


@pytest.mark.parametrize(
    ("estado", "comprometido", "ejecutado"),
    [
        (EstadoOC.RECEPCION_CONFORME, True, True),
        (EstadoOC.ACEPTADA, True, True),
        (EstadoOC.ENVIADA_A_PROVEEDOR, True, False),
        (EstadoOC.EN_PROCESO, True, False),
        (EstadoOC.CANCELADA, False, False),
    ],
)
def test_comprometido_y_ejecutado_son_cosas_distintas(
    estado: EstadoOC, comprometido: bool, ejecutado: bool
) -> None:
    """La brecha son las órdenes cuyo destino todavía no se sabe."""
    o = OrdenCompra(codigo="1-1-SE25", codigo_estado=estado)
    assert o.es_comprometido is comprometido
    assert o.es_ejecutado is ejecutado


def test_un_estado_desconocido_no_se_adivina() -> None:
    crudo = dict(_crudo("se_con_licitacion"))
    crudo["CodigoEstado"] = 99

    with pytest.raises(EstadoNoConocido) as e:
        OrdenCompra.desde_api(crudo)

    assert "99" in str(e.value)
    assert "cuarentena" in str(e.value)


@respx.mock
def test_detallar_aparta_las_malas_y_sigue_con_las_buenas(config: Config) -> None:
    """Un registro que no valida no puede abortar la corrida."""
    buena = {"Listado": [_crudo("se_con_licitacion")]}
    mala_crudo = dict(_crudo("ag_sin_licitacion"))
    mala_crudo["CodigoEstado"] = 99
    mala = {"Listado": [mala_crudo]}

    respx.get(url__regex=r".*codigo=BUENA.*").mock(
        return_value=httpx.Response(200, json=buena)
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, json=mala))

    with Cliente(config) as c:
        lote = detallar(c, ["BUENA", "MALA"])

    assert len(lote.ordenes) == 1
    assert len(lote.cuarentena) == 1
    assert lote.cuarentena[0][0] == "MALA"


@respx.mock
def test_el_lote_cuenta_cuantas_quedaron_sin_licitacion(config: Config) -> None:
    respx.get(url__regex=r".*").mock(
        return_value=httpx.Response(
            200, json={"Listado": [_crudo("ag_sin_licitacion")]}
        )
    )
    with Cliente(config) as c:
        lote = detallar(c, ["A", "B"])

    assert lote.sin_licitacion == 2


@respx.mock
def test_una_respuesta_sin_listado_falla_con_mensaje_claro(config: Config) -> None:
    respx.get(url__regex=r".*").mock(
        return_value=httpx.Response(200, json={"Cantidad": 0, "Listado": []})
    )
    with Cliente(config) as c, pytest.raises(ValueError, match="no trae Listado"):
        detalle(c, "1002-1-SE25")

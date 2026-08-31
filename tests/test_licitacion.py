"""Criterios de aceptación del Incremento 5.

Acá se cierra el circuito: la licitación entrega el token de la ficha, y la ficha
alimenta al parser de garantías del incremento 4.
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
from contratos.fuentes.api_licitacion import (
    SinFicha,
    bajar_ficha,
    detalle,
    url_ficha,
)
from contratos.fuentes.ficha_web import parsear_garantias
from contratos.fuentes.ocds import consultar
from contratos.modelos import Licitacion, UnidadDuracion, decodificar_unidad

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(  # type: ignore[call-arg]
        _env_file=None,
        mp_api_ticket="ticket-de-prueba",
        http_cache_dir=tmp_path / "raw",
        request_delay_seconds=0.0,
    )


def test_el_detalle_trae_duracion_renovacion_y_fechas() -> None:
    lic = _lic("2678-1-LR25")

    assert lic.duracion_valor == 10
    assert lic.duracion_unidad is UnidadDuracion.MESES
    assert lic.es_renovable is False
    # Ambas fechas son necesarias para la pregunta de negocio 3.
    assert lic.fecha_publicacion is not None
    assert lic.fecha_adjudicacion is not None
    assert lic.fecha_publicacion < lic.fecha_adjudicacion


@pytest.mark.parametrize(
    ("codigo", "unidad"),
    [
        ("2678-1-LR25", UnidadDuracion.MESES),
        ("2328-443-LR24", UnidadDuracion.MESES),
        # SENAMA declara 36 HORAS para un contrato de aseo. El dato es corrupto
        # y el modelo lo conserva tal cual: corregirlo escondería el problema.
        ("1300-43-LP24", UnidadDuracion.HORAS),
    ],
)
def test_la_unidad_de_duracion_se_decodifica(
    codigo: str, unidad: UnidadDuracion
) -> None:
    assert _lic(codigo).duracion_unidad is unidad


@pytest.mark.parametrize("valor", [0, 2, 3, 7, 99, None, "", "x"])
def test_una_unidad_no_decodificada_no_se_adivina(valor: object) -> None:
    """Solo 1 y 4 están confirmados. El resto no se supone."""
    assert decodificar_unidad(valor) is UnidadDuracion.DESCONOCIDO


def test_el_monto_se_atribuye_por_rut_sin_prorratear() -> None:
    """El reparto real va de $19M a $167M. Por partes iguales daría $88,3M."""
    lic = _lic("2678-1-LR25")

    ruts = {i.proveedor_rut for i in lic.items if i.proveedor_rut}
    assert len(ruts) == 5, "la adjudicación se repartió entre cinco proveedores"

    mayor = lic.monto_adjudicado_a("76.036.979-9")
    assert mayor == Decimal("167000000.00")
    assert lic.monto_adjudicado_por_items == Decimal("441600000.00")


def test_un_rut_que_no_participo_no_recibe_monto() -> None:
    assert _lic("2678-1-LR25").monto_adjudicado_a("11.111.111-1") is None


@respx.mock
def test_ocds_cuadra_con_la_suma_de_items_y_no_gasta_cupo(config: Config) -> None:
    """Dos fuentes independientes que coinciden: de ahí sale la regla cruzada."""
    datos = json.loads((FIXTURES / "ocds_2678-1-LR25.json").read_text(encoding="utf-8"))
    ruta = respx.get(url__regex=r".*/OCDS/.*").mock(
        return_value=httpx.Response(200, json=datos)
    )

    with Cliente(config) as c:
        o = consultar(c, "2678-1-LR25")

    assert o.monto_adjudicado == Decimal("441600000.0")
    assert o.monto_estimado == Decimal("522500000.0")
    assert o.n_oferentes == 6
    assert o.monto_adjudicado == _lic("2678-1-LR25").monto_adjudicado_por_items
    # Sin ticket: la URL de OCDS no lo lleva.
    assert "ticket" not in str(ruta.calls[0].request.url)


def test_la_url_de_la_ficha_sale_del_token_que_entrega_la_api() -> None:
    """No hay ingeniería inversa: UrlActa ya trae el token cifrado."""
    u = url_ficha(_lic("2678-1-LR25"), "https://www.mercadopublico.cl")

    assert "DetailsAcquisition.aspx?qs=" in u
    assert "%2F" in u or "%2B" in u or "%3D" in u, "el token va escapado"


def test_una_licitacion_sin_url_acta_falla_con_mensaje_claro() -> None:
    lic = Licitacion(codigo="1-1-LP25")
    with pytest.raises(SinFicha, match="no trae UrlActa"):
        url_ficha(lic, "https://www.mercadopublico.cl")


@respx.mock
def test_se_cierra_el_circuito_ficha_a_garantias(config: Config) -> None:
    """La ficha bajada acá alimenta al parser del incremento 4."""
    html = (FIXTURES / "ficha_2678-1-LR25.html").read_text(
        encoding="utf-8", errors="replace"
    )
    respx.get(url__regex=r".*DetailsAcquisition.*").mock(
        return_value=httpx.Response(200, text=html)
    )

    with Cliente(config) as c:
        bajado = bajar_ficha(c, _lic("2678-1-LR25"))

    garantias = parsear_garantias(bajado, "2678-1-LR25")
    assert len(garantias) == 2
    assert garantias[0].monto_valor == Decimal("1500000")


@respx.mock
def test_una_respuesta_sin_listado_falla_con_mensaje_claro(config: Config) -> None:
    respx.get(url__regex=r".*licitaciones.*").mock(
        return_value=httpx.Response(200, json={"Cantidad": 0, "Listado": []})
    )
    with Cliente(config) as c, pytest.raises(ValueError, match="no trae Listado"):
        detalle(c, "1-1-LP25")

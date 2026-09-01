"""Criterios de aceptación del Incremento 7 — el núcleo del proyecto.

Acá aparece la entidad que la fuente no publica y que da nombre al proyecto.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from contratos.fuentes.ficha_web import parsear_garantias
from contratos.modelos import (
    EstadoOC,
    EstadoVencimiento,
    Licitacion,
    OrdenCompra,
    UnidadDuracion,
)
from contratos.reconstruccion import (
    Procedencia,
    calcular_vencimiento,
    reconstruir,
    reconstruir_cartera,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _oc(nombre: str) -> OrdenCompra:
    datos = json.loads((FIXTURES / f"oc_{nombre}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return OrdenCompra.desde_api(crudo)


def _orden(codigo: str, licitacion: str | None, rut: str = "") -> OrdenCompra:
    return OrdenCompra(
        codigo=codigo,
        codigo_licitacion=licitacion,
        codigo_estado=EstadoOC.RECEPCION_CONFORME,
        proveedor_rut=rut,
        monto_total=Decimal(1000),
    )


# --------------------------------------------------------------------------
# Los tres casos dificiles del diseno
# --------------------------------------------------------------------------


def test_una_oc_con_licitacion_se_enriquece_con_su_proceso() -> None:
    lic = _lic("2678-1-LR25")
    orden = _orden("1-1-SE25", lic.codigo, rut="76.036.979-9")

    c = reconstruir(orden, lic)

    assert c.tiene_proceso is True
    assert c.codigo_licitacion == "2678-1-LR25"
    assert c.estado_vencimiento is EstadoVencimiento.CALCULADO
    assert c.fecha_termino_estimada is not None


def test_una_oc_huerfana_es_un_contrato_valido() -> None:
    """El 56% de las órdenes no nace de una licitación. No es un error."""
    c = reconstruir(_oc("ag_sin_licitacion"), None)

    assert c.tiene_proceso is False
    assert c.codigo_licitacion is None
    assert c.monto_ejecutado > 0, "sigue siendo dinero real que se movió"
    # Una compra puntual no tiene vigencia: no se le inventa un vencimiento.
    assert c.fecha_termino_estimada is None
    assert c.estado_vencimiento is EstadoVencimiento.NO_DECLARADO
    # Su anclaje temporal es la fecha de la propia orden.
    assert c.fecha_aceptacion is not None


def test_varias_ordenes_comparten_una_sola_licitacion() -> None:
    """Cinco órdenes de la misma licitación no replican sus garantías."""
    lic = _lic("2678-1-LR25")
    garantias = parsear_garantias(
        (FIXTURES / "ficha_2678-1-LR25.html").read_text(
            encoding="utf-8", errors="replace"
        ),
        lic.codigo,
    )
    ordenes = [_orden(f"1-{i}-SE25", lic.codigo) for i in range(5)]

    cartera = reconstruir_cartera(ordenes, {lic.codigo: lic}, {lic.codigo: garantias})

    assert len(cartera.contratos) == 5, "cinco contratos distintos"
    assert len(cartera.licitaciones) == 1, "una sola licitación"
    # Si se replicaran por contrato, contar garantías daría 10.
    assert cartera.total_garantias == 2


def test_una_cartera_mezcla_contratos_con_y_sin_proceso() -> None:
    lic = _lic("2678-1-LR25")
    ordenes = [_orden("1-1-SE25", lic.codigo), _orden("1-2-AG25", None)]

    cartera = reconstruir_cartera(ordenes, {lic.codigo: lic})

    assert len(cartera.contratos) == 2
    assert cartera.sin_proceso == 1
    assert len(cartera.licitaciones) == 1


# --------------------------------------------------------------------------
# Atribucion exacta del monto
# --------------------------------------------------------------------------


def test_el_monto_adjudicado_es_el_del_proveedor_no_el_total() -> None:
    """Prorratear está prohibido: la fuente da el dato exacto por RUT."""
    lic = _lic("2678-1-LR25")

    mayor = reconstruir(_orden("1-1-SE25", lic.codigo, "76.036.979-9"), lic)
    menor = reconstruir(_orden("1-2-SE25", lic.codigo, "10.200.595-3"), lic)

    assert mayor.monto_adjudicado == Decimal("167000000.00")
    assert menor.monto_adjudicado == Decimal("19000000.00")
    # El total de la licitación NO se le asigna a ninguno de los dos.
    assert mayor.monto_adjudicado != lic.monto_adjudicado_por_items


def test_un_proveedor_que_no_gano_no_recibe_monto() -> None:
    lic = _lic("2678-1-LR25")
    c = reconstruir(_orden("1-1-SE25", lic.codigo, "11.111.111-1"), lic)
    assert c.monto_adjudicado is None


# --------------------------------------------------------------------------
# Estado de vencimiento: por que falta, no solo que falta
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("2678-1-LR25", EstadoVencimiento.CALCULADO),
        ("1300-43-LP24", EstadoVencimiento.CALCULADO),
        ("2328-443-LR24", EstadoVencimiento.CALCULADO),
    ],
)
def test_las_tres_licitaciones_calculan_su_vencimiento(
    codigo: str, esperado: EstadoVencimiento
) -> None:
    _, estado = calcular_vencimiento(_lic(codigo))
    assert estado is esperado


def test_una_unidad_sin_decodificar_es_deuda_nuestra_no_de_la_fuente() -> None:
    lic = Licitacion(
        codigo="1-1-LP25",
        fecha_adjudicacion=date(2025, 1, 1),
        duracion_valor=12,
        duracion_unidad=UnidadDuracion.DESCONOCIDO,
    )
    fin, estado = calcular_vencimiento(lic)

    assert fin is None
    # Distinto de NO_DECLARADO: acá sí hay plazo, no sabemos leerlo.
    assert estado is EstadoVencimiento.UNIDAD_DESCONOCIDA


def test_senama_calcula_36_horas_tal_como_lo_dice_la_fuente() -> None:
    """El dato es implausible y el modelo NO lo corrige.

    Marcarlo es trabajo de la validación; reconstruir es trabajo de fidelidad.
    """
    lic = _lic("1300-43-LP24")
    fin, estado = calcular_vencimiento(lic)

    assert estado is EstadoVencimiento.CALCULADO
    assert lic.fecha_adjudicacion == date(2025, 3, 10)
    # 36 horas son dia y medio: el contrato de aseo "terminaria" al dia
    # siguiente de adjudicarse. Absurdo, y el modelo lo reproduce fielmente.
    # Marcarlo es trabajo de validacion.py, no de aca.
    assert fin == date(2025, 3, 11)


# --------------------------------------------------------------------------
# Procedencia
# --------------------------------------------------------------------------


def test_cada_campo_declara_su_procedencia() -> None:
    """Sin procedencia el dato no es defendible."""
    lic = _lic("2678-1-LR25")
    c = reconstruir(_orden("1-1-SE25", lic.codigo, "76.036.979-9"), lic)

    assert c.procedencias["monto_ejecutado"] is Procedencia.API_OC
    assert c.procedencias["monto_adjudicado"] is Procedencia.API_LICITACION
    assert c.procedencias["fecha_termino_estimada"] is Procedencia.DERIVADO

    campos = {f for f in vars(c) if f != "procedencias"}
    assert campos <= set(c.procedencias), "ningún campo sin procedencia declarada"


def test_una_licitacion_que_no_corresponde_falla() -> None:
    otra = _lic("2328-443-LR24")
    with pytest.raises(ValueError, match="apunta a"):
        reconstruir(_orden("1-1-SE25", "2678-1-LR25"), otra)


def test_una_licitacion_que_no_se_pudo_obtener_no_pierde_el_contrato(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El contrato se guarda igual, sin los datos del proceso."""
    cartera = reconstruir_cartera([_orden("1-1-SE25", "2678-1-LR25")], {})

    assert len(cartera.contratos) == 1
    assert cartera.contratos[0].codigo_licitacion == "2678-1-LR25"
    assert cartera.contratos[0].estado_vencimiento is EstadoVencimiento.NO_DECLARADO
    assert any("no se pudo obtener" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------
# Duracion cero: el fallo que publicaba vencimientos falsos como confiables
# --------------------------------------------------------------------------


def test_duracion_cero_no_produce_un_vencimiento() -> None:
    """Un contrato de duración cero no existe: el campo quedó sin llenar.

    Antes de esta guarda, `0 horas` daba `termino = adjudicacion` y se marcaba
    CALCULADO. Veinte contratos publicaban que terminaron el mismo día que se
    adjudicaron, con la misma etiqueta de confianza que un vencimiento real.
    """
    lic = Licitacion(
        codigo="1-1-LP25",
        fecha_adjudicacion=date(2025, 3, 10),
        duracion_valor=0,
        duracion_unidad=UnidadDuracion.HORAS,
    )
    fin, estado = calcular_vencimiento(lic)

    assert fin is None, "no se inventa una fecha desde un campo vacío"
    assert estado is EstadoVencimiento.DURACION_CERO
    assert estado is not EstadoVencimiento.CALCULADO


def test_duracion_cero_se_distingue_de_no_haber_declarado_nada() -> None:
    """Son dos cosas: la modalidad no declara plazo, o el campo quedó en 0."""
    sin_nada = Licitacion(codigo="1-1-LP25", fecha_adjudicacion=date(2025, 3, 10))
    _, estado = calcular_vencimiento(sin_nada)
    assert estado is EstadoVencimiento.NO_DECLARADO


def test_una_duracion_real_sigue_calculandose() -> None:
    """La guarda no puede haber roto el caso normal."""
    lic = Licitacion(
        codigo="1-1-LP25",
        fecha_adjudicacion=date(2025, 3, 10),
        duracion_valor=10,
        duracion_unidad=UnidadDuracion.MESES,
    )
    fin, estado = calcular_vencimiento(lic)

    assert fin == date(2025, 3, 10) + timedelta(days=300)
    assert estado is EstadoVencimiento.CALCULADO


def test_licitacion_es_inmutable_y_por_eso_se_copia() -> None:
    """Asignarle un campo lanza ValidationError, no lo asigna en silencio.

    Costó las 299 garantías de una corrida: `lic.url_ficha = ...` reventaba
    dentro del try de la ficha y se llevaba el parseo entero. La forma correcta
    es `model_copy`, y este test deja constancia de por qué.
    """
    lic = Licitacion(codigo="1-1-LP25")

    with pytest.raises(Exception, match="[Ff]rozen"):
        lic.url_ficha = "https://ejemplo"  # type: ignore[misc]

    copia = lic.model_copy(update={"url_ficha": "https://ejemplo"})
    assert copia.url_ficha == "https://ejemplo"
    assert lic.url_ficha is None, "el original no se toca"

"""Criterios de aceptación del Incremento 12.

Lo que se prueba es el **veredicto**: cuándo una corrida es confiable y cuándo
no. Un pipeline que siempre dice "listo" obliga a revisar la base a ojo.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from contratos.fuentes.ficha_web import parsear_garantias
from contratos.metricas import Metricas
from contratos.modelos import Licitacion
from contratos.validacion import Motivo, revisar_garantias

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _garantias(codigo: str) -> list[Any]:
    html = (FIXTURES / f"ficha_{codigo}.html").read_text(
        encoding="utf-8", errors="replace"
    )
    return parsear_garantias(html, codigo)


# --------------------------------------------------------------------------
# El reporte responde tres preguntas sin salir de la consola
# --------------------------------------------------------------------------


def test_el_reporte_dice_cuanto_costo_y_que_se_perdio() -> None:
    m = Metricas(requests_emitidos=44, aciertos_cache=3, procesados=20)
    m.suma("licitaciones", 7)
    m.suma("garantias", 9)
    m.cuarentena("1-1-SE25", Motivo.ESQUEMA, "estado 99")
    m.cerrar()

    texto = m.reporte()

    assert "44" in texto, "requests emitidos"
    assert "esquema_invalido" in texto, "la cuarentena dice por qué"
    assert "licitaciones" in texto and "garantias" in texto


def test_una_fuente_caida_se_reporta_sin_invalidar_la_corrida() -> None:
    """Una ficha sin tabla de garantías es normal, no una corrida rota."""
    m = Metricas(procesados=20)
    m.suma("licitaciones", 7)
    m.suma("garantias", 9)
    m.falla("ficha_web", "1002772-87-LE24: no se encontró la tabla")
    m.cerrar()

    assert "FUENTES CAÍDAS" in m.reporte()
    assert m.problemas(max_cuarentena=0.05, min_registros=1) == []


def test_si_casi_ninguna_ficha_rinde_garantias_la_corrida_no_es_confiable() -> None:
    """Ahí no hay fichas raras: hay un parser roto."""
    m = Metricas(procesados=20)
    m.suma("licitaciones", 10)
    m.suma("garantias", 1)
    m.cerrar()

    problemas = m.problemas(max_cuarentena=0.05, min_registros=1)
    assert len(problemas) == 1
    assert "parser de la ficha" in problemas[0]


# --------------------------------------------------------------------------
# Codigo de salida: permite encadenar la corrida sin revisarla a ojo
# --------------------------------------------------------------------------


def test_una_corrida_sana_sale_con_cero() -> None:
    m = Metricas(procesados=20)
    m.suma("licitaciones", 7)
    m.suma("garantias", 9)
    m.cerrar()

    assert m.codigo_salida(max_cuarentena=0.05, min_registros=1) == 0
    assert "corrida confiable" in m.reporte()


def test_demasiada_cuarentena_sale_con_uno() -> None:
    m = Metricas(procesados=100)
    for i in range(12):
        m.cuarentena(str(i), Motivo.ESQUEMA, "")
    m.cerrar()

    assert m.codigo_salida(max_cuarentena=0.05, min_registros=1) == 1
    assert "parser roto" in m.reporte()


def test_pocos_registros_delatan_un_descubrimiento_fallido() -> None:
    m = Metricas(procesados=3)
    m.cerrar()

    problemas = m.problemas(max_cuarentena=0.05, min_registros=50)
    assert any("falló en silencio" in p for p in problemas)
    assert "NO CONFIABLE" in m.reporte(0.05, min_registros=50)


def test_una_corrida_vacia_no_divide_por_cero() -> None:
    m = Metricas()
    m.cerrar()
    assert m.tasa_cuarentena == 0.0
    assert m.ahorro_cache == 0.0
    assert m.reporte()


# --------------------------------------------------------------------------
# La regla de garantias reporta MAGNITUD, no solo un si/no
# --------------------------------------------------------------------------


def test_el_hallazgo_dice_cuantas_veces_excede_el_plazo() -> None:
    """SENAMA excede su plazo unas mil veces: eso es absurdo, no discutible.

    Una caución 15 meses más larga que un contrato de 24 puede ser legítima.
    La regla señala la magnitud; quien mira decide.
    """
    lic = _lic("1300-43-LP24")
    h = revisar_garantias(lic, _garantias("1300-43-LP24"))[0]

    assert "dias_de_exceso" in h.valores
    assert "veces_la_duracion" in h.valores
    assert float(h.valores["veces_la_duracion"]) > 100, "36 horas contra 3 años"
    assert "podría estar mal cargado" in h.detalle, "señala, no acusa"


def test_un_contrato_coherente_no_genera_hallazgo() -> None:
    lic = _lic("2678-1-LR25")
    assert revisar_garantias(lic, _garantias("2678-1-LR25")) == []


def test_el_caso_real_encontrado_en_produccion_se_reporta_con_su_escala() -> None:
    """1004-56-LP24: 24 meses de contrato, garantía 451 días después.

    Es 1,6 veces el plazo. Muy distinto de SENAMA, y por eso la magnitud va en
    el hallazgo en vez de tratar ambos casos como iguales.
    """
    lic = Licitacion(
        codigo="1004-56-LP24",
        fecha_adjudicacion=date(2024, 12, 9),
        duracion_valor=24,
        duracion_unidad=_lic("2678-1-LR25").duracion_unidad,  # meses
    )
    from contratos.modelos import Garantia, TipoGarantia

    g = Garantia(
        licitacion_codigo=lic.codigo,
        tipo=TipoGarantia.FIEL_CUMPLIMIENTO,
        fecha_vencimiento=date(2028, 3, 5),
        fragmento_origen="grvGarantias_ctl02",
    )
    h = revisar_garantias(lic, [g])[0]

    veces = float(h.valores["veces_la_duracion"])
    assert 1.5 < veces < 2.0, "orden de magnitud muy distinto al de SENAMA"


@pytest.mark.parametrize("cobertura", [(10, 9), (10, 5)])
def test_la_cobertura_aceptable_no_marca_problema(cobertura: tuple[int, int]) -> None:
    licitaciones, garantias = cobertura
    m = Metricas(procesados=20)
    m.suma("licitaciones", licitaciones)
    m.suma("garantias", garantias)
    assert m.problemas(max_cuarentena=0.05, min_registros=1) == []

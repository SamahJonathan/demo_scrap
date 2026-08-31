"""Criterios de aceptación del Incremento 4 — el punto frágil del diseño.

**Cero requests.** Todo contra HTML real guardado. El riesgo de este incremento
está en el parseo, no en la descarga, así que se prueba aislado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contratos.fuentes.ficha_web import (
    FichaIlegible,
    cobertura_suficiente,
    parsear_garantias,
)
from contratos.modelos import TipoGarantia

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _html(codigo: str) -> str:
    return (FIXTURES / f"ficha_{codigo}.html").read_text(
        encoding="utf-8", errors="replace"
    )


def test_mostazal_trae_exactamente_las_dos_garantias_medidas() -> None:
    """Los valores son los de la ficha real, verificados a mano en el spike."""
    gs = parsear_garantias(_html("2678-1-LR25"), "2678-1-LR25")

    assert len(gs) == 2

    seriedad, fiel = gs
    assert seriedad.tipo is TipoGarantia.SERIEDAD_OFERTA
    assert seriedad.monto_valor == Decimal("1500000")
    assert seriedad.monto_es_porcentaje is False
    assert seriedad.fecha_vencimiento == date(2025, 4, 24)

    assert fiel.tipo is TipoGarantia.FIEL_CUMPLIMIENTO
    assert fiel.monto_valor == Decimal("5")
    assert fiel.monto_es_porcentaje is True, "5 % no es $5"
    assert fiel.fecha_vencimiento == date(2026, 3, 2)


@pytest.mark.parametrize(
    ("codigo", "monto_seriedad", "pct_fiel", "vence_fiel"),
    [
        ("2678-1-LR25", Decimal("1500000"), Decimal("5"), date(2026, 3, 2)),
        ("1300-43-LP24", Decimal("500000"), Decimal("10"), date(2027, 12, 29)),
        ("2328-443-LR24", Decimal("2500000"), Decimal("5"), date(2027, 4, 29)),
    ],
)
def test_las_tres_fichas_parsean_igual(
    codigo: str, monto_seriedad: Decimal, pct_fiel: Decimal, vence_fiel: date
) -> None:
    gs = parsear_garantias(_html(codigo), codigo)
    assert len(gs) == 2
    assert gs[0].monto_valor == monto_seriedad
    assert gs[1].monto_valor == pct_fiel
    assert gs[1].monto_es_porcentaje is True
    assert gs[1].fecha_vencimiento == vence_fiel


def test_toda_garantia_declara_su_origen() -> None:
    """Sin trazabilidad el dato no es defendible."""
    for g in parsear_garantias(_html("2678-1-LR25"), "2678-1-LR25"):
        assert g.fragmento_origen.startswith("grvGarantias_ctl")
        assert g.licitacion_codigo == "2678-1-LR25"


def test_un_html_sin_la_tabla_falla_ruidosamente() -> None:
    """No tiene garantías y no pudimos leerlas son cosas distintas.

    Confundirlas es lo que deja pasar una corrida con cero garantías sin que
    nadie lo note.
    """
    with pytest.raises(FichaIlegible) as e:
        parsear_garantias("<html><body>otra pagina</body></html>", "1-1-LP25")

    assert "grvGarantias" in str(e.value)
    assert "NO significa" in str(e.value)


def test_una_tabla_vacia_devuelve_lista_vacia_sin_error() -> None:
    """Acá sí: la tabla está, la licitación simplemente no exige garantías."""
    html = '<html><body><table id="grvGarantias"></table></body></html>'
    assert parsear_garantias(html, "1-1-LP25") == []


def test_un_titulo_desconocido_no_se_fuerza_a_un_tipo_conocido() -> None:
    html = (
        '<html><body><table id="grvGarantias">'
        '<tr><td id="grvGarantias_ctl02_lblFicha8TituloTipoGarantia">Caucion rara</td>'
        '<td id="grvGarantias_ctl02_lblFicha8Monto">100</td></tr>'
        "</table></body></html>"
    )
    g = parsear_garantias(html, "1-1-LP25")[0]

    assert g.tipo is TipoGarantia.OTRA
    assert g.titulo_original == "Caucion rara", "el texto original se conserva"


def test_el_umbral_de_cobertura_hace_fallar_una_corrida_vacia() -> None:
    """Un cero silencioso es el modo de falla peligroso del punto frágil."""
    assert cobertura_suficiente(con_garantias=95, con_ficha=100, minimo=0.90) is True
    assert cobertura_suficiente(con_garantias=50, con_ficha=100, minimo=0.90) is False
    # Sin fichas no hay nada que exigir: no se divide por cero ni se falla.
    assert cobertura_suficiente(con_garantias=0, con_ficha=0, minimo=0.90) is True

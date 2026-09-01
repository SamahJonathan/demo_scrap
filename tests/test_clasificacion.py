"""Criterios de la clasificación de causales contra el piso legal.

Lo que se prueba no es que agrupe, sino que **el ruido no tape lo excepcional**:
las causales que la ley impone a todos no pueden competir en pantalla con la
que hace que un contrato termine antes de su fecha.
"""

from __future__ import annotations

from contratos.clasificacion import Riesgo, clasificar, es_estandar

# Literales de fichas reales: aparecen palabra por palabra en licitaciones de
# organismos distintos, y por eso son el piso y no la excepción.
PISO = [
    "a) La muerte o incapacidad sobreviniente de la persona natural, o la "
    "extinción de la personalidad jurídica de la sociedad contratista.",
    "b) La resciliación o mutuo acuerdo entre las partes.",
    "c) El incumplimiento grave de las obligaciones contraídas por el proveedor.",
    "d) El estado de notoria insolvencia del contratista.",
]


def test_las_causales_que_la_ley_impone_se_reconocen() -> None:
    for causal in PISO:
        assert es_estandar(causal), causal[:50]


def test_la_letra_de_enumeracion_no_cambia_el_resultado() -> None:
    """Un organismo escribe `c)` y otro no. Es la misma causal."""
    assert es_estandar("El incumplimiento grave de las obligaciones contraídas")
    assert es_estandar("c) El incumplimiento grave de las obligaciones contraídas")


def test_las_tildes_tampoco() -> None:
    assert es_estandar("El estado de notoria insolvencia")
    assert es_estandar("d) El estado de notoria insolvencía del contratista")


def test_solo_el_piso_legal_no_produce_nada_que_reportar() -> None:
    """Repetir en cada contrato lo que la ley ya obliga es ruido."""
    riesgo, extra = clasificar(PISO)

    assert riesgo is Riesgo.ESTANDAR
    assert extra == [], "no se publica lo que es igual en todos"


def test_lo_que_agrega_el_organismo_se_separa() -> None:
    """Caso real de 1004-56-LP24."""
    riesgo, extra = clasificar(
        [*PISO, "Registrar saldos insolutos de remuneraciones o cotizaciones"]
    )

    assert riesgo is Riesgo.ADICIONALES
    assert len(extra) == 1
    assert "saldos insolutos" in extra[0]


def test_un_disparador_cuantificado_es_otra_categoria() -> None:
    """Caso real del MOP en 1002-25-LE25, y es el hallazgo que importa.

    El contrato puede terminar antes de su fecha declarada **por alcanzar un
    monto**, no por incumplir. Su vencimiento publicado puede no ser el real.
    """
    riesgo, extra = clasificar(
        [
            *PISO,
            "Si se alcanzare el monto de 2.000 UTM autorizado antes del "
            "término del periodo de vigencia del mismo.",
        ]
    )

    assert riesgo is Riesgo.DISPARADOR_CUANTIFICADO
    assert "2.000 UTM" in extra[0]


def test_un_disparador_manda_sobre_los_demas_adicionales() -> None:
    """Con varias adicionales, la cuantificada define la categoría."""
    riesgo, extra = clasificar(
        [
            *PISO,
            "No actuaren éticamente durante la ejecución del contrato",
            "Si se agotare el presupuesto autorizado",
        ]
    )

    assert riesgo is Riesgo.DISPARADOR_CUANTIFICADO
    assert len(extra) == 2


def test_sin_causales_no_hay_riesgo_que_declarar() -> None:
    assert clasificar([]) == (Riesgo.ESTANDAR, [])

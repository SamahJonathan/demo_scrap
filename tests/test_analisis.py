"""Criterios de aceptación del Incremento 9.

Cada consulta se prueba contra una base poblada con los casos reales que la
originaron: SENAMA para la garantía implausible, y órdenes con y sin proceso
para la proporción del gasto.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from contratos.analisis import PREGUNTAS, responder, responder_todas
from contratos.fuentes.ficha_web import parsear_garantias
from contratos.modelos import EstadoOC, Licitacion, OrdenCompra
from contratos.persistencia import guardar
from contratos.reconstruccion import reconstruir_cartera

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HOY = date(2025, 6, 1)


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _garantias(codigo: str) -> list[Any]:
    html = (FIXTURES / f"ficha_{codigo}.html").read_text(
        encoding="utf-8", errors="replace"
    )
    return parsear_garantias(html, codigo)


def _orden(
    codigo: str,
    licitacion: str | None = None,
    estado: EstadoOC = EstadoOC.RECEPCION_CONFORME,
    monto: int = 1000,
    organismo: str = "MUNICIPALIDAD DE PRUEBA",
    rut_prov: str = "76.036.979-9",
) -> OrdenCompra:
    return OrdenCompra(
        codigo=codigo,
        codigo_licitacion=licitacion,
        codigo_estado=estado,
        organismo=organismo,
        organismo_rut="60.000.000-0",
        proveedor_rut=rut_prov,
        monto_total=Decimal(monto),
    )


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """Base con las tres licitaciones reales y órdenes con y sin proceso."""
    ruta = tmp_path / "contratos.db"
    codigos = ("2678-1-LR25", "1300-43-LP24", "2328-443-LR24")
    licitaciones = {c: _lic(c) for c in codigos}
    garantias = {c: _garantias(c) for c in licitaciones}

    ordenes = [
        _orden("1-1-SE25", "2678-1-LR25", organismo="MOSTAZAL", monto=5000),
        _orden("1-2-SE25", "2678-1-LR25", organismo="MOSTAZAL", monto=3000),
        _orden("2-1-SE25", "1300-43-LP24", organismo="SENAMA", monto=2000),
        _orden("3-1-SE25", "2328-443-LR24", organismo="PUERTO MONTT", monto=9000),
        # Sin proceso: compra ágil y trato directo.
        _orden("4-1-AG25", None, organismo="MOSTAZAL", monto=700),
        _orden("4-2-TD25", None, organismo="SENAMA", monto=300),
        # Cancelada con monto: no debe entrar en ninguna suma.
        _orden("5-1-SE25", None, estado=EstadoOC.CANCELADA, monto=999999),
    ]
    guardar(ruta, reconstruir_cartera(ordenes, licitaciones, garantias))
    return ruta


def test_las_ocho_preguntas_se_ejecutan(base: Path) -> None:
    """Cinco responden al gestor, la 6 y la 7 dicen si se puede confiar, y la
    8 nació de la vista por área: Comercial pregunta con quién se repite."""
    resultados = responder_todas(base, hoy=HOY)
    assert set(resultados) == {1, 2, 3, 4, 5, 6, 7, 8}

    for numero in (1, 2, 3, 4, 5, 6):
        assert resultados[numero], f"la pregunta {numero} no devolvió filas"

    # La 7 vacía es una respuesta válida: no hay contradicciones detectadas.
    assert resultados[7] == []
    # La 8 también: en esta muestra ningún par comprador-proveedor se repite.
    assert isinstance(resultados[8], list)


# --------------------------------------------------------------------------
# P1 — vencimientos
# --------------------------------------------------------------------------


def test_p1_ordena_por_vencimiento_y_dice_que_hacer(base: Path) -> None:
    filas = responder(base, PREGUNTAS[0], hoy=HOY, meses=36)

    fechas = [f["fecha_termino_estimada"] for f in filas]
    assert fechas == sorted(fechas), "lo que vence antes va primero"
    # Lo accionable: la decisión que el gestor tiene que tomar.
    assert all(f["accion"] in ("renovar", "relicitar") for f in filas)
    assert all(f["dias_restantes"] >= 0 for f in filas)


def test_p1_excluye_los_contratos_sin_vigencia(base: Path) -> None:
    """Una compra ágil es puntual: no tiene vencimiento que vigilar."""
    filas = responder(base, PREGUNTAS[0], hoy=HOY, meses=36)
    codigos = {f["codigo_oc"] for f in filas}
    assert "4-1-AG25" not in codigos
    assert "4-2-TD25" not in codigos


# --------------------------------------------------------------------------
# P2 — garantias
# --------------------------------------------------------------------------


def test_p2_cuenta_las_garantias_una_vez_por_licitacion(base: Path) -> None:
    """Mostazal tiene DOS órdenes y DOS garantías, no cuatro."""
    filas = responder(base, PREGUNTAS[1], hoy=HOY)

    de_mostazal = [f for f in filas if f["licitacion_codigo"] == "2678-1-LR25"]
    assert len(de_mostazal) == 2


def test_p2_marca_senama_como_implausible(base: Path) -> None:
    """36 horas de contrato con garantía hasta 2027: la consulta lo detecta."""
    filas = responder(base, PREGUNTAS[1], hoy=HOY)

    implausibles = [f for f in filas if f["implausible"] == 1]
    assert len(implausibles) == 1
    assert implausibles[0]["licitacion_codigo"] == "1300-43-LP24"
    assert implausibles[0]["duracion_unidad"] == "horas"
    # Lo implausible va primero: es lo que hay que mirar.
    assert filas[0]["implausible"] == 1


# --------------------------------------------------------------------------
# P3 — plazos por organismo
# --------------------------------------------------------------------------


def test_p3_devuelve_percentiles_no_promedio(base: Path) -> None:
    """Se midieron 45, 115 y 215 días: con esa dispersión el promedio miente."""
    filas = responder(base, PREGUNTAS[2], hoy=HOY)

    assert filas
    for f in filas:
        assert {"p25", "mediana", "p75", "maximo"} <= set(f)
        assert f["p25"] <= f["mediana"] <= f["p75"]

    # Los tres valores reales medidos en la Fase 1.
    medianas = {f["organismo"]: f["mediana"] for f in filas}
    assert medianas["MOSTAZAL"] == 45
    assert medianas["PUERTO MONTT"] == 115
    assert medianas["SENAMA"] == 215


def test_p3_no_cuenta_dos_veces_una_licitacion_con_varias_ordenes(
    base: Path,
) -> None:
    """Mostazal tiene dos órdenes de la misma licitación: es UN proceso."""
    filas = responder(base, PREGUNTAS[2], hoy=HOY)
    mostazal = next(f for f in filas if f["organismo"] == "MOSTAZAL")
    assert mostazal["procesos"] == 1


# --------------------------------------------------------------------------
# P4 y P5 — montos
# --------------------------------------------------------------------------


def test_p4_distingue_comprometido_de_ejecutado(base: Path) -> None:
    filas = responder(base, PREGUNTAS[3], hoy=HOY)
    for f in filas:
        assert f["ejecutado"] <= f["comprometido"]


def test_p4_no_suma_la_cancelada(base: Path) -> None:
    """La cancelada trae $999.999 y no debe aparecer en ninguna métrica."""
    filas = responder(base, PREGUNTAS[3], hoy=HOY)
    total = sum(f["comprometido"] for f in filas)
    assert total == 5000 + 3000 + 2000 + 9000 + 700 + 300


def test_p5_compara_gasto_con_proceso_contra_sin_proceso(base: Path) -> None:
    """El 56% de las órdenes no nace de una licitación: es el hallazgo."""
    filas = responder(base, PREGUNTAS[4], hoy=HOY)

    por_origen = {f["origen"]: f for f in filas}
    assert set(por_origen) == {"con proceso", "sin proceso"}
    assert por_origen["con proceso"]["ejecutado"] == 19000
    assert por_origen["sin proceso"]["ejecutado"] == 1000
    assert sum(f["pct_contratos"] for f in filas) == pytest.approx(100.0, abs=0.2)


def test_las_consultas_viven_en_archivos_sql_legibles() -> None:
    """Se pueden abrir con cualquier cliente, sin ejecutar el proyecto."""
    for p in PREGUNTAS:
        sql = p.sql
        assert sql.lstrip().startswith("--"), "cada consulta explica qué responde"
        assert "SELECT" in sql


# --------------------------------------------------------------------------
# P6 y P7 — las que permiten confiar en las demas
# --------------------------------------------------------------------------


def test_p6_dice_sobre_que_universo_hablan_las_otras_paginas(base: Path) -> None:
    """La fixture tiene 4 contratos con proceso, 2 sin proceso y 1 cancelada.

    Los tres sin licitación no tienen vigencia: no aparecen en vencimientos, y
    la página debe decirlo en vez de omitirlos.
    """
    filas = responder(base, PREGUNTAS[5], hoy=HOY)

    por_estado = {f["estado_vencimiento"]: f for f in filas}
    assert por_estado["calculado"]["contratos"] == 4
    assert por_estado["no_declarado"]["contratos"] == 3
    assert sum(f["pct"] for f in filas) == pytest.approx(100.0, abs=0.2)
    # Cada estado explica su causa, no es un código suelto.
    assert all(f["explicacion"] for f in filas)


def test_p6_los_porcentajes_suman_el_total_de_la_cartera(base: Path) -> None:
    filas = responder(base, PREGUNTAS[5], hoy=HOY)
    assert sum(f["contratos"] for f in filas) == 7


def test_p7_sin_discrepancias_no_inventa_filas(base: Path) -> None:
    """La tabla existe desde el incremento 8 pero la puebla el 13."""
    assert responder(base, PREGUNTAS[6], hoy=HOY) == []


def test_p7_reporta_ambos_valores_y_cuantos_contratos_afecta(base: Path) -> None:
    """El caso de SENAMA: la sección 7 dice 36 horas, la prosa dice 36 meses."""
    from contratos.persistencia import abrir

    with abrir(base) as con:
        con.execute(
            "INSERT INTO discrepancia (licitacion_codigo, campo, "
            "valor_estructurado, valor_prosa, regla) VALUES (?,?,?,?,?)",
            ("1300-43-LP24", "duracion", "36 horas", "36 meses", "prosa vs campo"),
        )

    filas = responder(base, PREGUNTAS[6], hoy=HOY)

    assert len(filas) == 1
    d = filas[0]
    # Ninguno de los dos gana por defecto: se conservan ambos.
    assert d["valor_estructurado"] == "36 horas"
    assert d["valor_prosa"] == "36 meses"
    # Y dice cuánto daño hace: cuántos contratos dependen de ese plazo.
    assert d["contratos_afectados"] == 1


def test_una_garantia_porcentual_se_traduce_a_pesos_con_su_base(base: Path) -> None:
    """Una obligación declarativa no es exigible hasta que es un número.

    El 5% se calcula sobre el monto adjudicado, y la BASE viaja con el
    resultado: sin ella el número sería una afirmación nuestra en vez de una
    operación que cualquiera puede rehacer.
    """
    from contratos.persistencia import abrir

    with abrir(base) as con:
        con.execute(
            "UPDATE licitacion SET monto_adjudicado_total = '100000000', "
            "monto_es_unitario = 0 WHERE codigo = ?",
            ("2678-1-LR25",),
        )
        con.execute(
            "UPDATE garantia SET monto_es_porcentaje = 1, monto_valor = '5' "
            "WHERE licitacion_codigo = ?",
            ("2678-1-LR25",),
        )

    filas = [
        f
        for f in responder(base, PREGUNTAS[1], hoy=HOY)
        if f["licitacion_codigo"] == "2678-1-LR25"
    ]
    assert filas
    assert filas[0]["monto_pesos"] == 5_000_000
    assert filas[0]["base_calculo"] == 100_000_000


def test_un_monto_marcado_como_unitario_NO_se_traduce(base: Path) -> None:
    """Un convenio de suministro daría una boleta de centavos.

    Es la guarda que hace segura la traducción: sin ella publicaríamos una
    caución de $39 sobre un contrato de mil quinientos millones.
    """
    from contratos.persistencia import abrir

    with abrir(base) as con:
        con.execute(
            "UPDATE licitacion SET monto_adjudicado_total = '783', "
            "monto_es_unitario = 1 WHERE codigo = ?",
            ("2678-1-LR25",),
        )
        con.execute(
            "UPDATE garantia SET monto_es_porcentaje = 1, monto_valor = '5' "
            "WHERE licitacion_codigo = ?",
            ("2678-1-LR25",),
        )

    filas = [
        f
        for f in responder(base, PREGUNTAS[1], hoy=HOY)
        if f["licitacion_codigo"] == "2678-1-LR25"
    ]
    assert filas
    assert filas[0]["monto_pesos"] is None, "no se inventa una cifra sobre un unitario"

"""Criterios de aceptación del Incremento 8.

Lo que se prueba de verdad acá es la **idempotencia**: reprocesar tiene que ser
seguro, o corregir un parser costaría empezar de cero.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from contratos.fuentes.ficha_web import parsear_garantias
from contratos.modelos import EstadoOC, Licitacion, OrdenCompra
from contratos.persistencia import (
    abrir,
    contar,
    guardar,
    monto_ejecutado_total,
)
from contratos.reconstruccion import reconstruir_cartera

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


def _orden(
    codigo: str,
    licitacion: str | None = None,
    estado: EstadoOC = EstadoOC.RECEPCION_CONFORME,
    monto: int = 1000,
) -> OrdenCompra:
    return OrdenCompra(
        codigo=codigo,
        codigo_licitacion=licitacion,
        codigo_estado=estado,
        proveedor_rut="76.036.979-9",
        monto_total=Decimal(monto),
    )


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path / "contratos.db"


# --------------------------------------------------------------------------
# Idempotencia
# --------------------------------------------------------------------------


def test_persistir_dos_veces_no_duplica(base: Path) -> None:
    """Upsert por clave natural, no insert. Reprocesar debe ser seguro."""
    lic = _lic("2678-1-LR25")
    ordenes = [_orden(f"1-{i}-SE25", lic.codigo) for i in range(150)]
    cartera = reconstruir_cartera(ordenes, {lic.codigo: lic})

    primera = guardar(base, cartera)
    assert primera["contrato"] == 150

    segunda = guardar(base, cartera)
    assert segunda["contrato"] == 150, "la segunda corrida no duplica"
    assert segunda["licitacion"] == 1


def test_las_garantias_no_se_duplican_al_reprocesar(base: Path) -> None:
    lic = _lic("2678-1-LR25")
    cartera = reconstruir_cartera(
        [_orden("1-1-SE25", lic.codigo)],
        {lic.codigo: lic},
        {lic.codigo: _garantias("2678-1-LR25")},
    )

    assert guardar(base, cartera)["garantia"] == 2
    assert guardar(base, cartera)["garantia"] == 2, "dos, no cuatro"


def test_un_valor_corregido_se_actualiza_en_vez_de_insertarse(base: Path) -> None:
    """Si se corrige el parseo y se reprocesa, la base queda consistente."""
    lic = _lic("2678-1-LR25")
    catalogo = {lic.codigo: lic}
    for monto in (100, 999):
        orden = _orden("1-1-SE25", lic.codigo, monto=monto)
        guardar(base, reconstruir_cartera([orden], catalogo))

    with abrir(base) as con:
        filas = con.execute("SELECT monto_ejecutado FROM contrato").fetchall()

    assert len(filas) == 1
    assert filas[0][0] == "999"


# --------------------------------------------------------------------------
# El esquema
# --------------------------------------------------------------------------


def test_el_esquema_crea_las_cinco_tablas_desde_el_principio(base: Path) -> None:
    """Las dos últimas quedan vacías hasta el incremento 13, pero existen."""
    conteo = contar(base)
    assert set(conteo) == {
        "contrato",
        "licitacion",
        "garantia",
        "clausula_extraida",
        "discrepancia",
    }
    assert conteo["clausula_extraida"] == 0
    assert conteo["discrepancia"] == 0


def test_una_oc_huerfana_se_persiste_con_licitacion_nula(base: Path) -> None:
    """El 56% la tiene nula: la clave foránea es anulable a propósito."""
    cartera = reconstruir_cartera([_orden("1-1-AG25", None)], {})
    assert guardar(base, cartera)["contrato"] == 1

    with abrir(base) as con:
        fila = con.execute(
            "SELECT codigo_licitacion FROM contrato WHERE codigo_oc = ?", ("1-1-AG25",)
        ).fetchone()
    assert fila[0] is None


def test_la_clave_foranea_rechaza_una_licitacion_inexistente(base: Path) -> None:
    """Anulable no es lo mismo que sin integridad."""
    with abrir(base) as con, pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO contrato (codigo_oc, codigo_licitacion) VALUES (?, ?)",
            ("1-1-SE25", "no-existe"),
        )


def test_el_archivo_se_consulta_con_sqlite_sin_conversion(base: Path) -> None:
    """El mismo archivo que se explora en local se despliega al servidor."""
    lic = _lic("2678-1-LR25")
    guardar(
        base,
        reconstruir_cartera([_orden("1-1-SE25", lic.codigo)], {lic.codigo: lic}),
    )

    con = sqlite3.connect(base)
    try:
        fila = con.execute(
            "SELECT c.codigo_oc, l.duracion_valor, l.duracion_unidad "
            "FROM contrato c JOIN licitacion l ON l.codigo = c.codigo_licitacion"
        ).fetchone()
    finally:
        con.close()

    assert fila == ("1-1-SE25", 10, "meses")


# --------------------------------------------------------------------------
# Los montos no pierden precision ni suman canceladas
# --------------------------------------------------------------------------


def test_los_montos_no_pierden_precision(base: Path) -> None:
    """Van como TEXT: SQLite no tiene DECIMAL y REAL introduce error."""
    orden = OrdenCompra(
        codigo="1-1-SE25",
        codigo_estado=EstadoOC.RECEPCION_CONFORME,
        monto_total=Decimal("783.193"),
    )
    guardar(base, reconstruir_cartera([orden], {}))

    with abrir(base) as con:
        valor = con.execute("SELECT monto_ejecutado FROM contrato").fetchone()[0]
    assert Decimal(valor) == Decimal("783.193")


def test_la_suma_no_incluye_las_canceladas(base: Path) -> None:
    """Se midió una cancelada de $1.346.366: sumarla inflaría el gasto."""
    cartera = reconstruir_cartera(
        [
            _orden("1-1-SE25", monto=1000),
            _orden("1-2-SE25", estado=EstadoOC.CANCELADA, monto=1346366),
            _orden("1-3-SE25", estado=EstadoOC.ENVIADA_A_PROVEEDOR, monto=500),
        ],
        {},
    )
    guardar(base, cartera)

    ejecutado = monto_ejecutado_total(base, solo_ejecutado=True)
    comprometido = monto_ejecutado_total(base, solo_ejecutado=False)

    assert ejecutado == Decimal(1000), "solo la conforme"
    assert comprometido == Decimal(1500), "conforme + enviada, nunca la cancelada"


def test_garantias_sin_su_licitacion_se_omiten_con_aviso(
    base: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No se revienta: se avisa y la corrida sigue."""
    cartera = reconstruir_cartera([_orden("1-1-AG25", None)], {})
    cartera.garantias = {"no-existe": _garantias("2678-1-LR25")}

    assert guardar(base, cartera)["garantia"] == 0
    assert any("sin su licitación" in r.getMessage() for r in caplog.records)


def test_una_base_vieja_recibe_las_columnas_nuevas(tmp_path: Path) -> None:
    """`CREATE TABLE IF NOT EXISTS` no agrega columnas a una tabla que ya existe.

    Sin la migración, una base creada antes de `url_ficha` reventaría con
    "no such column" en el primer INSERT — y eso pasa en el servidor, no acá.
    """
    import sqlite3

    ruta = tmp_path / "vieja.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE licitacion ("
        "codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL DEFAULT '', "
        "fecha_publicacion TEXT, fecha_adjudicacion TEXT, duracion_valor INTEGER, "
        "duracion_unidad TEXT NOT NULL DEFAULT 'desconocido', "
        "es_renovable INTEGER NOT NULL DEFAULT 0, "
        "monto_adjudicado_total TEXT, n_oferentes INTEGER)"
    )
    con.commit()
    con.close()

    with abrir(ruta) as c:
        columnas = {f[1] for f in c.execute("PRAGMA table_info(licitacion)")}

    assert "url_ficha" in columnas


def test_migrar_dos_veces_no_falla(tmp_path: Path) -> None:
    """Es idempotente: el pipeline abre la base en cada corrida."""
    ruta = tmp_path / "c.db"
    with abrir(ruta):
        pass
    with abrir(ruta) as c:  # no debe reventar con "duplicate column"
        assert "url_ficha" in {f[1] for f in c.execute("PRAGMA table_info(licitacion)")}

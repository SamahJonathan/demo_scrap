"""Persistencia en SQLite, idempotente.

El mismo archivo se explora con SQL durante el desarrollo y se despliega al
servidor sin conversión. Un artefacto, dos usos.

**Re-ejecutar una corrida no duplica nada.** Upsert por clave natural, no
insert. Reprocesar tiene que ser seguro: si el parseo de garantías se corrige,
se corre de nuevo sobre la caché y la base queda consistente.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from contratos.modelos import Garantia, Licitacion
from contratos.reconstruccion import Cartera, Contrato

log = logging.getLogger(__name__)

ESQUEMA = Path(__file__).parent / "esquema.sql"


def _texto(valor: object) -> str | None:
    """Los montos van como TEXT: SQLite no tiene DECIMAL y REAL pierde pesos."""
    return None if valor is None else str(valor)


@contextmanager
def abrir(ruta: Path) -> Iterator[sqlite3.Connection]:
    """Abre la base, creando el esquema si hace falta."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(ESQUEMA.read_text(encoding="utf-8"))
        yield con
        con.commit()
    finally:
        con.close()


def guardar_licitacion(con: sqlite3.Connection, lic: Licitacion) -> None:
    con.execute(
        """
        INSERT INTO licitacion (codigo, nombre, fecha_publicacion,
            fecha_adjudicacion, duracion_valor, duracion_unidad, es_renovable,
            monto_adjudicado_total, n_oferentes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(codigo) DO UPDATE SET
            nombre = excluded.nombre,
            fecha_publicacion = excluded.fecha_publicacion,
            fecha_adjudicacion = excluded.fecha_adjudicacion,
            duracion_valor = excluded.duracion_valor,
            duracion_unidad = excluded.duracion_unidad,
            es_renovable = excluded.es_renovable,
            monto_adjudicado_total = excluded.monto_adjudicado_total,
            n_oferentes = excluded.n_oferentes
        """,
        (
            lic.codigo,
            lic.nombre,
            _texto(lic.fecha_publicacion),
            _texto(lic.fecha_adjudicacion),
            lic.duracion_valor,
            lic.duracion_unidad.value,
            int(lic.es_renovable),
            _texto(lic.monto_adjudicado_total),
            lic.n_oferentes,
        ),
    )


def guardar_contrato(con: sqlite3.Connection, c: Contrato) -> None:
    con.execute(
        """
        INSERT INTO contrato (codigo_oc, codigo_licitacion, organismo,
            organismo_rut, proveedor, proveedor_rut, monto_ejecutado,
            monto_adjudicado, es_comprometido, es_ejecutado, estado,
            fecha_aceptacion, fecha_termino_estimada, estado_vencimiento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(codigo_oc) DO UPDATE SET
            codigo_licitacion = excluded.codigo_licitacion,
            organismo = excluded.organismo,
            organismo_rut = excluded.organismo_rut,
            proveedor = excluded.proveedor,
            proveedor_rut = excluded.proveedor_rut,
            monto_ejecutado = excluded.monto_ejecutado,
            monto_adjudicado = excluded.monto_adjudicado,
            es_comprometido = excluded.es_comprometido,
            es_ejecutado = excluded.es_ejecutado,
            estado = excluded.estado,
            fecha_aceptacion = excluded.fecha_aceptacion,
            fecha_termino_estimada = excluded.fecha_termino_estimada,
            estado_vencimiento = excluded.estado_vencimiento
        """,
        (
            c.codigo_oc,
            c.codigo_licitacion,
            c.organismo,
            c.organismo_rut,
            c.proveedor,
            c.proveedor_rut,
            _texto(c.monto_ejecutado),
            _texto(c.monto_adjudicado),
            int(c.es_comprometido),
            int(c.es_ejecutado),
            c.estado,
            _texto(c.fecha_aceptacion),
            _texto(c.fecha_termino_estimada),
            c.estado_vencimiento.value,
        ),
    )


def guardar_garantia(con: sqlite3.Connection, g: Garantia) -> None:
    con.execute(
        """
        INSERT INTO garantia (licitacion_codigo, tipo, titulo_original,
            monto_valor, monto_es_porcentaje, moneda, fecha_vencimiento,
            beneficiario, fragmento_origen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(licitacion_codigo, tipo, fragmento_origen) DO UPDATE SET
            titulo_original = excluded.titulo_original,
            monto_valor = excluded.monto_valor,
            monto_es_porcentaje = excluded.monto_es_porcentaje,
            moneda = excluded.moneda,
            fecha_vencimiento = excluded.fecha_vencimiento,
            beneficiario = excluded.beneficiario
        """,
        (
            g.licitacion_codigo,
            g.tipo.value,
            g.titulo_original,
            _texto(g.monto_valor),
            int(g.monto_es_porcentaje),
            g.moneda,
            _texto(g.fecha_vencimiento),
            g.beneficiario,
            g.fragmento_origen,
        ),
    )


def guardar(ruta: Path, cartera: Cartera) -> dict[str, int]:
    """Persiste una cartera completa. Re-ejecutar no duplica.

    Las licitaciones van primero: la clave foránea de contrato las necesita.
    """
    with abrir(ruta) as con:
        for lic in cartera.licitaciones.values():
            guardar_licitacion(con, lic)

        for codigo, garantias in cartera.garantias.items():
            if codigo not in cartera.licitaciones:
                # La clave foránea la rechazaría; se avisa en vez de reventar.
                log.warning(
                    "garantías de %s sin su licitación en la cartera: se omiten",
                    codigo,
                )
                continue
            for g in garantias:
                guardar_garantia(con, g)

        for c in cartera.contratos:
            guardar_contrato(con, c)

    return contar(ruta)


def contar(ruta: Path) -> dict[str, int]:
    """Cuántas filas hay en cada tabla. Es el chequeo rápido de una corrida."""
    with abrir(ruta) as con:
        return {
            tabla: int(con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0])
            for tabla in (
                "contrato",
                "licitacion",
                "garantia",
                "clausula_extraida",
                "discrepancia",
            )
        }


def monto_ejecutado_total(ruta: Path, solo_ejecutado: bool = True) -> Decimal:
    """Suma de montos. **Filtra por estado**: las canceladas traen monto.

    Se midió una cancelada de $1.346.366: sumarla inflaría el gasto.
    """
    columna = "es_ejecutado" if solo_ejecutado else "es_comprometido"
    with abrir(ruta) as con:
        filas = con.execute(
            f"SELECT monto_ejecutado FROM contrato WHERE {columna} = 1"  # noqa: S608
        ).fetchall()
    return sum((Decimal(f[0]) for f in filas), Decimal(0))

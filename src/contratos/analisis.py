"""Las preguntas de negocio, respondidas con SQL.

Las consultas viven en `consultas/*.sql`, no incrustadas en Python. Así se
pueden abrir con cualquier cliente de SQLite, leer sin ejecutar el proyecto, y
mostrar en la entrevista como lo que son: la traducción directa de una pregunta
de negocio a una consulta.

Cada archivo empieza con la pregunta que responde y el porqué de sus filtros.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CONSULTAS = Path(__file__).parent / "consultas"


@dataclass(frozen=True)
class Pregunta:
    """Una pregunta de negocio y la consulta que la responde."""

    numero: int
    titulo: str
    archivo: str

    @property
    def sql(self) -> str:
        return (CONSULTAS / self.archivo).read_text(encoding="utf-8")


PREGUNTAS = (
    Pregunta(1, "Contratos que vencen: renovar o relicitar", "p1_vencimientos.sql"),
    Pregunta(2, "Garantías vigentes e incoherentes con el plazo", "p2_garantias.sql"),
    Pregunta(3, "Días entre publicar y adjudicar, por organismo", "p3_plazos.sql"),
    Pregunta(4, "Monto por organismo y proveedores", "p4_montos.sql"),
    Pregunta(5, "Gasto con proceso frente a gasto sin proceso", "p5_sin_proceso.sql"),
)


def _parametros(sql: str, hoy: date, meses: int) -> dict[str, Any]:
    """Solo pasa los parámetros que la consulta realmente nombra."""
    disponibles = {
        "hoy": hoy.isoformat(),
        "hasta": (hoy + timedelta(days=30 * meses)).isoformat(),
    }
    return {k: v for k, v in disponibles.items() if f":{k}" in sql}


def responder(
    ruta: Path, pregunta: Pregunta, hoy: date | None = None, meses: int = 12
) -> list[dict[str, Any]]:
    """Ejecuta una consulta y devuelve sus filas como diccionarios."""
    hoy = hoy or date.today()
    con = sqlite3.connect(ruta)
    try:
        con.row_factory = sqlite3.Row
        sql = pregunta.sql
        filas = con.execute(sql, _parametros(sql, hoy, meses)).fetchall()
    finally:
        con.close()
    return [dict(f) for f in filas]


def responder_todas(
    ruta: Path, hoy: date | None = None, meses: int = 12
) -> dict[int, list[dict[str, Any]]]:
    return {p.numero: responder(ruta, p, hoy, meses) for p in PREGUNTAS}

"""Dashboard de ciclo de vida contractual.

**Lee filas, nunca infiere.** La capa de inferencia corre en lote, offline, y
persiste sus resultados: un endpoint que invoque al modelo tardaría minutos y
reservaría 7,34 GB. Ver docs/02-diseno.md.

Sirve un `contratos.db` de solo lectura: el mismo archivo que se explora con SQL
en la máquina de desarrollo y se copia al servidor sin conversión.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from contratos.analisis import PREGUNTAS, responder
from contratos.config import cargar
from contratos.reconstruccion import PROCEDENCIAS

AQUI = Path(__file__).parent
PLANTILLAS = Jinja2Templates(directory=str(AQUI / "plantillas"))

# Cuántos contratos esperamos de una corrida completa: 150 OC × 3 fechas.
# El umbral no exige el total exacto porque la cuarentena puede descartar
# algunos legítimamente, pero sí detecta una corrida que trajo doce.
ESPERADOS = 450
MINIMO = 400


def ruta_base() -> Path:
    """SQLite en el servidor, por `DATABASE_URL`."""
    url = cargar().database_url
    return Path(url.removeprefix("sqlite:///"))


def _conectar(ruta: Path) -> sqlite3.Connection:
    if not ruta.exists():
        raise HTTPException(503, f"no existe la base {ruta}. Corre el pipeline.")
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def crear_app(base: Path | None = None) -> FastAPI:
    app = FastAPI(title="Contratos públicos", docs_url="/api")
    resolver: Callable[[], Path] = (lambda: base) if base is not None else ruta_base

    def _diagnostico() -> dict[str, Any]:
        """Los mismos datos para la maquina y para la persona."""
        ruta = resolver()
        con = _conectar(ruta)
        try:
            conteo = {
                t: int(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
                for t in (
                    "contrato",
                    "licitacion",
                    "garantia",
                    "discrepancia",
                    "clausula_extraida",
                )
            }
        finally:
            con.close()
        return {
            **conteo,
            "esperados": ESPERADOS,
            "minimo": MINIMO,
            # Un conteo muy bajo es una corrida a medias, no una base vacía.
            "suficiente": conteo["contrato"] >= MINIMO,
            "ultima_corrida": datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(
                timespec="seconds"
            ),
        }

    @app.get("/salud")
    def salud() -> dict[str, Any]:
        """Endpoint de maquina: lo consumen la monitorizacion y el despliegue.

        Se deja como JSON a proposito. La version para personas es /estado.
        """
        return _diagnostico()

    @app.get("/estado", response_class=HTMLResponse)
    def estado(request: Request) -> Any:
        """La misma informacion, legible. Va en el pie, no en el menu.

        Le sirve a quien mantiene el pipeline, no al gestor de contratos: no
        responde ninguna de las tres preguntas del objetivo.
        """
        return PLANTILLAS.TemplateResponse(
            request, "estado.html", {"d": _diagnostico()}
        )

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request) -> Any:
        ruta = resolver()
        con = _conectar(ruta)
        try:
            ind = con.execute(
                """
                SELECT
                    COUNT(*) AS contratos,
                    SUM(CASE WHEN codigo_licitacion IS NULL THEN 1 ELSE 0 END)
                        AS sin_proceso,
                    SUM(CASE WHEN es_ejecutado = 1
                             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END)
                        AS ejecutado,
                    SUM(CASE WHEN es_comprometido = 1
                             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END)
                        AS comprometido
                FROM contrato
                """
            ).fetchone()
            hoy = date.today()
            por_vencer = con.execute(
                "SELECT COUNT(*) FROM garantia WHERE fecha_vencimiento >= ? "
                "AND fecha_vencimiento <= ?",
                (hoy.isoformat(), (hoy + timedelta(days=180)).isoformat()),
            ).fetchone()[0]
        finally:
            con.close()

        implausibles = [
            f for f in responder(ruta, PREGUNTAS[1]) if f["implausible"] == 1
        ]
        return PLANTILLAS.TemplateResponse(
            request,
            "inicio.html",
            {
                "ind": dict(ind),
                "por_vencer": por_vencer,
                "implausibles": implausibles,
                "vencimientos": responder(ruta, PREGUNTAS[0], meses=12)[:10],
                # Sobre que universo habla la pagina, y si se puede confiar.
                "cobertura": responder(ruta, PREGUNTAS[5]),
                "discrepancias": responder(ruta, PREGUNTAS[6]),
            },
        )

    @app.get("/vencimientos", response_class=HTMLResponse)
    def vencimientos(request: Request, meses: int = 12) -> Any:
        """Qué relicitar y qué renovar: dos de las tres preguntas del objetivo."""
        return PLANTILLAS.TemplateResponse(
            request,
            "vencimientos.html",
            {
                "filas": responder(resolver(), PREGUNTAS[0], meses=meses),
                "meses": meses,
            },
        )

    @app.get("/garantias", response_class=HTMLResponse)
    def garantias(request: Request) -> Any:
        """Qué cauciones siguen vivas: la tercera pregunta del objetivo."""
        filas = responder(resolver(), PREGUNTAS[1])
        return PLANTILLAS.TemplateResponse(
            request,
            "garantias.html",
            {
                "filas": filas,
                "implausibles": [f for f in filas if f["implausible"] == 1],
            },
        )

    @app.get("/plazos", response_class=HTMLResponse)
    def plazos(request: Request) -> Any:
        """Cuanto tarda cada organismo en adjudicar.

        Convierte el vencimiento en un plazo para actuar: un contrato que vence
        en 90 dias no da margen si el organismo tarda 215 en adjudicar.
        """
        return PLANTILLAS.TemplateResponse(
            request, "plazos.html", {"filas": responder(resolver(), PREGUNTAS[2])}
        )

    @app.get("/contratos", response_class=HTMLResponse)
    def listado(
        request: Request,
        organismo: str = Query("", description="filtro por nombre"),
        solo_con_proceso: bool = False,
    ) -> Any:
        con = _conectar(resolver())
        try:
            sql = "SELECT * FROM contrato WHERE organismo LIKE ?"
            params: list[Any] = [f"%{organismo}%"]
            if solo_con_proceso:
                sql += " AND codigo_licitacion IS NOT NULL"
            sql += " ORDER BY fecha_termino_estimada IS NULL, fecha_termino_estimada"
            filas = [dict(f) for f in con.execute(sql, params).fetchall()]
        finally:
            con.close()
        return PLANTILLAS.TemplateResponse(
            request,
            "listado.html",
            {
                "filas": filas,
                "organismo": organismo,
                "solo_con_proceso": solo_con_proceso,
            },
        )

    @app.get("/contratos/{codigo}", response_class=HTMLResponse)
    def detalle(request: Request, codigo: str) -> Any:
        con = _conectar(resolver())
        try:
            fila = con.execute(
                "SELECT * FROM contrato WHERE codigo_oc = ?", (codigo,)
            ).fetchone()
            if fila is None:
                raise HTTPException(404, f"no existe el contrato {codigo}")
            contrato = dict(fila)
            licitacion = None
            garantias: list[dict[str, Any]] = []
            clausulas: list[dict[str, Any]] = []
            if contrato["codigo_licitacion"]:
                lic = con.execute(
                    "SELECT * FROM licitacion WHERE codigo = ?",
                    (contrato["codigo_licitacion"],),
                ).fetchone()
                licitacion = dict(lic) if lic else None
                garantias = [
                    dict(g)
                    for g in con.execute(
                        "SELECT * FROM garantia WHERE licitacion_codigo = ?",
                        (contrato["codigo_licitacion"],),
                    ).fetchall()
                ]
                # Cuelgan de la licitacion igual que las garantias: varias
                # ordenes del mismo proceso comparten las mismas clausulas.
                clausulas = [
                    dict(cl)
                    for cl in con.execute(
                        "SELECT * FROM clausula_extraida WHERE licitacion_codigo = ?",
                        (contrato["codigo_licitacion"],),
                    ).fetchall()
                ]
        finally:
            con.close()

        return PLANTILLAS.TemplateResponse(
            request,
            "detalle.html",
            {
                "c": contrato,
                "licitacion": licitacion,
                "garantias": garantias,
                "clausulas": clausulas,
                # Sin procedencia el dato no es defendible: se muestra siempre.
                "procedencias": {k: v.value for k, v in PROCEDENCIAS.items()},
            },
        )

    return app


app = crear_app()

"""Export a un HTML autocontenido. **Es el respaldo de la demo.**

Un solo archivo con los datos embebidos, sin servidor, sin red y sin
dependencias externas: se abre con doble clic. Si el día de la entrevista algo
falla —la conexión, el servidor, el certificado— esto sigue funcionando.

No compite con el dashboard: lo respalda. El dashboard permite filtrar y
explorar; esto garantiza que haya algo que mostrar.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from contratos.analisis import PREGUNTAS, responder

CSS = """
:root{--tinta:#1a1a1a;--suave:#666;--linea:#e2e2e2;--alerta:#b02a2a;--ok:#1d6b3a}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;
     color:var(--tinta);background:#fafafa}
main{max-width:1100px;margin:0 auto;padding:24px}
h1{font-size:1.35rem;margin:0 0 4px}
h2{font-size:1.05rem;margin:28px 0 8px}
.sub{color:var(--suave);font-size:.9rem;margin:0 0 18px}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
          gap:12px;margin-bottom:22px}
.tarjeta{background:#fff;border:1px solid var(--linea);border-radius:6px;padding:14px}
.tarjeta b{display:block;font-size:1.5rem;font-weight:600}
.tarjeta span{color:var(--suave);font-size:.82rem}
table{width:100%;border-collapse:collapse;background:#fff;font-size:.86rem;
      margin-bottom:8px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--linea)}
th{color:var(--suave);font-weight:600;font-size:.76rem;text-transform:uppercase}
.alerta{color:var(--alerta);font-weight:600}
.pie{color:var(--suave);font-size:.8rem;margin-top:30px;
     border-top:1px solid var(--linea);padding-top:12px}
"""


def _tabla(filas: list[dict[str, Any]], limite: int = 40) -> str:
    if not filas:
        return '<p class="sub">Sin resultados.</p>'
    columnas = list(filas[0])
    cabecera = "".join(f"<th>{html.escape(c)}</th>" for c in columnas)
    cuerpo = []
    for f in filas[:limite]:
        # Lo implausible se destaca: es lo que hay que mirar primero.
        clase = ' class="alerta"' if f.get("implausible") == 1 else ""
        celdas = "".join(
            f"<td>{html.escape('' if f[c] is None else str(f[c]))}</td>"
            for c in columnas
        )
        cuerpo.append(f"<tr{clase}>{celdas}</tr>")
    extra = (
        f'<p class="sub">... {len(filas) - limite} filas más</p>'
        if len(filas) > limite
        else ""
    )
    return f"<table><tr>{cabecera}</tr>{''.join(cuerpo)}</table>{extra}"


def generar(base: Path, destino: Path, hoy: date | None = None) -> Path:
    """Escribe el HTML autocontenido y devuelve su ruta."""
    hoy = hoy or date.today()

    con = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        ind = dict(
            con.execute(
                """
                SELECT COUNT(*) AS contratos,
                       SUM(CASE WHEN codigo_licitacion IS NULL THEN 1 ELSE 0 END)
                           AS sin_proceso,
                       SUM(CASE WHEN es_ejecutado = 1
                                THEN CAST(monto_ejecutado AS REAL) ELSE 0 END)
                           AS ejecutado
                FROM contrato
                """
            ).fetchone()
        )
    finally:
        con.close()

    secciones = []
    for pregunta in PREGUNTAS:
        filas = responder(base, pregunta, hoy=hoy, meses=12)
        secciones.append(
            f"<h2>P{pregunta.numero}. {html.escape(pregunta.titulo)}</h2>"
            f"{_tabla(filas)}"
        )

    sello = f"{datetime.now():%Y-%m-%d %H:%M}"
    origen = html.escape(base.name)

    documento = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contratos públicos — {hoy}</title><style>{CSS}</style></head>
<body><main>
<h1>Ciclo de vida contractual</h1>
<p class="sub">Contratos reconstruidos desde Mercado Público. La fuente no los
publica como tales: se arman uniendo orden de compra, licitación, OCDS y
ficha web.</p>
<div class="tarjetas">
  <div class="tarjeta"><b>{ind["contratos"]}</b><span>contratos</span></div>
  <div class="tarjeta"><b>{ind["sin_proceso"] or 0}</b>
    <span>sin licitación previa</span></div>
  <div class="tarjeta"><b>${ind["ejecutado"] or 0:,.0f}</b><span>ejecutado</span></div>
</div>
{"".join(secciones)}
<p class="pie">Generado el {sello} desde {origen}.
Archivo autocontenido: no requiere servidor, red ni dependencias.</p>
</main></body></html>
"""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(documento, encoding="utf-8")
    return destino

"""Registro de corridas: qué pasó cada vez que se ejecutó el pipeline.

El reporte de `metricas.py` se imprime y se pierde. Este módulo lo **persiste**,
que es lo que permite responder la pregunta que una corrida sola no puede:
*¿esto viene empeorando?*

Un scraper no se rompe de golpe. La fuente cambia un `id`, la cobertura baja de
95% a 60%, y el pipeline sigue terminando en verde porque 60% pasa el umbral.
Comparar contra la corrida anterior es lo que delata esa caída lenta.

**Los registros van a archivos, no a una tabla de la base.** Una corrida que
falla y no escribe ni un contrato es justamente la que más hay que diagnosticar;
si su reporte viviera en la base, no dejaría rastro.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from contratos.metricas import Metricas

# Caída de registros que se considera sospechosa aunque la corrida pase el
# umbral. No es un numero teorico: por debajo de esto, la explicacion "hubo
# menos licitaciones ese dia" deja de ser plausible.
CAIDA_SOSPECHOSA = 0.20


def instantanea(
    m: Metricas, max_cuarentena: float, min_registros: int, fechas: list[str]
) -> dict[str, Any]:
    """Los números de una corrida, serializables.

    Incluye el veredicto y **sus motivos**: dentro de un mes, "NO CONFIABLE" sin
    la razón al lado no sirve para nada.
    """
    por_motivo: dict[str, int] = {}
    for _id, motivo, _detalle in m.cuarentenados:
        por_motivo[motivo.value] = por_motivo.get(motivo.value, 0) + 1

    problemas = m.problemas(max_cuarentena, min_registros)
    return {
        "momento": datetime.now().isoformat(timespec="seconds"),
        "fechas": fechas,
        "duracion_s": round(m.duracion, 1),
        "requests_emitidos": m.requests_emitidos,
        "aciertos_cache": m.aciertos_cache,
        "ahorro_cache": round(m.ahorro_cache, 3),
        "procesados": m.procesados,
        "por_fuente": dict(sorted(m.por_fuente.items())),
        "fuentes_fallidas": dict(sorted(m.fuentes_fallidas.items())),
        "cuarentena": len(m.cuarentenados),
        "tasa_cuarentena": round(m.tasa_cuarentena, 4),
        "cuarentena_por_motivo": dict(sorted(por_motivo.items())),
        "hallazgos": [
            {"identificador": h.identificador, "motivo": h.motivo.value}
            for h in m.hallazgos
        ],
        "confiable": not problemas,
        "problemas": problemas,
    }


def guardar(registro: dict[str, Any], directorio: Path) -> Path:
    """Escribe el registro con el momento en el nombre, para ordenar por fecha."""
    directorio.mkdir(parents=True, exist_ok=True)
    # Los dos puntos del ISO no son validos en un nombre de archivo en Windows.
    momento: str = registro["momento"]
    ruta = directorio / (momento.replace(":", "-") + ".json")
    ruta.write_text(
        json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return ruta


# Los registros de corrida se llaman por su marca de tiempo ISO. El glob se
# ata a ese formato y no a "*.json": el mismo directorio guarda el registro de
# inferencia, y leerlo como si fuera una corrida reventaba con KeyError.
_NOMBRE = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-*.json"


def historial(directorio: Path, limite: int = 10) -> list[dict[str, Any]]:
    """Las últimas corridas, de la más nueva a la más vieja."""
    if not directorio.is_dir():
        return []
    archivos = sorted(directorio.glob(_NOMBRE), reverse=True)[:limite]
    corridas = []
    for a in archivos:
        datos = json.loads(a.read_text(encoding="utf-8"))
        # Defensa en profundidad: un archivo que no tenga la forma de una
        # corrida se ignora en vez de tumbar el comando que lo lee.
        if "procesados" in datos:
            corridas.append(datos)
    return corridas


def regresiones(actual: dict[str, Any], anterior: dict[str, Any]) -> list[str]:
    """Qué empeoró respecto de la corrida anterior, aunque ambas pasen el umbral.

    Esta es la razón de existir del módulo: un umbral fijo no ve una degradación
    gradual, y una comparación contra la corrida previa sí.
    """
    avisos: list[str] = []

    antes, ahora = anterior["procesados"], actual["procesados"]
    if antes and ahora < antes * (1 - CAIDA_SOSPECHOSA):
        avisos.append(
            f"contratos: {antes} -> {ahora} "
            f"({(ahora - antes) / antes:+.0%}), caída mayor al "
            f"{CAIDA_SOSPECHOSA:.0%} tolerado"
        )

    # Una fuente que aportaba y dejó de aportar es el sintoma clasico de un
    # selector que la fuente cambio. El total puede disimularlo; esto no.
    for fuente, n_antes in anterior.get("por_fuente", {}).items():
        n_ahora = actual.get("por_fuente", {}).get(fuente, 0)
        if n_antes > 0 and n_ahora == 0:
            avisos.append(f"la fuente '{fuente}' aportaba {n_antes} y ahora aporta 0")

    if actual["tasa_cuarentena"] > anterior["tasa_cuarentena"]:
        avisos.append(
            f"cuarentena: {anterior['tasa_cuarentena']:.1%} -> "
            f"{actual['tasa_cuarentena']:.1%}"
        )

    nuevas = set(actual.get("fuentes_fallidas", {})) - set(
        anterior.get("fuentes_fallidas", {})
    )
    for fuente in sorted(nuevas):
        avisos.append(f"fuente caída que antes no fallaba: '{fuente}'")

    return avisos


def tabla(corridas: list[dict[str, Any]]) -> str:
    """Las corridas una debajo de otra, y qué empeoró en la más reciente."""
    if not corridas:
        return "No hay corridas registradas todavía."

    lineas = [
        "",
        f"{'momento':<20}{'contratos':>10}{'cuarent.':>10}"
        f"{'requests':>10}{'seg':>8}  veredicto",
        "-" * 74,
    ]
    for c in corridas:
        lineas.append(
            f"{c['momento']:<20}{c['procesados']:>10}"
            f"{c['tasa_cuarentena']:>9.1%}{c['requests_emitidos']:>10}"
            f"{c['duracion_s']:>8.0f}  "
            + ("confiable" if c["confiable"] else "NO CONFIABLE")
        )

    if len(corridas) >= 2:
        avisos = regresiones(corridas[0], corridas[1])
        lineas += ["", "  Comparada con la corrida anterior:"]
        lineas += (
            [f"     - {a}" for a in avisos]
            if avisos
            else ["     sin regresiones: nada aportó menos que la vez pasada"]
        )

    for problema in corridas[0]["problemas"]:
        lineas.append(f"  PROBLEMA: {problema}")

    return "\n".join(lineas) + "\n"

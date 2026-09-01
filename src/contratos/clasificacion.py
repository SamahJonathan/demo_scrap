"""Clasifica las causales de término contra el piso legal.

**El problema que resuelve.** Publicar el texto de las causales, contrato por
contrato, no es reportería: un párrafo no se compara, no se agrega y no se
acciona. Y a primera vista parece que cada organismo redacta lo suyo.

**Lo que muestran los datos.** No es así. Medido sobre las fichas reales, dos
licitaciones de organismos distintos comparten **cuatro de cinco causales
palabra por palabra**: son el mínimo que la ley de compras públicas impone a
todos. Se repiten porque tienen que repetirse.

Entonces el dato útil no es la lista, es **lo que sobra por encima del piso**.
Y encontrarlo no necesita un modelo: comparar contra un patrón es
determinista. El modelo solo hizo falta para leer la prosa.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

# Las causales que la ley impone a todo contrato de compra pública. Salieron de
# comparar fichas reales, no de leer la ley: son las que aparecen literales en
# licitaciones de organismos distintos.
_ESTANDAR = (
    r"muerte o incapacidad sobreviniente",
    r"resciliacion o mutuo acuerdo",
    r"incumplimiento grave de las obligaciones",
    r"notoria insolvencia",
    r"imposibilidad de ejecutar la prestacion",
    r"exigirlo el interes publico",
    r"demas (causales )?(establecidas|que se establezcan)",
    r"perder la habilidad para contratar",
)

# Un disparador CUANTIFICADO es el hallazgo que importa: el contrato puede
# terminar antes de su fecha declarada por alcanzar un monto o un tope, no por
# incumplir. Caso real: el MOP corta al llegar a 2.000 UTM.
# Las formas verbales van sueltas a proposito: la prosa legal chilena usa el
# futuro de subjuntivo ("si se alcanzare", "si se agotare"), que un patron
# escrito en presente no captura. Salio de un test que fallo por eso.
_CUANTIFICADO = re.compile(
    r"(?i)(\d[\d.,]*\s*(utm|uf|unidades tributarias)"
    r"|alcanzar\w*\s+el\s+monto"
    r"|agotar\w*\s+el\s+(presupuesto|monto)"
    r"|monto\s+(maximo|total|autorizado))"
)


class Riesgo(StrEnum):
    """Cuánto hay que mirar este contrato antes de renovarlo."""

    ESTANDAR = "solo_causales_estandar"
    ADICIONALES = "con_causales_adicionales"
    # El vencimiento declarado puede no ser el real.
    DISPARADOR_CUANTIFICADO = "con_disparador_cuantificado"


def _normalizar(texto: str) -> str:
    """Sin tildes, sin la letra de enumeración y en minúsculas."""
    sin_tildes = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    sin_marca = re.sub(r"^\s*[a-z]\)\s*", "", sin_tildes, flags=re.I)
    return re.sub(r"\s+", " ", sin_marca).strip().lower()


def es_estandar(causal: str) -> bool:
    """¿Es una de las que la ley impone a todos?"""
    limpia = _normalizar(causal)
    return any(re.search(p, limpia) for p in _ESTANDAR)


def clasificar(causales: list[str]) -> tuple[Riesgo, list[str]]:
    """Devuelve el riesgo y **las causales que sobran** sobre el piso legal.

    Lo que se publica es el sobrante, no la lista entera: repetir en cada
    contrato lo que la ley ya obliga es ruido que esconde lo excepcional.
    """
    adicionales = [c for c in causales if not es_estandar(c)]
    if not adicionales:
        return Riesgo.ESTANDAR, []
    if any(_CUANTIFICADO.search(c) for c in adicionales):
        return Riesgo.DISPARADOR_CUANTIFICADO, adicionales
    return Riesgo.ADICIONALES, adicionales

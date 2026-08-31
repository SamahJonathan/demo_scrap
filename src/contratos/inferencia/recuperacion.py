"""Filtro de pasajes: se le manda al modelo solo lo que puede contener la
respuesta, no el documento entero.

Medido en el Spike 0: fragmentar bajó la corrida de 88 a 10,2 minutos —**8,7
veces**— y ademas corrigio dos de los tres fallos del enfoque monolitico.

Y hace algo que el modelo no supo hacer: cuando no hay pasajes, **la respuesta
es null sin llamar al modelo**. En Mostazal, el modelo con el documento completo
invento una readjudicacion como causal de termino tras 8 minutos de computo. El
filtro acierta en microsegundos.
"""

from __future__ import annotations

import re

# Palabras que delatan una clausula de termino. Salieron de leer las tres fichas
# del spike, no de imaginarlas.
CLAVES_TERMINO = re.compile(
    r"(?i)(t[eé]rmino anticipado|causal(es)? de t[eé]rmino|poner t[eé]rmino"
    r"|resciliaci[oó]n|t[eé]rmino administrativo|incumplimiento grave)"
)

ANTES, DESPUES = 600, 900


def pasajes(
    texto: str, patron: re.Pattern[str] = CLAVES_TERMINO
) -> list[tuple[int, int]]:
    """Ventanas alrededor de cada coincidencia, fusionando las que se solapan.

    Devuelve posiciones y no texto: la posicion es lo que permite trazar de
    donde salio un dato inferido, y sin eso no entra a la base.
    """
    ventanas: list[tuple[int, int]] = []
    for m in patron.finditer(texto):
        inicio = max(0, m.start() - ANTES)
        fin = min(len(texto), m.start() + DESPUES)
        if ventanas and inicio <= ventanas[-1][1]:
            ventanas[-1] = (ventanas[-1][0], max(ventanas[-1][1], fin))
        else:
            ventanas.append((inicio, fin))
    return ventanas


def extraer(texto: str, patron: re.Pattern[str] = CLAVES_TERMINO) -> str:
    """El texto de los pasajes, unido. Cadena vacia si no hay ninguno."""
    return "\n---\n".join(texto[a:b] for a, b in pasajes(texto, patron))

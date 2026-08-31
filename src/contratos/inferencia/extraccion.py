"""Extracción de cláusulas y verificación cruzada.

Las dos funciones que el Spike 0 justificó, y ninguna más. El modelo no toca
campos estructurados: los extrae la API o un selector, más rápido y sin razonar
sobre lo que lee.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from contratos.inferencia.interfaz import Modelo, ModeloNoDisponible
from contratos.inferencia.recuperacion import extraer, pasajes
from contratos.modelos import ClausulaExtraida, Discrepancia, Licitacion

log = logging.getLogger(__name__)

PROMPT_TERMINO = """De estos fragmentos de una licitación pública chilena extrae
las causales de TERMINO ANTICIPADO del contrato.

OJO: la readjudicación NO es una causal de término. Readjudicar es pasar al
siguiente oferente cuando el primero no firma; terminar es cortar un contrato ya
vigente. Si el texto solo habla de readjudicación, responde null.

Responde SOLO un objeto JSON: {{"causales": ["...", "..."]}} o {{"causales": null}}

TEXTO:
{texto}"""

PROMPT_DURACION = """De este texto de una licitación pública chilena, extrae la
duración del contrato tal como la enuncia la PROSA.

No infieras ni corrijas: si el texto dice "24 meses", responde 24 meses. Si no
menciona ninguna duración, responde null.

Responde SOLO un objeto JSON: {{"valor": 24, "unidad": "meses"}} o {{"valor": null}}

TEXTO:
{texto}"""

# La prosa enuncia la duración en frases como "duración del contrato: 24 MESES".
_DURACION = re.compile(
    r"(?i)(duraci[oó]n|vigencia|plazo)\s+(del?\s+)?(contrato|servicio|convenio)"
)


@dataclass
class Resultado:
    """Lo que produjo la inferencia sobre una licitación."""

    clausula: ClausulaExtraida | None = None
    discrepancia: Discrepancia | None = None
    # El crudo de una respuesta mal formada se conserva: auditarla vale más que
    # perderla, y el contrato se guarda igual.
    respuestas_no_parseables: list[str] = field(default_factory=list)


def _json_o_none(crudo: str) -> dict[str, object] | None:
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def extraer_causales(
    modelo: Modelo, licitacion: Licitacion, seccion9: str
) -> tuple[ClausulaExtraida | None, str | None]:
    """Causales de término. Devuelve `(clausula, crudo_no_parseable)`.

    Si el filtro no encuentra pasajes, **no se llama al modelo**: la respuesta
    correcta es `null`. En Mostazal, el modelo con el documento completo inventó
    una readjudicación tras 8 minutos; el filtro acierta en microsegundos.
    """
    ventanas = pasajes(seccion9)
    if not ventanas:
        log.info(
            "%s: sin pasajes de término, null sin llamar al modelo",
            licitacion.codigo,
        )
        return None, None

    crudo = modelo.responder(PROMPT_TERMINO.format(texto=extraer(seccion9)))
    datos = _json_o_none(crudo)
    if datos is None:
        log.warning("%s: respuesta no parseable, se conserva", licitacion.codigo)
        return None, crudo

    causales = datos.get("causales")
    if not causales or not isinstance(causales, list):
        return None, None

    inicio = ventanas[0][0]
    return (
        ClausulaExtraida(
            licitacion_codigo=licitacion.codigo,
            tipo="causales_termino",
            texto=" | ".join(str(c) for c in causales),
            # Sin trazabilidad no entra: el fragmento y su posición son lo que
            # permitió auditar un resultado mal interpretado en el spike.
            fragmento_origen=seccion9[inicio : ventanas[0][1]][:400],
            posicion_inicio=inicio,
            modelo=modelo.nombre,
        ),
        None,
    )


def verificar_duracion(
    modelo: Modelo, licitacion: Licitacion, texto: str
) -> tuple[Discrepancia | None, str | None]:
    """Contrasta el campo estructurado contra lo que dice la prosa.

    Es el rol que el spike descubrió. SENAMA declara `36 Horas` en su sección 7
    y su prosa dice "36 meses" **tres veces**. La contradicción se registra con
    ambos valores; **ninguno se corrige**.
    """
    if licitacion.duracion_valor is None:
        return None, None

    ventanas = pasajes(texto, _DURACION)
    if not ventanas:
        return None, None

    crudo = modelo.responder(PROMPT_DURACION.format(texto=extraer(texto, _DURACION)))
    datos = _json_o_none(crudo)
    if datos is None:
        return None, crudo

    valor, unidad = datos.get("valor"), str(datos.get("unidad") or "").lower()
    if valor is None:
        return None, None

    estructurado = f"{licitacion.duracion_valor} {licitacion.duracion_unidad.value}"
    prosa = f"{valor} {unidad}"
    if estructurado.strip().lower() == prosa.strip().lower():
        return None, None

    return (
        Discrepancia(
            licitacion_codigo=licitacion.codigo,
            campo="duracion",
            valor_estructurado=estructurado,
            valor_prosa=prosa,
            regla="el campo tipado y la prosa del documento no coinciden",
        ),
        None,
    )


def procesar(
    modelo: Modelo, licitacion: Licitacion, seccion9: str, texto_completo: str
) -> Resultado:
    """Las dos funciones sobre una licitación. Ningún fallo pierde el contrato."""
    r = Resultado()
    try:
        r.clausula, crudo = extraer_causales(modelo, licitacion, seccion9)
        if crudo:
            r.respuestas_no_parseables.append(crudo)

        r.discrepancia, crudo = verificar_duracion(modelo, licitacion, texto_completo)
        if crudo:
            r.respuestas_no_parseables.append(crudo)
    except ModeloNoDisponible as e:
        # El contrato ya existe sin esto: la inferencia es upside.
        log.warning("%s: sin inferencia (%s)", licitacion.codigo, e)
    return r

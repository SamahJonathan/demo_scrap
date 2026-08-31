"""Parseo de la ficha web. **Es el punto frágil declarado del diseño.**

Las garantías solo existen acá: ninguno de los 54 campos de la API REST las
expone, y OCDS tampoco (0 menciones). Ver docs/02-diseno.md § 6.

Este módulo es una **función pura**: recibe HTML y devuelve garantías. No toca la
red. La descarga llega en el incremento 5, cuando exista `UrlActa`.

El modo de falla peligroso no es que reviente: es que **devuelva vacío en
silencio** y una corrida termine "bien" con cero garantías. Por eso hay una
distinción explícita entre "no tiene garantías" y "no pudimos leerlas", y un
umbral de cobertura que hace fallar la corrida.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from selectolax.parser import HTMLParser

from contratos.modelos import Garantia, TipoGarantia

log = logging.getLogger(__name__)

# La ficha es ASP.NET WebForms y su GridView deja ids estables:
#   grvGarantias_ctl02_lblFicha8Monto, ..._lblFicha8FechaVencimiento, etc.
# Se usan selectores sobre esos ids en vez de regex sobre el texto: si el sitio
# cambia el maquetado pero mantiene el GridView, esto sigue funcionando.
_FILA = re.compile(r"^(grvGarantias_ctl\d+)_")
_TABLA = "grvGarantias"


class FichaIlegible(RuntimeError):
    """La ficha no trae la estructura esperada.

    Distinto de "no tiene garantías": esto significa que **no pudimos leerlas**,
    y confundir ambos casos es lo que deja pasar un cero silencioso.
    """


def _texto(arbol: HTMLParser, id_: str) -> str | None:
    nodo = arbol.css_first(f"#{id_}")
    if nodo is None:
        return None
    valor = (nodo.text() or "").strip()
    return valor or None


def _monto(valor: str | None) -> Decimal | None:
    if not valor:
        return None
    limpio = valor.replace(".", "").replace(",", ".").strip()
    try:
        return Decimal(limpio)
    except InvalidOperation:
        log.warning("monto de garantía ilegible: %r", valor)
        return None


def _fecha(valor: str | None) -> date | None:
    """La ficha usa dd-mm-aaaa."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d-%m-%Y").date()
    except ValueError:
        log.warning("fecha de garantía ilegible: %r", valor)
        return None


def _tipo(titulo: str | None) -> TipoGarantia:
    """Clasifica por el título de la fila.

    Un título que no reconocemos NO se fuerza a un tipo conocido: queda como
    `OTRA` y su texto original se conserva.
    """
    t = (titulo or "").lower()
    if "seriedad" in t:
        return TipoGarantia.SERIEDAD_OFERTA
    if "fiel" in t or "cumplimiento" in t:
        return TipoGarantia.FIEL_CUMPLIMIENTO
    return TipoGarantia.OTRA


def parsear_garantias(html: str, licitacion_codigo: str) -> list[Garantia]:
    """Devuelve las garantías de la sección 8 de una ficha.

    Lanza `FichaIlegible` si la tabla no está. Devuelve lista vacía solo cuando
    la tabla existe y no tiene filas: ahí sí, la licitación no exige garantías.
    """
    arbol = HTMLParser(html)

    if arbol.css_first(f"#{_TABLA}") is None:
        raise FichaIlegible(
            f"{licitacion_codigo}: no se encontró la tabla #{_TABLA}. "
            "La ficha cambió de estructura, o no es una ficha. "
            "Esto NO significa que la licitación no tenga garantías."
        )

    filas = sorted(
        {
            m.group(1)
            for m in (
                _FILA.match(n.attributes.get("id") or "")
                for n in arbol.css(f"[id^={_TABLA}_ctl]")
            )
            if m
        }
    )

    garantias: list[Garantia] = []
    for fila in filas:
        titulo = _texto(arbol, f"{fila}_lblFicha8TituloTipoGarantia")
        moneda = _texto(arbol, f"{fila}_lblFicha8TipoMoneda")
        monto = _monto(_texto(arbol, f"{fila}_lblFicha8Monto"))
        if titulo is None and monto is None:
            continue  # fila de encabezado del GridView

        garantias.append(
            Garantia(
                licitacion_codigo=licitacion_codigo,
                tipo=_tipo(titulo),
                titulo_original=titulo or "",
                monto_valor=monto,
                # La ficha distingue pesos de porcentaje en TipoMoneda. Un 5 %
                # y $5 no son lo mismo y no pueden colapsarse en un campo.
                monto_es_porcentaje=(moneda or "").strip() == "%",
                moneda=None if (moneda or "").strip() == "%" else moneda,
                fecha_vencimiento=_fecha(
                    _texto(arbol, f"{fila}_lblFicha8FechaVencimiento")
                ),
                beneficiario=_texto(arbol, f"{fila}_lblFicha8Beneficiario"),
                fragmento_origen=fila,
            )
        )

    if not garantias:
        log.info(
            "%s: la tabla existe pero no trae filas de garantía", licitacion_codigo
        )
    return garantias


def cobertura_suficiente(
    con_garantias: int, con_ficha: int, minimo: float = 0.90
) -> bool:
    """Si casi ninguna ficha rindio garantias, el parser esta roto.

    Es el resguardo contra el modo de falla peligroso del punto fragil: no que
    reviente, sino que devuelva vacio en silencio y la corrida termine "bien"
    con cero garantias.

    Sin fichas procesadas no hay nada que exigir.
    """
    if con_ficha == 0:
        return True
    cobertura = con_garantias / con_ficha
    if cobertura < minimo:
        log.error(
            "cobertura de garantias %.0f%% bajo el minimo %.0f%%: "
            "%d de %d fichas rindieron alguna. El parser probablemente se rompio.",
            cobertura * 100,
            minimo * 100,
            con_garantias,
            con_ficha,
        )
    return cobertura >= minimo

"""Detalle de licitaciones y descarga de su ficha web.

Se llega acá desde la orden de compra: su `CodigoLicitacion` dice qué proceso la
originó. El recorrido inverso no existe en la API.

Acá se cierra el circuito del incremento 4: el detalle entrega `UrlActa`, de ahí
sale el token `qs`, y con él se baja la ficha que el parser de garantías espera.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from contratos.cliente import Cliente
from contratos.modelos import Licitacion

log = logging.getLogger(__name__)


class SinFicha(RuntimeError):
    """La licitación no trae `UrlActa`, así que no hay token para la ficha."""


def detalle(cliente: Cliente, codigo: str) -> Licitacion:
    """Los 54 campos del detalle, incluidos duración, renovación e ítems."""
    url = f"{cliente.config.mp_api_base_url}/licitaciones.json"
    datos = cliente.obtener_json(
        url, {"codigo": codigo, "ticket": cliente.config.mp_api_ticket}
    )
    listado = datos.get("Listado") or []
    if not listado:
        raise ValueError(f"la licitación {codigo} no trae Listado en la respuesta")
    return Licitacion.desde_api(listado[0])


def url_ficha(licitacion: Licitacion, base: str) -> str:
    """Arma la URL de la ficha a partir del token `qs` que entrega la API.

    **No hay ingeniería inversa**: `Adjudicacion.UrlActa` ya trae el token
    cifrado, y la misma clave sirve para la ficha de detalle.
    """
    if not licitacion.url_acta or "qs=" not in licitacion.url_acta:
        raise SinFicha(
            f"{licitacion.codigo}: no trae UrlActa, no hay token para la ficha"
        )
    token = licitacion.url_acta.split("qs=", 1)[1]
    return (
        f"{base}/Procurement/Modules/RFB/DetailsAcquisition.aspx"
        f"?qs={quote(token, safe='')}"
    )


def bajar_ficha(cliente: Cliente, licitacion: Licitacion) -> str:
    """Baja el HTML de la ficha con un GET limpio.

    Corrige el supuesto del método: el ViewState de ASP.NET no impide el GET.
    Lo que sí está bloqueado son los ADJUNTOS, tras reCAPTCHA, y eso queda
    fuera de alcance por decisión explícita del proyecto.
    """
    url = url_ficha(licitacion, cliente.config.mp_web_base_url)
    return cliente.obtener(url, sufijo=".html")

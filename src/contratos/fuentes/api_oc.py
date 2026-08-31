"""Descubrimiento de órdenes de compra en la API de Mercado Público.

La extracción parte de acá y no de las licitaciones, porque la API **no permite
el recorrido inverso**: rechaza `codigoLicitacion` como parámetro (HTTP 400) y el
listado de OC no incluye ese campo. Ver docs/01-analisis.md § 3.5.

El listado es pobre —solo `Codigo`, `Nombre` y `CodigoEstado`— pero el sufijo del
código basta para clasificar sin gastar un solo request adicional.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel

from contratos.cliente import Cliente
from contratos.config import Config, cargar

# El código de una orden es <organismo>-<correlativo>-<TIPO><AA>, por ejemplo
# 1002-183-SE25. El tipo son las letras finales antes del año.
_TIPO = re.compile(r"-([A-Z]{1,2})\d{2}$", re.IGNORECASE)


class OrdenResumen(BaseModel):
    """Lo poco que entrega el listado. El detalle llega en el incremento 3."""

    codigo: str
    nombre: str
    codigo_estado: int

    @property
    def tipo(self) -> str:
        """`SE`, `CC`, `AG`, `CM`, `TD`... o cadena vacía si el código es raro."""
        m = _TIPO.search(self.codigo)
        return m.group(1).upper() if m else ""


@dataclass
class Clasificacion:
    """Las órdenes de una fecha, separadas por si pueden tener licitación.

    Las huérfanas NO son un descarte: son el 56% del gasto y responden la
    pregunta de negocio 5. Sin ellas, el caso 'OC sin licitación' del modelo
    nunca se ejercitaría.
    """

    con_proceso: list[OrdenResumen] = field(default_factory=list)
    sin_proceso: list[OrdenResumen] = field(default_factory=list)
    otros: list[OrdenResumen] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.con_proceso) + len(self.sin_proceso) + len(self.otros)


def parsear_listado(datos: dict[str, Any]) -> list[OrdenResumen]:
    return [
        OrdenResumen(
            codigo=x["Codigo"],
            nombre=x.get("Nombre") or "",
            codigo_estado=int(x["CodigoEstado"]),
        )
        for x in (datos.get("Listado") or [])
    ]


def clasificar(
    ordenes: list[OrdenResumen], config: Config | None = None
) -> Clasificacion:
    """Separa por sufijo del código. **No emite ningún request**: es texto."""
    cfg = config or cargar()
    con = set(cfg.tipos_oc_con_licitacion)
    sin = set(cfg.tipos_oc_sin_licitacion)

    c = Clasificacion()
    for o in ordenes:
        if o.tipo in con:
            c.con_proceso.append(o)
        elif o.tipo in sin:
            c.sin_proceso.append(o)
        else:
            # Un tipo que no conocemos no se adivina: se aparta y se cuenta.
            c.otros.append(o)
    return c


def listar(cliente: Cliente, fecha: date) -> list[OrdenResumen]:
    """Listado crudo de una fecha. Un request, o cero si ya está en caché."""
    url = f"{cliente.config.mp_api_base_url}/ordenesdecompra.json"
    datos = cliente.obtener_json(
        url,
        {"fecha": fecha.strftime("%d%m%Y"), "ticket": cliente.config.mp_api_ticket},
    )
    return parsear_listado(datos)


def descubrir(
    cliente: Cliente,
    fecha: date,
    limite_con_proceso: int | None = None,
    limite_sin_proceso: int | None = None,
) -> Clasificacion:
    """Listado de una fecha, clasificado y recortado a los límites configurados."""
    cfg = cliente.config
    n_con = (
        cfg.oc_con_proceso_por_fecha
        if limite_con_proceso is None
        else limite_con_proceso
    )
    n_sin = (
        cfg.oc_sin_proceso_por_fecha
        if limite_sin_proceso is None
        else limite_sin_proceso
    )

    todo = clasificar(listar(cliente, fecha), cfg)
    return Clasificacion(
        con_proceso=todo.con_proceso[:n_con],
        sin_proceso=todo.sin_proceso[:n_sin],
        otros=todo.otros,
    )

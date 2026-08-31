"""Reconstrucción de la entidad Contrato. **Es el núcleo del proyecto.**

La fuente NO publica contratos: expone licitaciones, órdenes de compra, compra
ágil y proveedores. El contrato hay que armarlo uniendo el proceso, la
adjudicación, el instrumento de ejecución y los documentos.

Dos reglas que ordenan todo:

1. **Cada campo declara de dónde vino.** Sin procedencia el dato no es
   defendible, y la mitad del valor de la demo está en poder mostrarla.
2. **Dos niveles, porque la fuente tiene dos niveles.** Lo que pertenece al
   proceso vive en `Licitacion` y NO se replica en cada orden: cinco órdenes de
   la misma licitación comparten sus dos garantías y sus seis oferentes.
   Replicarlos haría que contarlos diera diez y treinta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from contratos.modelos import (
    EstadoVencimiento,
    Garantia,
    Licitacion,
    OrdenCompra,
    UnidadDuracion,
)

log = logging.getLogger(__name__)


class Procedencia(StrEnum):
    """De dónde salió cada campo. Sin esto el dato no se puede defender."""

    API_OC = "api_oc"
    API_LICITACION = "api_licitacion"
    OCDS = "ocds"
    FICHA_WEB = "ficha_web"
    INFERENCIA = "inferencia"
    DERIVADO = "derivado"


@dataclass(frozen=True)
class Contrato:
    """Una orden de compra, enriquecida con el proceso que la originó.

    La clave es `codigo_oc`, no la licitación: una licitación puede originar
    varias órdenes, y el 56% de las órdenes no tiene licitación.
    """

    codigo_oc: str
    codigo_licitacion: str | None

    organismo: str
    organismo_rut: str
    proveedor: str
    proveedor_rut: str

    monto_ejecutado: Decimal
    monto_adjudicado: Decimal | None

    es_comprometido: bool
    es_ejecutado: bool
    estado: str

    fecha_aceptacion: date | None
    fecha_termino_estimada: date | None
    estado_vencimiento: EstadoVencimiento

    procedencias: dict[str, Procedencia] = field(default_factory=dict)

    @property
    def tiene_proceso(self) -> bool:
        return self.codigo_licitacion is not None


@dataclass
class Cartera:
    """Lo reconstruido de una corrida, en sus dos niveles."""

    contratos: list[Contrato] = field(default_factory=list)
    licitaciones: dict[str, Licitacion] = field(default_factory=dict)
    garantias: dict[str, list[Garantia]] = field(default_factory=dict)

    @property
    def sin_proceso(self) -> int:
        return sum(1 for c in self.contratos if not c.tiene_proceso)

    @property
    def total_garantias(self) -> int:
        """Se cuentan por licitación, no por contrato: no se duplican."""
        return sum(len(g) for g in self.garantias.values())


# Procedencia de cada campo. Es parte del contrato publico del modulo: el
# dashboard la muestra y un test exige que ningun campo quede sin ella.
PROCEDENCIAS: dict[str, Procedencia] = {
    "codigo_oc": Procedencia.API_OC,
    "codigo_licitacion": Procedencia.API_OC,
    "organismo": Procedencia.API_OC,
    "organismo_rut": Procedencia.API_OC,
    "proveedor": Procedencia.API_OC,
    "proveedor_rut": Procedencia.API_OC,
    "monto_ejecutado": Procedencia.API_OC,
    "es_comprometido": Procedencia.DERIVADO,
    "es_ejecutado": Procedencia.DERIVADO,
    "estado": Procedencia.API_OC,
    "fecha_aceptacion": Procedencia.API_OC,
    "monto_adjudicado": Procedencia.API_LICITACION,
    "fecha_termino_estimada": Procedencia.DERIVADO,
    "estado_vencimiento": Procedencia.DERIVADO,
}


def calcular_vencimiento(
    licitacion: Licitacion | None,
) -> tuple[date | None, EstadoVencimiento]:
    """Devuelve la fecha de término y **por qué** falta cuando falta.

    Un `None` mudo mezcla tres situaciones que exigen respuestas distintas:
    la modalidad no declara plazo, no sabemos leer la unidad, o sí se pudo
    calcular.
    """
    if licitacion is None:
        # Compra ágil, convenio marco, trato directo: compra puntual, no
        # contrato con vigencia. No se le inventa un vencimiento.
        return None, EstadoVencimiento.NO_DECLARADO

    if licitacion.fecha_adjudicacion is None or licitacion.duracion_valor is None:
        return None, EstadoVencimiento.NO_DECLARADO

    if licitacion.duracion_unidad is UnidadDuracion.MESES:
        fin = licitacion.fecha_adjudicacion + timedelta(
            days=30 * licitacion.duracion_valor
        )
        return fin, EstadoVencimiento.CALCULADO

    if licitacion.duracion_unidad is UnidadDuracion.HORAS:
        fin = licitacion.fecha_adjudicacion + timedelta(hours=licitacion.duracion_valor)
        return fin, EstadoVencimiento.CALCULADO

    # Hay duración pero la unidad no está decodificada. Es deuda nuestra, no
    # una característica de la fuente: se marca para investigarla.
    return None, EstadoVencimiento.UNIDAD_DESCONOCIDA


def reconstruir(orden: OrdenCompra, licitacion: Licitacion | None) -> Contrato:
    """Une una orden con su proceso. Sin proceso también es un contrato válido."""
    if licitacion is not None and orden.codigo_licitacion != licitacion.codigo:
        raise ValueError(
            f"{orden.codigo} apunta a {orden.codigo_licitacion} "
            f"pero se le pasó {licitacion.codigo}"
        )

    fin, estado_venc = calcular_vencimiento(licitacion)

    return Contrato(
        codigo_oc=orden.codigo,
        codigo_licitacion=orden.codigo_licitacion,
        organismo=orden.organismo,
        organismo_rut=orden.organismo_rut,
        proveedor=orden.proveedor,
        proveedor_rut=orden.proveedor_rut,
        monto_ejecutado=orden.monto_total,
        # Atribución EXACTA por RUT, nunca prorrateo: la fuente dice cuánto le
        # tocó a cada proveedor y el reparto real va de $19M a $167M.
        monto_adjudicado=(
            licitacion.monto_adjudicado_a(orden.proveedor_rut)
            if licitacion is not None
            else None
        ),
        es_comprometido=orden.es_comprometido,
        es_ejecutado=orden.es_ejecutado,
        estado=orden.estado,
        fecha_aceptacion=orden.fecha_aceptacion,
        fecha_termino_estimada=fin,
        estado_vencimiento=estado_venc,
        procedencias=dict(PROCEDENCIAS),
    )


def reconstruir_cartera(
    ordenes: list[OrdenCompra],
    licitaciones: dict[str, Licitacion],
    garantias: dict[str, list[Garantia]] | None = None,
) -> Cartera:
    """Reconstruye una corrida completa, en dos niveles.

    Las licitaciones y sus garantías se guardan **una vez**, aunque varias
    órdenes las compartan.
    """
    cartera = Cartera(garantias=dict(garantias or {}))

    for orden in ordenes:
        lic = (
            licitaciones.get(orden.codigo_licitacion)
            if orden.codigo_licitacion
            else None
        )
        if orden.codigo_licitacion and lic is None:
            log.warning(
                "%s apunta a la licitación %s, que no se pudo obtener. "
                "El contrato se guarda igual, sin los datos del proceso.",
                orden.codigo,
                orden.codigo_licitacion,
            )
        cartera.contratos.append(reconstruir(orden, lic))
        if lic is not None:
            cartera.licitaciones[lic.codigo] = lic

    return cartera

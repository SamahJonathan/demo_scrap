"""Entidades del dominio, tipadas y validadas.

Todo dato que entra se valida contra un esquema explícito. Lo que no cumple se
aparta con su motivo; nunca se corrige en silencio ni se adivina.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EstadoNoConocido(ValueError):
    """Apareció un `CodigoEstado` fuera de los cinco medidos.

    No se adivina a qué se parece: el registro va a cuarentena y el valor nuevo
    queda como señal de que hay que investigarlo.
    """


class EstadoOC(IntEnum):
    """Los cinco estados medidos sobre 9.206 órdenes del 15-05-2025."""

    ENVIADA_A_PROVEEDOR = 4  # 1,0 %
    EN_PROCESO = 5  # 0,03 %
    ACEPTADA = 6  # 24,3 %
    CANCELADA = 9  # 3,6 %
    RECEPCION_CONFORME = 12  # 71,1 %


# "Gasto" son dos cosas distintas y el modelo las separa. Ver docs/02-diseno.md.
COMPROMETIDO = frozenset(
    {
        EstadoOC.ENVIADA_A_PROVEEDOR,
        EstadoOC.EN_PROCESO,
        EstadoOC.ACEPTADA,
        EstadoOC.RECEPCION_CONFORME,
    }
)
EJECUTADO = frozenset({EstadoOC.ACEPTADA, EstadoOC.RECEPCION_CONFORME})


def _fecha(valor: Any) -> date | None:
    """La API entrega ISO con hora, o `None`, o cadena vacía."""
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    return datetime.fromisoformat(str(valor).split(".")[0]).date()


class OrdenCompra(BaseModel):
    """Una orden de compra. Es la unidad de la demo: un proveedor, un monto real."""

    model_config = ConfigDict(frozen=True)

    codigo: str = Field(min_length=1)
    # Vacío en el 56% de las órdenes. Es un caso VÁLIDO, no un error: compra
    # ágil, convenio marco y trato directo no nacen de una licitación.
    codigo_licitacion: str | None = None
    nombre: str = ""
    tipo: str = ""

    codigo_estado: EstadoOC
    estado: str = ""

    organismo: str = ""
    organismo_rut: str = ""
    proveedor: str = ""
    proveedor_rut: str = ""

    monto_total: Decimal = Decimal(0)
    fecha_envio: date | None = None
    fecha_aceptacion: date | None = None

    @property
    def tiene_proceso(self) -> bool:
        return self.codigo_licitacion is not None

    @property
    def es_comprometido(self) -> bool:
        """La orden existe y no fue anulada."""
        return self.codigo_estado in COMPROMETIDO

    @property
    def es_ejecutado(self) -> bool:
        """El proveedor aceptó o entregó.

        Se midió una orden Cancelada con monto $1.346.366: sumarla al gasto lo
        inflaría. Por eso las dos métricas viven separadas.
        """
        return self.codigo_estado in EJECUTADO

    @field_validator("codigo_licitacion", mode="before")
    @classmethod
    def _vacio_es_none(cls, v: object) -> object:
        """La API devuelve cadena vacía, no null, cuando no hay licitación."""
        return None if v in ("", None) else v

    @classmethod
    def desde_api(cls, crudo: dict[str, Any]) -> OrdenCompra:
        """Construye desde el detalle de `ordenesdecompra.json?codigo=`."""
        try:
            estado = EstadoOC(int(crudo["CodigoEstado"]))
        except ValueError as e:
            raise EstadoNoConocido(
                f"CodigoEstado={crudo.get('CodigoEstado')} no está entre los cinco "
                f"conocidos {sorted(int(x) for x in EstadoOC)}. "
                "No se adivina: el registro va a cuarentena."
            ) from e

        comprador = crudo.get("Comprador") or {}
        proveedor = crudo.get("Proveedor") or {}
        fechas = crudo.get("Fechas") or {}

        return cls(
            codigo=crudo["Codigo"],
            codigo_licitacion=crudo.get("CodigoLicitacion"),
            nombre=crudo.get("Nombre") or "",
            tipo=crudo.get("Tipo") or "",
            codigo_estado=estado,
            estado=crudo.get("Estado") or "",
            organismo=comprador.get("NombreOrganismo") or "",
            organismo_rut=comprador.get("RutUnidad") or "",
            proveedor=proveedor.get("Nombre") or "",
            proveedor_rut=proveedor.get("RutSucursal") or "",
            monto_total=Decimal(str(crudo.get("Total") or 0)),
            fecha_envio=_fecha(fechas.get("FechaEnvio")),
            fecha_aceptacion=_fecha(fechas.get("FechaAceptacion")),
        )


class TipoGarantia(StrEnum):
    """Un titulo que no reconocemos queda como OTRA, no se fuerza a un tipo."""

    SERIEDAD_OFERTA = "seriedad_oferta"
    FIEL_CUMPLIMIENTO = "fiel_cumplimiento"
    OTRA = "otra"


class Garantia(BaseModel):
    """Caucion exigida por una licitacion.

    Pertenece a la LICITACION, no a la orden de compra: si una licitacion
    origina cinco ordenes, sus garantias son las mismas dos. Replicarlas por
    contrato haria que contarlas diera diez.
    """

    model_config = ConfigDict(frozen=True)

    licitacion_codigo: str = Field(min_length=1)
    tipo: TipoGarantia
    titulo_original: str = ""

    monto_valor: Decimal | None = None
    # Un 5 % y $5 no son lo mismo. La ficha los distingue en TipoMoneda y el
    # modelo tambien: colapsarlos haria que sumar montos diera cualquier cosa.
    monto_es_porcentaje: bool = False
    moneda: str | None = None

    fecha_vencimiento: date | None = None
    beneficiario: str | None = None

    # Sin trazabilidad al origen el dato no es defendible.
    fragmento_origen: str = Field(min_length=1)


class UnidadDuracion(StrEnum):
    """Decodificado cruzando la API contra la seccion 7 de la ficha.

    Solo dos valores estan confirmados. Cualquier otro queda DESCONOCIDO y NO
    se adivina: un plazo mal interpretado corrompe la fecha de vencimiento, que
    es el eje de la demo.
    """

    HORAS = "horas"
    MESES = "meses"
    DESCONOCIDO = "desconocido"


#   1 -> 36 en la API, "36 Horas" en la ficha de SENAMA
#   4 -> 24 en la API, "24 Meses" en la ficha de Puerto Montt (y 10 Meses en Mostazal)
_UNIDADES = {1: UnidadDuracion.HORAS, 4: UnidadDuracion.MESES}


def decodificar_unidad(codigo: object) -> UnidadDuracion:
    if not isinstance(codigo, int | str):
        return UnidadDuracion.DESCONOCIDO
    try:
        return _UNIDADES.get(int(codigo), UnidadDuracion.DESCONOCIDO)
    except ValueError:
        return UnidadDuracion.DESCONOCIDO


class ItemAdjudicado(BaseModel):
    """Un item de la licitacion, con el proveedor al que se le adjudico.

    Es lo que permite atribuir el monto EXACTO a cada proveedor en vez de
    prorratear. En 2678-1-LR25 el reparto real va de 19 a 167 millones; por
    partes iguales daria 88,3 a cada uno, un numero que no existe.
    """

    model_config = ConfigDict(frozen=True)

    correlativo: int
    descripcion: str = ""
    proveedor_rut: str | None = None
    cantidad: Decimal = Decimal(0)
    monto_unitario: Decimal = Decimal(0)

    @property
    def monto(self) -> Decimal:
        return self.cantidad * self.monto_unitario


class Licitacion(BaseModel):
    """El proceso. Solo existe para el 44% de las ordenes que lo tiene.

    Guarda lo que pertenece al proceso y seria redundante replicar en cada
    orden: si una licitacion origina cinco ordenes, hay UNA fila aca.
    """

    model_config = ConfigDict(frozen=True)

    codigo: str = Field(min_length=1)
    nombre: str = ""

    fecha_publicacion: date | None = None
    fecha_adjudicacion: date | None = None

    duracion_valor: int | None = None
    duracion_unidad: UnidadDuracion = UnidadDuracion.DESCONOCIDO
    es_renovable: bool = False

    items: tuple[ItemAdjudicado, ...] = ()
    url_acta: str | None = None

    # De OCDS, que no consume cupo de requests.
    monto_adjudicado_total: Decimal | None = None
    n_oferentes: int | None = None

    def monto_adjudicado_a(self, proveedor_rut: str) -> Decimal | None:
        """Suma los items adjudicados a un RUT. Atribucion exacta, sin prorrateo."""
        if not proveedor_rut:
            return None
        propios = [i for i in self.items if i.proveedor_rut == proveedor_rut]
        return sum((i.monto for i in propios), Decimal(0)) if propios else None

    @property
    def monto_adjudicado_por_items(self) -> Decimal:
        """Total segun los items. Debe cuadrar con el award.value de OCDS."""
        return sum((i.monto for i in self.items), Decimal(0))

    @classmethod
    def desde_api(cls, crudo: dict[str, Any]) -> Licitacion:
        fechas = crudo.get("Fechas") or {}
        adj = crudo.get("Adjudicacion") or {}
        items = []
        for it in (crudo.get("Items") or {}).get("Listado") or []:
            a = it.get("Adjudicacion") or {}
            items.append(
                ItemAdjudicado(
                    correlativo=int(it.get("Correlativo") or 0),
                    descripcion=it.get("Descripcion") or "",
                    proveedor_rut=(a.get("RutProveedor") or None),
                    cantidad=Decimal(str(a.get("Cantidad") or 0)),
                    monto_unitario=Decimal(str(a.get("MontoUnitario") or 0)),
                )
            )
        return cls(
            codigo=crudo["CodigoExterno"],
            nombre=crudo.get("Nombre") or "",
            fecha_publicacion=_fecha(fechas.get("FechaPublicacion")),
            fecha_adjudicacion=_fecha(fechas.get("FechaAdjudicacion")),
            duracion_valor=int(crudo["TiempoDuracionContrato"])
            if str(crudo.get("TiempoDuracionContrato") or "").strip().isdigit()
            else None,
            duracion_unidad=decodificar_unidad(
                crudo.get("UnidadTiempoDuracionContrato")
            ),
            es_renovable=bool(int(crudo.get("EsRenovable") or 0)),
            items=tuple(items),
            url_acta=adj.get("UrlActa") or None,
        )


class EstadoVencimiento(StrEnum):
    """Por que falta la fecha de termino, en vez de un NULL mudo.

    Un nulo mezcla tres situaciones que exigen respuestas distintas:
    NO_DECLARADO es una caracteristica de la modalidad de compra y no hay nada
    que arreglar; UNIDAD_DESCONOCIDA es deuda nuestra y hay que investigarla.
    """

    CALCULADO = "calculado"
    NO_DECLARADO = "no_declarado"
    UNIDAD_DESCONOCIDA = "unidad_desconocida"

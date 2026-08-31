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

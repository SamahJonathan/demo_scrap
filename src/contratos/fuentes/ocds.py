"""OCDS — Open Contracting Data Standard.

ChileCompra publica en el estándar internacional de contratación abierta, y esto
importa por dos razones medidas:

1. **No requiere ticket**, así que no consume el cupo de 10.000 requests
   diarios. Todo lo que salga de acá es gratis en presupuesto.
2. **Trae datos que la API REST no expone**: el monto adjudicado y quiénes
   ofertaron. El contrato se firma por el monto adjudicado ($441,6M en
   2678-1-LR25), no por el estimado ($522,5M).

El estándar tiene una etapa `contract` y Chile **la deja vacía**: publica hasta
la adjudicación. Ese hueco es justamente lo que este proyecto reconstruye.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from contratos.cliente import Cliente

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatosOcds:
    """Lo que OCDS aporta y la API REST no."""

    monto_adjudicado: Decimal | None = None
    monto_estimado: Decimal | None = None
    n_oferentes: int | None = None


def consultar(cliente: Cliente, codigo: str) -> DatosOcds:
    """Pide el *record* de una licitación. **Sin ticket, sin gastar cupo.**"""
    url = f"{cliente.config.ocds_base_url}/record/{codigo}"
    datos = cliente.obtener_json(url)

    registros = datos.get("records") or []
    if not registros:
        log.warning("%s: OCDS no devolvió records", codigo)
        return DatosOcds()

    compilado = registros[0].get("compiledRelease") or {}
    licitacion = compilado.get("tender") or {}
    adjudicaciones = compilado.get("awards") or []
    valor_adj = (adjudicaciones[0].get("value") or {}) if adjudicaciones else {}
    valor_est = licitacion.get("value") or {}

    return DatosOcds(
        monto_adjudicado=_decimal(valor_adj.get("amount")),
        monto_estimado=_decimal(valor_est.get("amount")),
        n_oferentes=len(licitacion.get("tenderers") or []) or None,
    )


def _decimal(valor: object) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))

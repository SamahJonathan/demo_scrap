"""Validación y cuarentena. **Es el corazón de la calidad del dato.**

Dos principios que ordenan todo el módulo:

1. **Un registro malo no aborta la corrida.** Se aparta con su motivo y el resto
   sigue. Reprocesar 450 contratos porque uno vino torcido es inaceptable.
2. **Nada se corrige en silencio.** Una regla marca lo implausible; no arregla
   el valor. El caso de SENAMA —36 horas de contrato con garantía hasta 2027—
   es un hallazgo, no un error a tapar.

Las reglas nacieron de datos reales medidos, no de la teoría.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from contratos.modelos import (
    Garantia,
    Licitacion,
    OrdenCompra,
    TipoGarantia,
    UnidadDuracion,
)

log = logging.getLogger(__name__)

# Un contrato puede exigir que la garantía siga viva un tiempo después de
# terminar: se midió "aumentado en un periodo de 90 días corridos" en SENAMA.
# El margen es generoso a propósito: la regla debe cazar lo absurdo, no lo
# discutible.
MARGEN_GARANTIA = timedelta(days=365)


class Motivo(StrEnum):
    """Por qué un registro quedó apartado. Un motivo por causa, no un cajón."""

    ESQUEMA = "esquema_invalido"
    GARANTIA_VENCE_ANTES = "garantia_vence_antes_del_contrato"
    MONTOS_NO_CUADRAN = "items_no_cuadran_con_ocds"
    PRECIO_UNITARIO = "monto_adjudicado_parece_precio_unitario"
    UNIDAD_DESCONOCIDA = "unidad_de_duracion_sin_decodificar"


@dataclass
class Hallazgo:
    """Algo que no cuadra, con lo necesario para auditarlo."""

    identificador: str
    motivo: Motivo
    detalle: str
    valores: dict[str, str] = field(default_factory=dict)


@dataclass
class Reporte:
    """Resultado de validar una corrida."""

    revisados: int = 0
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def tasa(self) -> float:
        return len(self.hallazgos) / self.revisados if self.revisados else 0.0

    def supera_umbral(self, maximo: float) -> bool:
        """Sobre el umbral no hay un dato malo: hay un parser roto."""
        if self.tasa > maximo:
            log.error(
                "tasa de cuarentena %.1f%% sobre el máximo %.1f%% "
                "(%d de %d). Eso no son datos malos, es un parser roto.",
                self.tasa * 100,
                maximo * 100,
                len(self.hallazgos),
                self.revisados,
            )
            return True
        return False


def fecha_termino(licitacion: Licitacion) -> date | None:
    """Adjudicación más duración. `None` si no se puede calcular.

    No se inventa un vencimiento cuando la unidad no está decodificada: un
    plazo mal interpretado corrompe el eje de la demo.
    """
    if licitacion.fecha_adjudicacion is None or licitacion.duracion_valor is None:
        return None
    if licitacion.duracion_unidad is UnidadDuracion.MESES:
        return licitacion.fecha_adjudicacion + timedelta(
            days=30 * licitacion.duracion_valor
        )
    if licitacion.duracion_unidad is UnidadDuracion.HORAS:
        return licitacion.fecha_adjudicacion + timedelta(
            hours=licitacion.duracion_valor
        )
    return None


def revisar_garantias(
    licitacion: Licitacion, garantias: list[Garantia]
) -> list[Hallazgo]:
    """La garantía de fiel cumplimiento no puede vencer antes que el contrato.

    Regla nacida de un dato corrupto real: SENAMA declara un contrato de **36
    horas** y una garantía que vence el **29-12-2027**, tres años después. Nadie
    cauciona hasta 2027 algo que dura 36 horas.
    """
    termino = fecha_termino(licitacion)
    if termino is None:
        return []

    hallazgos = []
    for g in garantias:
        if g.tipo is not TipoGarantia.FIEL_CUMPLIMIENTO or g.fecha_vencimiento is None:
            continue
        exceso = (g.fecha_vencimiento - termino).days
        if exceso > MARGEN_GARANTIA.days:
            # La magnitud importa y la regla la reporta: SENAMA excede su plazo
            # unas mil veces (36 horas contra tres anios) y eso es absurdo; una
            # caucion 15 meses mas larga que un contrato de 24 puede ser
            # legitima. La regla senala; quien mira decide.
            dias_contrato = (
                max((termino - licitacion.fecha_adjudicacion).days, 1)
                if licitacion.fecha_adjudicacion
                else 1
            )
            veces = (dias_contrato + exceso) / dias_contrato
            hallazgos.append(
                Hallazgo(
                    identificador=licitacion.codigo,
                    motivo=Motivo.GARANTIA_VENCE_ANTES,
                    detalle=(
                        f"la garantía vence {g.fecha_vencimiento}, "
                        f"{exceso} días después de que el contrato termina "
                        f"({termino}, {licitacion.duracion_valor} "
                        f"{licitacion.duracion_unidad.value}). "
                        f"Cubre {veces:.1f}x la duración del contrato. "
                        "Uno de los dos datos podría estar mal cargado."
                    ),
                    valores={
                        "vence_garantia": str(g.fecha_vencimiento),
                        "termina_contrato": str(termino),
                        "duracion": f"{licitacion.duracion_valor} "
                        f"{licitacion.duracion_unidad.value}",
                        "dias_de_exceso": str(exceso),
                        "veces_la_duracion": f"{veces:.1f}",
                        "origen": g.fragmento_origen,
                    },
                )
            )
    return hallazgos


def revisar_montos(
    licitacion: Licitacion,
    monto_ocds: Decimal | None,
    monto_ejecutado: Decimal | None = None,
) -> list[Hallazgo]:
    """Cruza la suma de ítems contra OCDS y detecta precios unitarios.

    Son dos fuentes independientes: si no coinciden, algo cambió en la fuente.
    """
    hallazgos = []
    suma = licitacion.monto_adjudicado_por_items

    if monto_ocds is not None and suma > 0 and suma != monto_ocds:
        hallazgos.append(
            Hallazgo(
                identificador=licitacion.codigo,
                motivo=Motivo.MONTOS_NO_CUADRAN,
                detalle=(
                    f"la suma de ítems da {suma} y OCDS declara {monto_ocds}. "
                    "Dos fuentes independientes en desacuerdo."
                ),
                valores={"items": str(suma), "ocds": str(monto_ocds)},
            )
        )

    # Puerto Montt adjudica $783,19 —el litro de diésel— con órdenes por
    # millones. Es un convenio de precio unitario: el monto adjudicado NO es el
    # valor del contrato y no puede sumarse entre organismos.
    if monto_ejecutado is not None and suma > 0 and monto_ejecutado > suma * 10:
        hallazgos.append(
            Hallazgo(
                identificador=licitacion.codigo,
                motivo=Motivo.PRECIO_UNITARIO,
                detalle=(
                    f"lo ejecutado ({monto_ejecutado}) supera con holgura lo "
                    f"adjudicado ({suma}): parece un convenio de precio "
                    "unitario. El monto adjudicado no debe sumarse."
                ),
                valores={"ejecutado": str(monto_ejecutado), "adjudicado": str(suma)},
            )
        )
    return hallazgos


def revisar_licitacion(licitacion: Licitacion) -> list[Hallazgo]:
    """Marca lo que impide calcular el vencimiento, que es el eje de la demo."""
    if (
        licitacion.duracion_valor is not None
        and licitacion.duracion_unidad is UnidadDuracion.DESCONOCIDO
    ):
        return [
            Hallazgo(
                identificador=licitacion.codigo,
                motivo=Motivo.UNIDAD_DESCONOCIDA,
                detalle=(
                    f"duración {licitacion.duracion_valor} con unidad sin "
                    "decodificar. Solo 1=horas y 4=meses están confirmados. "
                    "NO se adivina: hay que investigar el valor nuevo."
                ),
            )
        ]
    return []


def cuarentenar(
    identificador: str, motivo: Motivo, detalle: str, crudo: Any, carpeta: Path
) -> Path:
    """Guarda un registro apartado con su motivo. La corrida continúa."""
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{identificador.replace('/', '_')}__{motivo.value}.json"
    destino.write_text(
        json.dumps(
            {
                "identificador": identificador,
                "motivo": motivo.value,
                "detalle": detalle,
                "crudo": crudo,
            },
            ensure_ascii=False,
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    log.warning("cuarentena %s (%s): %s", identificador, motivo.value, detalle)
    return destino


def validar_orden(crudo: dict[str, Any], carpeta: Path) -> OrdenCompra | None:
    """Valida una orden. Si no cumple, la aparta y devuelve `None`."""
    try:
        return OrdenCompra.desde_api(crudo)
    except Exception as e:  # el motivo se registra, nunca se traga
        cuarentenar(
            str(crudo.get("Codigo") or "desconocido"),
            Motivo.ESQUEMA,
            str(e),
            crudo,
            carpeta,
        )
        return None

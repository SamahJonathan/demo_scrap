"""Orquestación de una corrida completa.

Recorre el flujo de `docs/02-diseno.md` § 1: descubrimiento, detalle de órdenes,
licitaciones, OCDS, ficha web, validación, reconstrucción y persistencia.

**Ninguna fuente puede abortar la corrida.** Si OCDS no responde, el contrato se
guarda sin monto adjudicado; si la ficha cambia de estructura, se guarda sin
garantías. Lo que no se puede hacer es terminar "bien" sin decir qué faltó: por
eso cada fallo queda en las métricas.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date
from pathlib import Path

from contratos.cliente import Cliente, ErrorDeLaFuente, RespuestaDefinitiva
from contratos.fuentes import api_licitacion, api_oc, ocds
from contratos.fuentes.api_licitacion import SinFicha
from contratos.fuentes.ficha_web import FichaIlegible, parsear_garantias
from contratos.metricas import Metricas
from contratos.modelos import Garantia, Licitacion, OrdenCompra
from contratos.persistencia import guardar
from contratos.reconstruccion import reconstruir_cartera
from contratos.validacion import (
    Motivo,
    cuarentenar,
    revisar_garantias,
    revisar_licitacion,
    revisar_montos,
)

log = logging.getLogger(__name__)


def _ordenes_de(
    cliente: Cliente, fecha: date, n_con: int, n_sin: int, m: Metricas
) -> list[OrdenCompra]:
    """Descubre y detalla las órdenes de una fecha."""
    clasificadas = api_oc.descubrir(cliente, fecha, n_con, n_sin)
    codigos = [o.codigo for o in clasificadas.con_proceso + clasificadas.sin_proceso]
    m.suma("oc_listadas", len(codigos))

    lote = api_oc.detallar(cliente, codigos)
    for codigo, detalle in lote.cuarentena:
        m.cuarentena(codigo, Motivo.ESQUEMA, detalle)
    m.suma("oc_detalladas", len(lote.ordenes))
    return lote.ordenes


def _proceso_de(
    cliente: Cliente, codigo: str, m: Metricas, carpeta: Path
) -> tuple[Licitacion | None, list[Garantia]]:
    """Trae la licitación, su OCDS y sus garantías. Cada parte falla aparte."""
    try:
        lic = api_licitacion.detalle(cliente, codigo)
        m.suma("licitaciones")
    except (ValueError, ErrorDeLaFuente, RespuestaDefinitiva) as e:
        # Sin licitación el contrato existe igual, solo que sin su proceso.
        cuarentenar(codigo, Motivo.ESQUEMA, str(e), {"codigo": codigo}, carpeta)
        m.cuarentena(codigo, Motivo.ESQUEMA, str(e))
        return None, []

    # OCDS es opcional: aporta el monto adjudicado, no es imprescindible.
    monto_ocds = None
    try:
        datos = ocds.consultar(cliente, codigo)
        monto_ocds = datos.monto_adjudicado
        lic = lic.model_copy(
            update={
                "monto_adjudicado_total": datos.monto_adjudicado,
                "n_oferentes": datos.n_oferentes,
            }
        )
        m.suma("ocds")
    except Exception as e:  # noqa: BLE001 — se registra, la corrida sigue
        m.falla("ocds", f"{codigo}: {e}")

    # `Licitacion` es frozen: se copia con el campo nuevo, no se muta. Asignar
    # sobre ella lanza ValidationError, y hacerlo dentro del try de la ficha
    # se llevaba por delante TODAS las garantias de la corrida.
    #
    # Va en su propio try: una licitacion sin UrlActa no tiene ficha, pero eso
    # no debe parecerse a un parser roto.
    # Sin UrlActa queda en None: el dashboard no muestra enlace, y ya.
    with contextlib.suppress(SinFicha):
        lic = lic.model_copy(
            update={
                "url_ficha": api_licitacion.url_ficha(
                    lic, cliente.config.mp_web_base_url
                )
            }
        )

    garantias: list[Garantia] = []
    try:
        html = api_licitacion.bajar_ficha(cliente, lic)
        garantias = parsear_garantias(html, codigo)
        m.suma("garantias", len(garantias))
    except FichaIlegible as e:
        # "No pudimos leerlas" NO es "no tiene garantías": queda constancia.
        m.falla("ficha_web", str(e)[:80])
    except Exception as e:  # noqa: BLE001
        m.falla("ficha_web", f"{codigo}: {e}")

    m.hallazgos.extend(revisar_licitacion(lic))
    m.hallazgos.extend(revisar_garantias(lic, garantias))
    m.hallazgos.extend(revisar_montos(lic, monto_ocds))

    return lic, garantias


def correr(
    fechas: list[date],
    base: Path,
    n_con: int | None = None,
    n_sin: int | None = None,
    cliente: Cliente | None = None,
) -> Metricas:
    """Ejecuta el pipeline completo y devuelve sus métricas."""
    m = Metricas()
    propio = cliente is None
    c = cliente or Cliente()
    carpeta = Path("data/quarantine")

    try:
        cfg = c.config
        con = cfg.oc_con_proceso_por_fecha if n_con is None else n_con
        sin = cfg.oc_sin_proceso_por_fecha if n_sin is None else n_sin

        ordenes: list[OrdenCompra] = []
        for fecha in fechas:
            log.info("descubriendo %s", fecha)
            ordenes.extend(_ordenes_de(c, fecha, con, sin, m))

        licitaciones: dict[str, Licitacion] = {}
        garantias: dict[str, list[Garantia]] = {}
        pendientes = sorted(
            {o.codigo_licitacion for o in ordenes if o.codigo_licitacion}
        )
        for codigo in pendientes:
            lic, gs = _proceso_de(c, codigo, m, carpeta)
            if lic is not None:
                licitaciones[codigo] = lic
                if gs:
                    garantias[codigo] = gs

        cartera = reconstruir_cartera(ordenes, licitaciones, garantias)
        m.procesados = len(cartera.contratos)
        m.suma("contratos", m.procesados)

        conteo = guardar(base, cartera)
        m.suma("filas_persistidas", conteo["contrato"])

        m.requests_emitidos = c.emitidos
        m.aciertos_cache = c.aciertos_cache
    finally:
        if propio:
            c.cerrar()
        m.cerrar()

    return m

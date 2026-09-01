"""Línea de comandos del proyecto.

Nació sin subcomandos a propósito: **cada incremento agrega el suyo**, y así el
comando de verificación de ese incremento existe desde el momento en que se
escribe. Ver docs/03-plan-codificacion.md.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from contratos import __version__


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contratos",
        description=(
            "Reconstruye contratos públicos chilenos uniendo órdenes de compra, "
            "licitaciones, OCDS y la ficha web."
        ),
        epilog="Los subcomandos se agregan incremento a incremento.",
    )
    parser.add_argument(
        "--version", action="version", version=f"contratos {__version__}"
    )

    subs = parser.add_subparsers(dest="comando", metavar="<comando>")

    # --- descubrir (incremento 2) ------------------------------------------
    d = subs.add_parser(
        "descubrir",
        help="lista las órdenes de compra de una fecha y las clasifica",
    )
    d.add_argument(
        "--fecha", type=date.fromisoformat, required=True, metavar="AAAA-MM-DD"
    )
    d.add_argument(
        "--limite",
        type=int,
        default=None,
        help="tope para CADA grupo; por defecto usa el .env",
    )
    d.set_defaults(func=_cmd_descubrir)

    # --- detalle-oc (incremento 3) -----------------------------------------
    t = subs.add_parser(
        "detalle-oc",
        help="detalle de una orden de compra, con su enlace a la licitación",
    )
    t.add_argument("--codigo", required=True, metavar="1002-183-SE25")
    t.set_defaults(func=_cmd_detalle_oc)

    # --- licitacion (incremento 5) -----------------------------------------
    lic = subs.add_parser(
        "licitacion",
        help="detalle de una licitación, su OCDS y las garantías de su ficha",
    )
    lic.add_argument("--codigo", required=True, metavar="2678-1-LR25")
    lic.set_defaults(func=_cmd_licitacion)

    # --- analizar (incremento 9) -------------------------------------------
    a = subs.add_parser(
        "analizar", help="responde las siete preguntas de negocio con SQL"
    )
    a.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    a.add_argument("--meses", type=int, default=12, help="horizonte para P1")
    a.set_defaults(func=_cmd_analizar)

    # --- exportar (incremento 10) ------------------------------------------
    e = subs.add_parser(
        "exportar",
        help="genera dist/dashboard.html autocontenido (respaldo de la demo)",
    )
    e.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    e.add_argument("--destino", type=Path, default=Path("dist/dashboard.html"))
    e.set_defaults(func=_cmd_exportar)

    # --- correr (incremento 12) --------------------------------------------
    r = subs.add_parser(
        "correr", help="ejecuta el pipeline completo y reporta que paso"
    )
    r.add_argument(
        "--fecha",
        type=date.fromisoformat,
        action="append",
        metavar="AAAA-MM-DD",
        help="repetible; por defecto usa FECHAS_OC del .env",
    )
    r.add_argument("--limite", type=int, default=None, help="tope por grupo")
    r.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    r.add_argument(
        "--reporte", action="store_true", help="imprime el detalle de la corrida"
    )
    r.set_defaults(func=_cmd_correr)

    # --- inferir (incremento 13) -------------------------------------------
    i = subs.add_parser(
        "inferir",
        help="extrae clausulas y contradicciones. LENTO: minutos por documento",
    )
    i.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    i.add_argument("--limite", type=int, default=None, help="cuantas licitaciones")
    i.set_defaults(func=_cmd_inferir)

    # --- corridas -----------------------------------------------------------
    h = subs.add_parser(
        "corridas", help="compara las ultimas corridas y avisa que empeoro"
    )
    h.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    h.add_argument("--limite", type=int, default=10)
    h.set_defaults(func=_cmd_corridas)

    return parser


def _cmd_corridas(args: argparse.Namespace) -> int:
    """Historial de corridas. Un umbral fijo no ve una degradacion gradual."""
    from contratos.corridas import historial, tabla

    corridas = historial(args.base.parent / "corridas", limite=args.limite)
    print(tabla(corridas))
    return 0 if not corridas or corridas[0]["confiable"] else 1


def _cmd_inferir(args: argparse.Namespace) -> int:
    """Corre la capa de inferencia en LOTE. Nunca en la ruta de un request.

    Medido en el Spike 0: ~3,4 minutos por documento con el filtro de pasajes
    puesto, y varios GB de RAM. Por eso vive aca y no en el dashboard.
    """
    import json
    import time
    from datetime import datetime

    from contratos.cliente import Cliente
    from contratos.fuentes import api_licitacion
    from contratos.inferencia import elegir_modelo
    from contratos.inferencia.extraccion import procesar
    from contratos.inferencia.recuperacion import pasajes
    from contratos.persistencia import (
        abrir,
        guardar_clausula,
        guardar_discrepancia,
        licitaciones_guardadas,
    )
    from contratos.web.exportar import _texto_plano

    if not args.base.exists():
        print(f"no existe {args.base}. Corre primero el pipeline.")
        return 1

    codigos = licitaciones_guardadas(args.base)[: args.limite]
    if not codigos:
        print("no hay licitaciones en la base.")
        return 1

    modelo = elegir_modelo()
    print(f"modelo: {modelo.nombre} | licitaciones: {len(codigos)}")
    print("Esto tarda minutos por documento. Es lote, no interactivo.")

    clausulas = discrepancias = sin_pasajes = fallidas = 0
    t0 = time.time()

    # Donde el modelo NO hizo falta es tan publicable como lo que produjo: es
    # la unica forma de mostrar que se le llamo por necesidad y no por reflejo.
    detalle: list[dict[str, object]] = []
    destino = args.base.parent / "corridas" / "inferencia.json"

    def _volcar() -> None:
        """Se reescribe por documento: una corrida de una hora no se pierde."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(
                {
                    "momento": datetime.now().isoformat(timespec="seconds"),
                    "modelo": modelo.nombre,
                    "licitaciones": len(codigos),
                    # Cuantas se alcanzaron a procesar. Si es menor que
                    # `licitaciones`, la corrida se corto: el embudo describe
                    # solo lo que corrio, y decirlo es parte del dato.
                    "procesadas": len(detalle),
                    "resueltas_por_el_filtro": sin_pasajes,
                    "llamadas_al_modelo": len(codigos) - sin_pasajes - pendientes(),
                    "clausulas": clausulas,
                    "discrepancias": discrepancias,
                    "no_parseables": fallidas,
                    "segundos": round(time.time() - t0, 1),
                    "detalle": detalle,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def pendientes() -> int:
        return len(codigos) - len(detalle)

    with Cliente() as c:
        for n, codigo in enumerate(codigos, 1):
            lic = api_licitacion.detalle(c, codigo)
            texto = _texto_plano(api_licitacion.bajar_ficha(c, lic))

            if not pasajes(texto):
                # El filtro responde sin gastar una llamada al modelo.
                sin_pasajes += 1
                detalle.append({"codigo": codigo, "via": "filtro", "segundos": 0.0})
                _volcar()
                print(f"  [{n}/{len(codigos)}] {codigo}: sin pasajes -> null, 0 s")
                continue

            t = time.time()
            r = procesar(modelo, lic, texto, texto)
            dt = time.time() - t

            # Commit POR DOCUMENTO, no al final. Esta corrida puede durar horas
            # sobre la cartera completa: hacer un solo commit al terminar
            # significa que una caida en el documento 200 tira las 200 anteriores.
            with abrir(args.base) as con:
                if r.clausula:
                    guardar_clausula(con, r.clausula)
                    clausulas += 1
                if r.discrepancia:
                    guardar_discrepancia(con, r.discrepancia)
                    discrepancias += 1
            fallidas += len(r.respuestas_no_parseables)
            detalle.append(
                {
                    "codigo": codigo,
                    "via": "modelo",
                    "segundos": round(dt, 1),
                    "clausula": bool(r.clausula),
                }
            )
            _volcar()

            print(
                f"  [{n}/{len(codigos)}] {codigo}: {dt:.0f} s | "
                f"clausula={'si' if r.clausula else 'no'} "
                f"discrepancia={'si' if r.discrepancia else 'no'}"
            )

    print("")
    print(f"  clausulas extraidas   : {clausulas}")
    print(f"  discrepancias         : {discrepancias}")
    print(f"  sin pasajes (0 s)     : {sin_pasajes}")
    print(f"  respuestas no parseables: {fallidas}")
    print(f"  duracion              : {(time.time() - t0) / 60:.1f} min")
    print(f"  registro              : {destino}")
    return 0


def _cmd_correr(args: argparse.Namespace) -> int:
    from contratos.config import cargar
    from contratos.corridas import guardar, historial, instantanea, regresiones
    from contratos.pipeline import correr

    cfg = cargar()
    fechas = args.fecha or cfg.fechas_oc

    m = correr(fechas, args.base, n_con=args.limite, n_sin=args.limite)

    if args.reporte:
        print(m.reporte(cfg.max_quarantine_rate, min_registros=1))
    else:
        print(
            f"{m.procesados} contratos en {m.duracion:.1f}s "
            f"({m.requests_emitidos} requests, {m.aciertos_cache} de cache)"
        )

    # El registro se escribe SIEMPRE, tambien cuando la corrida sale mal: una
    # corrida que fallo es la que mas hay que poder comparar despues.
    reg = instantanea(m, cfg.max_quarantine_rate, 1, [str(f) for f in fechas])
    ruta = guardar(reg, args.base.parent / "corridas")
    print(f"  registro de la corrida: {ruta}")

    previas = historial(args.base.parent / "corridas", limite=2)
    if len(previas) >= 2:
        for aviso in regresiones(previas[0], previas[1]):
            print(f"  REGRESION: {aviso}")

    # Codigo distinto de cero si un umbral se supera: asi la corrida se puede
    # encadenar en un cron o en CI sin revisarla a ojo.
    return m.codigo_salida(cfg.max_quarantine_rate, min_registros=1)


def _cmd_exportar(args: argparse.Namespace) -> int:
    from contratos.web.exportar import generar

    if not args.base.exists():
        print(f"no existe {args.base}. Corre primero el pipeline.")
        return 1

    destino = generar(args.base, args.destino)
    kb = destino.stat().st_size / 1024
    print(f"{destino}  ({kb:.0f} KB)")
    print("Autocontenido: se abre con doble clic, sin servidor ni red.")
    return 0


def _cmd_analizar(args: argparse.Namespace) -> int:
    from contratos.analisis import PREGUNTAS, responder

    if not args.base.exists():
        print(f"no existe {args.base}. Corre primero el pipeline.")
        return 1

    for pregunta in PREGUNTAS:
        filas = responder(args.base, pregunta, meses=args.meses)
        print("")
        print(f"P{pregunta.numero}. {pregunta.titulo}")
        print("-" * 72)
        if not filas:
            print("   (sin resultados)")
            continue
        columnas = list(filas[0])
        print("   " + " | ".join(f"{c[:16]:<16}" for c in columnas))
        for f in filas[:12]:
            print("   " + " | ".join(f"{str(f[c])[:16]:<16}" for c in columnas))
        if len(filas) > 12:
            print(f"   ... {len(filas) - 12} filas más")
    return 0


def _cmd_licitacion(args: argparse.Namespace) -> int:
    from contratos.cliente import Cliente
    from contratos.fuentes import api_licitacion, ocds
    from contratos.fuentes.ficha_web import FichaIlegible, parsear_garantias

    with Cliente() as c:
        lic = api_licitacion.detalle(c, args.codigo)
        o = ocds.consultar(c, args.codigo)

        print(f"{lic.codigo}  {lic.nombre[:58]}")
        print(
            f"  publicación -> adjudicación : {lic.fecha_publicacion} a "
            f"{lic.fecha_adjudicacion}"
        )
        print(
            f"  duración                    : {lic.duracion_valor} "
            f"{lic.duracion_unidad.value}   renovable: {lic.es_renovable}"
        )
        print(f"  monto estimado   (ocds)     : {o.monto_estimado}")
        print(f"  monto adjudicado (ocds)     : {o.monto_adjudicado}")
        print(f"  suma de ítems    (api)      : {lic.monto_adjudicado_por_items}")
        cuadra = o.monto_adjudicado == lic.monto_adjudicado_por_items
        print(f"  ¿cuadran las dos fuentes?   : {'SI' if cuadra else 'NO'}")
        print(f"  oferentes        (ocds)     : {o.n_oferentes}")

        ruts = sorted({i.proveedor_rut for i in lic.items if i.proveedor_rut})
        if ruts:
            print(f"  adjudicado a {len(ruts)} proveedor(es):")
            for r in ruts:
                print(f"     {r:<16} {lic.monto_adjudicado_a(r)}")

        try:
            html = api_licitacion.bajar_ficha(c, lic)
            garantias = parsear_garantias(html, lic.codigo)
            print(f"  garantías (ficha web)       : {len(garantias)}")
            for g in garantias:
                unidad = "%" if g.monto_es_porcentaje else (g.moneda or "")
                print(
                    f"     {g.tipo.value:<20} {g.monto_valor} {unidad:<12} "
                    f"vence {g.fecha_vencimiento}"
                )
        except FichaIlegible as e:
            print(f"  garantías: NO SE PUDIERON LEER -> {e}")

        print(f"requests emitidos: {c.emitidos}  |  caché: {c.aciertos_cache}")
    return 0


def _cmd_detalle_oc(args: argparse.Namespace) -> int:
    import json

    from contratos.cliente import Cliente
    from contratos.fuentes.api_oc import detalle

    with Cliente() as c:
        o = detalle(c, args.codigo)
        salida = o.model_dump(mode="json")
        # Las tres derivadas no son campos: se calculan y conviene verlas.
        salida["tiene_proceso"] = o.tiene_proceso
        salida["es_comprometido"] = o.es_comprometido
        salida["es_ejecutado"] = o.es_ejecutado
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    return 0


def _cmd_descubrir(args: argparse.Namespace) -> int:
    from contratos.cliente import Cliente
    from contratos.fuentes.api_oc import clasificar, listar

    with Cliente() as c:
        cfg = c.config
        todas = listar(c, args.fecha)
        full = clasificar(todas, cfg)

        n_con = args.limite if args.limite is not None else cfg.oc_con_proceso_por_fecha
        n_sin = args.limite if args.limite is not None else cfg.oc_sin_proceso_por_fecha

        print(f"fecha {args.fecha}: {len(todas)} ordenes en el listado")
        print(
            f"  con proceso ({','.join(cfg.tipos_oc_con_licitacion)}): "
            f"{len(full.con_proceso)} -> muestra {min(n_con, len(full.con_proceso))}"
        )
        print(
            f"  sin proceso ({','.join(cfg.tipos_oc_sin_licitacion)}): "
            f"{len(full.sin_proceso)} -> muestra {min(n_sin, len(full.sin_proceso))}"
        )
        if full.otros:
            print(f"  tipo desconocido: {len(full.otros)} (no se adivina, se apartan)")
        print(f"requests emitidos: {c.emitidos}")
        print(f"aciertos de cache: {c.aciertos_cache}")

        for titulo, grupo, tope in (
            ("con proceso", full.con_proceso, n_con),
            ("sin proceso", full.sin_proceso, n_sin),
        ):
            print("")
            print(f"{titulo}:")
            for o in grupo[:tope]:
                print(f"  {o.codigo:<22} estado {o.codigo_estado:<3} {o.nombre[:44]}")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.comando is None:
        parser.print_help()
        return 0

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    codigo: int = args.func(args)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())

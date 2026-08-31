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
        "analizar", help="responde las cinco preguntas de negocio con SQL"
    )
    a.add_argument("--base", type=Path, default=Path("data/contratos.db"))
    a.add_argument("--meses", type=int, default=12, help="horizonte para P1")
    a.set_defaults(func=_cmd_analizar)

    return parser


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

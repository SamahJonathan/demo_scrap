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

    return parser


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

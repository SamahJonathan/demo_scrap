"""Línea de comandos del proyecto.

Nace sin subcomandos a propósito: **cada incremento agrega el suyo**, y así el
comando de verificación de ese incremento existe desde el momento en que se
escribe. Ver docs/03-plan-codificacion.md.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

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

    # Se crea vacío. Cada incremento registra su subcomando acá.
    parser.add_subparsers(dest="comando", metavar="<comando>")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.comando is None:
        parser.print_help()
        return 0

    # Red de seguridad para cuando haya subcomandos registrados.
    # parser.error() lanza SystemExit, por eso no hay return despues.
    parser.error(f"comando no reconocido: {args.comando}")


if __name__ == "__main__":
    raise SystemExit(main())

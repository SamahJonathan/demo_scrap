"""Qué pasó en una corrida, para diagnosticar sin adivinar.

Un pipeline que solo dice "listo" obliga a abrir la base para saber si sirvió.
Este módulo responde tres preguntas sin salir de la consola: cuánto costó, qué
se perdió por el camino, y si el resultado es confiable.

**La corrida sale con código distinto de cero cuando un umbral se supera.** Eso
es lo que permite encadenarla en un cron o en CI sin revisarla a ojo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from contratos.validacion import Hallazgo, Motivo


@dataclass
class Metricas:
    """Contadores de una corrida. Se llenan mientras avanza, no al final."""

    requests_emitidos: int = 0
    aciertos_cache: int = 0

    # Cuántos registros aportó cada fuente. Un cero acá delata una fuente caída
    # que el resto del pipeline disimuló.
    por_fuente: dict[str, int] = field(default_factory=dict)

    # Una fuente puede fallar sin abortar la corrida, pero tiene que constar.
    fuentes_fallidas: dict[str, str] = field(default_factory=dict)

    cuarentenados: list[tuple[str, Motivo, str]] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)

    procesados: int = 0
    # Bajo esta cobertura no hay fichas raras: hay un parser roto.
    min_cobertura_garantias: float = 0.5
    _inicio: float = field(default_factory=time.monotonic)
    duracion: float = 0.0

    def suma(self, fuente: str, cuantos: int = 1) -> None:
        self.por_fuente[fuente] = self.por_fuente.get(fuente, 0) + cuantos

    def falla(self, fuente: str, motivo: str) -> None:
        """Registra una fuente caída. La corrida sigue con las demás."""
        self.fuentes_fallidas[fuente] = motivo

    def cuarentena(self, identificador: str, motivo: Motivo, detalle: str) -> None:
        self.cuarentenados.append((identificador, motivo, detalle))

    def cerrar(self) -> None:
        self.duracion = time.monotonic() - self._inicio

    @property
    def tasa_cuarentena(self) -> float:
        return len(self.cuarentenados) / self.procesados if self.procesados else 0.0

    @property
    def ahorro_cache(self) -> float:
        total = self.requests_emitidos + self.aciertos_cache
        return self.aciertos_cache / total if total else 0.0

    # -- veredicto ----------------------------------------------------------

    def problemas(self, max_cuarentena: float, min_registros: int) -> list[str]:
        """Motivos por los que la corrida NO es confiable.

        Vacío significa que se puede publicar; cualquier cosa acá significa que
        no, y dice por qué.
        """
        motivos = []
        if self.tasa_cuarentena > max_cuarentena:
            motivos.append(
                f"tasa de cuarentena {self.tasa_cuarentena:.1%} sobre el máximo "
                f"{max_cuarentena:.1%}: eso no son datos malos, es un parser roto"
            )
        if self.procesados < min_registros:
            motivos.append(
                f"solo {self.procesados} registros, se esperaban al menos "
                f"{min_registros}: el descubrimiento falló en silencio"
            )
        # Una fuente que falla en UN registro se reporta pero no invalida la
        # corrida: una ficha sin tabla de garantias es normal. Lo que si la
        # invalida es que falle en muchos, y eso lo mide la cobertura.
        cubiertas = self.por_fuente.get("garantias", 0)
        con_proceso = self.por_fuente.get("licitaciones", 0)
        if con_proceso and cubiertas / con_proceso < self.min_cobertura_garantias:
            motivos.append(
                f"solo {cubiertas} garantías para {con_proceso} licitaciones "
                f"({cubiertas / con_proceso:.0%}, mínimo "
                f"{self.min_cobertura_garantias:.0%}): el parser de la ficha "
                "probablemente se rompió"
            )
        return motivos

    def codigo_salida(self, max_cuarentena: float, min_registros: int) -> int:
        return 1 if self.problemas(max_cuarentena, min_registros) else 0

    # -- reporte ------------------------------------------------------------

    def reporte(self, max_cuarentena: float = 0.05, min_registros: int = 1) -> str:
        lineas = [
            "",
            "=" * 66,
            f"CORRIDA — {self.duracion:.1f} s",
            "=" * 66,
            f"  requests emitidos   : {self.requests_emitidos}",
            f"  aciertos de caché   : {self.aciertos_cache} "
            f"({self.ahorro_cache:.0%} evitado)",
            f"  contratos           : {self.procesados}",
            "",
            "  registros por fuente:",
        ]
        for fuente, n in sorted(self.por_fuente.items()):
            lineas.append(f"     {fuente:<22} {n}")

        if self.fuentes_fallidas:
            lineas += ["", "  FUENTES CAÍDAS (las demás continuaron):"]
            for fuente, causa in self.fuentes_fallidas.items():
                lineas.append(f"     {fuente:<22} {causa[:44]}")

        lineas += [
            "",
            f"  cuarentena          : {len(self.cuarentenados)} "
            f"({self.tasa_cuarentena:.1%})",
        ]
        por_motivo: dict[str, int] = {}
        for _, motivo, _d in self.cuarentenados:
            por_motivo[motivo.value] = por_motivo.get(motivo.value, 0) + 1
        for nombre, n in sorted(por_motivo.items()):
            lineas.append(f"     {nombre:<38} {n}")

        if self.hallazgos:
            lineas += ["", "  HALLAZGOS (la fuente se contradice):"]
            for h in self.hallazgos[:8]:
                lineas.append(f"     {h.identificador:<18} {h.motivo.value}")
            if len(self.hallazgos) > 8:
                lineas.append(f"     ... {len(self.hallazgos) - 8} más")

        problemas = self.problemas(max_cuarentena, min_registros)
        lineas.append("")
        if problemas:
            lineas.append("  RESULTADO: NO CONFIABLE")
            lineas += [f"     - {p}" for p in problemas]
        else:
            lineas.append("  RESULTADO: corrida confiable")
        lineas.append("=" * 66)
        return "\n".join(lineas)

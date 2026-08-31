"""Capa de inferencia. **Fuera de la linea de corte: es upside.**

Su rol lo definio el Spike 0, y no es el que se habia previsto. No es un
extractor de campos: los campos estructurados salen de la API o de parseo
determinista, que es mas rapido y no razona sobre lo que extrae.

Hace dos cosas que ninguna alternativa deterministica puede hacer:

1. **Extraer clausulas en prosa libre** —causales de termino—, donde no hay
   tabla ni selector que valga.
2. **Verificar de forma cruzada** el campo estructurado contra el texto. En
   SENAMA, la seccion 7 declara "36 Horas" y la prosa dice "36 meses" tres
   veces. El modelo lee la prosa; la contradiccion se registra.
"""

from __future__ import annotations

from contratos.config import Config, cargar
from contratos.inferencia.interfaz import Modelo, ModeloNoDisponible

__all__ = ["Modelo", "ModeloNoDisponible", "elegir_modelo"]


def elegir_modelo(config: Config | None = None) -> Modelo:
    """Devuelve el adaptador segun INFERENCE_PROVIDER. Local por defecto."""
    cfg = config or cargar()
    if cfg.inference_provider == "hosted":
        from contratos.inferencia.hosted import ModeloHosted

        return ModeloHosted(cfg)

    from contratos.inferencia.local import ModeloLocal

    return ModeloLocal(cfg)

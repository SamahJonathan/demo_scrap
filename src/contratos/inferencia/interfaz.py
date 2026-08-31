"""Interfaz unica con dos adaptadores: local por defecto, hosted conmutable.

El fundamento es comercial y conviene decirlo sin adornos: el cliente objetivo
de un CLM enterprise procesa contratos confidenciales, y la pregunta que
enfrenta en cada venta es a donde van esos documentos. El adaptador local
responde "a ninguna parte".

**La parte honesta:** los datos de esta demo son publicos. La decision es
arquitectonica, no una necesidad de este caso.
"""

from __future__ import annotations

from typing import Protocol


class ModeloNoDisponible(RuntimeError):
    """El proveedor no responde. La corrida sigue sin la clausula."""


class Modelo(Protocol):
    """Lo unico que el pipeline necesita saber de un modelo."""

    nombre: str

    def responder(self, prompt: str) -> str:
        """Devuelve la respuesta cruda. **Sin parsear**: eso es de quien llama.

        Guardar el crudo permite auditar una respuesta mal formada en vez de
        perderla.
        """
        ...

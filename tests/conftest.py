"""Aislamiento del entorno para toda la suite.

Un test que depende de que una variable de entorno **no** exista es un test que
pasa por casualidad: en la máquina del desarrollador pasa, y en CI —donde el
workflow exporta esa variable— falla. Nos pasó con `MP_API_TICKET`.

`_env_file=None` desactiva el archivo .env, pero **no** las variables del
sistema: pydantic-settings las sigue leyendo. Este fixture las quita, así cada
test construye su propio entorno y el resultado no depende de dónde corre.
"""

from __future__ import annotations

import pytest

from contratos.config import Config, cargar

# Todo lo que Config puede leer del entorno, en mayúsculas.
_VARIABLES = tuple(nombre.upper() for nombre in Config.model_fields)


@pytest.fixture(autouse=True)
def entorno_aislado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quita del entorno cualquier variable que Config pueda leer."""
    for nombre in _VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    # `cargar()` está cacheada: si un test la usó, el siguiente heredaría su
    # resultado y dejaría de ser independiente.
    cargar.cache_clear()

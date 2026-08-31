"""Criterios de aceptación del Incremento 0.

Ninguno toca la red ni depende del .env real de la máquina: cada test construye
su propio entorno.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contratos.cli import main
from contratos.config import Config


def _config(**extra: object) -> Config:
    """Construye una Config sin leer el .env del disco."""
    base: dict[str, object] = {"mp_api_ticket": "ticket-de-prueba", "_env_file": None}
    base.update(extra)
    return Config(**base)  # type: ignore[arg-type]


def test_falta_el_ticket_y_el_error_nombra_la_variable() -> None:
    """Dado un entorno sin MP_API_TICKET, importar la config falla nombrándola."""
    with pytest.raises(ValidationError) as e:
        Config(_env_file=None)  # type: ignore[call-arg]
    assert "mp_api_ticket" in str(e.value).lower()


def test_la_config_valida_carga_con_los_defaults_del_diseno() -> None:
    c = _config()
    assert c.mp_api_ticket == "ticket-de-prueba"
    # Las tres fechas se eligieron midiendo volumen; ver docs/02-diseno.md.
    assert len(c.fechas_oc) == 3
    # Los tipos que traen CodigoLicitacion poblado.
    assert c.tipos_oc_con_licitacion == ["SE", "CC"]
    # Comprometido y ejecutado son cosas distintas y el modelo las separa.
    assert c.estados_comprometido != c.estados_ejecutado


def test_los_tipos_de_oc_se_normalizan_a_mayusculas() -> None:
    c = _config(tipos_oc_con_licitacion=[" se ", "cc"])
    assert c.tipos_oc_con_licitacion == ["SE", "CC"]


def test_una_proporcion_fuera_de_rango_falla() -> None:
    with pytest.raises(ValidationError) as e:
        _config(max_quarantine_rate=1.5)
    assert "proporción" in str(e.value)


def test_el_cli_sin_argumentos_muestra_la_ayuda_y_sale_en_cero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([]) == 0
    assert "contratos" in capsys.readouterr().out

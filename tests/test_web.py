"""Criterios de aceptación del Incremento 10.

El dashboard **lee filas, nunca infiere**: un endpoint que invocara al modelo
tardaría minutos y reservaría 7,34 GB. Estos tests lo dan por sentado y prueban
lo que sí hace.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from contratos.fuentes.ficha_web import parsear_garantias
from contratos.modelos import EstadoOC, Licitacion, OrdenCompra
from contratos.persistencia import guardar
from contratos.reconstruccion import reconstruir_cartera
from contratos.web.app import crear_app
from contratos.web.exportar import generar

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _orden(
    codigo: str,
    licitacion: str | None = None,
    organismo: str = "MOSTAZAL",
    monto: int = 1000,
    estado: EstadoOC = EstadoOC.RECEPCION_CONFORME,
) -> OrdenCompra:
    return OrdenCompra(
        codigo=codigo,
        codigo_licitacion=licitacion,
        codigo_estado=estado,
        organismo=organismo,
        organismo_rut="60.000.000-0",
        proveedor="PROVEEDOR DEMO",
        proveedor_rut="76.036.979-9",
        monto_total=Decimal(monto),
    )


@pytest.fixture
def base(tmp_path: Path) -> Path:
    ruta = tmp_path / "contratos.db"
    codigos = ("2678-1-LR25", "1300-43-LP24")
    licitaciones = {c: _lic(c) for c in codigos}
    garantias = {
        c: parsear_garantias(
            (FIXTURES / f"ficha_{c}.html").read_text(
                encoding="utf-8", errors="replace"
            ),
            c,
        )
        for c in codigos
    }
    ordenes = [
        _orden("1-1-SE25", "2678-1-LR25", "MOSTAZAL", 5000),
        _orden("2-1-SE25", "1300-43-LP24", "SENAMA", 2000),
        _orden("3-1-AG25", None, "MOSTAZAL", 700),
        _orden("4-1-SE25", None, "SENAMA", 999, estado=EstadoOC.CANCELADA),
    ]
    guardar(ruta, reconstruir_cartera(ordenes, licitaciones, garantias))
    return ruta


@pytest.fixture
def cliente(base: Path) -> TestClient:
    return TestClient(crear_app(base))


# --------------------------------------------------------------------------
# Salud: diagnostico, no solo un ping
# --------------------------------------------------------------------------


def test_salud_reporta_conteos_y_si_alcanzan(cliente: TestClient) -> None:
    r = cliente.get("/salud")
    assert r.status_code == 200

    d = r.json()
    assert d["contrato"] == 4
    assert d["licitacion"] == 2
    assert d["garantia"] == 4
    assert d["ultima_corrida"]
    # Cuatro contratos no alcanzan los 400 esperados: la corrida esta a medias.
    assert d["suficiente"] is False
    assert d["minimo"] == 400


def test_salud_avisa_si_no_hay_base(tmp_path: Path) -> None:
    """Un 503 explicito vale mas que un 500 sin explicacion."""
    cliente = TestClient(crear_app(tmp_path / "no-existe.db"))
    r = cliente.get("/salud")
    assert r.status_code == 503
    assert "Corre el pipeline" in r.json()["detail"]


# --------------------------------------------------------------------------
# Inicio
# --------------------------------------------------------------------------


def test_el_inicio_muestra_los_indicadores(cliente: TestClient) -> None:
    r = cliente.get("/")
    assert r.status_code == 200

    cuerpo = r.text
    assert "contratos" in cuerpo
    assert "sin licitación previa" in cuerpo
    assert "ejecutado" in cuerpo


def test_el_inicio_destaca_la_garantia_implausible(cliente: TestClient) -> None:
    """SENAMA: 36 horas de contrato con garantía hasta 2027."""
    cuerpo = cliente.get("/").text

    assert "incoherente" in cuerpo
    assert "1300-43-LP24" in cuerpo
    assert "36 horas" in cuerpo


# --------------------------------------------------------------------------
# Listado y detalle
# --------------------------------------------------------------------------


def test_el_listado_filtra_por_organismo(cliente: TestClient) -> None:
    todos = cliente.get("/contratos").text
    assert "1-1-SE25" in todos and "2-1-SE25" in todos

    solo_senama = cliente.get("/contratos", params={"organismo": "SENAMA"}).text
    assert "2-1-SE25" in solo_senama
    assert "1-1-SE25" not in solo_senama


def test_el_listado_filtra_las_que_no_tienen_proceso(cliente: TestClient) -> None:
    r = cliente.get("/contratos", params={"solo_con_proceso": "true"})
    assert "3-1-AG25" not in r.text
    assert "1-1-SE25" in r.text


def test_el_detalle_muestra_la_procedencia_de_cada_campo(
    cliente: TestClient,
) -> None:
    """Sin procedencia el dato no es defendible."""
    cuerpo = cliente.get("/contratos/1-1-SE25").text

    assert "api_oc" in cuerpo
    assert "api_licitacion" in cuerpo
    assert "derivado" in cuerpo


def test_el_detalle_de_una_huerfana_lo_explica_en_vez_de_dejarlo_vacio(
    cliente: TestClient,
) -> None:
    cuerpo = cliente.get("/contratos/3-1-AG25").text

    assert "Sin licitación previa" in cuerpo
    assert "no un error" in cuerpo
    assert "56%" in cuerpo, "dice cuan comun es el caso, no solo que es valido"


def test_un_contrato_inexistente_devuelve_404(cliente: TestClient) -> None:
    assert cliente.get("/contratos/no-existe").status_code == 404


# --------------------------------------------------------------------------
# Export autocontenido: el respaldo de la demo
# --------------------------------------------------------------------------


def test_el_export_es_un_solo_archivo_sin_dependencias(
    base: Path, tmp_path: Path
) -> None:
    """Se abre con doble clic: sin servidor, sin red, sin CDN."""
    destino = generar(base, tmp_path / "dist" / "dashboard.html")

    assert destino.exists()
    cuerpo = destino.read_text(encoding="utf-8")

    assert cuerpo.startswith("<!doctype html>")
    assert "<style>" in cuerpo, "el CSS va embebido"
    # Nada que pedir por red: ni scripts, ni hojas de estilo, ni imagenes.
    for externo in ("<script", "src=", 'rel="stylesheet"', "http://", "https://"):
        assert externo not in cuerpo, f"referencia externa: {externo}"


def test_el_export_trae_las_cinco_preguntas_y_los_datos(
    base: Path, tmp_path: Path
) -> None:
    cuerpo = generar(base, tmp_path / "d.html").read_text(encoding="utf-8")

    for numero in range(1, 6):
        assert f"P{numero}." in cuerpo
    assert "1300-43-LP24" in cuerpo, "los datos van embebidos, no se consultan"

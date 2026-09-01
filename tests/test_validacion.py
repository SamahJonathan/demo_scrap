"""Criterios de aceptación del Incremento 6 — el corazón de la calidad del dato.

Las reglas se prueban contra los casos REALES que las originaron, no contra
ejemplos inventados.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from contratos.fuentes.ficha_web import parsear_garantias
from contratos.modelos import Licitacion, UnidadDuracion
from contratos.validacion import (
    MARGEN_GARANTIA,
    Hallazgo,
    Motivo,
    Reporte,
    cuarentenar,
    fecha_termino,
    revisar_garantias,
    revisar_licitacion,
    revisar_monto_adjudicado,
    revisar_montos,
    validar_orden,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _garantias(codigo: str) -> list[Any]:
    html = (FIXTURES / f"ficha_{codigo}.html").read_text(
        encoding="utf-8", errors="replace"
    )
    return parsear_garantias(html, codigo)


# --------------------------------------------------------------------------
# La regla estrella, contra el caso real que la origino
# --------------------------------------------------------------------------


def test_senama_36_horas_es_implausible() -> None:
    """SENAMA: contrato de 36 HORAS con garantía hasta 2027-12-29.

    Nadie cauciona hasta 2027 algo que dura 36 horas. El dato está mal cargado
    en la fuente y la regla lo detecta cruzando dos campos independientes.
    """
    lic = _lic("1300-43-LP24")
    assert lic.duracion_unidad is UnidadDuracion.HORAS, "la fuente dice 36 horas"

    hallazgos = revisar_garantias(lic, _garantias("1300-43-LP24"))

    assert len(hallazgos) == 1
    h = hallazgos[0]
    assert h.motivo is Motivo.GARANTIA_VENCE_ANTES
    assert h.valores["vence_garantia"] == "2027-12-29"
    assert "36 horas" in h.valores["duracion"]
    # El hallazgo dice qué mirar, no elige un culpable.
    assert "mal cargado" in h.detalle


@pytest.mark.parametrize("codigo", ["2678-1-LR25", "2328-443-LR24"])
def test_los_contratos_coherentes_no_se_marcan(codigo: str) -> None:
    """Mostazal 10 meses y Puerto Montt 24 meses son plausibles."""
    assert revisar_garantias(_lic(codigo), _garantias(codigo)) == []


def test_el_margen_tolera_una_garantia_que_sobrevive_al_contrato() -> None:
    """Es normal exigir la caución un tiempo después de terminar."""
    lic = _lic("2678-1-LR25")
    termino = fecha_termino(lic)
    assert termino is not None
    # Justo dentro del margen: no se marca. Un año después: sí.
    assert MARGEN_GARANTIA.days == 365


def test_sin_unidad_decodificada_no_se_calcula_el_vencimiento() -> None:
    """No se inventa una fecha: eso corrompería el eje de la demo."""
    lic = Licitacion(
        codigo="1-1-LP25",
        fecha_adjudicacion=date(2025, 1, 1),
        duracion_valor=12,
        duracion_unidad=UnidadDuracion.DESCONOCIDO,
    )
    assert fecha_termino(lic) is None

    hallazgos = revisar_licitacion(lic)
    assert len(hallazgos) == 1
    assert hallazgos[0].motivo is Motivo.UNIDAD_DESCONOCIDA
    assert "NO se adivina" in hallazgos[0].detalle


# --------------------------------------------------------------------------
# Cruce entre fuentes independientes
# --------------------------------------------------------------------------


def test_los_items_cuadran_con_ocds_en_las_tres_licitaciones() -> None:
    esperado = {
        "2678-1-LR25": Decimal("441600000.0"),
        "1300-43-LP24": Decimal("1900000.0"),
        "2328-443-LR24": Decimal("783.193"),
    }
    for codigo, monto in esperado.items():
        assert revisar_montos(_lic(codigo), monto) == []


def test_un_desacuerdo_entre_fuentes_se_marca() -> None:
    hallazgos = revisar_montos(_lic("2678-1-LR25"), Decimal("999"))

    assert len(hallazgos) == 1
    assert hallazgos[0].motivo is Motivo.MONTOS_NO_CUADRAN
    assert "dos fuentes independientes" in hallazgos[0].detalle.lower()


def test_puerto_montt_se_detecta_como_precio_unitario() -> None:
    """Adjudica $783,19 —el litro de diésel— y ejecuta millones.

    El monto adjudicado no es el valor del contrato y no puede sumarse entre
    organismos: la pregunta de negocio 4 se responde con lo ejecutado.
    """
    lic = _lic("2328-443-LR24")
    hallazgos = revisar_montos(
        lic, Decimal("783.193"), monto_ejecutado=Decimal("50000000")
    )

    assert len(hallazgos) == 1
    assert hallazgos[0].motivo is Motivo.PRECIO_UNITARIO
    assert "no debe sumarse" in hallazgos[0].detalle


# --------------------------------------------------------------------------
# Cuarentena: un registro malo no aborta la corrida
# --------------------------------------------------------------------------


def test_una_orden_invalida_se_aparta_y_la_corrida_sigue(tmp_path: Path) -> None:
    crudo = json.loads(
        (FIXTURES / "oc_se_con_licitacion.json").read_text(encoding="utf-8")
    )["Listado"][0]
    malo = dict(crudo)
    malo["CodigoEstado"] = 99

    assert validar_orden(dict(crudo), tmp_path) is not None, "la buena pasa"
    assert validar_orden(malo, tmp_path) is None, "la mala se aparta"

    archivos = list(tmp_path.glob("*.json"))
    assert len(archivos) == 1
    guardado = json.loads(archivos[0].read_text(encoding="utf-8"))
    assert guardado["motivo"] == Motivo.ESQUEMA.value
    assert "99" in guardado["detalle"]
    assert guardado["crudo"]["Codigo"], "el crudo se conserva para reprocesar"


def test_el_archivo_de_cuarentena_nombra_el_motivo(tmp_path: Path) -> None:
    destino = cuarentenar("1002-1-SE25", Motivo.ESQUEMA, "algo", {"x": 1}, tmp_path)
    assert "1002-1-SE25" in destino.name
    assert Motivo.ESQUEMA.value in destino.name


# --------------------------------------------------------------------------
# Umbral: sobre cierto punto no son datos malos, es un parser roto
# --------------------------------------------------------------------------


def test_la_tasa_de_cuarentena_hace_fallar_la_corrida() -> None:
    r = Reporte(revisados=100)
    r.hallazgos = [
        Hallazgo(identificador=str(i), motivo=Motivo.ESQUEMA, detalle="")
        for i in range(3)
    ]
    assert r.tasa == pytest.approx(0.03)
    assert r.supera_umbral(0.05) is False

    r.hallazgos *= 4  # 12 %
    assert r.supera_umbral(0.05) is True


def test_una_corrida_sin_registros_no_divide_por_cero() -> None:
    assert Reporte().tasa == 0.0
    assert Reporte().supera_umbral(0.05) is False


# --------------------------------------------------------------------------
# El monto adjudicado que en realidad es un precio unitario
# --------------------------------------------------------------------------


def test_un_monto_irrisorio_con_garantias_delata_un_precio_unitario() -> None:
    """Caso real: seis licitaciones adjudicadas en exactamente $1 con boleta.

    Nadie cauciona un peso. OCDS está entregando el precio ofertado por
    unidad, no el total del convenio.
    """
    h = revisar_monto_adjudicado(
        _lic("2678-1-LR25"), Decimal("1"), tiene_garantias=True
    )

    assert h, "un contrato de $1 con garantías no es un contrato de $1"
    assert h[0].motivo is Motivo.PRECIO_UNITARIO
    assert "nadie cauciona" in h[0].detalle


def test_un_monto_irrisorio_SIN_garantias_no_se_marca() -> None:
    """Sin caución no hay contradicción: puede ser una compra chica de verdad."""
    assert (
        revisar_monto_adjudicado(
            _lic("2678-1-LR25"), Decimal("1"), tiene_garantias=False
        )
        == []
    )


def test_lo_ejecutado_que_desborda_lo_adjudicado_tambien_lo_delata() -> None:
    """Puerto Montt adjudica $783,19 el litro y sus órdenes suman millones."""
    h = revisar_monto_adjudicado(
        _lic("2328-443-LR24"),
        Decimal("783.19"),
        tiene_garantias=False,
        monto_ejecutado=Decimal("1500000000"),
    )

    assert h and h[0].motivo is Motivo.PRECIO_UNITARIO
    assert "supera diez veces" in h[0].detalle


def test_un_monto_normal_no_se_marca() -> None:
    """La regla no puede ensuciar los contratos sanos."""
    assert (
        revisar_monto_adjudicado(
            _lic("2678-1-LR25"),
            Decimal("140452700"),
            tiene_garantias=True,
            monto_ejecutado=Decimal("120000000"),
        )
        == []
    )


def test_sin_monto_declarado_no_hay_nada_que_juzgar() -> None:
    assert revisar_monto_adjudicado(_lic("2678-1-LR25"), None, True) == []
    assert revisar_monto_adjudicado(_lic("2678-1-LR25"), Decimal("0"), True) == []

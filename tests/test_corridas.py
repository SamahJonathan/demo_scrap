"""Criterios de aceptación del registro de corridas (Fase 4, punto 3).

Lo que se prueba no es que el JSON se escriba, sino que **detecte una caída que
el umbral fijo deja pasar**. Un scraper no se rompe de golpe: la fuente cambia
un id, la cobertura baja de 95% a 60%, y la corrida sigue en verde.
"""

from __future__ import annotations

import json
from pathlib import Path

from contratos.corridas import (
    guardar,
    historial,
    instantanea,
    regresiones,
    tabla,
)
from contratos.metricas import Metricas
from contratos.validacion import Motivo


def _metricas(procesados: int = 100, **fuentes: int) -> Metricas:
    m = Metricas()
    m.procesados = procesados
    m.requests_emitidos = 500
    for nombre, n in fuentes.items():
        m.suma(nombre, n)
    m.cerrar()
    return m


def _reg(**cambios: object) -> dict:
    base = instantanea(_metricas(), 0.05, 1, ["2025-01-15"])
    base.update(cambios)
    return base


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------


def test_el_registro_guarda_el_veredicto_con_sus_motivos(tmp_path: Path) -> None:
    """ "NO CONFIABLE" sin la razón al lado no sirve dentro de un mes."""
    m = _metricas(procesados=0)
    reg = instantanea(m, 0.05, min_registros=10, fechas=["2025-01-15"])

    assert reg["confiable"] is False
    assert reg["problemas"], "el veredicto viaja con su causa"
    assert "10" in reg["problemas"][0]

    ruta = guardar(reg, tmp_path / "corridas")
    assert json.loads(ruta.read_text(encoding="utf-8"))["problemas"] == reg["problemas"]


def test_el_nombre_del_archivo_es_valido_en_windows(tmp_path: Path) -> None:
    """Los dos puntos del ISO no son un nombre de archivo válido en Windows."""
    ruta = guardar(_reg(), tmp_path / "corridas")
    assert ":" not in ruta.name
    assert ruta.exists()


def test_el_historial_viene_de_la_mas_nueva_a_la_mas_vieja(tmp_path: Path) -> None:
    d = tmp_path / "corridas"
    for momento in ("2025-01-01T10:00:00", "2025-03-01T10:00:00"):
        guardar(_reg(momento=momento), d)

    orden = [c["momento"] for c in historial(d)]
    assert orden == ["2025-03-01T10:00:00", "2025-01-01T10:00:00"]


def test_sin_corridas_no_revienta(tmp_path: Path) -> None:
    assert historial(tmp_path / "no-existe") == []
    assert "No hay corridas" in tabla([])


# --------------------------------------------------------------------------
# Lo que un umbral fijo NO ve
# --------------------------------------------------------------------------


def test_una_caida_de_registros_se_avisa_aunque_ambas_pasen_el_umbral() -> None:
    """Las dos corridas son "confiables" y aun así algo se rompió."""
    anterior = _reg(procesados=100)
    actual = _reg(procesados=60)

    assert anterior["confiable"] and actual["confiable"]
    avisos = regresiones(actual, anterior)

    assert avisos, "una caída del 40% no puede pasar en silencio"
    assert "100" in avisos[0] and "60" in avisos[0]


def test_una_caida_pequena_no_es_una_regresion() -> None:
    """Menos licitaciones un día es normal. El aviso tiene que significar algo."""
    assert regresiones(_reg(procesados=95), _reg(procesados=100)) == []


def test_una_fuente_que_dejo_de_aportar_se_delata_aunque_el_total_aguante() -> None:
    """El síntoma clásico de un selector que la fuente cambió."""
    anterior = _reg(por_fuente={"licitaciones": 50, "garantias": 48})
    actual = _reg(por_fuente={"licitaciones": 50, "garantias": 0})

    avisos = regresiones(actual, anterior)
    assert any("garantias" in a for a in avisos)
    assert any("aporta 0" in a for a in avisos)


def test_una_fuente_recien_caida_se_distingue_de_una_que_ya_fallaba() -> None:
    anterior = _reg(fuentes_fallidas={"ficha_web": "timeout"})
    actual = _reg(fuentes_fallidas={"ficha_web": "timeout", "ocds": "404"})

    avisos = regresiones(actual, anterior)
    assert [a for a in avisos if "ocds" in a]
    assert not [a for a in avisos if "ficha_web" in a], "esa ya fallaba, no es nueva"


def test_la_tabla_dice_explicitamente_que_no_hubo_regresiones() -> None:
    """El silencio es ambiguo: podría ser que nadie miró."""
    salida = tabla(
        [_reg(momento="2025-03-01T10:00:00"), _reg(momento="2025-01-01T10:00:00")]
    )
    assert "sin regresiones" in salida


def test_la_tabla_muestra_el_veredicto_de_cada_corrida() -> None:
    m = _metricas(procesados=0)
    mala = instantanea(m, 0.05, min_registros=10, fechas=[])
    salida = tabla([mala])

    assert "NO CONFIABLE" in salida
    assert "PROBLEMA:" in salida


def test_la_cuarentena_se_desglosa_por_motivo() -> None:
    m = _metricas()
    m.cuarentena("1-1-SE25", Motivo.ESQUEMA, "falta el monto")
    m.cuarentena("2-1-SE25", Motivo.ESQUEMA, "falta el monto")

    reg = instantanea(m, 0.05, 1, [])
    assert reg["cuarentena_por_motivo"][Motivo.ESQUEMA.value] == 2


def test_el_historial_ignora_los_archivos_que_no_son_corridas(tmp_path: Path) -> None:
    """El mismo directorio guarda el registro de inferencia.

    Leerlo como si fuera una corrida tumbaba `cli corridas` con KeyError.
    """
    import json

    d = tmp_path / "corridas"
    guardar(_reg(momento="2026-08-31T10:00:00"), d)
    (d / "inferencia.json").write_text(
        json.dumps({"modelo": "llama3.1:8b", "licitaciones": 218}), encoding="utf-8"
    )

    corridas = historial(d)

    assert len(corridas) == 1
    assert "procesados" in corridas[0]
    assert "sin regresiones" in tabla(corridas) or corridas  # no revienta


def test_una_fuente_que_cae_a_cero_se_delata_aunque_el_total_no_cambie() -> None:
    """El caso real: 299 garantías pasaron a 0 y los 450 contratos siguieron.

    Sin comparar contra la corrida anterior, el total intacto lo disimulaba.
    """
    anterior = _reg(procesados=450, por_fuente={"licitaciones": 218, "garantias": 299})
    actual = _reg(procesados=450, por_fuente={"licitaciones": 218, "garantias": 0})

    avisos = regresiones(actual, anterior)
    assert any("garantias" in a and "299" in a for a in avisos)

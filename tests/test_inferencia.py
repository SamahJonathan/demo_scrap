"""Criterios de aceptación del Incremento 13.

**Sin modelo real.** Un doble devuelve respuestas fijas y cuenta cuántas veces
lo llamaron: eso es lo que permite verificar en segundos algo que en producción
tarda 3,4 minutos por documento.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from contratos.config import Config
from contratos.inferencia import elegir_modelo
from contratos.inferencia.extraccion import (
    extraer_causales,
    procesar,
    verificar_duracion,
)
from contratos.inferencia.hosted import ModeloHosted
from contratos.inferencia.interfaz import ModeloNoDisponible
from contratos.inferencia.local import ModeloLocal
from contratos.inferencia.recuperacion import extraer, pasajes
from contratos.modelos import Licitacion, UnidadDuracion

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class ModeloDoble:
    """Devuelve respuestas fijas y cuenta las llamadas."""

    def __init__(self, *respuestas: str) -> None:
        self.nombre = "doble"
        self._respuestas = list(respuestas)
        self.llamadas = 0

    def responder(self, prompt: str) -> str:
        self.llamadas += 1
        return self._respuestas.pop(0) if self._respuestas else "{}"


class ModeloCaido:
    nombre = "caido"

    def responder(self, prompt: str) -> str:
        raise ModeloNoDisponible("Ollama no responde")


def _lic(codigo: str) -> Licitacion:
    datos = json.loads((FIXTURES / f"lic_{codigo}.json").read_text(encoding="utf-8"))
    crudo: dict[str, Any] = datos["Listado"][0]
    return Licitacion.desde_api(crudo)


def _texto(codigo: str) -> str:
    """Texto plano de la ficha, como lo recibe la capa de inferencia."""
    import re
    from html import unescape

    html = (FIXTURES / f"ficha_{codigo}.html").read_text(
        encoding="utf-8", errors="replace"
    )
    cuerpo = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cuerpo)))


# --------------------------------------------------------------------------
# El filtro de recuperacion
# --------------------------------------------------------------------------


def test_el_filtro_devuelve_solo_las_ventanas_de_las_palabras_clave() -> None:
    texto = "relleno " * 500 + "causales de término anticipado" + " relleno" * 500
    ventanas = pasajes(texto)

    assert len(ventanas) == 1
    recorte = extraer(texto)
    assert "término anticipado" in recorte
    assert len(recorte) < len(texto) / 3, "se envía una fracción, no el documento"


def test_las_ventanas_que_se_solapan_se_fusionan() -> None:
    texto = "x" * 100 + "término anticipado" + "y" * 50 + "resciliación" + "z" * 100
    assert len(pasajes(texto)) == 1, "dos claves cercanas son una sola ventana"


def test_mostazal_no_tiene_pasajes_de_termino() -> None:
    """Su ficha habla de readjudicación, que es otra cosa."""
    assert pasajes(_texto("2678-1-LR25")) == []


@pytest.mark.parametrize("codigo", ["1300-43-LP24", "2328-443-LR24"])
def test_las_que_si_tienen_causales_producen_pasajes(codigo: str) -> None:
    assert pasajes(_texto(codigo))


# --------------------------------------------------------------------------
# Sin pasajes NO se llama al modelo
# --------------------------------------------------------------------------


def test_sin_pasajes_responde_null_sin_llamar_al_modelo() -> None:
    """El fallo más caro del spike, resuelto en microsegundos.

    Con el documento completo, el modelo inventó una readjudicación como causal
    de término tras 8 minutos de cómputo.
    """
    modelo = ModeloDoble('{"causales": ["inventada"]}')
    lic = _lic("2678-1-LR25")
    clausula, crudo = extraer_causales(modelo, lic, "sin nada relevante")

    assert clausula is None
    assert crudo is None
    assert modelo.llamadas == 0, "no se gastó ni una llamada"


# --------------------------------------------------------------------------
# Trazabilidad: sin ella no entra
# --------------------------------------------------------------------------


def test_toda_clausula_extraida_declara_su_origen() -> None:
    modelo = ModeloDoble('{"causales": ["incumplimiento grave", "quiebra"]}')
    seccion = "relleno " * 200 + "causales de término anticipado" + " y mas"

    clausula, _ = extraer_causales(modelo, _lic("1300-43-LP24"), seccion)

    assert clausula is not None
    assert clausula.posicion_inicio >= 0
    assert clausula.fragmento_origen, "sin fragmento no entra"
    assert clausula.modelo == "doble", "queda registrado qué modelo lo produjo"
    assert "incumplimiento grave" in clausula.texto


def test_una_respuesta_no_parseable_se_conserva_y_no_pierde_el_contrato() -> None:
    modelo = ModeloDoble("esto no es JSON, es una disculpa del modelo")
    seccion = "x " * 200 + "término anticipado" + " y"

    clausula, crudo = extraer_causales(modelo, _lic("1300-43-LP24"), seccion)

    assert clausula is None
    assert crudo is not None, "el crudo se guarda para auditarlo"
    assert "disculpa" in crudo


# --------------------------------------------------------------------------
# Verificacion cruzada: el hallazgo central del spike
# --------------------------------------------------------------------------


def test_senama_produce_una_discrepancia_con_ambos_valores() -> None:
    """La sección 7 dice `36 Horas`; la prosa dice `36 meses` tres veces.

    Ninguno se corrige: se registran los dos y quien mira decide.
    """
    lic = _lic("1300-43-LP24")
    assert lic.duracion_unidad is UnidadDuracion.HORAS

    modelo = ModeloDoble('{"valor": 36, "unidad": "meses"}')
    d, _ = verificar_duracion(modelo, lic, _texto("1300-43-LP24"))

    assert d is not None
    assert d.valor_estructurado == "36 horas"
    assert d.valor_prosa == "36 meses"
    assert d.campo == "duracion"


def test_si_la_prosa_coincide_con_el_campo_no_hay_discrepancia() -> None:
    lic = _lic("2328-443-LR24")
    modelo = ModeloDoble('{"valor": 24, "unidad": "meses"}')

    d, _ = verificar_duracion(modelo, lic, _texto("2328-443-LR24"))
    assert d is None


def test_sin_duracion_declarada_no_hay_nada_que_verificar() -> None:
    modelo = ModeloDoble('{"valor": 12, "unidad": "meses"}')
    d, _ = verificar_duracion(modelo, Licitacion(codigo="1-1-LP25"), "texto")

    assert d is None
    assert modelo.llamadas == 0


# --------------------------------------------------------------------------
# Nada de esto puede perder un contrato
# --------------------------------------------------------------------------


def test_si_el_modelo_no_responde_la_corrida_sigue() -> None:
    """La inferencia es upside: el contrato ya existe sin ella."""
    r = procesar(ModeloCaido(), _lic("1300-43-LP24"), _texto("1300-43-LP24"), "x")

    assert r.clausula is None
    assert r.discrepancia is None


# --------------------------------------------------------------------------
# Los dos adaptadores
# --------------------------------------------------------------------------


def _config(**extra: object) -> Config:
    base: dict[str, object] = {"_env_file": None, "mp_api_ticket": "t"}
    base.update(extra)
    return Config(**base)  # type: ignore[arg-type]


def test_el_proveedor_por_defecto_es_local() -> None:
    """Local por defecto: es el argumento de confidencialidad del proyecto."""
    assert isinstance(elegir_modelo(_config()), ModeloLocal)


def test_se_conmuta_a_hosted_por_variable_de_entorno() -> None:
    """Sin tocar el resto del código."""
    modelo = elegir_modelo(_config(inference_provider="hosted"))
    assert isinstance(modelo, ModeloHosted)


def test_hosted_sin_clave_avisa_en_vez_de_fallar_oscuro() -> None:
    modelo = ModeloHosted(_config(inference_provider="hosted"))
    with pytest.raises(ModeloNoDisponible, match="HOSTED_INFERENCE_API_KEY"):
        modelo.responder("hola")


def test_el_adaptador_local_fija_num_ctx_explicito() -> None:
    """El default de Ollama es 2048 y recortaría el 92% sin avisar.

    Ese fallo casi arruina el Spike 0: el modelo habría visto el 8% del
    documento y devuelto null en todo.
    """
    fuente = Path("src/contratos/inferencia/local.py").read_text(encoding="utf-8")
    assert '"num_ctx"' in fuente

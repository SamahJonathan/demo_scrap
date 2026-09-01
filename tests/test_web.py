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


def test_el_inicio_destaca_la_garantia_con_unidad_sospechosa(
    cliente: TestClient,
) -> None:
    """SENAMA: 36 horas de contrato con garantía hasta 2027.

    La portada usa el MISMO criterio que /garantias: separa la unidad
    sospechosa del campo sin llenar. Antes decía "12 incoherentes" para dos
    defectos distintos, y sin enlace a la fuente.
    """
    cuerpo = cliente.get("/").text

    assert "unidad del plazo" in cuerpo
    assert "1300-43-LP24" in cuerpo
    assert "36 horas" in cuerpo
    assert "meses cargados como horas" in cuerpo, "dice cuál es la hipótesis"


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


# --------------------------------------------------------------------------
# /estado: la version para personas de /salud
# --------------------------------------------------------------------------


def test_estado_muestra_los_mismos_datos_pero_legibles(cliente: TestClient) -> None:
    """El menu enlaza aca: un visitante no deberia encontrarse JSON crudo."""
    r = cliente.get("/estado")
    assert r.status_code == 200

    cuerpo = r.text
    assert "Estado de la corrida" in cuerpo
    assert "contratos" in cuerpo and "garantías" in cuerpo
    # Y ofrece el JSON a quien lo necesite.
    assert 'href="/salud"' in cuerpo


def test_estado_explica_una_corrida_parcial_en_vez_de_solo_marcarla(
    cliente: TestClient,
) -> None:
    """Cuatro contratos no son un error del servidor: la base es parcial."""
    cuerpo = cliente.get("/estado").text

    assert "Corrida parcial" in cuerpo
    assert "no es un error del servidor" in cuerpo.lower()


def test_salud_sigue_siendo_json_para_la_monitorizacion(cliente: TestClient) -> None:
    """El script de despliegue y cualquier monitor lo consumen asi."""
    r = cliente.get("/salud")
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["contrato"] == 4


# --------------------------------------------------------------------------
# Congruencia con el objetivo
# --------------------------------------------------------------------------

# El objetivo nombra tres cosas: que relicitar, que renovar y que cauciones
# siguen vivas. El menu debe ofrecerlas; lo operativo va al pie.


def test_el_menu_ofrece_las_areas_y_la_entidad_compartida(
    cliente: TestClient,
) -> None:
    """El menú se organiza por QUIÉN pregunta, no por pregunta suelta.

    Es la propuesta de valor de un CLM hecha visible: no son cinco sistemas,
    es una entidad que cinco áreas leen distinto. `/contratos` va primero
    porque es la entidad que todas comparten.
    """
    encabezado = cliente.get("/").text.split("</header>")[0]

    assert 'href="/contratos"' in encabezado, "la entidad compartida"
    for area in ("/legal", "/compras", "/finanzas", "/comercial"):
        assert f'href="{area}"' in encabezado, area


def test_las_tres_preguntas_del_objetivo_siguen_alcanzables(
    cliente: TestClient,
) -> None:
    """Reorganizar por área no puede esconder el objetivo.

    Qué relicitar y qué renovar viven en Compras; qué cauciones siguen vivas,
    en Legal. Si un día dejan de enlazarse, el menú dejó de servir al objetivo.
    """
    assert 'href="/vencimientos"' in cliente.get("/compras").text
    # "Qué cauciones siguen vivas" ya no es un enlace: es la propia página.
    assert "cauciones vigentes" in cliente.get("/legal").text


def test_lo_operativo_no_ocupa_el_menu(cliente: TestClient) -> None:
    """/estado le sirve a quien mantiene el pipeline, no al gestor."""
    cuerpo = cliente.get("/").text
    encabezado, pie = cuerpo.split("</header>")[0], cuerpo.split("<footer>")[-1]

    assert 'href="/estado"' not in encabezado
    assert 'href="/estado"' in pie


def test_vencimientos_dice_lo_accionable(cliente: TestClient) -> None:
    cuerpo = cliente.get("/vencimientos", params={"meses": 36}).text

    assert "relicitar" in cuerpo or "renovar" in cuerpo
    # Y explica por que faltan las compras puntuales, en vez de omitirlas.
    assert "no tiene vencimiento que vigilar" in cuerpo


def test_legal_separa_la_unidad_sospechosa_del_campo_sin_llenar(
    cliente: TestClient,
) -> None:
    """Dos defectos distintos no pueden compartir una sola alerta.

    Una duración declarada en CERO es un campo que el organismo no llenó. Una
    duración en HORAS con una caución de años es una unidad mal cargada. Se
    diagnostican distinto, así que se muestran distinto.
    """
    cuerpo = cliente.get("/legal").text

    assert "1300-43-LP24" in cuerpo, "SENAMA, 36 horas contra 2027"
    assert "unidad sospechosa" in cuerpo
    assert "meses cargados como horas" in cuerpo, "dice cuál es la hipótesis"
    assert "no se corrige" in cuerpo.lower(), "se marca, no se arregla"


def test_legal_dice_por_que_hubo_que_scrapear(cliente: TestClient) -> None:
    """Es el caso que justifica la capa de scraping."""
    cuerpo = cliente.get("/legal").text
    assert "54 campos" in cuerpo and "OCDS" in cuerpo


def test_plazos_vive_en_compras_y_muestra_percentiles(cliente: TestClient) -> None:
    """Convierte el vencimiento en un plazo para actuar.

    Ya no está en el menú: es una pregunta de Compras, no de todos.
    """
    encabezado = cliente.get("/compras").text
    assert 'href="/plazos"' in encabezado

    cuerpo = cliente.get("/plazos").text
    assert "Mediana" in cuerpo and "p75" in cuerpo
    assert "el promedio no describe a nadie" in cuerpo


def test_la_portada_dice_sobre_que_universo_habla(cliente: TestClient) -> None:
    """Un panel de vencimientos que omite lo que deja fuera miente."""
    cuerpo = cliente.get("/").text

    assert "Sobre qué parte de la cartera" in cuerpo
    assert "no_declarado" in cuerpo
    assert "compra puntual" in cuerpo


# --------------------------------------------------------------------------
# Lo que produjo el modelo se muestra CON su trazabilidad
# --------------------------------------------------------------------------


def test_la_ficha_de_contrato_NO_publica_las_causales(base: Path) -> None:
    """Retiradas del dashboard por decisión: no eran reportería.

    Una lista de causales por contrato no se compara ni se agrega, y cuatro de
    cada cinco son idénticas entre organismos porque la ley las impone. Lo que
    el modelo produjo sigue auditable en /inferencia, con su trazabilidad.
    """
    from contratos.modelos import ClausulaExtraida
    from contratos.persistencia import abrir, guardar_clausula

    with abrir(base) as con:
        guardar_clausula(
            con,
            ClausulaExtraida(
                licitacion_codigo="1300-43-LP24",
                tipo="causales_termino",
                texto="quiebra del proveedor",
                fragmento_origen="…término anticipado…",
                posicion_inicio=10,
                modelo="llama3.1:8b",
            ),
        )

    cliente = TestClient(crear_app(base))

    for ruta in ("/contratos/2-1-SE25", "/legal"):
        cuerpo = cliente.get(ruta).text
        assert "quiebra del proveedor" not in cuerpo, ruta
        assert "Causales de término" not in cuerpo, ruta

    # Pero el dato NO se borró: sigue auditable donde corresponde.
    auditoria = cliente.get("/inferencia").text
    assert "quiebra del proveedor" in auditoria
    assert "llama3.1:8b" in auditoria


# --------------------------------------------------------------------------
# La pagina que muestra donde intervino el modelo
# --------------------------------------------------------------------------


def _registro(base: Path, **cambios: object) -> None:
    import json

    datos: dict[str, Any] = {
        "momento": "2026-08-31T21:00:00",
        "modelo": "llama3.1:8b",
        "licitaciones": 100,
        "resueltas_por_el_filtro": 67,
        "llamadas_al_modelo": 33,
        "clausulas": 12,
        "discrepancias": 0,
        "no_parseables": 0,
        "segundos": 1800.0,
        "detalle": [],
    }
    datos.update(cambios)
    # `detalle` es la fuente de verdad de cuántas se procesaron: la app deriva
    # `procesadas` de su largo. Un fixture con detalle vacío describiría una
    # corrida que no procesó nada, diga lo que diga el contador.
    procesadas = int(datos.pop("procesadas", datos["licitaciones"]))
    datos["detalle"] = [
        {"codigo": f"{i}-1-LE25", "via": "filtro", "segundos": 0.0}
        for i in range(procesadas)
    ]
    d = base.parent / "corridas"
    d.mkdir(parents=True, exist_ok=True)
    (d / "inferencia.json").write_text(
        json.dumps(datos, ensure_ascii=False), encoding="utf-8"
    )


def test_la_pagina_muestra_cuantos_documentos_NO_necesitaron_el_modelo(
    base: Path,
) -> None:
    """El embudo es el dato honesto: publicar solo lo producido exagera su peso."""
    _registro(base)
    html = TestClient(crear_app(base)).get("/inferencia").text

    assert "67" in html, "los resueltos por el filtro son el número principal"
    assert "no necesitaron el modelo" in html


def test_sin_registro_falta_el_embudo_pero_NO_se_esconden_las_clausulas(
    base: Path,
) -> None:
    """Un dato real no puede desaparecer porque falte un archivo de metadatos.

    Pasó en el servidor: el `.db` viajaba con sus cláusulas y el registro de
    la corrida no, así que la página decía "no se ha corrido" y ocultaba tres
    cláusulas que sí estaban publicadas.
    """
    from contratos.modelos import ClausulaExtraida
    from contratos.persistencia import abrir, guardar_clausula

    with abrir(base) as con:
        guardar_clausula(
            con,
            ClausulaExtraida(
                licitacion_codigo="1300-43-LP24",
                tipo="causales_termino",
                texto="quiebra del proveedor",
                fragmento_origen="…término anticipado…",
                posicion_inicio=10,
                modelo="llama3.1:8b",
            ),
        )

    html = TestClient(crear_app(base)).get("/inferencia").text

    assert "No hay registro" in html, "se declara que falta el embudo"
    assert "quiebra del proveedor" in html, "pero el dato real se muestra igual"
    assert "llama3.1:8b" in html, "con su trazabilidad"


def test_cero_discrepancias_se_explica_como_resultado_no_como_fallo(
    base: Path,
) -> None:
    _registro(base)
    html = TestClient(crear_app(base)).get("/inferencia").text
    assert "Cero es un resultado" in html
    assert "regla SQL" in html, "dice quién sí detecta el caso conocido"


def test_la_pagina_declara_que_no_puede_tocar_el_modelo(base: Path) -> None:
    """Sin esa tabla, la página vendería al modelo en vez de acotarlo."""
    _registro(base)
    html = TestClient(crear_app(base)).get("/inferencia").text

    assert "prohibido tocar" in html
    for dato in ("Fechas del proceso", "Garantías", "Montos"):
        assert dato in html


def test_el_metodo_no_ocupa_el_menu_del_gestor(base: Path) -> None:
    """Misma regla que /estado: el menú es para las tres preguntas del objetivo."""
    _registro(base)
    cuerpo = TestClient(crear_app(base)).get("/").text
    encabezado, pie = cuerpo.split("</header>")[0], cuerpo.split("<footer>")[-1]

    assert 'href="/inferencia"' not in encabezado
    assert 'href="/inferencia"' in pie


def test_una_garantia_marcada_enlaza_a_la_ficha_original(base: Path) -> None:
    """Lo que marcamos como dudoso tiene que poder contrastarse en un clic.

    Sin el enlace, el usuario tiene que creernos. Con él, abre el documento de
    Mercado Público y lo comprueba con sus propios ojos.
    """
    from contratos.persistencia import abrir

    url = (
        "https://www.mercadopublico.cl/Procurement/Modules/RFB/"
        "DetailsAcquisition.aspx?qs=TOKEN"
    )
    with abrir(base) as con:
        con.execute(
            "UPDATE licitacion SET url_ficha = ? WHERE codigo = ?",
            (url, "1300-43-LP24"),
        )

    cuerpo = TestClient(crear_app(base)).get("/legal").text

    assert url in cuerpo
    assert 'target="_blank"' in cuerpo, "no saca al usuario del dashboard"
    assert 'rel="noopener"' in cuerpo


def test_sin_url_guardada_la_fila_no_muestra_un_enlace_roto(base: Path) -> None:
    """Una licitación sin ficha no puede producir un href vacío."""
    cuerpo = TestClient(crear_app(base)).get("/legal").text
    assert 'href=""' not in cuerpo


# --------------------------------------------------------------------------
# Vistas por area: la misma entidad, cinco lecturas
# --------------------------------------------------------------------------


def test_las_cuatro_areas_responden(cliente: TestClient) -> None:
    for area in ("/legal", "/compras", "/finanzas", "/comercial"):
        assert cliente.get(area).status_code == 200, area


def test_las_areas_leen_el_mismo_contrato_y_no_copias(cliente: TestClient) -> None:
    """El argumento de la vista por área: una entidad, no cinco planillas.

    Si Legal y Compras hablaran de universos distintos, serían dos sistemas
    con el mismo maquillaje. Ambas tienen que llegar al MISMO contrato.
    """
    legal = cliente.get("/legal").text
    compras = cliente.get("/compras").text
    detalle = cliente.get("/contratos/2-1-SE25").text

    # Legal llega por la caución, Compras por el organismo que adjudica...
    assert "1300-43-LP24" in legal, "Legal ve la licitación por sus cauciones"
    assert "SENAMA" in compras, "Compras la ve por su plazo de adjudicación"
    # ...y las dos desembocan en la MISMA ficha, que nombra esa licitación.
    assert "1300-43-LP24" in detalle


def test_legal_explica_por_que_las_garantias_no_salen_de_la_api(
    cliente: TestClient,
) -> None:
    """Sin ese porqué, la página parece un listado más."""
    cuerpo = cliente.get("/legal").text
    assert "54 campos" in cuerpo
    assert "ficha web" in cuerpo.lower()


def test_finanzas_avisa_que_lo_cancelado_no_es_gasto(cliente: TestClient) -> None:
    """Una orden cancelada CONSERVA su monto: sumarla infla el gasto."""
    cuerpo = cliente.get("/finanzas").text
    assert "cancelada" in cuerpo.lower()
    assert "infla el gasto" in cuerpo


def test_finanzas_declara_lo_que_no_puede_responder(cliente: TestClient) -> None:
    """El monto adjudicado no es comparable: en suministro es precio unitario."""
    cuerpo = cliente.get("/finanzas").text
    assert "NO responde" in cuerpo
    assert "precio" in cuerpo and "unitario" in cuerpo


def test_comercial_agrupa_por_rut_y_lo_dice(cliente: TestClient) -> None:
    """El mismo organismo aparece escrito de varias formas en la fuente."""
    cuerpo = cliente.get("/comercial").text
    assert "RUT y no por" in cuerpo


def test_una_corrida_de_inferencia_cortada_se_declara(base: Path) -> None:
    """El embudo describe la corrida; las cláusulas vienen de la base.

    Si la corrida se cortó, mezclarlos sin avisar produce una página que se
    contradice: "0 cláusulas" arriba y tres listadas abajo.
    """
    _registro(base, licitaciones=218, procesadas=2, clausulas=0)
    html = TestClient(crear_app(base)).get("/inferencia").text

    assert "se cortó en" in html
    assert "2 de 218" in html
    assert "pueden venir de corridas anteriores" in html
    # Y no se publica un porcentaje calculado sobre lo que no se completó.
    assert "no necesitaron el modelo" not in html


def test_una_corrida_completa_si_publica_el_porcentaje(base: Path) -> None:
    _registro(base, licitaciones=100, procesadas=100, resueltas_por_el_filtro=67)
    html = TestClient(crear_app(base)).get("/inferencia").text

    assert "67" in html and "no necesitaron el modelo" in html
    assert "se cortó en" not in html


def test_la_alerta_de_garantias_lidera_con_las_vigentes(cliente: TestClient) -> None:
    """Vigencia y marca son ortogonales, y mezclarlas exagera la alerta.

    De 12 cauciones marcadas en la cartera real, 9 ya habían vencido: un dato
    mal cargado en un contrato cerrado es un defecto histórico, no un riesgo
    de hoy. La página tiene que distinguirlo o está inflando el número.
    """
    for ruta in ("/", "/garantias"):
        cuerpo = cliente.get(ruta).text
        assert "vigente" in cuerpo, ruta
        assert "en total" in cuerpo, f"{ruta}: declara cuántas son sin filtrar"


def test_la_tabla_de_garantias_no_tapa_la_vigencia_con_la_marca(
    cliente: TestClient,
) -> None:
    """La columna de estado mostraba el motivo EN VEZ de si seguía viva.

    Una caución vencida marcada como "duración en cero" se veía solo como
    "duración en cero", y no había forma de saber que ya no cubre nada.
    """
    cuerpo = cliente.get("/legal").text

    assert "<th>Estado</th>" in cuerpo
    assert "<th>Marca</th>" in cuerpo, "la marca va en su propia columna"


def test_garantias_redirige_a_legal(cliente: TestClient) -> None:
    """Eran dos rutas sobre el mismo dato, con nombres distintos.

    La URL se conserva porque está enlazada desde los documentos y desde el
    guion de la demo: romperla sería peor que la duplicación que tenía.
    """
    r = cliente.get("/garantias", follow_redirects=False)

    assert r.status_code == 308
    assert r.headers["location"] == "/legal"
    # Y siguiéndola se llega a la página real.
    assert "cauciones vigentes" in cliente.get("/garantias").text

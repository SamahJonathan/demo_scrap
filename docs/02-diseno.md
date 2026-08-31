# Fase 2 — Diseño

**Autonomía A1**, con A2 solo para archivos de esquema.

Todo lo que sigue se apoya en hechos verificados contra la fuente durante la
Fase 1 y el Spike 0. Ver `docs/01-analisis.md` y `docs/00-spike.md`.

---

## 1. Flujo del programa

```mermaid
flowchart TD
    subgraph LOCAL["EN LA MÁQUINA DE DESARROLLO"]
        A["1· DESCUBRIMIENTO<br/>ordenesdecompra.json?fecha=<br/>3 fechas · 3 requests"]
        B["Filtrar sufijo SE/CC<br/>9.206 → 150 por día<br/>0 requests"]
        C["2· DETALLE DE OC<br/>?codigo= · 450 requests"]
        D{"¿CodigoLicitacion?"}
        E["OC huérfana · 56%<br/>ágil, marco, trato directo"]
        F["3· LICITACIÓN<br/>?codigo= · 54 campos"]
        G["4· OCDS<br/>monto adjudicado, oferentes<br/>SIN consumir cupo"]
        H["5· FICHA WEB<br/>qs sale de UrlActa<br/>secciones 7, 8, 9"]
        I["6· INFERENCIA offline<br/>filtro de pasajes → modelo"]
        RAW[("data/raw/<br/>JSON y HTML crudos<br/>= CACHÉ")]
        K["7· VALIDACIÓN<br/>esquema + plausibilidad"]
        Q[("data/quarantine/")]
        M["8· RECONSTRUCCIÓN<br/>entidad Contrato<br/>procedencia por campo"]
        DB[("contratos.db · SQLite")]
        EXP["Explorar con SQL"]
    end

    subgraph SRV["LIGHTSAIL · SÃO PAULO"]
        DB2[("contratos.db<br/>el MISMO archivo")]
        API["FastAPI + uvicorn"]
        NGX["nginx + certbot"]
        WEB(["contratos.54-207-164-201.sslip.io"])
    end

    A --> B --> C --> D
    D -->|no| E
    D -->|sí| F
    F --> G
    F --> H
    H --> I
    C -.-> RAW
    F -.-> RAW
    G -.-> RAW
    H -.-> RAW
    RAW -.->|reprocesar sin red| K
    E --> K
    G --> K
    I --> K
    K -->|falla| Q
    K -->|pasa| M --> DB
    DB --> EXP
    DB -->|scp, sin convertir| DB2
    DB2 --> API --> NGX --> WEB
```

### Dónde ocurre cada control

| Control | Dónde | Cómo |
|---|---|---|
| **Throttling** | Pasos 1 a 5 | `REQUEST_DELAY_SECONDS`, concurrencia 1, autothrottle |
| **Reintentos** | Pasos 1 a 5 | Backoff exponencial en 429 y 5xx; el resto falla y se registra |
| **Caché** | Pasos 1 a 5 | Todo crudo se escribe a `data/raw/` antes de parsear |
| **Descarte de inválidos** | Paso 7 | A `data/quarantine/` con el motivo; **nunca aborta la corrida** |
| **Tope de gasto** | Paso 1 | `MAX_REQUESTS_PER_RUN` corta antes de quemar el cupo |

### Por qué el crudo no entra a la base

`data/raw/` guarda las respuestas tal como llegan y funciona como caché. Si el
parseo de garantías falla, se corrige y se reprocesa **desde disco, sin gastar un
request ni volver a la fuente**. Es lo que mantiene corto el bucle de
verificación: cambiar un selector y re-validar 450 contratos toma segundos.

La base solo recibe entidades ya normalizadas.

---

## 2. Modelo de datos

### La entidad Contrato es DERIVADA

No existe en la fuente. Se construye uniendo orden de compra, licitación, OCDS y
ficha web. **Cada campo declara de dónde vino**; sin esa procedencia el dato no
es defendible.

Procedencias posibles: `api_oc`, `api_licitacion`, `ocds`, `ficha_web`,
`inferencia`, `derivado`.

### Contrato

| Campo | Tipo | Oblig. | Procedencia | Ejemplo | Validación |
|---|---|---|---|---|---|
| `id` | texto | sí | derivado | `1002-183-SE25` | código de la OC |
| `codigo_oc` | texto | sí | api_oc | `1002-183-SE25` | formato `N-N-XX##` |
| `codigo_licitacion` | texto | **no** | api_oc | `1002-9-LQ25` | nulo en el 56% |
| `tiene_proceso` | bool | sí | derivado | `true` | `codigo_licitacion is not null` |
| `organismo` | texto | sí | api_oc | `I. MUNICIPALIDAD DE MOSTAZAL` | no vacío |
| `organismo_rut` | texto | sí | api_oc | `69.080.500-6` | dígito verificador |
| `proveedor` | texto | sí | api_oc | `COMERCIALIZADORA C&J LTDA.` | no vacío |
| `monto_ejecutado` | decimal | sí | api_oc | `975800` | > 0 |
| `monto_estimado` | decimal | no | api_licitacion | `522500000` | > 0 si existe |
| `monto_adjudicado` | decimal | no | **ocds** | `441600000` | > 0 si existe |
| `fecha_adjudicacion` | fecha | no | api_licitacion | `2025-03-10` | ≤ hoy |
| `duracion_valor` | entero | no | api_licitacion | `10` | > 0 |
| `duracion_unidad` | enum | no | api_licitacion | `meses` | `1`=horas, `4`=meses; **otros = desconocido** |
| `fecha_termino_estimada` | fecha | no | derivado | `2026-01-10` | adjudicación + duración |
| `es_renovable` | bool | no | api_licitacion | `false` | — |
| `permite_subcontratacion` | bool | no | api_licitacion | `true` | — |
| `n_oferentes` | entero | no | ocds | `6` | ≥ 1 |
| `estado_ejecucion` | texto | sí | api_oc | `Recepción Conforme` | — |

**Nota sobre montos:** son tres cosas distintas y el modelo las separa a
propósito. El estimado es el presupuesto publicado, el adjudicado es por lo que
se firmó, y el ejecutado es lo que la orden de compra realmente movió. En
`2678-1-LR25` el estimado eran $522,5M y el adjudicado $441,6M: **81 millones de
diferencia**, y solo OCDS expone el segundo.

### Garantia

| Campo | Tipo | Oblig. | Procedencia | Ejemplo |
|---|---|---|---|---|
| `contrato_id` | texto | sí | derivado | `1002-183-SE25` |
| `tipo` | enum | sí | ficha_web | `seriedad_oferta`, `fiel_cumplimiento` |
| `monto_valor` | decimal | no | ficha_web | `1500000` |
| `monto_es_porcentaje` | bool | sí | ficha_web | `true` para "5 %" |
| `moneda` | texto | no | ficha_web | `CLP` |
| `fecha_vencimiento` | fecha | no | ficha_web | `2026-03-02` |
| `beneficiario` | texto | no | ficha_web | `Municipalidad de Mostazal` |
| `fragmento_origen` | texto | sí | ficha_web | posición en el HTML |

**Solo la ficha web las tiene.** Ninguno de los 54 campos de la API REST expone
garantías, y OCDS tampoco (0 menciones). Es el caso que justifica el scraping.

### ClausulaExtraida

Solo se crea si el Spike dejó la capa dentro del alcance. Lo hizo, como upside.

| Campo | Tipo | Oblig. | Procedencia |
|---|---|---|---|
| `contrato_id` | texto | sí | derivado |
| `tipo` | enum | sí | derivado (`causales_termino`) |
| `texto` | texto | sí | inferencia |
| `fragmento_origen` | texto | **sí** | ficha_web |
| `posicion_inicio` | entero | **sí** | ficha_web |
| `modelo` | texto | sí | derivado |

**`fragmento_origen` y `posicion_inicio` son obligatorios.** Un dato inferido sin
poder mostrar de dónde salió no entra. Durante el Spike, esa trazabilidad fue lo
que permitió auditar un resultado que se había interpretado mal.

### Discrepancia

Nace del hallazgo central del Spike: la ficha de SENAMA declara `36 Horas` en su
campo estructurado y **36 meses tres veces en su propia prosa**.

| Campo | Tipo | Procedencia |
|---|---|---|
| `contrato_id` | texto | derivado |
| `campo` | texto | derivado |
| `valor_estructurado` | texto | api_licitacion o ficha_web |
| `valor_prosa` | texto | inferencia |
| `regla` | texto | derivado |

**Una discrepancia se registra, nunca se resuelve en silencio.** Ni el parseo ni
el modelo ganan por defecto. Detectar que la fuente se contradice es el
resultado, no un problema a ocultar.

### Los tres casos difíciles

| Caso | Frecuencia medida | Respuesta del modelo |
|---|---|---|
| Una licitación con **varias** OC | esperado | Varios `Contrato` comparten `codigo_licitacion`. La licitación NO es la clave |
| Una OC **sin** licitación | **56%** | `codigo_licitacion` nulo y `tiene_proceso=false`. Es un contrato válido, no un error |
| La ficha **se contradice** | 1 de 3 en el spike | Fila en `Discrepancia`; ambos valores se conservan |

**La clave primaria es el código de la orden de compra**, no el de la licitación.
Esa decisión sale directamente de los dos primeros casos.

---

## 3. Estrategia de extracción

### Capa 1 — Esqueleto, invertido

Se parte de las **órdenes de compra**, no de las licitaciones, porque la API no
permite el recorrido inverso: rechaza `codigoLicitacion` como parámetro (HTTP
400) y el listado de OC no incluye ese campo. Indexar un día completo costaría
9.206 requests, el 92% del cupo diario.

Partiendo de la OC, además, **desaparece el problema del rezago**: si la orden ya
está publicada, su licitación existe con certeza.

### Capa 2 — Documentos, con un límite infranqueable

La ficha se obtiene con **GET limpio** usando el token `qs` que la propia API
entrega en `Adjudicacion.UrlActa`. No hay ingeniería inversa.

**Los adjuntos quedan FUERA DE ALCANCE**: `ViewAttachment.aspx` está protegida
por reCAPTCHA Enterprise. El token de redirección está en el HTML y permitiría
saltarse el chequeo; hacerlo sería evadir detección de bots. No se hace.

Se parsean solo las secciones 7, 8 y 9. Las secciones 1 a 6 son duplicado exacto
de la API o relleno legal idéntico en toda ficha.

### Capa 3 — Reconstrucción

Une las cuatro fuentes y produce `Contrato` con procedencia por campo, más las
filas de `Garantia`, `ClausulaExtraida` y `Discrepancia`.

### Idempotencia

Clave natural: `codigo_oc`. Re-ejecutar hace *upsert*, no inserta duplicados.
`data/raw/` funciona como caché: una segunda corrida sobre la misma ventana no
emite requests nuevos.

### Reintentos

Se reintenta en `429, 500, 502, 503, 504` con backoff exponencial y tope de 3.
Todo lo demás falla de inmediato y queda registrado. Nada de `except` silencioso.

---

## 4. Decisiones de tecnología

| Decisión | Elegido | Descartado | Criterio | Se revierte si |
|---|---|---|---|---|
| Lenguaje | Python 3.11+ | — | Ecosistema de datos y scraping | — |
| Cliente HTTP | **httpx** | Scrapy, requests | Timeouts explícitos, HTTP/2, API limpia. Ver el apartado siguiente sobre Scrapy | — |
| Reintentos | **tenacity** | Middleware propio | Decorador declarativo: backoff y tope en 5 líneas legibles | — |
| Parseo HTML | **selectolax** | BeautifulSoup, lxml | Las fichas pesan ~370 KB y son 450. La velocidad se nota en el bucle de verificación | Se prefiere familiaridad sobre velocidad |
| Validación | Pydantic | Esquemas a mano | Tipado, mensajes de error claros, integración con FastAPI | — |
| **Persistencia** | **SQLite** | PostgreSQL | **450 filas de solo lectura. Un servidor sería ceremonia. Y el mismo archivo se explora con SQL en local y se despliega sin conversión** | El volumen crece o hay escrituras concurrentes |
| API | FastAPI + uvicorn | Streamlit, HTML estático | Control del render, ~100 MB, y una app real se defiende mejor | — |
| Servidor web | nginx existente | Caddy | **Ya está activo en 80/443 con certbot funcionando. Caddy sería conflicto de puertos y RAM duplicada** | — |
| Dominio | sslip.io | Comprar dominio | DNS comodín con IP embebida, sin costo, ya en uso en el servidor | Se necesita un dominio propio |
| Inferencia | Ollama local, adaptador hosted conmutable | Solo hosted | Un CLM enterprise procesa contratos confidenciales y la pregunta comercial es a dónde van. **Honestidad: estos datos son públicos, la decisión es arquitectónica** | — |
| Tests | pytest + **respx** | — | Sobre parseo y validación, con HTML y JSON guardados. `respx` simula respuestas HTTP para que **ningún test toque la red** | — |
| Calidad | ruff + mypy | — | Rápidos, un solo binario para lint y formato | — |

### Por qué NO Scrapy

Era la preferencia de partida declarada en el método. Se descarta con criterio.

Scrapy está diseñado para recorrer **miles de URLs del mismo sitio** con
scheduler, spiders, middlewares y pipelines. Este proyecto tiene **cuatro fuentes
de formas distintas** —API de órdenes de compra, API de licitaciones, OCDS y
HTML— y ~900 requests secuenciales.

Lo que aporta Scrapy y con qué se reemplaza:

| Scrapy | Reemplazo | Costo |
|---|---|---|
| Cliente HTTP | `httpx` | librería |
| `DOWNLOAD_DELAY`, autothrottle | `sleep` + contador de requests | ~15 líneas |
| `RetryMiddleware` | `tenacity` | ~5 líneas |
| `HttpCacheMiddleware` | Crudo a `data/raw/` con hash de URL | ~20 líneas |
| Selectores | `selectolax` | librería |
| Item pipelines | `validacion.py`, `reconstruccion.py` | ya están en el diseño |

Total: **~50 líneas propias** en `cliente.py`, legibles y testeables.

Y hay un costo que pesa dado el método de trabajo: **testear Scrapy es
incómodo**, exige fabricar objetos `Response`. Una función que recibe HTML y
devuelve garantías se testea con un archivo guardado y un `assert`. Con el bucle
de generación-verificación como eje del proyecto, eso decide.

**Se revierte si** el volumen crece a decenas de miles de URLs o aparece la
necesidad de concurrencia amplia sobre un mismo dominio.

### Límite de responsabilidad del modelo

Fijado con la evidencia del Spike 0:

- **Campos estructurados** (montos, fechas, RUT, códigos, garantías tabuladas):
  API o parseo determinista. **El modelo no es fuente primaria de ninguno.**
- **Prosa libre** (causales de término): el modelo, siempre con filtro de
  recuperación por delante. Sin pasajes coincidentes, el campo es `null` y **no
  se llama al modelo**.
- **Verificación cruzada**: cuando la lectura de la prosa contradice al campo
  tipado, se emite una `Discrepancia`. Nunca se corrige en silencio.

**La inferencia NUNCA va en la ruta de un request.** Medido: 7,34 GB de RAM y
entre 8 y 65 minutos por documento. Corre en lote, offline, y persiste.

---

## 5. Estructura de carpetas

```
demo_scrap/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example
├── docs/
│   ├── 00-metodo.md
│   ├── 00-spike.md
│   ├── 01-analisis.md
│   ├── 02-diseno.md
│   └── 03-plan-codificacion.md
├── src/contratos/
│   ├── config.py            # carga y valida el entorno
│   ├── cli.py               # subcomandos; cada incremento suma el suyo
│   ├── cliente.py           # HTTP con throttling, reintentos y caché
│   ├── fuentes/
│   │   ├── api_oc.py        # listado y detalle de órdenes de compra
│   │   ├── api_licitacion.py
│   │   ├── ocds.py          # monto adjudicado y oferentes
│   │   └── ficha_web.py     # secciones 7, 8 y 9
│   ├── modelos.py           # entidades Pydantic
│   ├── validacion.py        # esquema + reglas de plausibilidad
│   ├── reconstruccion.py    # arma el Contrato con procedencia
│   ├── inferencia/
│   │   ├── interfaz.py
│   │   ├── local.py         # Ollama
│   │   ├── hosted.py
│   │   └── recuperacion.py  # filtro de pasajes
│   ├── persistencia.py      # SQLite, upsert idempotente
│   └── web/
│       ├── app.py           # FastAPI
│       ├── exportar.py      # dashboard.html autocontenido (respaldo)
│       └── plantillas/
├── tests/
│   └── fixtures/            # HTML y JSON reales guardados
├── data/
│   ├── raw/                 # no versionado
│   ├── quarantine/          # no versionado
│   └── samples/             # sí versionado
└── despliegue/
    ├── nginx.conf
    └── desplegar.sh         # scp del .db + reinicio del servicio
```

---

## 6. El punto frágil

**El parseo de la sección 8 de la ficha web.**

Es la única fuente de garantías, y es HTML de una aplicación ASP.NET WebForms que
nadie se comprometió a mantener estable. No hay contrato de API detrás: si
ChileCompra rediseña la ficha, los selectores dejan de encontrar nada.

Y el modo de falla es el peligroso: **no revienta, devuelve vacío.** Una corrida
podría terminar "bien" con cero garantías extraídas y nadie notarlo.

Mitigación, en tres capas:

1. **Umbral de cobertura.** Si menos del 90% de los contratos con ficha tiene al
   menos una garantía, la corrida **falla ruidosamente**. Un cero silencioso es
   inaceptable.
2. **Tests sobre HTML guardado.** Los fixtures son fichas reales descargadas. Si
   un cambio de selector rompe el parseo, el test lo detecta sin tocar la red.
3. **Degradación explícita.** Si la ficha no se puede parsear, el contrato se
   guarda igual con `garantias = []` y una marca de que la fuente falló — no se
   confunde "sin garantías" con "no pudimos leerlas".

El segundo candidato a punto frágil sería el enum `UnidadTiempoDuracionContrato`:
solo `1` (horas) y `4` (meses) están decodificados. Cualquier otro valor se
guarda como `desconocido` y **no se intenta adivinar**.

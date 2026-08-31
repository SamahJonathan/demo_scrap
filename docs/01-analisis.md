# Fase 1 — Análisis

**Autonomía A1.** Documento en curso. Lo verificado contra la fuente va marcado
como tal; lo demás dice SUPUESTO POR VERIFICAR.

**Eje de la demo: ciclo de vida contractual.** Vencimientos, renovaciones y
garantías al centro; los montos agregados son contexto, no el titular.

---

## 1. Objetivo del programa

> **Reconstruir contratos públicos chilenos que ninguna fuente publica como
> tales, y seguir su ciclo de vida —vigencia, vencimiento, renovación y
> garantías— para responder qué contratos hay que relicitar, cuáles se pueden
> renovar y qué cauciones siguen vivas, sin abrir fichas una por una.**

Ni tecnología ni herramientas en la frase: dice qué entrega.

### El hecho que obliga a esa formulación

**VERIFICADO.** La fuente NO tiene un listado de contratos. Expone licitaciones,
órdenes de compra, compra ágil y proveedores; ninguna entidad llamada contrato.
Se revisaron los 54 campos de `licitaciones.json?codigo=` y no existe tal
recurso.

El contrato hay que RECONSTRUIRLO uniendo cuatro piezas dispersas: el proceso
(licitación), el acto de adjudicación, el instrumento de ejecución (orden de
compra) y los documentos. Esa reconstrucción no es un obstáculo del proyecto: es
su núcleo.

### Preguntas de negocio

Ordenadas por el eje elegido. Las cinco se responden con datos que ya
confirmamos que existen.

| # | Pregunta | Fuente del dato | Estado |
|---|---|---|---|
| 1 | ¿Qué contratos vencen en los próximos N meses, y cuáles son renovables frente a cuáles hay que relicitar? | API: `FechaAdjudicacion` + `TiempoDuracionContrato` + `UnidadTiempoDuracionContrato` + `EsRenovable` | VERIFICADO |
| 2 | ¿Qué garantías siguen vigentes, y cuáles vencen antes que el contrato que caucionan? | Ficha web § 8 + API | VERIFICADO |
| 3 | ¿Cuánto tarda cada organismo entre publicar y adjudicar, y cuánto varía? | API: bloque `Fechas` | VERIFICADO |
| 4 | ¿Qué organismos concentran mayor monto vigente, y con qué proveedores? | API: `MontoEstimado` + `Comprador` + `Adjudicacion` | VERIFICADO |
| 5 | ¿Qué órdenes de compra no nacen de una licitación, y qué proporción del gasto representan? | API de OC: `CodigoLicitacion` vacío | **VERIFICADO**: 56% de las OC de un día |

**Evidencia de la pregunta 3.** Medida sobre tres casos reales adjudicados el
10-03-2025:

| Organismo | Publicación → adjudicación |
|---|---|
| I. Municipalidad de Mostazal | 45 días |
| I. Municipalidad de Puerto Montt | 115 días |
| Servicio Nacional del Adulto Mayor | 215 días |

Casi 5x de diferencia. El promedio va a mentir: lo que informa es la dispersión
por organismo.

**Evidencia de la pregunta 2.** La regla nació de un dato corrupto real, no de la
teoría. `1300-43-LP24` (SENAMA, aseo de una casa de acogida) declara en su campo
estructurado un plazo de **36 horas**, mientras su propia prosa dice tres veces
**36 meses** y la garantía de fiel cumplimiento vence el **29-12-2027**. El campo
tipado está mal cargado y el documento se contradice a sí mismo.

**VERIFICADO en el Spike 0:** la contradicción se detecta cruzando el campo
estructurado contra la prosa. Ver `docs/00-spike.md`. Los otros dos casos son
coherentes (Mostazal 10 meses, garantía hasta 02-03-2026; Puerto Montt 24 meses,
hasta 29-04-2027).

### Conexión con el dominio de un CLM

Un CLM gestiona el ciclo de vida de contratos: alta, obligaciones, hitos,
vencimientos, renovaciones y cauciones. Su problema más duro no es guardar
contratos propios, sino **ingestar contratos nacidos fuera del sistema**, donde
los datos llegan dispersos entre fuentes, sin entidad unificada, con relaciones
que no son uno a uno y con la parte valiosa encerrada en documentos.

Reconstruir contratos desde Mercado Público es una versión pública y verificable
de ese mismo problema. Las preguntas 1 y 2 son literalmente funciones de producto
de un CLM: alertas de vencimiento y control de garantías vivas.

### Resultado del Spike 0 (cerrado)

El método exige que, si la capa de inferencia queda dentro del alcance, al menos
una pregunta de negocio la requiera. **El spike cambió el rol de esa capa:** no
es extractora de campos, es **verificadora cruzada**. Detectó que la ficha de
SENAMA se contradice a sí misma, algo que ningún parseo determinista podía hacer.

Eso habilita una sexta pregunta, que sí la requiere:

| # | Pregunta | Fuente | Estado |
|---|---|---|---|
| 6 | ¿Qué contratos tienen su campo estructurado en contradicción con su propio texto, y cuál de los dos valores es el correcto? | Campo tipado + prosa vía inferencia | VERIFICADO en el spike |

La capa queda **dentro del alcance pero fuera de la línea de corte**: es upside.
Su costo medido —minutos por documento y 7,34 GB de RAM— no permite ponerla en la
ruta crítica de la demo.

---

## 2. Actores

**Gestor de contratos de un organismo público.** Decide cuándo iniciar la
relicitación de un servicio que vence, si conviene ejercer una renovación, y si
las garantías de sus contratos vigentes siguen cubiertas. Hoy lo hace abriendo
fichas de a una. Con las preguntas 1 y 3 sabe además cuánto tiempo necesita: si
su organismo tarda 215 días en adjudicar, empezar tres meses antes del
vencimiento llega tarde.

**Analista comercial de un proveedor del Estado.** Busca qué contratos de su
rubro vencen en los próximos meses para preparar oferta con tiempo, y con qué
compradores existen relaciones recurrentes. Decide dónde invertir esfuerzo
comercial.

---

## 3. Investigación de la fuente

Todo lo de esta sección se comprobó ejecutando requests contra la fuente, no
leyendo documentación. La evidencia completa está en `CLAUDE.md`.

### 3.1 Lo confirmado

- **API dirigida por fecha**, sin cursor ni offset. Se recorre día por día:
  `licitaciones.json?fecha=ddmmaaaa&estado=<estado>&ticket=...`
- **El listado es pobre:** solo `CodigoExterno`, `Nombre`, `CodigoEstado` y
  `FechaCierre`. El detalle exige una segunda llamada por código y devuelve 54
  campos.
- **Costo real: 1 request por día + 1 por licitación.** El 10-03-2025 tuvo 248
  licitaciones adjudicadas. Con tope de 10.000 requests diarios, la ventana debe
  ser angosta.
- **`robots.txt` devuelve 404.** La fuente no declara reglas de exclusión. No
  habilita nada: el throttling conservador se mantiene igual.

### 3.2 Cadena de acceso a la ficha web

1. `licitaciones.json?codigo=` devuelve `Adjudicacion.UrlActa`, que **contiene el
   token `qs` cifrado de la ficha**. No hay que hacer ingeniería inversa.
2. `RFB/DetailsAcquisition.aspx?qs=` carga con un **GET limpio**, HTTP 200. Esto
   corrige el supuesto del método, que daba por hecho que el ViewState lo
   impedía.
3. El HTML de la ficha trae el token `enc` de la página de adjuntos.
4. `Attachment/ViewAttachment.aspx?enc=` está protegida por **reCAPTCHA
   Enterprise** con scoring de bot, umbral 0.5, y 403 para quien no lo pasa.

**Decisión, no negociable:** la descarga automatizada de adjuntos queda FUERA DE
ALCANCE. El token de redirección viene en el HTML y permitiría saltarse el
chequeo; hacerlo sería evadir detección de bots, que el proyecto prohíbe
explícitamente. El hallazgo se documenta y se defiende.

### 3.3 Qué da la API y qué solo da el HTML

| Dato | API | Ficha web |
|---|---|---|
| Fechas del proceso | ✅ las 11, exactas | duplicado |
| Monto estimado, plazo, renovación, subcontratación | ✅ | duplicado |
| Adjudicación, oferentes, ítems | ✅ | duplicado |
| **Garantías** (tipo, monto, vencimiento, glosa) | ❌ **ninguno de los 54 campos** | ✅ sección 8 |
| Cláusulas en prosa (término, readjudicación) | ❌ | ✅ sección 9 |
| Bases administrativas y anexos | ❌ | 🔒 tras reCAPTCHA |

Esta tabla justifica la capa de scraping bajo la regla "API primero, HTML solo
para lo que la API no expone".

### 3.4 Enum sin documentar, decodificado

`UnidadTiempoDuracionContrato`: **`1` = horas**, **`4` = meses**. Decodificado
cruzando la API contra la sección 7 de la ficha en tres licitaciones. El resto de
los valores sigue SIN decodificar y no debe asumirse.

### 3.5 El enlace licitación ↔ orden de compra — RESUELTO

**VERIFICADO.** El enlace existe como campo tipado: el detalle de una orden de
compra trae **`CodigoLicitacion`**, no un texto libre.

Pero solo lo traen algunas modalidades. Medido sobre las 9.206 OC del
15-05-2025:

| Tipo | Qué es | `CodigoLicitacion` | Volumen del día |
|---|---|---|---|
| **SE** | Solicitud desde licitación | ✅ poblado | 3.968 |
| **CC** | — | ✅ poblado | 79 |
| AG | Compra ágil | vacío | 3.473 |
| CM | Convenio marco | vacío | 1.021 |
| TD | Trato directo | vacío | 664 |

**El 56% de las órdenes de compra no nace de una licitación.** No es un defecto
del dato: compra ágil, convenio marco y trato directo son modalidades que no
pasan por licitación. El modelo de datos debe aceptar OC huérfanas como caso
válido, no como error.

#### La restricción operativa que cambia la estrategia

El enlace **solo se puede recorrer en una dirección**:

- De OC a licitación: directo, el campo está ahí.
- De licitación a sus OC: **no existe.** La API rechaza `codigoLicitacion` como
  parámetro (HTTP 400, "Nombre de parametro no valido"). Y el LISTADO de OC solo
  devuelve `Codigo`, `Nombre` y `CodigoEstado` — sin `CodigoLicitacion`, que solo
  aparece pidiendo el detalle de cada una.

Indexar un solo día de OC para poder ir de licitación a orden costaría **9.206
requests**, el 92% del cupo diario. Filtrando a SE y CC siguen siendo ~4.047.
Inviable para una ventana amplia.

#### Consecuencia: la extracción se invierte

En vez de partir de licitaciones y buscarles órdenes, **se parte de las órdenes
de compra de tipo SE y CC**, se lee su `CodigoLicitacion` y se piden esas
licitaciones. Cada contrato queda completo —proceso, adjudicación y ejecución—
con costo acotado y predecible:

```
1 request    listado de OC de un día
N requests   detalle de las OC tipo SE/CC de la muestra
M requests   detalle de las licitaciones referenciadas (M <= N)
```

Para una muestra de 150 órdenes: ~300 requests, contra un cupo de 10.000.

Además elimina el problema del rezago: si se parte de una OC ya publicada, su
licitación existe con certeza. Partiendo al revés, la mayoría de las
licitaciones recientes aparecería sin ejecución por el rezago de 1 a 2 meses.

### 3.6 OCDS — evaluado, y NO se descarta

**OCDS** es el *Open Contracting Data Standard*: el estándar internacional
abierto para publicar datos de compras públicas, mantenido por la Open
Contracting Partnership. Modela el proceso en cinco etapas —planning, tender,
award, **contract**, implementation— y compila la historia de cada proceso en un
*record* con identificador estable (`ocid`).

**VERIFICADO.** ChileCompra publica en OCDS 1.1:

```
https://apis.mercadopublico.cl/OCDS/data/record/<codigo>
```

Dos hechos que cambian el diseño:

1. **No requiere ticket.** Responde HTTP 200 sin autenticación: **no consume el
   cupo de 10.000 requests diarios.**
2. **Trae datos que la API REST no expone.**

| Dato | API REST | OCDS | Ficha web |
|---|---|---|---|
| Monto estimado | ✅ | ✅ | ✅ |
| **Monto adjudicado** | ❌ | ✅ $441.600.000 | ❌ |
| **Quiénes ofertaron** | solo el número | ✅ los 6, con RUT | ✅ |
| **Proveedores adjudicados** | ❌ | ✅ los 3, con identificador | ✅ |
| **Cronología del proceso** | fechas sueltas | ✅ 10 *releases* fechados | parcial |
| Duración y unidad del contrato | ✅ | ❌ | ✅ |
| Renovación, subcontratación | ✅ | ❌ | ✅ |
| **Garantías** | ❌ | ❌ (0 menciones) | ✅ sección 8 |
| Enlace con orden de compra | ✅ desde la OC | ❌ | ❌ |
| Cupo de requests | consume | **no consume** | no consume |

**Hallazgo clave:** OCDS entrega el **monto adjudicado** y **quiénes ofertaron y
ganaron**, que la API REST no da en el detalle de la licitación. Para el eje de
ciclo de vida es material: el contrato se firma por el monto adjudicado
($441,6M), no por el estimado ($522,5M).

**El hueco que define el proyecto.** El estándar tiene una etapa `contract`, y
Chile **la deja vacía**: no existe el array `contracts` en el record. Publica
hasta la adjudicación. Ese hueco es exactamente lo que este proyecto reconstruye,
y el estándar internacional respalda que ahí debería haber algo.

**Otras limitaciones medidas:**
- Cero menciones de garantías o cauciones.
- Sus `documents` apuntan a la misma URL `ViewAttachment.aspx` protegida por
  reCAPTCHA. No abre esa puerta.
- **No se encontró listado masivo por fecha.** `listaAnnoMes`, `fecha/ddmmaaaa` y
  variantes devuelven 404. Se consulta por código, uno a uno.

**Decisión: se usan las cuatro fuentes, cada una para lo que hace mejor.**

| Capa | Fuente | Por qué |
|---|---|---|
| Descubrimiento | API REST por fecha | Única con recorrido temporal |
| Ejecución y enlace | API REST de OC | `CodigoLicitacion` solo está ahí |
| Enriquecimiento | **OCDS** | Monto adjudicado, oferentes, cronología, sin gastar cupo |
| Garantías y cláusulas | Ficha web | Única fuente que las tiene |

La respuesta a "¿por qué no usaste el bulk?" no es que lo descartamos: **lo
usamos donde es superior, y documentamos dónde no alcanza.**

### 3.7 Licencia y condiciones de uso

**VERIFICADO, y es el dato más contundente:** el propio *record* OCDS declara su
licencia de forma legible por máquina.

```json
"publisher": {"name": "Dirección de Compras y Contratación Pública"},
"license":   "https://creativecommons.org/publicdomain/zero/1.0/"
```

**CC0 1.0 Universal**: dedicación al dominio público. El organismo que publica
renuncia a sus derechos sobre estos datos. No es una interpretación nuestra sobre
un texto legal ambiguo: es una declaración explícita del publicador, dentro del
dato mismo.

Eso respalda directamente la restricción "solo datos públicos" del proyecto.

Otros hechos comprobados:

| Señal | Estado |
|---|---|
| `robots.txt` de `mercadopublico.cl` | **404** — no declara reglas de exclusión |
| Ticket de la API | Personal, vía Clave Única, tope 10.000 requests/día |
| Horario sugerido por el proveedor | 22:00 a 07:00, por baja carga |
| Adjuntos | Control de acceso técnico activo (reCAPTCHA Enterprise) |
| `publicationPolicy` declarada en el OCDS | **404** — el enlace está roto |

**Cómo se traduce en conducta, y es más estricto que lo exigido:**

- Ausencia de `robots.txt` no es permiso amplio. Se mantiene el throttling
  conservador y el User-Agent con contacto real.
- El reCAPTCHA de los adjuntos **sí** es una restricción declarada por el
  operador, aunque sea técnica y no textual. Se respeta: esos documentos quedan
  fuera de alcance.
- El tope de 10.000 diarios se respeta con `MAX_REQUESTS_PER_RUN` y caché de
  respuestas en desarrollo.

**SUPUESTO POR VERIFICAR:** no se localizó un documento de términos de uso
específico para la API. La página de términos de `chilecompra.cl` que sí
responde trata del Registro de Proveedores, no del consumo de datos. La licencia
CC0 del OCDS es la declaración más específica encontrada.

### 3.8 Pendiente de investigar

- Diccionario de datos completo de cada endpoint y significado de cada
  `CodigoEstado`. Se decodificaron solo los valores encontrados en la muestra.
- Resto del enum `UnidadTiempoDuracionContrato`: solo `1` (horas) y `4` (meses)
  están confirmados.
- Si OCDS expone algún listado por fecha bajo otra ruta no probada.

---

## 4. Alcance

### Dentro

- **Órdenes de compra de tipo SE y CC** de una ventana angosta, como punto de
  partida, y las licitaciones que referencian.
- Detalle por código, con los 54 campos de la licitación y los 28 de la OC.
- Ficha web por GET limpio, para extraer garantías y cláusulas.
- Reconstrucción de la entidad Contrato con procedencia declarada por campo.
- Validación con reglas de plausibilidad, incluida garantía contra plazo.
- Persistencia en PostgreSQL, idempotente.
- Dashboard orientado a ciclo de vida: vencimientos, renovables, garantías vivas.

### Fuera

- **Descarga de adjuntos** (bases, anexos): bloqueada por reCAPTCHA y no se evade.
- Compra ágil y trato directo.
- Licitaciones no adjudicadas.
- Histórico amplio: la ventana es deliberadamente angosta.
- Ingesta en tiempo real o programada.
- **Capa de extracción con modelo de lenguaje: pendiente del Spike 0.**

---

## 5. Riesgos y supuestos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| ~~El enlace licitación ↔ OC no existe~~ | — | — | **DESCARTADO.** El campo `CodigoLicitacion` existe y está poblado en las OC tipo SE y CC |
| El recorrido licitación → OC no es posible por API | **Confirmado** | Alto: obliga a invertir la extracción | Partir de órdenes de compra, no de licitaciones. Ver 3.5 |
| Cambia la estructura HTML de la ficha | Media | Alto: se pierden las garantías | Selectores acotados, tests sobre HTML guardado, fallo ruidoso |
| Se agota el cupo de 10.000 requests diarios | Media | Alto: corrida cortada | `MAX_REQUESTS_PER_RUN`, caché de respuestas, ventana angosta |
| Datos corruptos en la fuente | **Confirmado** | Medio | Reglas de plausibilidad y cuarentena. Caso real ya detectado |
| Rezago de 1 a 2 meses en órdenes de compra | Confirmado | Medio | Ventana con colchón de 60 días |
| Caída o lentitud de la API | Media | Medio | Reintentos con backoff, caché local |
| Inferencia local inviable por recursos | **Confirmado** | Bajo si la capa sale del alcance | Medido: 499 s por documento y 7,34 GB de RAM |

## 5b. Línea de corte

**Demo mínima defendible**, decidida en frío y no la noche anterior:

> Extracción por API y ficha, validación con cuarentena, reconstrucción del
> contrato, persistencia y dashboard de vencimientos y garantías.

Todo lo demás es upside: enlace con órdenes de compra, extracción con modelo de
lenguaje, observabilidad avanzada.

---

## 6. Criterios de éxito

Observables, verificables ejecutando algo.

1. Una corrida completa termina sin intervención y reporta cuántos registros
   entraron, cuántos quedaron en cuarentena y por qué.
2. El dashboard responde las preguntas 1 a 4 sin abrir la base a mano.
3. Cada campo del contrato reconstruido declara su procedencia.
4. Re-ejecutar la corrida no duplica registros.
5. La regla garantía-contra-plazo detecta el caso de SENAMA sin ayuda.
6. Los tests de parseo y validación pasan sobre HTML y JSON guardados, sin red.

---

## Preguntas abiertas — RESUELTAS

1. **Tamaño y forma de la muestra.** → 150 órdenes de compra por día, en 3 días
   distintos. Se parte de OC tipo SE y CC, no de licitaciones. ~900 requests
   contra un cupo de 10.000.
2. **Presentación.** → FastAPI servido contra PostgreSQL, desplegado en una
   instancia Lightsail en `sa-east-1`, con SSL vía Caddy. Export de HTML
   autocontenido como respaldo.
3. **~~Plan B si el enlace con OC es inviable~~.** → Pregunta muerta: el enlace
   existe (`CodigoLicitacion`) y está verificado. Ver § 3.5.

**Regla que salió de estas decisiones:** la inferencia nunca va en la ruta de un
request. Corre en lote, offline, y persiste sus resultados. Medido: 7,34 GB de
RAM y entre 8 y 65 minutos por documento.

## Gate de salida

- [x] `docs/01-analisis.md` con las seis secciones
- [x] El objetivo cabe en una frase y no menciona Python ni Scrapy
- [x] Hay ejemplos reales de respuesta de la fuente, verificados con requests
- [x] El *out of scope* tiene más de 4 ítems
- [x] Los criterios de éxito se verifican ejecutando algo
- [x] Todo lo no verificado está marcado como SUPUESTO POR VERIFICAR
- [x] Preguntas abiertas resueltas
- [x] Infraestructura confirmada: Lightsail 1 GB / 2 vCPU en São Paulo

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
| 5 | ¿Qué licitaciones adjudicadas no tienen orden de compra asociada? | API de licitaciones + API de OC | SUPUESTO POR VERIFICAR |

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

### 3.5 Pendiente de investigar

- Enlace exacto entre una licitación y su o sus órdenes de compra. **Es el punto
  crítico del proyecto**: sin ese enlace no hay entidad contrato.
- Datasets de Datos Abiertos y publicación OCDS. Hay que evaluarlos en serio y
  justificar el descarte: "¿por qué no usaste el bulk?" es pregunta probable en
  la entrevista.
- Términos de uso de la plataforma.
- Diccionario de datos completo de cada endpoint y significado de cada estado.

---

## 4. Alcance

### Dentro

- Licitaciones adjudicadas de una ventana angosta (5 días hábiles), vía API.
- Detalle por código, con los 54 campos.
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
| El enlace licitación ↔ orden de compra no existe o no es uno a uno | Alta | **Crítico**: sin él no hay entidad contrato | Investigarlo primero en Fase 2. Plan B: contrato = licitación adjudicada, sin ejecución |
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

## Preguntas abiertas para el desarrollador

1. ¿La ventana de 5 días hábiles se mantiene, o conviene elegir días con más
   licitaciones adjudicadas?
2. ¿El dashboard es estático generado, o una aplicación servida contra
   PostgreSQL?
3. Si el enlace con órdenes de compra resulta inviable, ¿se acepta el plan B de
   contrato sin ejecución registrada?

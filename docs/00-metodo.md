# Proyecto demo — Scraping de contratos públicos (Mercado Público / ChileCompra)

**Guion de prompts por fases — Método Karpathy modificado**
Contexto: demo técnica para entrevista en **Webdox** (CLM con IA nativa, LATAM).
Repositorio: `git@github.com:SamahJonathan/demo_scrap.git`

---

## El método, en una página

Karpathy plantea que programar con un LLM es un **bucle de generación y verificación**. El modelo genera rápido; el cuello de botella siempre es tu capacidad de verificar. De ahí salen sus tres reglas prácticas:

1. **Mantén la correa corta.** Pídele el cambio más pequeño posible. Un diff que no puedes revisar de una sentada es un diff que vas a aceptar sin entender.
2. **Acelera la verificación.** Cada minuto que inviertes en hacer el chequeo más rápido y más visual se te devuelve en cada iteración. Un test que corre en 2 segundos vale más que uno exhaustivo que corre en 2 minutos.
3. **El contexto es todo.** El modelo es un colaborador brillante con amnesia. Si no le vuelves a dar la especificación, la reinventa.

Y una advertencia: el *vibe coding* —aceptar código sin leerlo— es legítimo para un prototipo desechable, y es veneno para algo que vas a defender frente a un entrevistador.

**La modificación** que aplicamos aquí son tres capas encima:

- **Ciclo de vida explícito en 5 fases** con un *gate* de salida en cada una. El bucle de Karpathy es táctico; las fases le dan dirección estratégica.
- **Dial de autonomía por fase.** No se le da la misma libertad al modelo para investigar una API que para tocar el pipeline de datos. Cada fase declara su nivel.
- **Especificación versionada como fuente de verdad.** Los documentos de `/docs` no son burocracia: son el contexto que le vuelves a inyectar al modelo en cada sesión, y son la evidencia de tu criterio en la entrevista.

### El dial de autonomía

| Nivel | Qué hace la IA | Qué haces tú | Tamaño máximo del diff |
|---|---|---|---|
| **A1 — Consulta** | Investiga, propone, compara. No toca archivos. | Decides. | 0 líneas |
| **A2 — Correa corta** | Un archivo, una función, un test a la vez. | Lees cada línea antes de aceptar. | ~50 líneas |
| **A3 — Incremento** | Un incremento completo del backlog. | Revisas el diff completo y corres la verificación. | ~200 líneas |
| **A4 — Suelto** | Refactor amplio, andamiaje repetitivo. | Verificas por resultado, no por línea. | Sin tope |

> **Regla:** nunca subes de nivel para ir más rápido. Subes de nivel cuando el riesgo del cambio baja. Andamiaje aburrido → A4. Lógica de parseo que sostiene toda la demo → A2.

---

---

## ⚠️ Bloqueante a resolver HOY, antes que nada

La API de Mercado Público requiere un **ticket** que se solicita con **Clave Única**, es uno por persona y tiene tope de **10.000 requests diarios**. No controlas cuánto demora la emisión, así que pídelo ahora mismo en <https://www.chilecompra.cl/api/>, antes de escribir una línea.

Mientras llega, no estás bloqueado: el **Spike 0** trabaja sobre PDF que bajas a mano, y las Fases 0 y 1 son documentación. La dependencia recién muerde en el Incremento 1.

Revisa además si el Diccionario de Datos publica un ticket de pruebas: si existe, te desbloquea el desarrollo inicial sin esperar el tuyo.

---

## Cómo usar este documento

1. Crea el repositorio vacío en GitHub como `demo_scrap` (sin README, sin .gitignore: los genera la Fase 0). Ese paso lo haces tú a mano, en la web.
2. Carpeta vacía en VS Code, arranca Claude Code dentro de ella.
3. Guarda este archivo como `docs/00-metodo.md` y ejecuta la **Fase 0**. Ella deja el repositorio armado y el `CLAUDE.md` en su lugar.
4. Una fase a la vez. No avanzas sin cumplir el gate.
5. Commit al cerrar cada incremento, tag al cerrar cada fase. El historial de git es parte de la demo: muestra proceso, no solo resultado.

---

## CONTEXTO PERMANENTE

```
Eres un ingeniero de datos senior especializado en web scraping de producción.
Trabajamos en un proyecto que presentaré como demo técnica en una entrevista, así
que la claridad de las decisiones pesa tanto como que el código funcione.

## Cómo trabajamos: bucle generación-verificación
Tú generas, yo verifico. Mi capacidad de verificar es el cuello de botella del
proyecto, así que TODO lo que propongas debe optimizar para que yo pueda
comprobarlo rápido:
- Cambios pequeños. Si un cambio no cabe en una revisión de una sentada, pártelo.
- Cada entrega viene con el comando exacto que yo ejecuto para verificarla y la
  salida que debería producir.
- Prefiere una verificación visible (un archivo que puedo abrir, una salida que
  puedo leer) sobre una afirmación tuya de que funciona.
- Si una verificación es lenta, propón cómo hacerla más rápida antes de seguir.

## Dial de autonomía
Cada tarea que te asigne viene con un nivel. Respétalo estrictamente:
- A1 Consulta: investigas y propones. NO editas archivos.
- A2 Correa corta: un archivo o una función por vez, máximo ~50 líneas de diff.
- A3 Incremento: un incremento completo del backlog, máximo ~200 líneas.
- A4 Suelto: andamiaje o refactor mecánico, sin tope.
Si crees que una tarea necesita más autonomía de la que le di, pídemela y
explica por qué. No la tomes por tu cuenta.

## Sobre mí
Soy el desarrollador y voy a leer cada línea que escribas. Cuando propongas algo,
explica el porqué y qué alternativa descartaste. Si no entiendo tu código, el
código está mal, no yo.

## Proyecto
Extraer y estructurar licitaciones y órdenes de compra públicas de Mercado
Público (ChileCompra, Chile): descubrimiento, extracción, validación,
persistencia y visualización.

## Por qué esta fuente
La empresa entrevistadora (Webdox) vende software de gestión del ciclo de vida de
contratos. Los datos de compras públicas SON datos contractuales: montos, plazos,
contrapartes, adjudicaciones, documentos adjuntos. La demo debe hacer visible esa
conexión.

## Especificación como fuente de verdad
Los documentos en /docs son el contexto del proyecto. Si el código y el documento
se contradicen, PARAS y me avisas. El código no diverge en silencio de la
especificación. Al iniciar cada sesión, relee /docs antes de proponer nada.

## Restricciones no negociables
- Respetar robots.txt, términos de uso y rate limits. Nada de evadir CAPTCHAs ni
  detección de bots.
- API oficial primero; scraping de HTML solo para lo que la API no expone, y
  documentando la decisión.
- User-Agent honesto con medio de contacto. Throttling conservador.
- Sin secretos en el repo. Todo por variables de entorno.
- Solo datos públicos.

## Estándares
- Python 3.11+, tipado, docstrings en funciones públicas.
- Todo dato que entra se valida contra un esquema explícito.
- Nada de except silencioso.
- Tests sobre la lógica de parseo y validación, no sobre el I/O de red.
- Commits pequeños, mensajes convencionales (feat:, fix:, docs:, test:).

## Formato de tus respuestas
- Directo, sin preámbulos ni resúmenes de lo que acabas de hacer.
- Documentos de fase como archivos markdown en /docs.
- Si una ambigüedad cambia el diseño, pregunta antes de asumir.
- Prohibido decir que algo funciona sin haberlo ejecutado. Si no lo corriste,
  dilo.
```

---

# FASE 0 — REPOSITORIO Y CONTEXTO

**Autonomía: A4 (andamiaje mecánico, sin lógica de negocio).**
**Verificación:** `git log` muestra un commit, `git remote -v` apunta al repo correcto, y `CLAUDE.md` existe.

Esta fase deja el repositorio listo y —más importante— instala el contexto permanente como archivo, para que se reinyecte solo en cada sesión en vez de depender de que lo pegues.

> **Ojo:** aquí NO se crea el andamiaje del código (dependencias, linter, tests, Scrapy). Eso es el Incremento 0 de la Fase 3 y se hace con su propio criterio de aceptación. Esta fase crea únicamente repositorio, contexto y documentación.

### Prompt

```
FASE 0 — REPOSITORIO. Autonomía A4: es andamiaje, sin lógica de negocio.

Este archivo, docs/00-metodo.md, es la especificación del proyecto. Léelo
completo antes de actuar.

Crea la estructura base del repositorio:

## 1. CLAUDE.md
Copia LITERALMENTE el bloque "CONTEXTO PERMANENTE" de docs/00-metodo.md a un
archivo CLAUDE.md en la raíz. Es el contexto que se reinyecta en cada sesión.
No lo resumas, no lo reescribas con tus palabras: cópialo tal cual.
Agrégale al final una sección "Estado actual" con la fase en curso, que
actualizarás al cerrar cada fase.

## 2. .gitignore
Debe excluir, como mínimo:
- Entorno virtual y .env (pero NO .env.example)
- Artefactos de Python, pytest, mypy, ruff
- .scrapy/ y la caché HTTP de desarrollo
- data/raw/, data/processed/, data/quarantine/, *.jsonl, *.sqlite
  Los datos extraídos NO se versionan: el repositorio contiene código y
  especificación, no el dataset.
- La carpeta spike/ completa: es código desechable por definición.
- Salidas generadas del dashboard.
- Archivos de editor y sistema operativo.

## 3. .env.example
Todas las variables de configuración, cada una con un comentario que explique
qué es y qué valor razonable tiene. Incluye: ticket de la API de Mercado
Público, User-Agent con contacto, parámetros de throttling y reintentos,
ventana de fechas de extracción, configuración de la capa de inferencia
(proveedor local u hosted), y los umbrales de calidad que hacen fallar la
corrida. Sin un solo valor real: es una plantilla.

## 4. README.md
Versión inicial honesta. Debe decir:
- Qué es el proyecto, en dos párrafos.
- Por qué esta fuente, conectándolo con el dominio de un CLM.
- Una tabla de fases con su estado, todas en pendiente salvo esta.
- Los principios que el repositorio respeta: API antes que scraping,
  identificación honesta, throttling, solo datos públicos, datos no
  versionados, sin secretos.
- Una sección de puesta en marcha que por ahora solo clona y copia el .env.

Regla del README: si algo está documentado ahí, funciona. Se actualiza en cada
incremento, nunca por adelantado.

## 5. LICENSE
MIT, a nombre de Jonathan Samah, año 2026.

## 6. Estructura de carpetas
Crea docs/ y data/samples/ con .gitkeep. Nada más: el resto lo define el
diseño de la Fase 2.

## 7. Git
- git init con rama principal main
- git remote add origin git@github.com:SamahJonathan/demo_scrap.git
- Primer commit: "chore: estructura inicial y método de trabajo"
- NO hagas push. El push lo ejecuto yo.

## Verificación
Al terminar, ejecuta y muéstrame la salida real de:
  git log --oneline
  git remote -v
  git status --short
  ls -la
Y confirma explícitamente que .env NO aparece en git status, es decir que el
.gitignore está haciendo su trabajo.
```

### Flujo de trabajo con git

Fijado desde ahora, porque el historial es parte de lo que vas a mostrar:

| Momento | Acción |
|---|---|
| Inicio de fase | Rama `fase/N-nombre` desde `main` |
| Inicio de incremento | Rama `inc/N-nombre` desde la rama de fase |
| Cierre de incremento | Commit convencional, merge a la rama de fase |
| Cierre de fase | Merge a `main` + tag `fase-N` |

Convención de mensajes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`.

Un commit por incremento, con el criterio de aceptación cumplido. Nunca un commit "WIP" en `main`.

### Push inicial

```bash
git push -u origin main
```

Si el repositorio remoto no existe todavía, créalo en GitHub como `demo_scrap`, **vacío**: sin README, sin .gitignore, sin licencia. Cualquiera de esos archivos generaría un conflicto en el primer push.

### Gate de salida

- [ ] `git remote -v` apunta a `git@github.com:SamahJonathan/demo_scrap.git`
- [ ] `CLAUDE.md` contiene el contexto permanente completo, copiado literal
- [ ] `git status` no muestra `.env` ni nada de `data/`
- [ ] El push a `main` funcionó
- [ ] **Karpathy check:** el contexto ya no depende de que lo pegues a mano

---

# SPIKE 0 — Validar el supuesto más riesgoso

**Antes de la Fase 1. Autonomía: A4 (código desechable, se borra al terminar).**
**Timebox: 1 hora. Si se pasa, el resultado es "no alcanza" y eso también es un resultado.**

El supuesto más riesgoso del proyecto no es si puedes scrapear: es si un modelo de lenguaje local extrae información contractual útil de unas bases de licitación chilenas reales. Cuesta una hora comprobarlo y define el diseño de todo lo demás.

### Prompt

```
SPIKE 0 — Validación de supuesto. Autonomía A4: código desechable, en una carpeta
/spike que borraremos. No apliques estándares de producción acá: no hay tests, no
hay tipado, no hay arquitectura. Es un experimento, no un cimiento.

Objetivo: responder con evidencia una sola pregunta.
¿Un modelo de lenguaje local extrae información contractual útil de las bases de
una licitación pública chilena?

Pasos:
1. Consígueme la URL de 2 o 3 licitaciones reales de Mercado Público que tengan
   bases administrativas descargables. Las bajo yo a mano a /spike/docs.
2. Script mínimo: leer el PDF, extraer texto, y si el texto sale vacío avisarme
   (sería un PDF escaneado, y eso cambia la conclusión).
3. Llamar a un modelo vía Ollama pidiendo extracción de 4 campos, con salida
   JSON: plazo de entrega, monto o presupuesto máximo, garantías exigidas,
   causales de término.
4. Correrlo sobre los 3 documentos.

Entregable: /spike/RESULTADO.md con
- La salida cruda del modelo para cada documento, sin maquillar.
- Cuántos de los 4 campos salieron correctos según mi revisión manual.
- Si el JSON fue parseable en los 3 casos o falló en alguno.
- Tiempo por documento.
- Tu recomendación en una frase: capa central, alcance acotado, o descartar.

No arregles los resultados malos. El valor de este spike es la medición honesta.
Si el modelo alucina campos, quiero verlo.
```

### Decisión posterior al spike

| Resultado | Decisión de diseño |
|---|---|
| Extrae cláusulas razonables | Capa central. Entra completa a Fase 1 y 2. |
| Inconsistente o parcial | Alcance acotado: 3 o 4 campos fijos, sin análisis abierto. |
| No sirve, o los PDF son escaneados | Fuera de alcance. El hallazgo se documenta y se defiende. |

La carpeta `spike/` está en `.gitignore` a propósito: no se versiona código desechable. Copia `RESULTADO.md` a `docs/00-spike.md` antes de borrarla. Ese archivo es evidencia de método en la entrevista: muestra que mediste antes de decidir.

---

# FASE 1 — ANÁLISIS

**Autonomía: A1 (Consulta).** La IA investiga y redacta. No crea código.
**Verificación:** ¿puedes explicar el objetivo del programa a alguien no técnico en 30 segundos?

### Prompt

```
FASE 1 — ANÁLISIS. Autonomía A1: investigas y documentas, no escribes código de
implementación.

Produce docs/01-analisis.md respondiendo con evidencia, no con suposiciones:

## 1. Objetivo del programa
- El objetivo en UNA frase, en términos del valor entregado, no de la tecnología.
- 3 a 5 preguntas de negocio concretas que el sistema debe poder responder.
  Del tipo: ¿qué organismos concentran mayor monto adjudicado en un período?,
  ¿cuál es el plazo promedio entre publicación y adjudicación?, ¿qué proveedores
  repiten adjudicación con un mismo comprador?
- En 3 o 4 líneas: cómo estas preguntas se conectan con el dominio de un CLM
  (ciclo contractual, obligaciones, vencimientos, contrapartes).
- HECHO VERIFICADO QUE DEBES INCORPORAR AL OBJETIVO: la fuente NO tiene un
  listado de contratos. Expone licitaciones, órdenes de compra, compra ágil y
  proveedores, pero ninguna entidad llamada contrato. El contrato hay que
  RECONSTRUIRLO uniendo el proceso (licitación), el acto de adjudicación, el
  instrumento de ejecución (orden de compra) y los documentos adjuntos.
  Esa reconstrucción no es un obstáculo: es el núcleo del trabajo de ingeniería
  y lo que conecta la demo con lo que hace un CLM al ingestar contratos nacidos
  fuera del sistema. El objetivo debe reflejarlo explícitamente.
- Incorpora el resultado de docs/00-spike.md: si la extracción con modelo de
  lenguaje quedó dentro del alcance, al menos UNA de las preguntas de negocio
  debe requerirla. Si no la requiere ninguna, esa capa no tiene por qué existir
  y hay que sacarla del proyecto.

## 2. Actores
2 perfiles concretos de consumidor de la salida, y qué decide cada uno con estos
datos.

## 3. Investigación de la fuente

Parte de esto YA está verificado. Tu trabajo no es redescubrirlo sino
CONFIRMARLO contra la fuente y profundizarlo. Si algo de lo siguiente resulta
falso o desactualizado, dímelo: es más valioso que confirmarlo.

Lo verificado:
- La API expone licitaciones, órdenes de compra, compra ágil y
  proveedores/organismos. NO existe endpoint de contratos.
- Es dirigida por FECHA: se consulta día por día, no hay cursor ni offset. Eso
  determina la estrategia de particionado.
  licitaciones.json?fecha=ddmmaaaa&estado=<estado>&ticket=...
  licitaciones.json?codigo=<código>&ticket=...
  ordenesdecompra.json?fecha=ddmmaaaa&ticket=...
  ordenesdecompra.json?codigo=<código>&ticket=...
- Ticket vía Clave Única, uno por persona, 10.000 requests diarios, con
  recomendación de consultar en horario de baja carga (22:00 a 07:00).
- Las órdenes de compra se publican con 1 a 2 meses de rezago. Esto condiciona
  la ventana de fechas de la demo: si eliges un rango muy reciente, vas a
  encontrar licitaciones sin su orden de compra asociada.
- Los documentos (bases administrativas, bases técnicas, anexos, y a veces el
  contrato firmado) están SOLO en la ficha web, no en la API.
- El sitio es ASP.NET WebForms con ViewState, así que la ficha de detalle no se
  obtiene con un GET limpio.

Lo que debes investigar y documentar tú, con URLs verificables:
- El diccionario de datos completo de cada endpoint: qué campos trae, cuáles son
  opcionales, qué estados existen y qué significan.
- Cómo se enlaza una licitación con su o sus órdenes de compra. Este es el punto
  crítico del proyecto: sin ese enlace no hay entidad contrato. Documenta el
  campo o mecanismo exacto, y qué pasa cuando la relación no es uno a uno.
- La estructura real de la ficha web: cómo se llega, qué requiere la sesión, y
  dónde están los enlaces a los adjuntos.
- Qué dice robots.txt y los términos de uso.
- Los datasets de Datos Abiertos y la publicación en formato OCDS. Evalúalos en
  serio: es la ruta fácil. Luego decide y JUSTIFICA. Descartar con criterio
  explícito vale más que no haberlos mirado, y "¿por qué no usaste el bulk?" es
  una pregunta probable en la entrevista.
- Un ejemplo real abreviado de respuesta JSON de cada endpoint y uno de la
  estructura HTML de la ficha de detalle.

## 4. Alcance
Lista IN SCOPE y lista OUT OF SCOPE, ambas explícitas. El out of scope acota la
demo a algo terminable y defendible. Justifica un recorte temporal y de volumen.

## 5. Riesgos y supuestos
Tabla: riesgo, probabilidad, impacto, mitigación. Incluye cambios en el HTML,
límites de rate, caídas de la API, datos faltantes, volumen mayor al esperado,
y calidad insuficiente de la extracción con modelo de lenguaje.

## 5b. Línea de corte
Declara explícitamente la DEMO MÍNIMA DEFENDIBLE: el subconjunto que, si el
tiempo se acaba, sigue siendo una demo coherente que puedo presentar sin excusas.
Mi propuesta: scraper + validación + dashboard. Todo lo demás es upside.
Esta decisión se toma ahora, en frío, no la noche antes de la entrevista.

## 6. Criterios de éxito
Qué debe ser cierto al final. Observables, no opiniones.

## Disciplina de esta fase
Haz la investigación real antes de escribir: consulta las URLs, mira las
respuestas. Lo que no puedas verificar va marcado como SUPUESTO POR VERIFICAR,
nunca afirmado. Cierra listando las preguntas abiertas que necesitas que yo
responda.
```

### Gate de salida

- [ ] `docs/01-analisis.md` con las 6 secciones.
- [ ] El objetivo cabe en una frase y no menciona Scrapy ni Python.
- [ ] Hay al menos un ejemplo real de respuesta de la fuente, pegado.
- [ ] El out of scope tiene 4+ ítems.
- [ ] Los criterios de éxito se verifican ejecutando algo.
- [ ] **Karpathy check:** todo lo no verificado está marcado como supuesto.

---

# FASE 2 — DISEÑO

**Autonomía: A1 (Consulta), con A2 solo para archivos de esquema.**
**Verificación:** el diagrama renderiza y cada campo del modelo se justifica contra una pregunta de la Fase 1.

### Prompt 2A — Flujo y tecnología

```
FASE 2A — DISEÑO. Autonomía A1.

Produce docs/02-diseno.md:

## 1. Flujo del programa
Diagrama Mermaid del recorrido completo del dato: descubrimiento, request,
parseo, validación, normalización, persistencia, agregación, render. Marca en el
diagrama dónde ocurren los reintentos, el throttling y el descarte de inválidos.

## 2. Modelo de datos
Contrato de datos explícito: campo, tipo, obligatoriedad, ejemplo, regla de
validación. Al menos Licitacion y OrdenDeCompra, más su relación.

La entidad central es **Contrato**, y es DERIVADA: no existe en la fuente, la
construyes tú uniendo licitación, adjudicación, orden u órdenes de compra y
documentos. Defínela explícitamente, con dos exigencias:
- Cada campo declara de qué fuente vino (API de licitaciones, API de OC, ficha
  web, o inferencia). Sin esa procedencia el dato no es defendible.
- Declara qué pasa cuando la relación no es uno a uno: una licitación con varias
  órdenes de compra, una orden de compra sin licitación (compra ágil o trato
  directo), o una licitación adjudicada cuya OC todavía no se publica por el
  rezago. Los tres casos existen y tu modelo debe tener una respuesta para cada
  uno, no reventar.

Si el spike dejó la capa
de extracción dentro del alcance, agrega las entidades que la sostienen
(Documento y ClausulaExtraida o equivalente), con trazabilidad al documento y
fragmento de origen: nunca un dato extraído por modelo sin poder mostrar de dónde
salió.
Justifica cada campo contra una pregunta de negocio de la Fase 1. Si no responde
ninguna, sobra: elimínalo.

## 3. Estrategia de extracción

Diséñala en tres capas explícitas:
- Capa 1, esqueleto: la API entrega licitaciones y órdenes de compra. Como es
  dirigida por fecha, el recorrido es día por día sobre la ventana elegida.
- Capa 2, documentos: scraping de la ficha web para los adjuntos que la API no
  expone. Considera el manejo de sesión y ViewState de ASP.NET WebForms, y qué
  haces si la ficha cambia de estructura.
- Capa 3, reconstrucción: la unión que produce la entidad Contrato, con su
  procedencia por campo.

Documenta además:
- Qué por API y qué por HTML, y por qué.
- Paginación y particionado por fecha, incluida la elección de la ventana
  temporal considerando el rezago de 1 a 2 meses de las órdenes de compra.
- Idempotencia: cómo evitar duplicados en re-ejecución, cómo hacer incremental.
- Reintentos: qué códigos, backoff, tope.
- Caché de respuestas en desarrollo. Esto es prioridad: sin caché, cada
  iteración de prueba golpea la fuente y el bucle de verificación se vuelve
  lento e irrespetuoso.

## 4. Decisiones de tecnología
Tabla. Por CADA decisión: qué elegimos, alternativa descartada, criterio, y en
qué caso se revierte. Cubre framework de scraping, validación, persistencia,
testing, dashboard, calidad de código, contenedores, CI, y — si aplica — el
proveedor de inferencia.

Sobre la inferencia, la decisión ya está tomada y quiero que la documentes con su
fundamento: interfaz única con DOS adaptadores, local por defecto (Ollama) y
hosted como alternativa conmutable por variable de entorno. El fundamento: el
cliente objetivo de un CLM enterprise procesa contratos confidenciales, y la
pregunta comercial que enfrentan en cada venta es a dónde van esos documentos.
Documenta también la parte honesta: los datos de esta demo son públicos, así que
la decisión es arquitectónica y no una necesidad real de este caso.

Define además el límite de responsabilidad del modelo: los campos estructurados
(montos, RUT, fechas, códigos) se extraen de forma DETERMINISTA desde la API o
con parseo validado. El modelo de lenguaje interviene únicamente donde el texto
es no estructurado. Justifica ese límite en el documento.
Mi preferencia de partida: Python + Scrapy, dashboard HTML estático generado
desde los datos. Justifícala o discútela si hay algo mejor para este caso.

## 5. Estructura de carpetas
Árbol completo, una línea por archivo relevante.

## 6. El punto frágil
Cuál es la parte más frágil de este diseño y qué haríamos si falla.
```

### Prompt 2B — Backlog verificable

```
FASE 2B — BACKLOG. Autonomía A1.

Desde docs/02-diseno.md produce docs/03-plan-codificacion.md.

Principio rector: cada incremento debe poder verificarse MÁS RÁPIDO de lo que
toma escribirlo. Si un incremento requiere 10 minutos de comprobación manual,
está mal dimensionado: pártelo o define primero la herramienta que lo verifica.

Reglas:
- Cada incremento deja el sistema FUNCIONANDO. Nada de "esto sirve recién en el
  incremento 5".
- Orden por riesgo, no por comodidad: primero lo que puede hundir el proyecto
  (¿la fuente responde?, ¿los campos existen?).
- Cada incremento declara su nivel de autonomía (A2, A3 o A4) según el riesgo de
  lo que toca.

Formato obligatorio:

### Incremento N — <título>   [Autonomía: A_]
**Historia:** Como <rol>, quiero <capacidad> para <beneficio>.
**Entrega:** archivos creados o modificados.
**Criterios de aceptación:** condiciones observables en Given/When/Then.
**Comando de verificación:** el comando exacto que ejecuto, y la salida esperada.
**Tiempo de verificación:** cuánto demora comprobarlo. Si supera 60 segundos,
  justifica por qué no se puede acelerar.
**Terminado:** tests pasan, linter limpio, tipos correctos, README actualizado.
**Fuera de alcance:** qué NO se hace todavía.

Incrementos mínimos (ajusta si tu diseño lo pide):
0. Scaffolding: estructura, dependencias, linter, formateador, tipos,
   pre-commit, esqueleto de tests, CI. [A4 — es andamiaje mecánico]
1. Cliente de la fuente: conexión, autenticación, errores, límites, CACHÉ local
   de respuestas. Este incremento es el que acelera todos los siguientes. [A2]
2. Spider de listado: recorrido y paginación, salida cruda a disco. [A3]
3. Validación y normalización: crudo → esquema; los inválidos se cuarentenan, no
   rompen el proceso. [A2 — es el corazón de la calidad del dato]
4. Spider de detalle: lo que solo está en HTML, incluyendo metadatos de adjuntos.
   [A3]
5. Persistencia e incrementalidad: deduplicación y re-ejecución segura. [A2]
6. Capa de análisis: las preguntas de la Fase 1 respondidas con consultas
   concretas. [A3]
7. Dashboard HTML autocontenido: indicadores y tabla explorable. [A4]
8. Endurecimiento: observabilidad, métricas de corrida, fallos parciales,
   documentación de operación. [A3]
9. Extracción contractual con modelo de lenguaje, SOLO si el spike la dejó dentro
   del alcance. Interfaz de extracción con adaptador local y adaptador hosted,
   salida validada contra esquema, trazabilidad al fragmento de origen, y manejo
   del caso en que el modelo devuelve algo no parseable. [A2 — es la capa que más
   fácil se degrada en silencio]
   Va ÚLTIMO por dos razones: depende de los incrementos 4 y 5, y es el único que
   puedo cortar sin que la demo pierda coherencia.

Marca en la tabla resumen qué incrementos están sobre la línea de corte definida
en la Fase 1 y cuáles son upside.

Cierra con tabla resumen: incremento, autonomía, tiempo estimado, dependencia,
riesgo que mitiga.
```

### Gate de salida

- [ ] `docs/02-diseno.md` con Mermaid que renderiza.
- [ ] Cada campo del modelo justificado contra una pregunta de negocio.
- [ ] Tabla de decisiones con alternativa descartada en cada fila.
- [ ] `docs/03-plan-codificacion.md` en el formato exigido.
- [ ] **Karpathy check:** cada incremento declara autonomía y tiempo de verificación. Si alguno dice "verificar manualmente que funcione", devuélvelo.

---

# FASE 3 — CODIFICACIÓN

**Autonomía: la que declare cada incremento.**
**Verificación:** el bucle. Aquí es donde el método vive o muere.

### Prompt de arranque

```
FASE 3 — CODIFICACIÓN.

Implementamos docs/03-plan-codificacion.md un incremento a la vez, respetando el
nivel de autonomía declarado en cada uno.

Protocolo por incremento, sin saltos:
1. Anuncias qué incremento haces, su nivel de autonomía, y relees en voz alta sus
   criterios de aceptación.
2. Escribes PRIMERO la prueba que demuestra el criterio. La ejecutas. Me muestras
   que falla. Una prueba que nunca falló no prueba nada.
3. Escribes el código mínimo para que pase. Nada especulativo "por si acaso".
4. Ejecutas el comando de verificación y me pegas la salida REAL, no la esperada.
5. Ejecutas el pipeline de calidad: linter, formateador, tipos, tests.
6. Actualizas el README con lo que ahora se puede hacer.
7. Propones el mensaje de commit.
8. Te DETIENES y esperas mi aprobación.

Reglas duras:
- Test que falla se arregla antes de seguir. No se comenta ni se marca skip.
- Si el diseño de la Fase 2 resultó equivocado, PARAS, me avisas, y actualizamos
  el documento antes de continuar.
- Si la fuente devuelve algo distinto a lo asumido, va a docs/hallazgos.md. Esos
  hallazgos son el mejor material que vas a tener para la entrevista: demuestran
  que trabajaste con la realidad y no con una fuente imaginaria.
- Nunca inventes datos para hacer pasar un test que debería usar datos reales.
  Usa respuestas reales grabadas como fixture.
- Si te pasas del tamaño de diff de tu nivel de autonomía, párate y pártelo.

Empieza por el Incremento 0.
```

### Prompt de cierre de cada incremento

```
Incremento <N> listo. Antes de que lo apruebe, autocrítica honesta:
- ¿Qué parte de este código se rompe primero cuando cambie la fuente?
- ¿Qué caso borde no cubren los tests?
- ¿Escribiste algo "por si acaso" que deberíamos borrar ahora?
- ¿Hay alguna línea que yo no podría explicar si me la preguntan en la
  entrevista? Si la hay, simplifícala o explícamela.
```

### Prompt de rescate — cuando el bucle se atasca

```
Llevamos varias iteraciones sin cerrar este incremento. Alto.
No propongas otro arreglo todavía. Primero:
1. ¿Cuál es tu hipótesis actual de por qué falla, en una frase?
2. ¿Qué evidencia concreta la sostiene? Si no tienes evidencia, el siguiente paso
   es conseguirla, no arreglar a ciegas.
3. ¿Cuál es el experimento más pequeño que confirma o descarta esa hipótesis?
Ejecuta solo ese experimento y muéstrame el resultado.
```

### Gate de salida

- [ ] Todos los incrementos cerrados con su verificación pasando.
- [ ] Un comando levanta el proyecto desde cero en una máquina limpia.
- [ ] `docs/hallazgos.md` con contenido real.
- [ ] El dashboard se genera y abre.
- [ ] Linter, tipos y tests en verde.
- [ ] **Karpathy check:** puedes explicar cualquier línea del repo. Si hay código que no entiendes, no está terminado.

---

# FASE 4 — DESPLIEGUE

**Autonomía: A3.**
**Verificación:** otra persona lo ejecuta sin tu ayuda.

### Prompt

```
FASE 4 — DESPLIEGUE. Autonomía A3.

## 1. Reproducibilidad
- Contenedor con build reproducible, sin secretos incrustados.
- Archivo de ejemplo de variables de entorno, cada variable documentada.
- Un comando único que en máquina limpia corre el pipeline completo y deja el
  dashboard generado.
- Verifícalo de verdad: construye la imagen, ejecútala, pégame la salida.

## 2. Ejecución programada
- Automatización periódica que publique el dashboard como sitio estático.
- La corrida FALLA RUIDOSAMENTE si la extracción devuelve cero registros o si la
  tasa de inválidos supera un umbral. Un scraper que falla en silencio es peor
  que uno caído: envenena los datos sin avisar.

## 3. Integridad de la corrida
Cada ejecución deja un reporte: extraídos, válidos, rechazados, duración, errores
por tipo. Versionado o publicado, para comparar corridas entre sí.

## 4. README para dos lectores
- Quien quiere ejecutarlo en 2 minutos.
- Quien quiere entender las decisiones de arquitectura.
Más una sección de limitaciones conocidas, honesta.

## 5. Guion de demo
docs/demo.md con el recorrido de 5 minutos: qué ejecutar, en qué orden, qué
señalar en cada paso, y las 3 preguntas técnicas más probables con su respuesta.
```

### Gate de salida

- [ ] Corre desde cero en máquina sin configuración previa.
- [ ] La ejecución automatizada quedó probada al menos una vez.
- [ ] README distingue camino rápido de camino profundo.
- [ ] `docs/demo.md` cronometrado.

---

# FASE 5 — MANTENCIÓN

*Pendiente, se aborda después del despliegue.*

Temas a cubrir: detección de cambios en la estructura de la fuente, alertas de degradación silenciosa, versionado del esquema de datos, política de reprocesamiento histórico, rotación de dependencias.

---

# Anexo — Cómo defender esto en la entrevista

Lo que separa una demo de scraping buena de una mediocre no es el spider. Es todo lo que lo rodea.

**"¿Qué haces cuando cambian el HTML?"**
Fase 4: validación con umbrales y fallo ruidoso. Muestra el reporte de corrida.

**"¿Cómo escalas a 10 millones de registros?"**
Fase 2: particionado por fecha, incrementalidad, idempotencia. Ten claro qué se rompe primero.

**"¿Y el tema legal y ético?"**
Contexto permanente: robots.txt, API antes que scraping, User-Agent identificable, throttling conservador, solo datos públicos. En una empresa de contratos y compliance, esta no es una pregunta de relleno.

**"¿Por qué no usaste los datos abiertos en bulk, que ya están descargados?"**
Fase 1: los evaluaste. El bulk trae el registro tabular, no los documentos, y el
objetivo incluye reconstruir la entidad contractual desde las bases de
licitación. Muestra la justificación escrita en el análisis, no improvises.

**"¿Por qué Scrapy y no requests o Playwright?"**
Tabla de decisiones de la Fase 2, con alternativa descartada y criterio. La parte fuerte de la respuesta: en qué caso cambiarías de opinión.

**"¿Usaste IA para esto?"**
Sí, y esa es la respuesta correcta en 2026. Lo que te distingue es *cómo*: muéstrales `/docs`, el dial de autonomía, y el hecho de que cada incremento tiene un comando de verificación. Tu argumento es que la IA aceleró la generación y tú construiste el sistema de verificación. Eso es exactamente lo que una empresa que vende IA nativa quiere escuchar de un candidato.

**"¿No había una lista de contratos que bajar?"**
No, y esa es la mejor parte. La fuente no tiene entidad contrato: tiene un
proceso, un instrumento de ejecución y unos documentos, en formatos distintos.
Reconstruir la entidad contractual desde fragmentos dispersos, con procedencia
por campo, es exactamente lo que hace un CLM al ingestar contratos que nacieron
fuera del sistema. Bajar una lista habría sido un ejercicio de paginación.

**El cierre que conecta con Webdox:** los datos que extrajiste son datos contractuales —monto, plazo, contraparte, adjudicación, adjuntos—. Es precisamente lo que un CLM necesita capturar cuando ingesta contratos nacidos fuera del sistema. Ese puente es lo que van a recordar.

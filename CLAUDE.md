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

## Estado actual

**Fase en curso:** Fase 0 — Repositorio y contexto (cerrada).
**Siguiente:** Spike 0 — Validar el supuesto más riesgoso (extracción con modelo
de lenguaje local sobre bases de licitación reales). Timebox: 1 hora.

| Fase | Estado |
|---|---|
| Fase 0 — Repositorio y contexto | ✅ Cerrada |
| Spike 0 — Validación de supuesto | ⏳ Pendiente |
| Fase 1 — Análisis | ⏳ Pendiente |
| Fase 2 — Diseño | ⏳ Pendiente |
| Fase 3 — Codificación | ⏳ Pendiente |
| Fase 4 — Cierre y presentación | ⏳ Pendiente |

**Bloqueante resuelto (2026-08-31):** ticket de la API de Mercado Público
obtenido y verificado contra la fuente. Vive en `.env` como `MP_API_TICKET`,
nunca en el repositorio.

**Hechos verificados contra la API en la prueba de humo del 2026-08-31**, para
no redescubrirlos en la Fase 1:
- `licitaciones.json?fecha=ddmmaaaa&estado=adjudicada` devuelve un LISTADO
  pobre: solo 4 campos (`CodigoExterno`, `Nombre`, `CodigoEstado`,
  `FechaCierre`). No trae montos, ni organismo, ni adjudicación.
- El detalle exige una segunda llamada, `licitaciones.json?codigo=<código>`, y
  devuelve 54 campos de nivel 1, incluido un bloque contractual directamente
  relevante para un CLM: `Adjudicacion` (con `UrlActa`),
  `TiempoDuracionContrato`, `EsRenovable`, `PeriodoTiempoRenovacion`,
  `SubContratacion`, `ProhibicionContratacion`, `NombreResponsableContrato`,
  `Items`, `Comprador`.
- Costo real: **1 request por día + 1 request por licitación**. El 10-03-2025
  tuvo 248 licitaciones adjudicadas. Con tope de 10.000 requests diarios, una
  ventana amplia no cabe en una sola corrida.

## Cadena de acceso a los documentos, verificada el 2026-08-31

Recorrido real, comprobado request a request:
1. `licitaciones.json?codigo=<código>` devuelve `Adjudicacion.UrlActa`, que
   contiene el token `qs` cifrado de la ficha. **No hay que hacer ingeniería
   inversa del token: la API lo entrega.**
2. `RFB/DetailsAcquisition.aspx?qs=<token>` carga con un **GET limpio**
   (HTTP 200, ~370 KB). Corrige el supuesto de `docs/00-metodo.md`, que daba
   por hecho que el ViewState impedía el GET directo. La ficha sí trae
   ViewState, pero no lo exige para leerla.
3. El HTML de la ficha trae, en el `onclick` de `imgAdjuntos`, el token `enc`
   de la página de adjuntos.
4. **`Attachment/ViewAttachment.aspx?enc=<token>` está protegida por reCAPTCHA
   Enterprise con scoring de bot.** Devuelve 4.6 KB que ejecutan
   `grecaptcha.enterprise.execute(...)`, envían el token por POST a
   `ViewAttachment.aspx?ajax=1`, y según el score (umbral 0.5) redirigen a
   `ViewAttachmentLC.aspx?enc=...` o a `/Procurement/403.html`.

**Consecuencia de diseño, no negociable:** la descarga automatizada de adjuntos
queda FUERA DE ALCANCE. El token de redirección viene en el HTML y permitiría
saltarse el chequeo, pero eso es evadir detección de bots y contradice una
restricción explícita del proyecto. No se hace, y el hallazgo se documenta y se
defiende como decisión.

Alternativas para la capa de documentos, a resolver en la Fase 1:
- Apoyarse en los campos contractuales que la API YA entrega de forma
  determinista, que son sustanciales.
- Ingesta asistida: un humano deposita los PDF en una carpeta y el pipeline los
  procesa. Es honesto y además refleja cómo un CLM real ingesta contratos
  nacidos fuera del sistema.
- Evaluar Datos Abiertos / OCDS como fuente alternativa de documentos.

Dato menor pero útil: **`https://www.mercadopublico.cl/robots.txt` devuelve 404.**
La fuente no declara reglas de exclusión. No habilita nada: el throttling
conservador se mantiene igual.

## Límite de responsabilidad del modelo, verificado con evidencia

La sección "Etapas y plazos" de la ficha web es, campo por campo, el bloque
`Fechas` de la API. Comprobado en 2678-1-LR25 con coincidencia 11 de 11,
incluidos los tres "No hay información" que corresponden a `FechaSoporteFisico`,
`FechaEstimadaFirma` y `FechaTiempoEvaluacion` en `None`.

Consecuencia: **ninguna fecha del proceso se le pide a un modelo de lenguaje.**
Son campos estructurados, tipados y exactos que la API entrega gratis. Pedirlos
por inferencia es pagar alucinaciones por datos que ya están ciertos.

Cuidado con la ambigüedad de la palabra "plazo", que designa dos cosas
distintas:
- **Plazos del proceso** (preguntas, apertura, adjudicación): bloque `Fechas`.
- **Plazo del contrato**: `TiempoDuracionContrato` +
  `UnidadTiempoDuracionContrato`.

Enum `UnidadTiempoDuracionContrato`, decodificado cruzando la API contra la
ficha web (sección "7. Montos y duración del contrato"):
- **`1` = HORAS** — 1300-43-LP24: API `TiempoDuracionContrato='36'`, `Unidad=1`;
  ficha: "36 Horas".
- **`4` = MESES** — 2328-443-LR24: API `'24'`/`Unidad=4`; ficha: "24 Meses"; el
  acta lo repite en prosa. Y 2678-1-LR25: API `'10'`/`Unidad=4`; ficha:
  "10 Meses".
- Los demás valores siguen SIN decodificar. No asumirlos.

Esa validación cruzada —enum sin documentar contra prosa de un documento
independiente— es material de demo: es como se audita un campo cuyo significado
el proveedor de datos no publica.

## La ficha web expone garantías que la API NO tiene

Revisados los 54 campos de la respuesta de `licitaciones.json?codigo=`: **no hay
ni un solo campo de garantías ni cauciones.** La ficha web sí las trae, en su
sección "8. Garantías requeridas", y con detalle: tipo, beneficiario, fecha de
vencimiento, monto (en pesos o en porcentaje), glosa exigida y condiciones de
restitución.

Este es EL caso que justifica la capa de scraping HTML bajo la regla "API
primero, HTML solo para lo que la API no expone". Y la ficha se obtiene con un
GET limpio, sin reCAPTCHA.

Estructura constante en las tres fichas medidas: exactamente 2 garantías,
seriedad de la oferta y fiel cumplimiento del contrato, con los mismos rótulos
(`Beneficiario:`, `Fecha de vencimiento:`, `Monto:`, `Glosa:`).

**Consecuencia para la capa de inferencia:** esa sección es TABULAR, y un regex
la extrae entera y sin error. El modelo de lenguaje no debe tocarla. Su dominio
legítimo se reduce a la prosa libre (descripción, glosa, condiciones de
restitución) y a lo que solo vive en las bases administrativas, que están tras
el reCAPTCHA. Esto acota mucho la capa 9 del backlog y hay que decidirlo con el
resultado del spike en la mano.

## Regla de validación derivada de un dato corrupto real

1300-43-LP24 (SENAMA, aseo de una casa de acogida) declara plazo de contrato
**36 horas** y, a la vez, una garantía de fiel cumplimiento que vence el
**29-12-2027**. Nadie cauciona hasta 2027 un contrato de 36 horas: el plazo está
mal cargado por el organismo, casi seguro son 36 meses.

Regla de plausibilidad que se deriva y entra al pipeline: *el vencimiento de la
garantía de fiel cumplimiento debe ser coherente con la fecha de adjudicación
más la duración declarada del contrato.* Los otros dos casos la cumplen
(Mostazal 10 meses / vence 02-03-2026; Puerto Montt 24 meses / vence
29-04-2027). Es una regla nacida de los datos, no inventada, y detecta basura de
la fuente sin necesidad de un modelo.

## El acta de adjudicación SÍ es accesible

`RFB/StepsProcessAward/PreviewAwardAct.aspx?qs=<token>` responde HTTP 200 con un
GET limpio y **sin reCAPTCHA**, con el mismo token `qs` de la ficha. Rescata en
parte la capa de documentos que el bloqueo de adjuntos daba por perdida.

Riqueza muy desigual entre organismos, medida sobre tres actas:
| Acta | Caracteres | Contenido contractual |
|---|---|---|
| 2328-443-LR24 (Puerto Montt) | 7.374 | Duración, monto y garantía de fiel cumplimiento en prosa |
| 1300-43-LP24 (SENAMA) | 14.207 | Menciona garantía al pasar |
| 2678-1-LR25 (Mostazal) | 29.533 | Ninguno: se remite a las bases |

La variabilidad NO depende del estado de la licitación, sino de la práctica de
redacción del organismo. El modelo de datos debe tolerar que el acta no aporte
nada.

## Persistencia: PostgreSQL (decidido el 2026-08-31)

**PostgreSQL 18** como motor principal, ya instalado y corriendo como servicio en
la máquina de desarrollo.

El criterio que decidió: **la demo la ejecuta el desarrollador compartiendo
pantalla, no el entrevistador clonando el repositorio.** Esa es la razón, y si
cambia, la decisión se revisa. SQLite ganaba solo bajo el supuesto contrario
—cero configuración para un tercero— y ese supuesto no aplica.

Lo que Postgres aporta al caso concreto:
- Funciones de ventana para las preguntas de negocio de la Fase 1 (dispersión de
  plazos por organismo, proveedores que repiten con un mismo comprador).
- `JSONB` para guardar la respuesta cruda de la API junto al registro
  normalizado, sin inventar tablas paralelas.
- Es lo que un CLM enterprise usa en producción.

**Condición que se mantiene:** la capa de acceso a datos queda detrás de
`DATABASE_URL` y con SQL portable. No para soportar dos motores hoy, sino para
que agregar SQLite después —si alguna vez hace falta que un tercero clone y
ejecute— sea un adaptador y no una reescritura. Mismo patrón que la capa de
inferencia: la dependencia externa es conmutable, no incrustada.

**Riesgo asumido, explícito:** un repositorio que exige un servidor Postgres
corriendo no se ejecuta solo. Si el entrevistador quiere probarlo por su cuenta
después de la reunión, no va a poder sin instalar. Se acepta a cambio de una
demo más cercana a producción.

## Decisiones tomadas (2026-08-31)

- **Profundidad sobre volumen.** La demo no aspira a cobertura exhaustiva de la
  fuente. Reconstruye BIEN un conjunto acotado de contratos: ventana de 5 días
  hábiles y tope de `MAX_LICITACIONES_DETALLE` por corrida. El criterio de
  éxito es la completitud y la trazabilidad de cada contrato reconstruido, no
  cuántos son. Si en la entrevista preguntan por el volumen, la respuesta es
  que el volumen es una variable de configuración y la parte difícil —la
  reconstrucción de la entidad contrato— es la misma con 50 que con 50.000.
- **`CantidadReclamos` queda FUERA del modelo de datos.** Marcó 11819 en una
  licitación individual, lo que delata un contador global mal expuesto y no un
  dato del registro. No se incluye ningún campo cuyo significado no podamos
  defender.

Este archivo se actualiza al cerrar cada fase.

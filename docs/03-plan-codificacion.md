# Fase 2B — Plan de codificación

Backlog derivado de `docs/02-diseno.md`.

**Principio rector:** cada incremento debe poder verificarse **más rápido de lo
que toma escribirlo**. Si comprobarlo exige diez minutos de revisión manual, está
mal dimensionado: se parte, o se construye primero la herramienta que lo
verifica.

**Orden por riesgo, no por comodidad.** Primero lo que puede hundir el proyecto.

## Definición de TERMINADO

Aplica a todos los incrementos, no se repite en cada uno:

- `pytest` pasa
- `ruff check` y `ruff format --check` limpios
- `mypy src/` sin errores
- README actualizado con lo que ahora funciona
- Commit convencional en su rama `inc/N-nombre`

## Resumen

| # | Incremento | Autonomía | Verificación | Línea de corte |
|---|---|---|---|---|
| 0 | Andamiaje | A4 | 30 s | ✅ dentro |
| 1 | Cliente HTTP con caché | A2 | 20 s | ✅ dentro |
| 2 | Descubrimiento de órdenes de compra | A3 | 40 s | ✅ dentro |
| 3 | Detalle de OC y enlace a licitación | A2 | 45 s | ✅ dentro |
| 4 | **Parseo de garantías (sin red)** | A3 | 30 s | ✅ dentro |
| 5 | Licitación, OCDS y descarga de ficha | A3 | 50 s | ✅ dentro |
| 6 | Validación y cuarentena | A2 | 15 s | ✅ dentro |
| 7 | Reconstrucción del Contrato | A2 | 20 s | ✅ dentro |
| 8 | Persistencia idempotente | A2 | 25 s | ✅ dentro |
| 9 | Consultas de análisis | A3 | 15 s | ✅ dentro |
| 10 | Dashboard FastAPI + export de respaldo | A3 | 30 s | ✅ dentro |
| 11 | Despliegue a Lightsail | A4 | 60 s | ✅ dentro |
| 12 | Endurecimiento y observabilidad | A3 | 40 s | ⬜ upside |
| 13 | Inferencia: causales y discrepancias | A2 | 8 min | ⬜ upside |

**Todo lo marcado "dentro" es la demo mínima defendible.** Si el tiempo se
acaba en el 11, hay una demo coherente que se presenta sin excusas.

**El incremento 4 va adelantado a propósito.** Es el punto frágil declarado en el
diseño y la única fuente de garantías. Si el parseo de la ficha resulta inviable,
hay que saberlo antes de construir ocho incrementos encima.

---

### Incremento 0 — Andamiaje   [Autonomía: A4]

**Historia:** Como desarrollador, quiero un proyecto con calidad automatizada
para que cada incremento posterior se verifique solo.

**Entrega:** `pyproject.toml`, `src/contratos/__init__.py`, `src/contratos/config.py`,
**`src/contratos/cli.py`** (esqueleto con `--help`, sin subcomandos aun),
`tests/test_config.py`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`.

**Nota:** `cli.py` nace vacio aqui y **cada incremento posterior agrega su
propio subcomando**. Sin esto, los comandos de verificacion de los
incrementos 2 en adelante invocarian algo que no existe.

**Criterios de aceptación:**
- **Dado** un clon limpio, **cuando** ejecuto `pip install -e ".[dev]"`,
  **entonces** instala sin errores.
- **Dado** el proyecto instalado, **cuando** ejecuto `pytest`, **entonces** corre
  al menos un test y pasa.
- **Dado** el CLI, **cuando** ejecuto `python -m contratos.cli --help`,
  **entonces** imprime la ayuda y sale con codigo 0.
- **Dado** un `.env` con una variable obligatoria ausente, **cuando** importo
  `config`, **entonces** falla con un mensaje que nombra la variable faltante.

**Comando de verificación:**
```bash
pip install -e ".[dev]" && ruff check . && mypy src/ && pytest -q
python -m contratos.cli --help
```
Salida esperada: **`5 passed`**, sin errores de ruff ni mypy, y la ayuda del
CLI. **Medido: 16 s**, bajo el presupuesto de 30.

**Tiempo de verificación:** ~30 s.

**Fuera de alcance:** nada de red, nada de parseo.

---

### Incremento 1 — Cliente HTTP con caché   [Autonomía: A2]

**Historia:** Como desarrollador, quiero un cliente que cachee cada respuesta en
disco para que iterar sobre el parseo no vuelva a golpear la fuente.

**Este incremento es el que acelera todos los siguientes.** Sin la caché, cada
prueba consume cupo del ticket y espera a la red.

**Entrega:** `src/contratos/cliente.py`, `tests/test_cliente.py`,
`tests/fixtures/respuesta_oc.json`.

**Criterios de aceptación:**
- **Dado** un GET a una URL nueva, **cuando** el cliente responde 200,
  **entonces** escribe el cuerpo crudo en `data/raw/<hash>.json` antes de
  parsear.
- **Dado** que esa URL ya está en caché, **cuando** se pide de nuevo,
  **entonces** se sirve desde disco y **no se emite ningún request**.
- **Dado** un 429 o un 503, **cuando** el cliente reintenta, **entonces** aplica
  backoff exponencial con tope de 3 intentos.
- **Dado** un 404, **cuando** ocurre, **entonces** falla de inmediato sin
  reintentar y registra el error. Nada de `except` silencioso.
- **Dado** `MAX_REQUESTS_PER_RUN` alcanzado, **cuando** se pide uno más,
  **entonces** aborta con un mensaje explícito.
- **Dado** un cuerpo con sobre de error (`Codigo` y `Mensaje` sin `Listado`),
  **cuando** llega con un código 2xx, **entonces** falla y **no se cachea**.
  Mercado Público responde **HTTP 203** con "Ticket no válido" cuando el ticket
  vence, y 203 es un código de éxito: un cliente que solo mire `status >= 400`
  cachearía el error como dato y la corrida daría cero registros sin avisar.
  El ticket se renueva a diario, así que esto pasa seguido.

**Comando de verificación:**
```bash
pytest tests/test_cliente.py -v
```
Salida esperada: **6 tests pasan**. Ninguno toca la red — usan `respx` para
simular respuestas.

**Tiempo de verificación:** **10 s medidos**, bajo el presupuesto de 20.

**Comprobación adicional contra la fuente real**, hecha una vez: 9.206 órdenes
en 0,34 s la primera llamada y 0,02 s la segunda desde caché. **16× más rápida
y un request menos.**

**Fuera de alcance:** conocimiento de qué endpoint es cuál. El cliente es
genérico.

**Lección de método.** El criterio "pre-commit configurado" del Incremento 0 se
dio por cumplido con el archivo presente, pero **nadie había ejecutado
`pre-commit install`**: los tres primeros commits pasaron sin hooks. Un criterio
que comprueba que un archivo existe no comprueba que haga algo. Los criterios de
los incrementos siguientes verifican comportamiento, no presencia.

---

### Incremento 2 — Descubrimiento de órdenes de compra   [Autonomía: A3]

**Historia:** Como analista, quiero obtener las órdenes de compra de una fecha y
quedarme solo con las que pueden tener licitación, para acotar el trabajo.

**Entrega:** `src/contratos/fuentes/api_oc.py`, `tests/test_api_oc.py`,
`data/samples/oc_listado.json`.

**Criterios de aceptación:**
- **Dado** una fecha, **cuando** pido el listado, **entonces** obtengo los
  registros con `Codigo`, `Nombre` y `CodigoEstado`.
- **Dado** el listado, **cuando** clasifico por sufijo del código, **entonces**
  separo los que pueden tener licitación (`SE`, `CC`) de los que no
  (`AG`, `CM`, `TD`), **sin emitir ningún request adicional**.
- **Dado** el listado de muestra guardado, **cuando** clasifico, **entonces** de
  9.206 registros 4.047 son enlazables y 5.159 huérfanos.
- **Dado** un tipo de orden que no está en ninguna lista, **cuando** clasifico,
  **entonces** se aparta y se cuenta. **No se asume a qué grupo pertenece.**
- **Dado** los límites configurados, **cuando** los aplico, **entonces** devuelve
  100 con proceso y 50 sin proceso. **Ambos grupos entran a la muestra**: sin los
  huérfanos, la pregunta de negocio 5 no tiene respuesta y el caso 'OC sin
  licitación' del modelo nunca se ejercita.

**Comando de verificación:**
```bash
pytest tests/test_api_oc.py -v
python -m contratos.cli descubrir --fecha 2025-05-15 --limite 5
```
Salida esperada: los dos grupos con sus conteos —4.047 con proceso y 5.159 sin
proceso— y `requests emitidos: 1` en la primera corrida, **0 en las siguientes**
porque salen de caché.

**Tiempo de verificación:** **3 s medidos** con un request real, bajo el
presupuesto de 40. La suite: 25 tests en ~3 s.

**Hallazgo del incremento.** Apareció un sexto tipo de orden, `CT`, que no
estaba en ninguna de las dos listas. Se verificó pidiendo su detalle antes de
clasificarlo: `CodigoLicitacion` vacío, o sea huérfana. Se agregó a la lista con
evidencia, no por descarte.

**Fallo corregido.** El logger de `httpx` imprimía la URL completa en INFO, y el
ticket viaja como parámetro: quedaba a la vista en cualquier consola o captura
de pantalla. Se subió su umbral a WARNING y hay un test de regresión.

**Fuera de alcance:** el detalle de cada orden.

---

### Incremento 3 — Detalle de OC y enlace a licitación   [Autonomía: A2]

**Historia:** Como analista, quiero el detalle de cada orden y el código de su
licitación, para poder reconstruir el proceso que la originó.

**Entrega:** `api_oc.py` ampliado, `src/contratos/modelos.py` con `OrdenCompra`,
`tests/test_detalle_oc.py`.

**Criterios de aceptación:**
- **Dado** un código de OC, **cuando** pido el detalle, **entonces** obtengo los
  28 campos, incluidos `Total`, `Proveedor`, `Comprador` y `Fechas`.
- **Dado** una OC de tipo `SE`, **cuando** leo `CodigoLicitacion`, **entonces**
  viene poblado.
- **Dado** una OC de tipo `AG`, `CM` o `TD`, **cuando** leo ese campo,
  **entonces** viene vacío, y el modelo lo acepta como **`None` válido, no como
  error**.
- **Dado** un lote, **cuando** proceso, **entonces** se registra cuántas quedaron
  sin licitación.
- **Dado** el `CodigoEstado`, **cuando** lo mapeo, **entonces** reconozco los
  cinco valores medidos: 12 Recepción Conforme, 6 Aceptada, 9 Cancelada,
  4 Enviada a proveedor, 5 En proceso. **Un valor desconocido no se adivina**:
  el registro va a cuarentena.
- **Dado** una orden en estado 9 (Cancelada), **cuando** la proceso, **entonces**
  se ingesta igual pero con `es_comprometido = false` y `es_ejecutado = false`.
  Se midió una cancelada con monto $1.346.366: sumarla al gasto lo inflaría.
- **Dado** un lote con un registro que no valida, **cuando** lo proceso,
  **entonces** ese va a cuarentena con su motivo y **los demás continúan**. Un
  registro malo no aborta la corrida.

**Comando de verificación:**
```bash
pytest tests/test_detalle_oc.py -v
python -m contratos.cli detalle-oc --codigo 1002772-10006-SE25
```
Salida esperada: JSON con `codigo_licitacion: "1002772-78-LR24"`, más las tres
derivadas `tiene_proceso`, `es_comprometido` y `es_ejecutado`.

**Tiempo de verificación:** **3 s medidos** para 13 tests, bajo el presupuesto
de 45.

**Fuera de alcance:** pedir la licitación.

---

### Incremento 4 — Parseo de garantías desde HTML guardado   [Autonomía: A3]

**Historia:** Como gestor de contratos, quiero las garantías exigidas, para saber
qué cauciones siguen vivas.

**ADELANTADO A PROPÓSITO, y deliberadamente SIN RED.** Es el punto frágil del
diseño y la única fuente de garantías. El riesgo está en el **parseo**, no en la
descarga, así que este incremento es una **función pura**: recibe HTML y
devuelve garantías.

Eso resuelve además una dependencia invertida: `UrlActa` viene del detalle de la
licitación, que todavía no está construido. La **descarga** de la ficha se
conecta en el incremento 5.

**Entrega:** `src/contratos/fuentes/ficha_web.py` (solo el parser),
`tests/test_ficha_web.py`, tres fichas reales en `tests/fixtures/`.

**Criterios de aceptación:**
- **Dado** el HTML de una ficha, **cuando** parseo la sección 8, **entonces**
  obtengo las garantías con tipo, monto, si es porcentaje, y vencimiento.
- **Dado** `ficha_2678.html`, **cuando** parseo, **entonces** obtengo exactamente
  2 garantías: seriedad por `1500000 CLP` que vence `2025-04-24`, y fiel
  cumplimiento por `5%` que vence `2026-03-02`.
- **Dado** un HTML sin sección 8, **cuando** parseo, **entonces** devuelvo lista
  vacía **con una marca de que la fuente falló**, distinguible de "no tiene
  garantías".
- **Dado** un lote, **cuando** menos del 90% tiene al menos una garantía,
  **entonces** la corrida **falla ruidosamente**.

**Comando de verificación:**
```bash
pytest tests/test_ficha_web.py -v
```
Salida esperada: **9 tests pasan** en 0,23 s, todos contra HTML guardado, **sin
tocar la red**.

**El parseo NO usa regex sobre el texto.** La ficha es ASP.NET WebForms y su
GridView deja ids estables —`grvGarantias_ctl02_lblFicha8Monto`,
`..._lblFicha8FechaVencimiento`— así que se usan selectores CSS sobre esos ids.
Si el sitio cambia el maquetado pero mantiene el GridView, el parser sigue
funcionando. El regex del spike se rompía con cualquier cambio de espaciado.

**Tiempo de verificación:** ~30 s, con **cero requests**.

**Fuera de alcance:** descargar la ficha (incremento 5), las cláusulas en prosa
de la sección 9, y los adjuntos, fuera de alcance del proyecto por el reCAPTCHA.

---

### Incremento 5 — Licitación, OCDS y descarga de la ficha   [Autonomía: A3]

**Historia:** Como analista, quiero los datos del proceso, su monto adjudicado y
la ficha descargada, para alimentar el parser del incremento 4.

**Entrega:** `fuentes/api_licitacion.py`, `fuentes/ocds.py`, la función de
descarga en `fuentes/ficha_web.py`, `tests/` de los tres.

**Criterios de aceptación:**
- **Dado** un código de licitación, **cuando** pido el detalle, **entonces**
  obtengo los 54 campos, incluidos `TiempoDuracionContrato` y `EsRenovable`.
- **Dado** el bloque `Fechas`, **cuando** lo leo, **entonces** capturo
  `FechaPublicacion` y `FechaAdjudicacion`. **Ambas son necesarias para la
  pregunta de negocio 3** y sin ellas esa pregunta queda sin respuesta.
- **Dado** `Items[].Adjudicacion`, **cuando** lo leo, **entonces** capturo
  `RutProveedor`, `Cantidad` y `MontoUnitario` de cada ítem, que es lo que
  permite atribuir el monto adjudicado a un proveedor concreto.
- **Dado** `2678-1-LR25`, **cuando** sumo los ítems por RUT, **entonces** obtengo
  cinco proveedores, el mayor con $167.000.000, y el total da $441.600.000,
  **idéntico al `award.value` de OCDS**.
- **Dado** `UnidadTiempoDuracionContrato`, **cuando** lo decodifico, **entonces**
  `1` es horas y `4` es meses; **cualquier otro valor produce `desconocido`, no
  una suposición**.
- **Dado** el mismo código, **cuando** consulto OCDS, **entonces** obtengo el
  monto adjudicado y el número de oferentes, **sin ticket y sin consumir cupo**.
- **Dado** `2678-1-LR25`, **cuando** consulto ambas fuentes, **entonces** el
  estimado es `522500000` y el adjudicado `441600000`.
- **Dado** el `UrlActa` que devuelve el detalle, **cuando** extraigo el token
  `qs` y pido la ficha, **entonces** responde **200 con un GET limpio** y el HTML
  queda en `data/raw/`.
- **Dado** ese HTML, **cuando** lo paso al parser del incremento 4, **entonces**
  devuelve las garantías. **Aquí se cierra el circuito.**

**Comando de verificación:**
```bash
pytest tests/test_api_licitacion.py tests/test_ocds.py -v
python -m contratos.cli licitacion --codigo 2678-1-LR25
```
Salida esperada: tabla con estimado, adjudicado, duración `10 meses`, `renovable:
false`, `oferentes: 6`.

**Tiempo de verificación:** **3,6 s medidos** para 19 tests, bajo el presupuesto
de 50. El circuito completo contra la fuente real: 3 requests.

**Hallazgo del incremento.** El monto adjudicado **no es comparable entre
contratos**: en un convenio de suministro es un precio unitario. Puerto Montt
adjudica $783,19 —el litro de diésel— y su acta declara $1.500.000.000 aparte.
Las dos fuentes coinciden en los $783, así que la regla cruzada sigue siendo
válida; lo que no vale es sumarlos. Ver `docs/02-diseno.md`.

**Fuera de alcance:** unir las fuentes. Eso es el incremento 7.

---

### Incremento 6 — Validación y cuarentena   [Autonomía: A2]

**Historia:** Como responsable del dato, quiero que lo inválido se aparte en vez
de romper la corrida, para que un registro malo no cueste una re-ejecución
completa.

**Es el corazón de la calidad del dato.**

**Entrega:** `src/contratos/validacion.py`, `tests/test_validacion.py`.

**Criterios de aceptación:**
- **Dado** un registro que no cumple su esquema, **cuando** valido, **entonces**
  va a `data/quarantine/` con el motivo, y **la corrida continúa**.
- **Dado** una garantía de fiel cumplimiento que vence **antes** de la fecha de
  término estimada del contrato, **cuando** aplico la regla de plausibilidad,
  **entonces** se marca como implausible.
- **Dado** el caso real de SENAMA (`36 horas` de contrato, garantía hasta
  `2027-12-29`), **cuando** valido, **entonces** la regla lo detecta.
- **Dado** los ítems adjudicados de una licitación, **cuando** sumo los montos
  de todos sus proveedores, **entonces** el total debe coincidir con el
  `award.value` de OCDS. Si no coincide, el registro va a cuarentena: son dos
  fuentes independientes y su desacuerdo significa que algo cambió.
- **Dado** una tasa de cuarentena sobre `MAX_QUARANTINE_RATE`, **cuando**
  termina la corrida, **entonces** falla: no es un dato malo, es un parser roto.

**Comando de verificación:**
```bash
pytest tests/test_validacion.py -v
```
Salida esperada: incluye `test_senama_36_horas_es_implausible PASSED`.
**12 tests en 0,24 s**, bajo el presupuesto de 15.

**Las reglas se prueban contra los casos reales que las originaron**, no contra
ejemplos inventados: SENAMA para la garantia implausible, Puerto Montt para el
precio unitario, y las tres licitaciones para el cruce con OCDS.

**Tiempo de verificación:** ~15 s.

**Fuera de alcance:** corregir los datos. Se marcan, no se arreglan.

---

### Incremento 7 — Reconstrucción del Contrato   [Autonomía: A2]

**Historia:** Como gestor, quiero una entidad Contrato que una todas las fuentes
y declare de dónde vino cada campo, para poder defender cada dato.

**Entrega:** `src/contratos/reconstruccion.py`, `tests/test_reconstruccion.py`.

**Criterios de aceptación:**
- **Dado** una OC con licitación, **cuando** reconstruyo, **entonces** obtengo un
  `Contrato` con `tiene_proceso=true`, una fila en `Licitacion`, y **cada campo
  con su procedencia** (`api_oc`, `api_licitacion`, `ocds`, `ficha_web`,
  `derivado`).
- **Dado** cinco OC de la misma licitación, **cuando** reconstruyo, **entonces**
  hay **una sola** fila en `Licitacion`. Garantías y oferentes **no se
  replican**: contar oferentes debe dar 6, no 30.
- **Dado** una OC **sin** licitación, **cuando** reconstruyo, **entonces**
  obtengo un `Contrato` válido con `tiene_proceso=false` y **sin** fila en
  `Licitacion`. **No es un error.**
- **Dado** dos OC que comparten licitación, **cuando** reconstruyo, **entonces**
  obtengo **dos** contratos distintos con el mismo `codigo_licitacion`.
- **Dado** una OC cuyo proveedor tiene RUT `X`, **cuando** calculo
  `monto_adjudicado`, **entonces** sumo solo los ítems adjudicados a `X`, **no**
  el total de la licitación. Prorratear está prohibido: la fuente da el dato
  exacto.
- **Dado** adjudicación y duración con unidad conocida, **cuando** derivo
  `fecha_termino_estimada`, **entonces** el cálculo respeta la unidad y
  `estado_vencimiento` queda en `calculado`.
- **Dado** una OC huérfana, **cuando** reconstruyo, **entonces**
  `fecha_termino_estimada` queda sin valor y `estado_vencimiento` en
  `no_declarado`: una compra puntual no tiene vigencia y no se le inventa una.
  Su anclaje temporal es `fecha_aceptacion`.
- **Dado** una duración con `UnidadTiempoDuracionContrato` distinto de 1 o 4,
  **cuando** reconstruyo, **entonces** `estado_vencimiento` queda en
  `unidad_desconocida`. **No se adivina la unidad**, y ese valor es la señal de
  que apareció un caso del enum que hay que investigar.

**Comando de verificación:**
```bash
pytest tests/test_reconstruccion.py -v
```
Salida esperada: **14 tests pasan** en 1,6 s, bajo el presupuesto de 20,
incluido `test_una_oc_huerfana_es_un_contrato_valido`.

**Fidelidad sobre correccion.** SENAMA declara 36 horas y el modelo calcula el
vencimiento al dia siguiente de adjudicar. Es absurdo y se reproduce tal cual:
marcarlo es trabajo de `validacion.py`, no de la reconstruccion. Un modulo que
corrige mientras reconstruye esconde el problema que la validacion busca.

**Tiempo de verificación:** ~20 s.

**Fuera de alcance:** guardar en base de datos.

---

### Incremento 8 — Persistencia idempotente   [Autonomía: A2]

**Historia:** Como operador, quiero re-ejecutar la corrida sin duplicar nada,
para poder reprocesar sin miedo.

**Entrega:** `src/contratos/persistencia.py`, `esquema.sql`,
`tests/test_persistencia.py`.

**Criterios de aceptación:**
- **Dado** un `contratos.db` vacío, **cuando** persisto 150 contratos,
  **entonces** hay 150 filas.
- **Dado** esa base, **cuando** persisto **los mismos** 150, **entonces** siguen
  siendo 150. Upsert por `codigo_oc`, no insert.
- **Dado** un contrato con 2 garantías, **cuando** lo persisto dos veces,
  **entonces** hay 2 filas de garantía, no 4.
- **Dado** el archivo generado, **cuando** lo abro con `sqlite3`, **entonces**
  las consultas funcionan **sin conversión ni migración**.
- **Dado** el esquema, **cuando** se crea, **entonces** incluye `contrato`,
  `licitacion`, `garantia`, `clausula_extraida` y `discrepancia`. Las dos
  últimas quedan vacías hasta el incremento 13, pero el esquema no cambia
  después.
- **Dado** `contrato.codigo_licitacion`, **cuando** se define, **entonces** es
  clave foránea **anulable** hacia `licitacion.codigo`. El 56% la tiene nula y
  eso es válido.

**Comando de verificación:**
```bash
pytest tests/test_persistencia.py -v
python -m contratos.cli correr --fecha 2025-05-15 --limite 20
python -m contratos.cli correr --fecha 2025-05-15 --limite 20
sqlite3 data/contratos.db "SELECT COUNT(*) FROM contrato;"
```
**Medido: 10 tests en 2,4 s**, bajo el presupuesto de 25. La doble corrida sobre
150 contratos deja 150 filas, no 300.

**Los montos van como TEXT.** SQLite no tiene DECIMAL y REAL introduce error de
coma flotante en pesos. Un test guarda 783,193 —el litro de diesel de Puerto
Montt— y exige recuperarlo exacto.

Salida esperada: `20` después de la segunda corrida, no `40`. La segunda corrida
además reporta `requests emitidos: 0` porque todo sale de caché.

**Tiempo de verificación:** ~25 s la segunda corrida.

**Fuera de alcance:** consultas de análisis.

---

### Incremento 9 — Consultas de análisis   [Autonomía: A3]

**Historia:** Como gestor, quiero las preguntas de negocio respondidas con
consultas concretas, para no tener que explorar la base a mano.

**Entrega:** `src/contratos/analisis.py`, `consultas/*.sql`,
`tests/test_analisis.py`.

**Criterios de aceptación:**
- **Dado** la base poblada, **cuando** ejecuto cada consulta, **entonces**
  responde las preguntas 1 a 4 de `docs/01-analisis.md`.
- **Dado** la pregunta de vencimientos, **cuando** la ejecuto, **entonces**
  devuelve contratos ordenados por `fecha_termino_estimada`, marcando cuáles son
  renovables.
- **Dado** la pregunta de garantías, **cuando** la ejecuto, **entonces** lista
  las vigentes y **destaca las incoherentes con el plazo**, contándolas **una
  vez por licitación**, no una por contrato.
- **Dado** cualquier consulta de montos, **cuando** la ejecuto, **entonces**
  distingue **comprometido** (`es_comprometido = 1`) de **ejecutado**
  (`es_ejecutado = 1`), y el dashboard muestra ambos. Sumar sin filtrar
  incluiría las canceladas, que traen monto.
- **Dado** la pregunta 5, **cuando** la ejecuto, **entonces** compara gasto con
  proceso contra gasto sin proceso, usando los contratos huérfanos que el
  incremento 2 incluyó a propósito.
- **Dado** la pregunta de plazos por organismo, **cuando** la ejecuto,
  **entonces** devuelve **p25, mediana y p75** de los días entre
  `fecha_publicacion` y `fecha_adjudicacion`, por organismo, y **filtra por
  `tiene_proceso = 1`** porque una OC huérfana no tiene proceso que medir.
- **Dado** los tres casos verificados en la Fase 1, **cuando** ejecuto esa
  consulta sobre ellos, **entonces** Mostazal da 45 días, Puerto Montt 115 y
  SENAMA 215.

**Comando de verificación:**
```bash
pytest tests/test_analisis.py -v
python -m contratos.cli analizar
```
Salida esperada: **cinco tablas en consola**, una por pregunta.
**Medido: 11 tests en 2,6 s**, bajo el presupuesto de 15.

**Las consultas viven en `consultas/*.sql`, no incrustadas en Python.** Se
abren con cualquier cliente de SQLite, se leen sin ejecutar el proyecto, y cada
archivo empieza explicando que pregunta responde y por que filtra como filtra.
Un test exige que sea asi.

**Verificado con datos reales:** la P2 pone a SENAMA primera y marcada como
implausible —36 horas de contrato con garantia hasta 2027—, y la P3 devuelve las
medianas de 45, 115 y 215 dias medidas en la Fase 1.

**Tiempo de verificación:** ~15 s.

**Fuera de alcance:** el render web.

---

### Incremento 10 — Dashboard FastAPI   [Autonomía: A3]

**Historia:** Como gestor, quiero explorar los contratos en una interfaz, para
responder las preguntas sin escribir SQL.

**Entrega:** `src/contratos/web/app.py`, plantillas, `tests/test_web.py`.

**Criterios de aceptación:**
- **Dado** el servidor arriba, **cuando** pido `/`, **entonces** responde 200 con
  los indicadores: contratos totales, cuántos sin proceso, monto vigente,
  garantías por vencer.
- **Dado** `/contratos`, **cuando** filtro por organismo o por rango de
  vencimiento, **entonces** la tabla responde.
- **Dado** `/contratos/{id}`, **cuando** lo abro, **entonces** muestra el detalle
  **con la procedencia de cada campo visible**.
- **Dado** `/salud`, **cuando** lo consulto, **entonces** devuelve el conteo de
  filas, la fecha de la última corrida, y **al menos 400 contratos** de los 450
  esperados.
- **Dado** el subcomando `exportar`, **cuando** lo ejecuto, **entonces** genera
  `dist/dashboard.html` **autocontenido**, con los datos embebidos y sin
  dependencias externas. Es el **respaldo de la demo**: se abre con doble clic si
  el servidor falla en vivo.

**Comando de verificación:**
```bash
pytest tests/test_web.py -v
uvicorn contratos.web.app:app --port 8001 &
curl -s localhost:8001/salud | jq
python -m contratos.cli exportar && ls -la dist/dashboard.html
```
**Medido: 15 tests en 3,2 s**, bajo el presupuesto de 30.

**El export se verifica por lo que NO tiene.** Un test recorre el HTML buscando
`<script`, `src=`, `rel="stylesheet"`, `http://` y `https://`, y falla si
encuentra cualquiera. Autocontenido no es una intencion: es una propiedad que se
comprueba.

Salida esperada: un JSON con `contratos` **de al menos 400** de los 450
esperados, y `ultima_corrida` con fecha, más un `dashboard.html` de un solo
archivo.

**Umbral, no número exacto.** La cuarentena puede descartar algunos registros
legítimamente, así que exigir 450 fallaría sin que nada esté roto. Pero "mayor
que 0" dejaría pasar una corrida que trajo 12 contratos. El umbral se actualiza
si cambia el tamaño de la muestra.

**Tiempo de verificación:** ~30 s.

**Fuera de alcance:** despliegue.

---

### Incremento 11 — Despliegue a Lightsail   [Autonomía: A4]

**Historia:** Como desarrollador, quiero el dashboard accesible por HTTPS, para
compartir un link en vez de compartir pantalla.

**Entrega:** `despliegue/nginx.conf`, `despliegue/desplegar.sh`,
`despliegue/contratos.service`, sección de operación en el README.

**Criterios de aceptación:**
- **Dado** el `.db` local, **cuando** ejecuto `desplegar.sh`, **entonces** copia
  el archivo, reinicia el servicio y **no toca los otros 3 sitios del servidor**.
- **Dado** el server block de nginx, **cuando** se recarga, **entonces**
  `nginx -t` pasa y los sitios existentes siguen respondiendo.
- **Dado** el certificado emitido, **cuando** abro la URL pública, **entonces**
  responde 200 por HTTPS.
- **Dado** el servicio, **cuando** el servidor reinicia, **entonces** levanta
  solo (`systemctl enable`).

**Comando de verificación:**
```bash
bash despliegue/desplegar.sh
curl -sI https://contratos.54-207-164-201.sslip.io/salud | head -1
curl -sI https://serena.54-207-164-201.sslip.io | head -1
```
Salida esperada: `HTTP/2 200` en **ambas** — la segunda confirma que no se rompió
lo que ya estaba.

**Tiempo de verificación:** ~60 s. No se puede acelerar: incluye copia por red y
reinicio de servicio.

**Fuera de alcance:** CI que despliegue solo.

---

### Incremento 12 — Endurecimiento y observabilidad   [Autonomía: A3]   ⬜ upside

**Historia:** Como operador, quiero saber qué pasó en cada corrida, para
diagnosticar sin adivinar.

**Entrega:** `src/contratos/metricas.py`, logging estructurado,
`docs/04-operacion.md`.

**Criterios de aceptación:**
- **Dado** una corrida, **cuando** termina, **entonces** reporta requests
  emitidos, aciertos de caché, registros por fuente, cuarentenados con su motivo,
  y duración.
- **Dado** un fallo parcial en una fuente, **cuando** ocurre, **entonces** las
  demás continúan y el reporte lo dice.
- **Dado** los umbrales de calidad, **cuando** alguno se supera, **entonces** la
  corrida sale con código distinto de cero.

**Comando de verificación:**
```bash
python -m contratos.cli correr --fecha 2025-05-15 --limite 20 --reporte
echo "código de salida: $?"
```

**Tiempo de verificación:** ~40 s.

---

### Incremento 13 — Inferencia: causales y discrepancias   [Autonomía: A2]   ⬜ upside

**Historia:** Como gestor, quiero las causales de término y saber cuándo la
fuente se contradice, para no confiar ciegamente en un campo mal cargado.

**Va último por dos razones:** depende de los incrementos 4 y 8, y es el único
que se puede cortar sin que la demo pierda coherencia.

**Entrega:** `src/contratos/inferencia/` completo, `tests/test_inferencia.py`.

**Criterios de aceptación:**
- **Dado** la sección 9 de una ficha, **cuando** aplico el filtro de
  recuperación, **entonces** obtengo solo las ventanas alrededor de las palabras
  clave.
- **Dado** una ficha **sin** pasajes coincidentes (caso Mostazal), **cuando**
  proceso, **entonces** el campo es `null` y **no se llama al modelo**.
- **Dado** una respuesta del modelo, **cuando** no es JSON parseable,
  **entonces** se registra el crudo y el contrato se guarda sin la cláusula. No
  se pierde el contrato.
- **Dado** una cláusula extraída, **cuando** se persiste, **entonces** incluye
  `fragmento_origen` y `posicion_inicio`. **Sin trazabilidad no entra.**
- **Dado** un campo estructurado que contradice a la prosa (caso SENAMA),
  **cuando** proceso, **entonces** se emite una `Discrepancia` con ambos valores.
  **Ninguno se corrige en silencio.**
- **Dado** el adaptador, **cuando** cambio `INFERENCE_PROVIDER`, **entonces**
  funciona con local y con hosted sin tocar el resto del código.

**Comando de verificación:**
```bash
pytest tests/test_inferencia.py -v            # ~20 s, sin modelo, todo simulado
python -m contratos.cli inferir --limite 1    # ~8 min, con modelo real
```

**Tiempo de verificación:** los tests, 20 s. La corrida real, **~3,4 minutos por
documento** con el filtro de recuperación puesto — medido en el Spike 0: 10,2
minutos para los tres documentos, contra 88 minutos enviándolos completos. Son
**8,7 veces más rápido** y además corrige dos fallos del enfoque monolítico.

La verificación cruzada de discrepancias es otro asunto: exige el documento
entero y cuesta ~30 minutos. Por eso **no corre sobre todos los contratos**, solo
sobre aquellos donde una regla determinista ya sospecha algo. Por eso los tests usan respuestas simuladas y la
corrida real se ejecuta aparte, nunca en el bucle de desarrollo.

**Fuera de alcance:** cualquier inferencia en la ruta de un request.

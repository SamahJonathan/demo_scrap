# Guion de demo — 5 minutos

Recorrido cronometrado para la entrevista. Cada paso dice **qué ejecutar**, **qué
señalar** y **por qué importa** para una empresa que vende gestión del ciclo de
vida de contratos.

**Regla del guion: no se corre el pipeline en vivo.** Tarda ~35 minutos y depende
de una API de terceros. Se muestra el resultado ya publicado y se explica cómo se
produjo. Si preguntan por la corrida, está el registro de corridas (paso 4).

> **URL:** <https://contratos.54-207-164-201.sslip.io>
> **Respaldo:** `python -m contratos.cli exportar` deja un HTML autocontenido, por
> si falla la red.

---

## 0 · Antes de compartir pantalla (2 min, a solas)

```bash
curl -s https://contratos.54-207-164-201.sslip.io/salud
```

Debe devolver conteos, no un error. Si no responde:
`ssh ... "sudo systemctl restart contratos"`.

Cerrar Ollama y todo lo pesado: **el modelo no se corre en vivo**, pide 7,34 GB
y compite con la codificación de video de la videollamada.

---

## 1 · El problema, en una frase (40 s)

**No abrir el navegador todavía.** Decirlo primero:

> Mercado Público publica licitaciones y órdenes de compra. **No publica
> contratos.** El contrato hay que reconstruirlo uniendo el proceso, el acto de
> adjudicación y el instrumento de ejecución. Y la fecha de vencimiento —el dato
> más elemental de un CLM— no existe en ninguna parte: hay que derivarla.

Por qué importa: es exactamente el problema difícil de un CLM real, **ingestar
contratos nacidos fuera del sistema**.

---

## 2 · La portada (60 s)

Abrir `/`. Señalar, en este orden:

1. **La cobertura.** El 56% de las órdenes no nace de una licitación. La página
   lo declara antes de mostrar nada. *"Un panel que no dice de qué no puede
   hablar miente por omisión."*
2. **Las garantías incoherentes.** Marcadas, no corregidas. Se conservan los dos
   valores contradictorios.

Si hay tiempo, la frase que resume el criterio:

> Ni el parseo ni el modelo ganan por defecto. Cuando la fuente se contradice, se
> muestran ambos valores y decide quien mira.

---

## 3 · El hallazgo que vende el rigor (90 s) — **el núcleo de la demo**

Ir a `/legal` y buscar `1300-43-LP24` (SENAMA).

- El campo estructurado declara un plazo de contrato de **36 horas**.
- Su garantía de fiel cumplimiento vence el **29-12-2027**.

> Nadie cauciona hasta 2027 un contrato de 36 horas. El dato está mal cargado en
> el origen, casi seguro son 36 meses.

**La regla no se inventó, se derivó de este dato.** El vencimiento de la garantía
tiene que ser coherente con la adjudicación más la duración declarada. Los otros
casos la cumplen.

Y el remate, que es lo que distingue a un ingeniero de datos de un scraper:

> El enum `UnidadTiempoDuracionContrato` **no está documentado** por la fuente.
> `1`=horas y `4`=meses se decodificaron cruzando la API contra la ficha web y
> contra la prosa del acta de adjudicación. Los demás valores siguen sin
> decodificar y **no se asumen**: caen a cuarentena.

---

## 4 · Que no falle en silencio (45 s)

```bash
python -m contratos.cli corridas
```

Señalar dos cosas:

- La corrida **sale con código distinto de cero** si se supera un umbral. Se
  encadena en cron o CI sin revisarla a ojo.
- Y más importante: **compara contra la corrida anterior**. Un scraper no se
  rompe de golpe. La cobertura baja de 95% a 60% y el umbral fijo la deja pasar;
  la comparación no.

> Un scraper que falla en silencio es peor que uno caído: envenena los datos sin
> avisar.

---

## 5 · Dónde entra un modelo, y dónde no (60 s)

Abrir un contrato con causales: `/contratos/1002-183-SE25`.

Es **lo único de todo el sitio que produjo un modelo de lenguaje**, y lo único que
declara qué modelo lo produjo y en qué carácter del documento lo leyó.

La decisión que hay que defender:

> Ninguna fecha, ningún monto y ninguna garantía se le piden a un modelo. Son
> campos tipados que la API o un selector entregan exactos. Pedirlos por
> inferencia es pagar alucinaciones por datos que ya están ciertos.
>
> El modelo hace dos cosas: leer prosa que ningún campo expone, y **verificar de
> forma cruzada** el campo tipado contra lo que dice el documento.

Si preguntan por el costo: el filtro de pasajes evita **2 de cada 3 llamadas**, y
cuando no hay pasajes la respuesta es `null` sin invocar al modelo.

---

## 6 · Cierre (30 s)

> Los adjuntos quedaron fuera de alcance. La página de descarga está protegida
> por reCAPTCHA Enterprise. El token de redirección viene en el HTML y me
> permitiría saltarme el chequeo. **No lo hice**, y eso está documentado como
> decisión, no como limitación técnica.

En una empresa de contratos y compliance esa frase vale más que un adjunto
descargado.

---

## Las tres preguntas más probables

### "¿Cómo sabes que los datos son correctos?"

No lo sé por fe, lo sé por umbrales. Tres capas:

1. **Esquema explícito** en la entrada: nada entra sin validarse.
2. **Reglas de plausibilidad derivadas de datos reales**, como la de la garantía.
3. **Comparación entre corridas**, que detecta la degradación gradual que un
   umbral fijo no ve.

Y lo que no se puede validar **se apart**a a cuarentena con su motivo, no se
adivina. Mostrar `python -m contratos.cli correr --reporte`.

### "¿Cómo escalas a 10 millones de registros?"

Lo que ya está: particionado por fecha, idempotencia y caché con expiración, o
sea que reprocesar es seguro y barato.

**Qué se rompe primero, en orden honesto:**

1. El cupo de la API: 10.000 requests diarios. Es el techo duro, y llega antes
   que cualquier problema de cómputo.
2. La secuencialidad: `REQUEST_DELAY_SECONDS=2.0` es una decisión ética, no
   técnica. Paralelizar exige negociar rate limits con la fuente.
3. SQLite en el servidor. Por eso el acceso a datos está detrás de
   `DATABASE_URL`: cambiar a PostgreSQL es un adaptador, no una reescritura.

La parte difícil —reconstruir la entidad contrato— **es la misma con 50 que con
50.000**. El volumen es una variable de configuración.

### "¿Usaste IA para esto?"

Sí, y esa es la respuesta correcta en 2026. Lo que distingue es *cómo*:

- `/docs` tiene una fase por documento, con las decisiones y **la alternativa que
  se descartó**.
- Cada incremento trae el comando exacto de verificación y la salida esperada.
- Hubo un **dial de autonomía** explícito por tarea.

La IA aceleró la generación; yo construí el sistema de verificación. Y hay un
caso concreto que lo prueba: en una versión anterior el asistente **insertó a
mano** una discrepancia que parecía producida por el modelo. Se detectó porque la
base la delataba con `clausula_extraida = 0`. Está documentado en `CLAUDE.md`,
junto con la lección de método que dejó.

# demo_scrap — Contratos públicos de Mercado Público

Reconstruye algo que la fuente **no publica**: el contrato.

Mercado Público (ChileCompra) expone licitaciones, órdenes de compra, compra ágil
y proveedores. No existe una entidad "contrato". Hay que armarla uniendo el
proceso de licitación, el acto de adjudicación y el instrumento de ejecución —la
orden de compra—. Y la fecha de vencimiento, el dato más elemental de un CLM, no
existe en ninguna parte: se deriva.

**Demo en vivo:** <https://contratos.54-207-164-201.sslip.io>

Este README tiene dos mitades. La primera es para ejecutarlo en 2 minutos; la
segunda, para entender por qué está construido así.

---

# Parte 1 — Ejecutarlo

## Requisitos

Python 3.11+ y un ticket de la API de Mercado Público, que se pide con Clave
Única en <https://www.chilecompra.cl/api/>. Es personal, **se renueva a diario** y
tiene un tope de 10.000 requests.

## Instalación

```bash
git clone git@github.com:SamahJonathan/demo_scrap.git
cd demo_scrap
python -m venv .venv
source .venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                   # luego edita MP_API_TICKET
```

Verificar que quedó bien, en unos 25 segundos y **sin tocar la red**:

```bash
ruff check . && mypy src/ && pytest -q     # 182 tests
```

## Los comandos

```bash
python -m contratos.cli correr --reporte   # pipeline completo (~35 min)
python -m contratos.cli corridas           # compara corridas, avisa qué empeoró
python -m contratos.cli analizar           # las siete preguntas de negocio
python -m contratos.cli exportar           # HTML autocontenido, sin servidor
python -m contratos.cli inferir            # capa de modelo (LENTO, en lote)
```

Y tres para inspeccionar la fuente sin correr el pipeline entero:

```bash
python -m contratos.cli descubrir 2025-01-15
python -m contratos.cli detalle-oc  <código>
python -m contratos.cli licitacion  <código>
```

**`correr` sale con código distinto de cero** si se supera un umbral de calidad,
así se encadena en cron o CI sin revisarla a ojo.

## Qué mirar después

| | |
|---|---|
| Qué preguntas responde el dashboard | [docs/05-preguntas.md](docs/05-preguntas.md) |
| Operación y qué hacer cuando falla | [docs/04-operacion.md](docs/04-operacion.md) |
| Recorrido de demo de 5 minutos | [docs/demo.md](docs/demo.md) |

---

# Parte 2 — Por qué está construido así

## Por qué esta fuente

Los datos de compras públicas **son** datos contractuales: montos, plazos,
contrapartes, adjudicaciones y garantías. Un CLM enfrenta exactamente este
problema al ingestar contratos nacidos fuera del sistema: los datos llegan
dispersos, sin entidad unificada, con relaciones que no son uno a uno y con la
parte valiosa encerrada en documentos. Reconstruir el contrato desde Mercado
Público es una versión pública y verificable de ese mismo problema.

## La decisión de arquitectura que más costó

**La extracción va al revés de lo intuitivo: se parte de las órdenes de compra,
no de las licitaciones.** El detalle de una OC trae `CodigoLicitacion` como campo
tipado, pero **la API no permite el camino inverso**: dada una licitación, no hay
forma de pedir sus órdenes. Justificación en
[docs/01-analisis.md](docs/01-analisis.md) § 3.5.

## Cuatro fuentes, cada una para lo que hace mejor

| Fuente | Para qué | Por qué esa y no otra |
|---|---|---|
| API REST | Descubrimiento por fecha, detalle de OC y de licitación | Oficial, tipada, y trae el enlace OC → licitación |
| OCDS | Monto adjudicado y oferentes | **No consume cupo de requests** ni pide ticket |
| Ficha web | **Garantías** | 0 de los 54 campos de la API las expone. Es el único caso que justifica scrapear |
| Acta de adjudicación | Prosa contractual | GET limpio, sin reCAPTCHA |

## Dónde entra un modelo de lenguaje, y dónde no

Su dominio se reduce a **prosa que ningún campo expone** (causales de término) y
a **verificación cruzada** del campo tipado contra el documento.

Ninguna fecha, monto ni garantía se le pide a un modelo. Son campos tipados y
exactos; pedirlos por inferencia es pagar alucinaciones por datos ciertos. Se
comprobó campo por campo: la sección "Etapas y plazos" de la ficha es, 11 de 11,
el bloque `Fechas` de la API.

Además, **la inferencia nunca corre en la ruta de un request**: pide 7,34 GB y
minutos por documento. Es un paso de lote, offline, y el dashboard lee filas.

## Cómo se sabe que los datos son correctos

1. **Esquema explícito** a la entrada: nada entra sin validarse.
2. **Reglas de plausibilidad derivadas de datos reales.** La principal nació de
   un dato corrupto: `1300-43-LP24` declara un contrato de 36 horas con una
   garantía que vence en 2027.
3. **Comparación entre corridas**, que ve la degradación gradual que un umbral
   fijo deja pasar.

Lo que no se puede validar **se aparta a cuarentena con su motivo**, no se
adivina. Cuando la fuente se contradice se conservan **los dos valores** y se
marca la fila: ni el parseo ni el modelo ganan por defecto.

## Principios que este repositorio respeta

- **API oficial primero.** El scraping se usa solo para lo que la API no expone
  —las garantías— y la decisión está documentada.
- **Identificación honesta.** User-Agent con nombre del proyecto y contacto real.
  No se imita un navegador ni se evaden CAPTCHAs.
- **Throttling conservador.** 2 s entre requests, concurrencia mínima y tope por
  corrida. La fuente es un servicio público con cupo finito.
- **Solo datos públicos**, bajo licencia CC0 declarada por la Dirección de
  Compras dentro del propio dato.
- **Sin secretos en el repo.** Todo por variables de entorno; `.env.example` no
  tiene un solo valor real.
- **Los datos no se versionan.** El repositorio guarda código y especificación.

---

## Limitaciones conocidas

Honestidad antes que cobertura.

- **Los adjuntos quedan fuera de alcance.** `ViewAttachment.aspx` está protegida
  por reCAPTCHA Enterprise. El token de redirección viene en el HTML y permitiría
  saltarse el chequeo; **no se hace**, porque es evadir detección de bots. Es una
  decisión, no una limitación técnica.
- **La muestra es chica, a propósito.** Profundidad sobre volumen: el criterio de
  éxito es la trazabilidad de cada contrato reconstruido, no cuántos son. El
  volumen es una variable de configuración.
- **La ficha web es el punto frágil.** Se parsea con IDs estables de GridView, no
  con regex sobre texto, pero un rediseño del sitio la rompe. Por eso hay umbral
  de cobertura que hace fallar la corrida.
- **El enum `UnidadTiempoDuracionContrato` está decodificado a medias.** El valor
  `1` es horas y el `4` es meses, verificados cruzando tres fuentes. **Los demás
  no se asumen**: caen a cuarentena.
- **`monto_adjudicado` no es comparable entre contratos.** En un convenio de
  suministro es un precio unitario: Puerto Montt adjudica 783,19 pesos el litro
  de diésel.
- **El repositorio no se ejecuta solo en el servidor.** El servidor solo sirve un
  SQLite de lectura; el pipeline corre en la máquina de desarrollo, donde vive el
  ticket.
- **Sin contenedor todavía.** La reproducibilidad en máquina limpia está
  pendiente (Fase 4).
- **P4 y P5 no tienen página.** Existen como SQL y salen por `cli analizar`, pero
  ninguna ruta del dashboard las publica.

## Fases

Método completo en [docs/00-metodo.md](docs/00-metodo.md).

| Fase | Entregable | Estado |
|---|---|---|
| Fase 0 — Repositorio y contexto | `CLAUDE.md`, `.env.example`, README, licencia | ✅ |
| Spike 0 — Validación de supuesto | [`docs/00-spike.md`](docs/00-spike.md) | ✅ |
| Fase 1 — Análisis | [`docs/01-analisis.md`](docs/01-analisis.md) | ✅ |
| Fase 2 — Diseño | [`docs/02-diseno.md`](docs/02-diseno.md), [`docs/03-plan-codificacion.md`](docs/03-plan-codificacion.md) | ✅ |
| Fase 3 — Codificación | 14 incrementos, 182 tests | ✅ |
| Fase 4 — Despliegue | Reproducibilidad, corridas, README, [`docs/demo.md`](docs/demo.md) | 🟡 |

## Regla de este README

Si algo está documentado acá, funciona. Se actualiza al cerrar cada incremento,
nunca por adelantado.

## Licencia

MIT. Ver [LICENSE](LICENSE).

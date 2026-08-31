# demo_scrap — Contratos públicos de Mercado Público

Este proyecto extrae, valida y estructura información de compras públicas de
Chile (Mercado Público / ChileCompra) para reconstruir algo que la fuente no
publica como tal: el **contrato**. La plataforma expone licitaciones, órdenes de
compra, compra ágil y proveedores, pero no existe una entidad "contrato". Hay que
armarla uniendo el proceso de licitación, el acto de adjudicación, el instrumento
de ejecución —la orden de compra— y los documentos adjuntos de la ficha web.

Esa reconstrucción es el núcleo del trabajo de ingeniería. El pipeline recorre la
API oficial día por día, valida cada registro contra un esquema explícito, manda
a cuarentena lo que no cumple en vez de dejarlo pasar, persiste de forma
idempotente y termina en un dashboard estático que responde preguntas de negocio
concretas sobre montos, plazos, organismos y proveedores.

## Por qué esta fuente

Los datos de compras públicas **son** datos contractuales: montos, plazos,
contrapartes, adjudicaciones, garantías, causales de término y documentos
adjuntos. Un CLM —software de gestión del ciclo de vida de contratos— enfrenta
exactamente este problema cuando ingesta contratos nacidos fuera del sistema: los
datos llegan dispersos entre varias fuentes, sin una entidad unificada, con
relaciones que no siempre son uno a uno y con la parte más valiosa encerrada en
PDF. Reconstruir el contrato desde Mercado Público es una versión pública y
verificable de ese mismo problema.

## Fases

Este repositorio sigue un ciclo de vida explícito, con un *gate* de salida por
fase. El método completo está en [docs/00-metodo.md](docs/00-metodo.md).

| Fase | Entregable | Estado |
|---|---|---|
| Fase 0 — Repositorio y contexto | `CLAUDE.md`, `.gitignore`, `.env.example`, README, licencia | ✅ Cerrada |
| Spike 0 — Validación de supuesto | [`docs/00-spike.md`](docs/00-spike.md) | ✅ Cerrado |
| Fase 1 — Análisis | [`docs/01-analisis.md`](docs/01-analisis.md) | ✅ Cerrada |
| Fase 2 — Diseño | [`docs/02-diseno.md`](docs/02-diseno.md), [`docs/03-plan-codificacion.md`](docs/03-plan-codificacion.md) | ✅ Cerrada |
| Fase 3 — Codificación | 14 incrementos, 159 tests | ✅ Cerrada |
| Fase 4 — Cierre y presentación | Documentación final y demo | 🟡 En curso |

### Lo que la investigación ya estableció

Todo comprobado ejecutando requests contra la fuente, no leyendo documentación:

- **La fuente no publica contratos.** Expone licitaciones, órdenes de compra,
  compra ágil y proveedores. La entidad contrato hay que reconstruirla, y ese es
  el núcleo del trabajo.
- **Se usan cuatro fuentes, cada una para lo que hace mejor:** API REST para el
  descubrimiento por fecha y el enlace con órdenes de compra, **OCDS** para el
  monto adjudicado y los oferentes (y sin consumir cupo de requests), y la ficha
  web para las garantías, que ninguna API expone.
- **Los datos están bajo licencia CC0**, declarada por la Dirección de Compras y
  Contratación Pública dentro del propio dato.
- **Los documentos adjuntos quedan fuera de alcance:** están tras reCAPTCHA
  Enterprise y no se evade.

## La demo

**https://contratos.54-207-164-201.sslip.io**

```bash
python -m contratos.cli correr --reporte   # pipeline completo
python -m contratos.cli analizar           # las cinco preguntas de negocio
python -m contratos.cli exportar           # HTML autocontenido de respaldo
```

Operación, lectura del reporte y qué hacer cuando algo falla:
[docs/04-operacion.md](docs/04-operacion.md).

## Principios que este repositorio respeta

- **API oficial primero.** El scraping de HTML se usa solo para lo que la API no
  expone —principalmente los documentos adjuntos de la ficha— y esa decisión se
  documenta caso a caso.
- **Identificación honesta.** User-Agent con nombre del proyecto y medio de
  contacto real. No se imita un navegador, no se evaden CAPTCHAs ni mecanismos de
  detección.
- **Throttling conservador.** Espera entre requests, concurrencia mínima,
  autothrottle y un tope de requests por corrida. La fuente es un servicio
  público con un cupo diario finito.
- **Solo datos públicos.** Nada que requiera autenticación de un tercero ni que
  exponga información personal más allá de lo que la fuente ya publica.
- **Los datos no se versionan.** El repositorio contiene código y especificación,
  no el dataset. `data/raw/`, `data/processed/` y `data/quarantine/` están fuera
  del control de versiones.
- **Sin secretos en el repo.** Toda la configuración va por variables de entorno.
  `.env.example` es una plantilla sin un solo valor real.

## Puesta en marcha

```bash
git clone git@github.com:SamahJonathan/demo_scrap.git
cd demo_scrap
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scriptsctivate
pip install -e ".[dev]"
cp .env.example .env
```

Verificar que quedó bien, en unos 16 segundos:

```bash
ruff check . && mypy src/ && pytest -q
python -m contratos.cli --help
```

El CLI todavía no tiene subcomandos: **cada incremento agrega el suyo**, así que
el comando que verifica un incremento existe desde que ese incremento se
escribe.

Luego edita `.env`. Como mínimo necesitas `MP_API_TICKET`, que se solicita con
Clave Única en <https://www.chilecompra.cl/api/>; es personal y tiene un tope de
10.000 requests diarios.

## Regla de este README

Si algo está documentado acá, funciona. Se actualiza al cerrar cada incremento,
nunca por adelantado.

## Licencia

MIT. Ver [LICENSE](LICENSE).

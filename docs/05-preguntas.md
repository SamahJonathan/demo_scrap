# Qué preguntas responde el dashboard

Documento de referencia para la demo. Contrasta las preguntas que la Fase 1
declaró contra lo que la aplicación **publica hoy**, incluido lo que no publica.

El orden importa: primero el objetivo, después las preguntas, y al final lo que
queda fuera. Un panel que no dice de qué no puede hablar miente por omisión.

---

## El objetivo, que es lo que hace pertinentes a las preguntas

> Reconstruir contratos públicos chilenos que ninguna fuente publica como tales,
> y seguir su ciclo de vida —vigencia, vencimiento, renovación y garantías— para
> responder **qué contratos hay que relicitar, cuáles se pueden renovar y qué
> cauciones siguen vivas**, sin abrir fichas una por una.

Las tres decisiones que ese objetivo nombra son las tres primeras filas de la
tabla siguiente. Todo lo demás es contexto o control de calidad.

---

## Las siete preguntas

Cinco son de gestión: alguien decide algo con la respuesta. Las dos últimas no
responden una necesidad del gestor, responden **si se puede confiar** en las
cinco anteriores.

| # | Pregunta | Página | Qué decide quien la lee |
|---|---|---|---|
| 1 | ¿Qué contratos vencen en los próximos N meses, y cuáles son renovables frente a cuáles hay que relicitar? | `/vencimientos` y portada | Abrir un proceso nuevo, o ejercer la renovación |
| 2 | ¿Qué garantías siguen vigentes, y cuáles vencen antes que el contrato que caucionan? | `/garantias` y portada | Exigir renovación de la caución antes de quedar descubierto |
| 3 | ¿Cuánto tarda cada organismo entre publicar y adjudicar, y cuánto varía? | `/plazos` | Con cuánta anticipación hay que empezar a relicitar |
| 4 | ¿Qué organismos concentran mayor monto vigente, y con qué proveedores? | **ninguna** — solo `cli analizar` | — |
| 5 | ¿Qué órdenes de compra no nacen de una licitación, y qué proporción del gasto representan? | **ninguna** — solo `cli analizar` | — |
| 6 | ¿Sobre qué parte de la cartera puede hablar la página de vencimientos? | portada | Si el panel es representativo o parcial |
| 7 | ¿Qué contratos tienen datos que se contradicen entre sí? | portada | Qué filas NO hay que creerse |

### Cómo se verifica esta tabla

```bash
python -m contratos.cli analizar          # las siete, en consola
curl -s http://127.0.0.1:8001/salud       # conteos por tabla
```

Cada consulta vive en `src/contratos/consultas/pN_*.sql` y empieza declarando la
pregunta que responde y **por qué filtra como filtra**. No hay SQL sin esa
justificación arriba.

---

## Las tres del objetivo, en detalle

### P1 — Vencer, renovar o relicitar

Ningún campo dice "este contrato vence el día X". Se **deriva**:
`FechaAdjudicacion` + `TiempoDuracionContrato` + `UnidadTiempoDuracionContrato`.
`EsRenovable` separa las dos acciones posibles.

Es el caso central de la demo: la fecha de vencimiento —el dato más elemental de
un CLM— **no existe en la fuente** y hay que construirla.

### P2 — Garantías vivas

**Solo la ficha web las publica.** Se revisaron los 54 campos de
`licitaciones.json?codigo=` y no hay ni uno de garantías. Este es el caso que
justifica la capa de scraping HTML bajo la regla "API primero".

La consulta arranca en `garantia`, no en `contrato`: cinco órdenes de la misma
licitación comparten las mismas dos cauciones, y contarlas por contrato daría
diez donde hay dos.

### P3 — Plazos por organismo

Devuelve **p25, mediana y p75, no el promedio**. Medido en tres organismos: 45,
115 y 215 días. Con esa dispersión el promedio miente.

Convierte un vencimiento en un plazo para actuar: un contrato que vence en 90
días no da margen si su organismo tarda 215 en adjudicar.

---

## Las dos de confianza

### P6 — Cobertura

El 56% de las órdenes no nace de una licitación (compra ágil, convenio marco,
trato directo). Son contratos válidos, no errores, pero **no tienen vigencia que
vigilar**. La portada declara sobre qué parte de la cartera habla.

### P7 — Contradicciones

Un vencimiento calculado desde un plazo mal cargado es un vencimiento falso, y
se vería igual de confiable que uno bueno. Dos reglas lo detectan:

- **Campo tipado contra prosa.** `1300-43-LP24` declara `36 Horas` y su propia
  prosa dice `36 meses` tres veces.
- **Plausibilidad de la garantía.** Nadie cauciona hasta 2027 un contrato de 36
  horas. La regla nació de ese dato corrupto real, no de la teoría.

**Ninguno de los dos valores se corrige.** Se conservan ambos y se marca la
fila. Ni el parseo ni el modelo ganan por defecto.

---

## Lo único que produce un modelo de lenguaje

Las **causales de término anticipado**, visibles en la ficha de cada contrato
(`/contratos/<código>`). Viven solo en la prosa de las bases: ningún campo de la
API las expone.

Importan para P1: un contrato con causales amplias puede caerse antes de su
vencimiento, y entonces hay que relicitar antes de lo que dice la fecha.

Es lo único de la página que declara **qué modelo** lo produjo y **en qué
carácter** del documento lo leyó, porque es lo único que no es determinista.
Todo lo demás —fechas, montos, garantías, plazos— sale de la API o de un
selector, y pedirlo por inferencia sería pagar alucinaciones por datos ciertos.

---

## Lo que el dashboard NO responde

Honestidad antes que cobertura. Cada punto tiene su razón documentada:

| No responde | Por qué |
|---|---|
| **P4 y P5 no tienen página.** Existen como SQL y salen por `cli analizar`, pero ninguna ruta las publica | Deuda real, no decisión. Se detectó auditando este documento contra el código |
| Qué dicen las bases administrativas completas | Están tras un reCAPTCHA. Saltárselo contradice una restricción no negociable del proyecto |
| Ejecución real del contrato: entregas, multas, término efectivo | La fuente no lo publica. Un CLM lo tendría; Mercado Público no |
| Comparar montos entre contratos | `monto_adjudicado` no es comparable: Puerto Montt adjudica $783,19 **el litro** de diésel |
| Cuántos reclamos tiene un organismo | `CantidadReclamos` marcó 11819 en una licitación individual: es un contador global mal expuesto. No se incluye ningún campo cuyo significado no podamos defender |
| Preguntas en lenguaje natural | Evaluado y descartado: es el componente con más probabilidad de fallar en vivo, y un monto mal respondido derriba el rigor del resto |

---

## Estado de los datos publicados

Muestra acotada, por decisión: **profundidad sobre volumen**. El criterio de
éxito es la trazabilidad de cada contrato reconstruido, no cuántos son.

| | |
|---|---|
| contratos | 12 (6 con licitación, 6 sin) |
| licitaciones | 6 |
| garantías | 8 |
| cláusulas extraídas por el modelo | 2 |
| discrepancias | 0 |

**Las 0 discrepancias son un resultado, no un fallo.** Se verificó contando
llamadas: el modelo fue invocado en las dos licitaciones con duración declarada
y respondió `{"valor": 24, "unidad": "meses"}`, coincidiendo con el campo
tipado. El caso SENAMA es real pero su licitación no está en esta muestra.

# SPIKE 0 — Resultado

**Pregunta:** ¿un modelo de lenguaje local extrae información contractual útil de
documentos de una licitación pública chilena?

**Respuesta: sí, y en un caso hizo algo que el parseo determinista no puede
hacer. Pero su costo en este hardware lo deja fuera de la línea de corte.**

**Recomendación: ALCANCE ACOTADO, con un rol distinto al previsto.**

**Timebox:** 1 hora. **Excedido:** la inferencia sola tomó 88 minutos.

> **Nota de corrección.** La primera versión de este documento concluyó que el
> modelo había alucinado el plazo de SENAMA. Era falso: el valor estaba en la
> prosa de la ficha y el error era del regex de referencia. La conclusión se
> invirtió y está corregida más abajo. Se deja constancia porque el spike existe
> para medir, y una medición mal leída es peor que no medir.

---

## Cambio de entrada respecto al plan

El spike iba a correr sobre **bases administrativas** bajadas a mano. No se pudo:
`Attachment/ViewAttachment.aspx` está protegida por **reCAPTCHA Enterprise** con
scoring de bot. El token de redirección viene en el HTML y permitiría saltarse el
chequeo. **No se hizo:** evadir detección de bots contradice una restricción no
negociable del proyecto.

Entrada definitiva: la **ficha web**, secciones 7 (montos y duración), 8
(garantías) y 9 (cláusulas), por GET limpio sin reCAPTCHA.

## Configuración

| Parámetro | Valor |
|---|---|
| Modelo | `llama3.1:8b` (Q4_K_M), Ollama 0.33.2 |
| Hardware | Ryzen 7 7730U, 13,8 GB RAM, **sin GPU utilizable** |
| Temperatura | 0.0 · `num_ctx` 16384 explícito |
| Referencia | regex sobre la ficha + campos de la API |

---

## Medición

| Documento | Chars | Segundos | JSON parseable | Campos correctos |
|---|---|---|---|---|
| `2678-1-LR25` Mostazal | 19.098 | 499 | ✅ | 3 / 4 |
| `1300-43-LP24` SENAMA | 38.642 | 3.950 | ✅ | **4 / 4** |
| `2328-443-LR24` Puerto Montt | 43.056 | 860 | ✅ | 3,5 / 4 |

**JSON parseable: 3 de 3.** Con `format: json`, el formato nunca falló.

**Aciertos: 10,5 de 12.** Un solo fallo inequívoco.

---

## El hallazgo que decide el diseño

**La ficha de SENAMA se contradice a sí misma.**

| Dónde | Qué dice |
|---|---|
| Sección 7, campo estructurado | `Tiempo del Contrato: `**`36 Horas`** |
| Prosa, posición 4.404 | "la duración del contrato (1095 días/**36 meses**)" |
| Prosa, posición 22.261 | "la duración del servicio será de **36 meses**" |
| Prosa, posición 23.421 | "El contrato tendrá una duración de **36 meses**" |
| Garantía de fiel cumplimiento | vence **29-12-2027**, coherente con 36 meses |

- El **regex** devolvió `"36 Horas"`: fiel al campo estructurado, que está mal
  cargado.
- El **modelo** devolvió `"36 meses"`: correcto según el resto del documento.

El modelo no inventó nada. **Reconcilió un campo estructurado corrupto contra la
prosa que lo contradice**, que es precisamente el trabajo que un parseo por
selectores no puede hacer.

Esto invierte el rol previsto para la capa de inferencia. No es solo un extractor
de prosa: es un **verificador cruzado** del dato estructurado.

### La consecuencia de diseño

Un pipeline no debe elegir en silencio entre las dos versiones. Debe:

1. Extraer el campo estructurado de forma determinista (`36 Horas`).
2. Extraer el mismo hecho desde la prosa, con el modelo (`36 meses`).
3. **Cuando difieren, no resolver: marcar el registro como contradictorio**, con
   ambos valores y sus fragmentos de origen.

Eso es reconciliación de datos contractuales, y es una función real de un CLM que
ingesta contratos nacidos fuera del sistema. La pregunta de negocio 2 del
análisis se refuerza: la contradicción se detecta cruzando fuentes, no confiando
en una.

## El único fallo inequívoco

En Mostazal, cuya ficha **no tiene causales de término**, el modelo devolvió la
cláusula de readjudicación etiquetada como causal. No inventó texto —la cláusula
es real— pero la clasificó mal antes que dejar el campo vacío.

El filtro de recuperación por palabras clave resuelve ese caso sin llamar al
modelo: cero pasajes encontrados, por lo tanto `null`.

## El fallo parcial

En Puerto Montt, para las garantías, el modelo devolvió los montos correctos pero
reemplazó las fechas de vencimiento por la regla en prosa ("no podrá ser inferior
a 90 días corridos desde la apertura") en vez del valor tabulado (17-03-2025).

Ambas afirmaciones son verdaderas y están en el documento. **El problema es que
el modelo no distingue cuál es el valor canónico del campo.** Esa es su debilidad
real, y es más precisa que "alucina": ante varias afirmaciones ciertas, no sabe
cuál es la autoritativa.

## Donde el modelo gana claro

**Causales de término.** SENAMA: siete causales, de la a) a la g). Puerto Montt:
nueve numeradas, con la referencia al tope de multas del artículo 30 de las BAE.
Prosa legal densa, sin estructura, redactada distinto por cada organismo. Un
regex no llega ahí.

## Latencia y recursos

| Documento | Chars | Segundos |
|---|---|---|
| Mostazal | 19.098 | 499 |
| Puerto Montt | 43.056 | 860 |
| SENAMA | 38.642 | 3.950 |

**La relación no es lineal, y hay que ser honesto:** SENAMA tardó 4,6 veces más
que Puerto Montt siendo más corto. Se mezclan dos causas — su salida fue mucho
más larga (siete causales extensas) y corrió con 0,4 GB de RAM libre, con Windows
comprimiendo, mientras Puerto Montt corrió con 1,5 GB. **No se puede atribuir el
3.950 solo al modelo.** Aislarlo exigiría otra corrida.

Consumo: **7,34 GB de RAM**, 53% de la máquina. Extrapolado a las 300
licitaciones del tope: **más de 60 horas**. La capa local no procesa lotes en
este hardware.

---

## Decisión de diseño

**Alcance acotado**, con el rol corregido:

**1. El modelo NO es la fuente primaria de ningún campo estructurado.** Monto,
plazo, fechas, RUT y códigos salen de la API o de parseo determinista.

**2. El modelo cumple DOS funciones, ambas acotadas:**
   - **Extractor** de cláusulas en prosa libre (causales de término), donde no
     hay alternativa determinista.
   - **Verificador cruzado** del campo estructurado: cuando su lectura de la
     prosa contradice al campo tipado, el registro se marca como contradictorio.
     Nunca se corrige en silencio, en ninguna de las dos direcciones.

**3. Con filtro de recuperación por delante, siempre.** Se buscan pasajes por
palabras clave y solo esos se envían. Sin pasajes, el campo es `null` y no se
llama al modelo. Arregla el fallo de Mostazal y reduce el texto enviado entre un
43% y un 76%.

**4. Con trazabilidad obligatoria.** Todo valor inferido guarda su fragmento de
origen y su posición. Sin eso no es defendible, y sin eso este mismo hallazgo no
se habría podido auditar.

**5. Fuera de la línea de corte.** El costo —minutos por documento, 7,34 GB— lo
deja como upside, no como parte de la demo mínima.

## Lo que este spike compró

1. El rol correcto de la inferencia: verificación cruzada, no extracción de
   campos tipados.
2. La evidencia de que la fuente se contradice a sí misma dentro de un mismo
   documento, con un caso concreto.
3. El costo real de la inferencia local en este hardware.
4. La necesidad del filtro de recuperación antes del modelo.
5. Una lección de método: la referencia contra la que mides también puede estar
   equivocada. El regex era la "verdad" y era el que fallaba.

## Medición adicional: monolítico contra fragmentado

Se repitió el experimento enviando al modelo solo las secciones relevantes en vez
del documento entero, con un filtro de pasajes por palabras clave y `num_ctx`
bajado de 16384 a 4096.

| Documento | Monolítico | Fragmentado | Mejora | Texto enviado |
|---|---|---|---|---|
| Mostazal | 499 s | **108 s** | 4,6× | 30% |
| SENAMA | 3.950 s | **289 s** | **13,7×** | 50% |
| Puerto Montt | 860 s | **214 s** | 4,0× | 25% |
| **Total** | **88 min** | **10,2 min** | **8,7×** | 36% |

**Fragmentar arregló los dos fallos del monolítico:**

- **Mostazal, causales de término.** El monolítico inventó una readjudicación
  tras 8 minutos. El filtro no encuentra pasajes, responde `null` **sin llamar al
  modelo**, y acierta en cero segundos.
- **Puerto Montt, fechas de garantía.** El monolítico devolvía la regla en prosa
  ("no inferior a 90 días corridos") en vez del valor tabulado. El fragmentado
  devuelve `17-03-2025` y `29-04-2027`, exactas.

**Y perdió la reconciliación entre secciones:**

- **SENAMA, plazo.** El fragmentado responde `36 Horas`, fiel a la sección 7. El
  monolítico respondía `36 meses`, que es lo que dice la prosa tres veces.
- **Puerto Montt, monto.** El monolítico lo hallaba en la prosa; el fragmentado
  no, porque solo ve la sección 7.

### La conclusión que cierra el spike

**Fragmentar gana en extracción y pierde en reconciliación.** Son dos trabajos
distintos y el diseño ya los separa:

| Trabajo | Cómo se hace | Coste |
|---|---|---|
| **Extraer** cláusulas en prosa | Filtro de pasajes + modelo sobre la sección | ~3,4 min por documento |
| **Verificar** contradicciones | Modelo sobre el documento completo | ~30 min por documento |

La extracción entra en cada corrida. La verificación cruzada corre solo sobre los
contratos donde una regla determinista ya sospecha algo — no sobre todos.

## Pendiente

Comparación con `llama3.2:3b` y con el adaptador hosted, para responder cuál es
el modelo mínimo viable. No cambia la recomendación.

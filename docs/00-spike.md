# SPIKE 0 — Resultado

**Pregunta:** ¿un modelo de lenguaje local extrae información contractual útil de
documentos de una licitación pública chilena?

**Respuesta corta: sí, pero solo en un campo, y en los demás es activamente
peligroso.**

**Recomendación: ALCANCE ACOTADO.**

**Timebox:** 1 hora. **Excedido:** la inferencia sola tomó 88 minutos.

---

## Cambio de entrada respecto al plan, y por qué

El spike iba a correr sobre **bases administrativas** bajadas a mano. No se pudo,
y la razón importa más que el spike: `Attachment/ViewAttachment.aspx` está
protegida por **reCAPTCHA Enterprise** con scoring de bot. El token de
redirección viene en el HTML y permitiría saltarse el chequeo. **No se hizo:**
evadir detección de bots contradice una restricción no negociable del proyecto.

Primer intento de reemplazo: las **actas de adjudicación**, accesibles con GET
limpio. Resultaron pobres — una de las tres no menciona garantías ni plazos.

Entrada definitiva: la **ficha web**, secciones 7 (montos y duración), 8
(garantías) y 9 (cláusulas), obtenidas con GET limpio sin reCAPTCHA. Se
descartaron las secciones 1 a 6 por ser duplicado exacto de la API o relleno
legal idéntico en toda ficha.

## Configuración

| Parámetro | Valor |
|---|---|
| Modelo | `llama3.1:8b` (Q4_K_M), vía Ollama 0.33.2 |
| Hardware | Ryzen 7 7730U, 13,8 GB RAM, **sin GPU utilizable** |
| Temperatura | 0.0 |
| `num_ctx` | 16384 explícito (el default de Ollama es 2048 y habría recortado el 92% del documento más largo sin avisar) |
| Verdad de referencia | regex sobre la misma ficha + campos de la API |

---

## Medición

| Documento | Chars | Segundos | JSON parseable | Campos correctos |
|---|---|---|---|---|
| `2678-1-LR25` Mostazal | 19.098 | 499 | ✅ | **3 / 4** |
| `1300-43-LP24` SENAMA | 38.642 | **3.950** | ✅ | **3 / 4** |
| `2328-443-LR24` Puerto Montt | 43.056 | 860 | ✅ | **3 / 4** |

**JSON parseable: 3 de 3.** Con `format: json` de Ollama, nunca falló el formato.

**Aciertos: 9 de 12 campos (75%).** Pero el promedio esconde lo importante: los
tres fallos son de naturaleza distinta y solo uno es benigno.

### Por campo

| Campo | Aciertos | Dónde falla |
|---|---|---|
| Monto máximo | 3/3 | — |
| Causales de término | 2/3 | Inventó una donde no existían |
| Garantías | 2/3 | Perdió las fechas de vencimiento |
| **Plazo del contrato** | 2/3 | **Corrigió en silencio un dato corrupto** |

---

## El hallazgo que decide el diseño

`1300-43-LP24` declara en su ficha, textualmente, **"36 Horas"** como duración de
un contrato de aseo de una casa de acogida. Es un dato mal cargado por el
organismo: la garantía de fiel cumplimiento del mismo contrato vence el
**29-12-2027**, tres años después. Nadie cauciona hasta 2027 un contrato de 36
horas.

- El **regex** extrajo `"36 Horas"`. Lo que dice la fuente.
- El **modelo** respondió `"36 meses"`. Lo que la fuente *debería* haber dicho.

El modelo no se equivocó por ignorancia: **corrigió**. Silenciosamente, sin
marcar nada, reemplazó un valor implausible por el plausible.

Para un pipeline cuyo trabajo incluye detectar la basura de la fuente, eso es
peor que un error: **destruye la evidencia del problema que queremos encontrar.**
La pregunta de negocio 2 del análisis —qué garantías vencen antes que el contrato
que caucionan— nació precisamente de este dato. Con el modelo en esa ruta, la
anomalía desaparece y la pregunta deja de tener respuesta.

Un extractor no debe ser razonable. Debe ser fiel.

## El otro fallo revelador

En Mostazal, cuya ficha **no tiene causales de término**, el modelo devolvió la
cláusula de readjudicación etiquetada como causal de término. No inventó texto
—la cláusula es real— pero la clasificó mal antes que admitir que el campo estaba
vacío.

El filtro de recuperación por palabras clave responde ese caso correctamente y
sin llamar al modelo: cero pasajes encontrados, por lo tanto `null`.

## Donde el modelo sí gana, y gana claro

**Causales de término, en los dos documentos que las tienen.** SENAMA: siete
causales, de la a) a la g), completas y bien estructuradas. Puerto Montt: nueve,
numeradas, incluida la referencia al tope de multas del artículo 30 de las BAE.

Eso es prosa legal densa, sin estructura tabular, redactada distinto por cada
organismo. **Un regex no llega ahí.** Es el único campo donde el modelo aporta
algo que la alternativa determinista no puede dar.

## Latencia y recursos

| Documento | Chars | Segundos |
|---|---|---|
| Mostazal | 19.098 | 499 |
| Puerto Montt | 43.056 | 860 |
| SENAMA | 38.642 | **3.950** |

**La relación no es lineal, y hay que ser honesto sobre por qué.** SENAMA tardó
4,6 veces más que Puerto Montt siendo más corto. Dos causas se mezclan: su salida
fue mucho más larga (siete causales extensas), y corrió cuando la RAM libre
estaba en 0,4 GB, con Windows comprimiendo. Puerto Montt corrió con 1,5 GB
libres. **No se puede atribuir el 3.950 solo al modelo:** parte es presión de
memoria. Medirlo aislado exigiría otra corrida.

Consumo: **7,34 GB de RAM**, el 53% del total de la máquina, dejando el sistema
en 0,4 GB libres durante media hora.

Extrapolado a las 300 licitaciones del tope definido: **más de 60 horas de
inferencia local**. La capa local no procesa lotes en este hardware.

---

## Decisión de diseño

Según la tabla del método, el resultado es **"inconsistente o parcial" →
alcance acotado**. En concreto:

**1. El modelo NO toca ningún campo estructurado.** Monto, plazo, unidad, fechas,
RUT, códigos y garantías salen de la API o de parseo determinista sobre la ficha.
Están en tablas y en campos tipados; un regex los extrae mejor, en
milisegundos, y —crítico— sin corregirlos.

**2. El modelo se usa SOLO para cláusulas en prosa libre**, hoy únicamente
causales de término.

**3. Con un filtro de recuperación por delante, siempre.** Se buscan pasajes por
palabras clave y solo esos se le mandan. Si no hay pasajes, el campo es `null` y
**no se llama al modelo**. Esto arregla el fallo de Mostazal y reduce el texto
enviado entre un 43% y un 76%.

**4. Con trazabilidad obligatoria.** Todo valor inferido guarda el fragmento de
origen. Sin eso no es defendible.

## Consecuencia para la Fase 1

El análisis exige que al menos una pregunta de negocio requiera la capa de
inferencia, o esa capa sale del proyecto. Ninguna de las cinco actuales la
requiere.

Con este resultado hay dos caminos honestos, y es decisión del desarrollador:

- **Agregar una sexta pregunta** que solo se responda leyendo prosa: por ejemplo,
  comparar cómo distintos organismos redactan sus causales de término. El spike
  muestra que el modelo lo hace bien.
- **Sacar la capa del alcance** y documentar esta medición como el motivo. Es
  defendible: *"la probé, medí, y no justificaba su costo en cuatro de cinco
  campos"*.

En cualquiera de los dos, la capa queda fuera de la línea de corte: es upside.

## Lo que este spike compró

Cuatro decisiones que ya no son opinión:

1. El límite entre extracción determinista e inferencia, con un caso concreto de
   por qué cruzarlo es peligroso.
2. La necesidad del filtro de recuperación antes del modelo.
3. El costo real de la inferencia local en este hardware: 7,34 GB y minutos por
   documento.
4. Una regla de validación —garantía contra plazo— que detecta basura de la
   fuente sin modelo alguno.

## Pendiente

Comparación con `llama3.2:3b` y con el adaptador hosted, sobre el mismo
documento. Serviría para responder *"¿cuál es el modelo mínimo viable?"*, pero no
cambia la recomendación: el problema del campo `plazo` no es de tamaño de modelo,
es de que un extractor no debe razonar sobre lo que extrae.

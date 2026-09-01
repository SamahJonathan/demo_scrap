# Operación

Cómo correr el pipeline, cómo leer su reporte y qué hacer cuando algo falla.

---

## El ciclo completo

```bash
# 1. Corre el pipeline sobre las fechas del .env
python -m contratos.cli correr --reporte

# 2. Revisa las preguntas de negocio
python -m contratos.cli analizar

# 3. Publica
bash despliegue/desplegar.sh
```

El paso 3 se niega a publicar una base sin contratos: una corrida a medias no
llega al aire.

---

## Antes de correr: el ticket

**`MP_API_TICKET` se renueva a diario.** Si está vencido, Mercado Público
responde **HTTP 203** —un código de éxito— con `{"Codigo":203,"Mensaje":"Ticket
no válido."}`.

El cliente lo detecta mirando el cuerpo y no el código HTTP, falla con un
mensaje que dice qué hacer, y **no cachea la respuesta**. Sin ese control, la
corrida habría terminado "bien" con cero registros.

Se pide en <https://www.chilecompra.cl/api/> con Clave Única. Tope: 10.000
requests diarios.

---

## Cómo leer el reporte

```
==================================================================
CORRIDA — 87.0 s
==================================================================
  requests emitidos   : 44
  aciertos de caché   : 3 (6% evitado)
  contratos           : 20

  registros por fuente:
     garantias              9
     licitaciones           7
     oc_detalladas          20
     ocds                   7

  FUENTES CAÍDAS (las demás continuaron):
     ficha_web              1002772-87-LE24: no se encontró la tabla

  cuarentena          : 0 (0.0%)

  HALLAZGOS (la fuente se contradice):
     1004-56-LP24       garantia_vence_antes_del_contrato

  RESULTADO: corrida confiable
==================================================================
```

### Qué mirar, en orden

**`aciertos de caché`.** Un 0% en una re-ejecución significa que la caché no
está funcionando y cada prueba está gastando cupo del ticket.

**`registros por fuente`.** Un cero delata una fuente caída que el resto del
pipeline disimuló. Si `garantias` es mucho menor que `licitaciones`, el parser
de la ficha probablemente se rompió.

**`FUENTES CAÍDAS`.** Se reportan pero **no invalidan la corrida**: una ficha sin
tabla de garantías es normal. Lo que sí la invalida es que fallen muchas, y eso
lo mide la cobertura.

**`HALLAZGOS`.** No son errores del pipeline: son contradicciones **de la
fuente**. Ver la sección siguiente.

**`RESULTADO`.** Es el veredicto. La corrida sale con **código distinto de cero**
si no es confiable, para poder encadenarla en un cron o en CI sin revisarla a
ojo.

---

## Los hallazgos son de la fuente, no del código

Un hallazgo significa que **dos campos de Mercado Público se contradicen**. No se
corrige nada: se registran ambos valores y se marca el registro.

| Hallazgo | Qué significa |
|---|---|
| `garantia_vence_antes_del_contrato` | La caución sobrevive al contrato con holgura |
| `items_no_cuadran_con_ocds` | La suma de ítems difiere del `award.value` de OCDS |
| `monto_adjudicado_parece_precio_unitario` | Convenio de suministro: el monto no debe sumarse |
| `unidad_de_duracion_sin_decodificar` | Apareció un valor del enum que no sabemos leer |

### La magnitud importa

El hallazgo reporta **cuántas veces** la garantía excede el plazo, porque no
todos los casos son iguales:

| Caso | Contrato | Garantía | Exceso |
|---|---|---|---|
| `1300-43-LP24` SENAMA | 36 **horas** | 2027-12-29 | ~1000× |
| `1004-56-LP24` Vigilancia | 24 meses | 2028-03-05 | 1,6× |

El primero es absurdo: nadie cauciona hasta 2027 algo que dura día y medio. El
segundo puede ser una caución larga legítima. **La regla señala; quien mira
decide.**

### `unidad_de_duracion_sin_decodificar` es deuda nuestra

Los demás hallazgos son problemas de la fuente. Este no: significa que apareció
un valor de `UnidadTiempoDuracionContrato` distinto de `1` (horas) y `4` (meses),
que son los únicos confirmados. Hay que investigarlo y agregarlo, no adivinarlo.

---

## Cuando algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `Ticket no válido` | El ticket venció | Renovarlo en chilecompra.cl |
| `MAX_REQUESTS_PER_RUN` alcanzado | Ventana muy amplia | Bajar el límite o esperar al día siguiente |
| Cobertura de garantías baja | La ficha cambió de estructura | Revisar `#grvGarantias` en el HTML guardado |
| Cuarentena sobre el umbral | Un parser roto, no datos malos | Mirar `data/quarantine/` |
| `no existe la base` en el dashboard | No se corrió el pipeline | `contratos correr` |

### Reprocesar es seguro

Todo lo crudo queda en `data/raw/` y la persistencia es idempotente por clave
natural. Si se corrige un parser, se corre de nuevo **sin gastar un request**:
la caché responde y la base se actualiza en vez de duplicar.

```bash
python -m contratos.cli correr --reporte   # 0 requests si ya está en caché
```

---

## Antes de desplegar: la clave SSH

El script asume la clave en `~/.ssh/LightsailDefaultKey-sa-east-1.pem`. Si no
está ahí, se le indica dónde:

```bash
CLAVE="/c/Users/.../LightsailDefaultKey-sa-east-1.pem" bash despliegue/desplegar.sh
```

Sin eso el despliegue **falla en el primer `ssh`** con `Permission denied
(publickey)`, que parece un problema de permisos en el servidor y no lo es. La
clave nunca entra al repo: es una ruta local, no un secreto versionado.

`SERVIDOR`, `DOMINIO` y `BASE_LOCAL` se sobrescriben igual, por variable de
entorno.

---

## En el servidor

```bash
sudo systemctl status contratos      # estado del servicio
sudo journalctl -u contratos -n 50   # sus últimos logs
curl -s https://contratos.54-207-164-201.sslip.io/salud
```

`/salud` es diagnóstico, no un ping: devuelve conteos por tabla, la fecha de la
última corrida y si alcanza el mínimo esperado.

**El servidor nunca consulta a Mercado Público.** Solo sirve el `.db` que se le
copió. No tiene ticket ni lo necesita.

**Y nunca corre inferencia.** El modelo pide 7,34 GB y tarda minutos por
documento; la instancia tiene 911 MB compartidos con otros tres sitios. La
inferencia vive en la máquina de desarrollo, en lote.

### Por qué certbot corre en cada despliegue

**certbot modifica el archivo de nginx in situ** para agregar los bloques de
SSL. Como el script sobrescribe ese archivo, saltarse certbot cuando el
certificado ya existe **deja el sitio sin TLS**: el puerto 443 cae al
certificado de otro sitio y el navegador reporta nombre incorrecto.

Pasó una vez, en un redespliegue, y se detectó porque la verificación lo
comprueba. Por eso ahora corre siempre con `--keep-until-expiring`, que
reinstala la configuración sin volver a pedir el certificado ni gastar cuota de
Let's Encrypt.

La verificación final recorre **las siete rutas**, no solo la portada: un
despliegue que prueba una sola ruta no detecta las otras seis rotas.

### Para actualizar solo los datos

```bash
bash despliegue/desplegar.sh --solo-datos
```

Copia el `.db` y reinicia el servicio, sin tocar el código ni nginx.

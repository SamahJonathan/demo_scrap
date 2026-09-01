-- Esquema completo desde el primer dia. `clausula_extraida` y `discrepancia`
-- quedan vacias hasta el incremento 13, pero se crean ahora: migrar un esquema
-- despues cuesta mas que preverlo.
--
-- SQLite y no PostgreSQL: son ~450 filas de solo lectura y el MISMO archivo se
-- explora con SQL en local y se despliega sin conversion. Ver docs/02-diseno.md.

PRAGMA foreign_keys = ON;

-- El proceso. Solo existe para el 44% de las ordenes que lo tiene.
CREATE TABLE IF NOT EXISTS licitacion (
    codigo                  TEXT PRIMARY KEY,
    nombre                  TEXT NOT NULL DEFAULT '',
    fecha_publicacion       TEXT,
    fecha_adjudicacion      TEXT,
    duracion_valor          INTEGER,
    -- horas | meses | desconocido. Solo 1 y 4 estan decodificados en la fuente.
    duracion_unidad         TEXT NOT NULL DEFAULT 'desconocido',
    es_renovable            INTEGER NOT NULL DEFAULT 0,
    monto_adjudicado_total  TEXT,
    n_oferentes             INTEGER,
    -- URL de la ficha publica. Se guarda para que el dashboard pueda enlazar
    -- al documento original: un dato marcado como dudoso tiene que poder
    -- contrastarse contra la fuente en un clic, no de palabra.
    url_ficha               TEXT,
    -- El monto declarado parece un precio unitario y no el valor del contrato.
    monto_es_unitario       INTEGER NOT NULL DEFAULT 0
);

-- La unidad de la demo: una orden de compra, un proveedor, un monto real.
CREATE TABLE IF NOT EXISTS contrato (
    codigo_oc               TEXT PRIMARY KEY,
    -- ANULABLE a proposito: el 56% de las ordenes no nace de una licitacion.
    -- Compra agil, convenio marco y trato directo son casos VALIDOS.
    codigo_licitacion       TEXT REFERENCES licitacion(codigo),
    organismo               TEXT NOT NULL DEFAULT '',
    organismo_rut           TEXT NOT NULL DEFAULT '',
    proveedor               TEXT NOT NULL DEFAULT '',
    proveedor_rut           TEXT NOT NULL DEFAULT '',
    -- Los montos van como TEXT para no perder precision decimal: SQLite no
    -- tiene DECIMAL y REAL introduce error de coma flotante en pesos.
    monto_ejecutado         TEXT NOT NULL DEFAULT '0',
    monto_adjudicado        TEXT,
    -- "Gasto" son dos cosas distintas: comprometido es que la orden existe y
    -- no fue anulada; ejecutado es que el proveedor acepto o entrego.
    es_comprometido         INTEGER NOT NULL DEFAULT 0,
    es_ejecutado            INTEGER NOT NULL DEFAULT 0,
    estado                  TEXT NOT NULL DEFAULT '',
    fecha_aceptacion        TEXT,
    fecha_termino_estimada  TEXT,
    -- calculado | no_declarado | unidad_desconocida. Dice POR QUE falta la
    -- fecha, en vez de un NULL mudo que mezcla tres situaciones distintas.
    estado_vencimiento      TEXT NOT NULL DEFAULT 'no_declarado'
);

-- Pertenece a la LICITACION, no al contrato: cinco ordenes de la misma
-- licitacion comparten sus dos garantias. Replicarlas haria que contarlas
-- diera diez.
CREATE TABLE IF NOT EXISTS garantia (
    licitacion_codigo       TEXT NOT NULL REFERENCES licitacion(codigo),
    tipo                    TEXT NOT NULL,
    titulo_original         TEXT NOT NULL DEFAULT '',
    monto_valor             TEXT,
    -- Un 5 % y $5 no son lo mismo y no pueden colapsarse en un campo.
    monto_es_porcentaje     INTEGER NOT NULL DEFAULT 0,
    moneda                  TEXT,
    fecha_vencimiento       TEXT,
    beneficiario            TEXT,
    -- Sin trazabilidad al origen el dato no es defendible.
    fragmento_origen        TEXT NOT NULL,
    PRIMARY KEY (licitacion_codigo, tipo, fragmento_origen)
);

-- Se puebla en el incremento 13, si la capa de inferencia entra.
CREATE TABLE IF NOT EXISTS clausula_extraida (
    licitacion_codigo       TEXT NOT NULL REFERENCES licitacion(codigo),
    tipo                    TEXT NOT NULL,
    texto                   TEXT NOT NULL,
    -- Obligatorios: un dato inferido sin poder mostrar de donde salio no entra.
    fragmento_origen        TEXT NOT NULL,
    posicion_inicio         INTEGER NOT NULL,
    modelo                  TEXT NOT NULL,
    PRIMARY KEY (licitacion_codigo, tipo)
);

-- Cuando el campo estructurado contradice a la prosa. Se registran AMBOS
-- valores: ni el parseo ni el modelo ganan por defecto.
CREATE TABLE IF NOT EXISTS discrepancia (
    licitacion_codigo       TEXT NOT NULL REFERENCES licitacion(codigo),
    campo                   TEXT NOT NULL,
    valor_estructurado      TEXT,
    valor_prosa             TEXT,
    regla                   TEXT NOT NULL,
    PRIMARY KEY (licitacion_codigo, campo)
);

-- Indices para las preguntas de negocio de docs/01-analisis.md
CREATE INDEX IF NOT EXISTS ix_contrato_vencimiento
    ON contrato(fecha_termino_estimada);          -- P1: que vence
CREATE INDEX IF NOT EXISTS ix_contrato_organismo
    ON contrato(organismo_rut);                   -- P4: monto por organismo
CREATE INDEX IF NOT EXISTS ix_contrato_proveedor
    ON contrato(proveedor_rut);                   -- P4: con que proveedores
CREATE INDEX IF NOT EXISTS ix_contrato_proceso
    ON contrato(codigo_licitacion);               -- P5: cuales no tienen proceso
CREATE INDEX IF NOT EXISTS ix_garantia_vencimiento
    ON garantia(fecha_vencimiento);               -- P2: cauciones vivas

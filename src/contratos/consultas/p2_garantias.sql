-- P2: ¿Qué garantías siguen vigentes, y cuáles vencen antes que el contrato
--     que caucionan?
--
-- Se cuentan UNA VEZ POR LICITACION, no una por contrato: cinco ordenes de la
-- misma licitacion comparten sus dos garantias, y contarlas por contrato daria
-- diez. Por eso la consulta arranca en garantia y no en contrato.
--
-- `motivo` separa DOS defectos que antes se marcaban igual, y que se
-- diagnostican distinto:
--
--   duracion_cero      El organismo dejo el campo de duracion en 0. No es una
--                      contradiccion, es un vacio. Son la mayoria.
--   unidad_sospechosa  Hay una duracion real en HORAS y una garantia que vive
--                      mas de un anio. Nadie cauciona por un anio un contrato
--                      de horas: casi seguro son meses cargados como horas.
--                      Es el caso de SENAMA, del que nacio la regla.
SELECT
    g.licitacion_codigo,
    g.tipo,
    g.monto_valor,
    g.monto_es_porcentaje,
    g.fecha_vencimiento,
    l.duracion_valor,
    l.duracion_unidad,
    CASE
        WHEN g.tipo = 'fiel_cumplimiento'
         AND l.duracion_unidad = 'horas'
         AND julianday(g.fecha_vencimiento)
             - julianday(l.fecha_adjudicacion) > 365
        THEN 1 ELSE 0
    END AS implausible,
    CASE
        WHEN g.tipo = 'fiel_cumplimiento'
         AND l.duracion_unidad = 'horas'
         AND julianday(g.fecha_vencimiento)
             - julianday(l.fecha_adjudicacion) > 365
        THEN CASE WHEN l.duracion_valor = 0
                  THEN 'duracion_cero' ELSE 'unidad_sospechosa' END
    END AS motivo,
    CASE WHEN g.fecha_vencimiento >= :hoy THEN 1 ELSE 0 END AS vigente,
    -- Una caucion expresada en porcentaje no es exigible hasta traducirla a
    -- pesos. Se calcula SOLO si hay monto adjudicado y ese monto es creible:
    -- `monto_es_unitario` lo marca la validacion cuando el monto declarado
    -- parece un precio por unidad. Sin esa guarda, un convenio de suministro
    -- daria una boleta de centavos.
    CASE
        WHEN g.monto_es_porcentaje = 1
         AND l.monto_es_unitario = 0
         AND CAST(l.monto_adjudicado_total AS REAL) > 0
        THEN ROUND(CAST(l.monto_adjudicado_total AS REAL)
                   * CAST(g.monto_valor AS REAL) / 100.0)
    END AS monto_pesos,
    -- La base del calculo viaja con el resultado: sin ella el numero seria
    -- una afirmacion nuestra en vez de una operacion auditable.
    CASE
        WHEN g.monto_es_porcentaje = 1 AND l.monto_es_unitario = 0
        THEN CAST(l.monto_adjudicado_total AS REAL)
    END AS base_calculo,
    -- POR QUE no hay cifra. Una celda vacia se lee como un error nuestro; el
    -- motivo la convierte en un hecho sobre la fuente. Son dos causas
    -- distintas y se defienden distinto.
    CASE
        WHEN g.monto_es_porcentaje = 0 THEN NULL
        WHEN l.monto_es_unitario = 1 THEN 'monto_no_confiable'
        WHEN l.monto_adjudicado_total IS NULL
          OR CAST(l.monto_adjudicado_total AS REAL) = 0 THEN 'sin_monto_adjudicado'
    END AS sin_cifra_porque
FROM garantia g
JOIN licitacion l ON l.codigo = g.licitacion_codigo
ORDER BY implausible DESC, g.fecha_vencimiento;

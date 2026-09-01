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
    CASE WHEN g.fecha_vencimiento >= :hoy THEN 1 ELSE 0 END AS vigente
FROM garantia g
JOIN licitacion l ON l.codigo = g.licitacion_codigo
ORDER BY implausible DESC, g.fecha_vencimiento;

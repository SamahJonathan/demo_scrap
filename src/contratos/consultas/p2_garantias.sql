-- P2: ¿Qué garantías siguen vigentes, y cuáles vencen antes que el contrato
--     que caucionan?
--
-- Se cuentan UNA VEZ POR LICITACION, no una por contrato: cinco ordenes de la
-- misma licitacion comparten sus dos garantias, y contarlas por contrato daria
-- diez. Por eso la consulta arranca en garantia y no en contrato.
SELECT
    g.licitacion_codigo,
    g.tipo,
    g.monto_valor,
    g.monto_es_porcentaje,
    g.fecha_vencimiento,
    l.duracion_valor,
    l.duracion_unidad,
    -- La regla nacio de un dato corrupto real: SENAMA declara 36 HORAS de
    -- contrato y una garantia que vence tres anios despues.
    CASE
        WHEN g.tipo = 'fiel_cumplimiento'
         AND l.duracion_unidad = 'horas'
         AND julianday(g.fecha_vencimiento)
             - julianday(l.fecha_adjudicacion) > 365
        THEN 1 ELSE 0
    END AS implausible,
    CASE WHEN g.fecha_vencimiento >= :hoy THEN 1 ELSE 0 END AS vigente
FROM garantia g
JOIN licitacion l ON l.codigo = g.licitacion_codigo
ORDER BY implausible DESC, g.fecha_vencimiento;

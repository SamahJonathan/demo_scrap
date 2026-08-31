-- P1: ¿Qué contratos vencen en los próximos N meses, y cuáles son renovables
--     frente a cuáles hay que relicitar?
--
-- Solo aplica a contratos con proceso: una compra ágil es una compra puntual,
-- no un contrato con vigencia. Por eso se filtra por estado_vencimiento.
SELECT
    c.codigo_oc,
    c.organismo,
    c.proveedor,
    c.monto_ejecutado,
    c.fecha_termino_estimada,
    CAST(julianday(c.fecha_termino_estimada) - julianday(:hoy) AS INTEGER)
        AS dias_restantes,
    l.es_renovable,
    -- Lo accionable: renovar o relicitar. Es la decision que el gestor toma.
    CASE WHEN l.es_renovable = 1 THEN 'renovar' ELSE 'relicitar' END AS accion
FROM contrato c
JOIN licitacion l ON l.codigo = c.codigo_licitacion
WHERE c.estado_vencimiento = 'calculado'
  AND c.fecha_termino_estimada >= :hoy
  AND c.fecha_termino_estimada <= :hasta
ORDER BY c.fecha_termino_estimada;

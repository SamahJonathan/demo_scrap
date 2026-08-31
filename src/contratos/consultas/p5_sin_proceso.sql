-- P5: ¿Qué órdenes de compra no nacen de una licitación, y qué proporción del
--     gasto representan?
--
-- Compra agil, convenio marco y trato directo son el 56% de las ordenes. No
-- son un defecto del dato: son modalidades que no pasan por licitacion, y para
-- un CLM son contratos sin proceso previo, el caso dificil de ingestar.
SELECT
    CASE WHEN codigo_licitacion IS NULL THEN 'sin proceso' ELSE 'con proceso' END
        AS origen,
    COUNT(*) AS contratos,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM contrato), 1) AS pct_contratos,
    SUM(CASE WHEN es_ejecutado = 1
             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END) AS ejecutado
FROM contrato
GROUP BY origen
ORDER BY ejecutado DESC;

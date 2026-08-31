-- P6: ¿Sobre qué parte de la cartera puede hablar la página de vencimientos?
--
-- Un panel de vencimientos que no dice cuántos contratos NO tiene en cuenta
-- miente por omisión. El 56% de las órdenes no nace de una licitación y por lo
-- tanto no tiene vigencia que vigilar.
--
-- estado_vencimiento distingue POR QUE falta la fecha, en vez de un NULL mudo:
--   calculado           hay adjudicacion y unidad decodificable
--   no_declarado        compra puntual: agil, marco, trato directo
--   unidad_desconocida  hay plazo pero no sabemos leer su unidad -> deuda NUESTRA
SELECT
    estado_vencimiento,
    COUNT(*) AS contratos,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM contrato), 1) AS pct,
    CASE estado_vencimiento
        WHEN 'calculado'          THEN 'aparece en vencimientos'
        WHEN 'no_declarado'       THEN 'compra puntual, sin vigencia que vigilar'
        WHEN 'unidad_desconocida' THEN 'enum sin decodificar: hay que investigarlo'
    END AS explicacion
FROM contrato
GROUP BY estado_vencimiento
ORDER BY contratos DESC;

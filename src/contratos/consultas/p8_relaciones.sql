-- P8: ¿Qué pares comprador–proveedor se repiten, y cuánto pesan?
--
-- Para un area COMERCIAL la pregunta no es cuanto se gasto, sino con quien se
-- vuelve a contratar. Una relacion que se repite es una cuenta viva; una que
-- no se repite fue una venta suelta.
--
-- Se agrupa por RUT y no por nombre: el mismo organismo aparece escrito de
-- varias formas en la fuente ("MINISTERIO DE OBRAS PUBLICAS DIREC CION GRAL"
-- frente a "MOP - DIRECCION DE VIALIDAD"), y agrupar por texto los separaria.
SELECT
    organismo,
    proveedor,
    COUNT(*) AS contratos,
    SUM(CASE WHEN es_ejecutado = 1
             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END) AS ejecutado,
    MIN(fecha_aceptacion) AS desde,
    MAX(fecha_aceptacion) AS hasta,
    SUM(CASE WHEN codigo_licitacion IS NULL THEN 1 ELSE 0 END) AS sin_proceso
FROM contrato
WHERE es_comprometido = 1
GROUP BY organismo_rut, proveedor_rut
HAVING COUNT(*) > 1
ORDER BY contratos DESC, ejecutado DESC;

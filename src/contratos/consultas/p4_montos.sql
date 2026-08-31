-- P4: ¿Qué organismos concentran mayor monto vigente, y con qué proveedores?
--
-- Usa monto_ejecutado, NO monto_adjudicado: en un convenio de suministro lo
-- adjudicado es un precio unitario. Puerto Montt adjudica $783,19 el litro de
-- diesel y su convenio vale $1.500 millones. Sumar adjudicados mezclaria
-- totales con precios unitarios.
--
-- Comprometido y ejecutado son cosas distintas y se muestran las dos: la
-- brecha son las ordenes cuyo destino todavia no se sabe.
SELECT
    organismo,
    organismo_rut,
    COUNT(*) AS contratos,
    COUNT(DISTINCT proveedor_rut) AS proveedores,
    SUM(CASE WHEN es_ejecutado = 1
             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END) AS ejecutado,
    SUM(CASE WHEN es_comprometido = 1
             THEN CAST(monto_ejecutado AS REAL) ELSE 0 END) AS comprometido
FROM contrato
GROUP BY organismo, organismo_rut
ORDER BY ejecutado DESC;

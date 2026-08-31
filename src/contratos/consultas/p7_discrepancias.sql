-- P7: ¿Qué contratos tienen datos que se contradicen entre sí?
--
-- Es la pregunta que permite confiar en las demas. Un vencimiento calculado
-- desde un plazo mal cargado es un vencimiento falso, y la pagina de
-- vencimientos lo mostraria con la misma confianza que a los buenos.
--
-- Dos origenes distintos, y conviene no mezclarlos:
--   - la duracion contradice a la prosa del documento (capa de inferencia)
--   - la garantia es incoherente con el plazo (regla determinista)
--
-- En ambos casos se conservan LOS DOS valores. Ni el parseo ni el modelo ganan
-- por defecto: detectar la contradiccion es el resultado.
SELECT
    d.licitacion_codigo,
    d.campo,
    d.valor_estructurado,
    d.valor_prosa,
    d.regla,
    (SELECT COUNT(*) FROM contrato c
      WHERE c.codigo_licitacion = d.licitacion_codigo) AS contratos_afectados
FROM discrepancia d
ORDER BY contratos_afectados DESC, d.licitacion_codigo;

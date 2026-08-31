-- P3: ¿Cuánto tarda cada organismo entre publicar y adjudicar, y cuánto varía?
--
-- Devuelve p25, mediana y p75, no el promedio. Se midieron 45, 115 y 215 dias
-- en tres organismos: con esa dispersion el promedio miente.
--
-- Solo contratos CON proceso: una orden huerfana no tiene publicacion que medir.
WITH dias AS (
    SELECT DISTINCT
        c.organismo,
        l.codigo,
        CAST(julianday(l.fecha_adjudicacion)
             - julianday(l.fecha_publicacion) AS INTEGER) AS d
    FROM contrato c
    JOIN licitacion l ON l.codigo = c.codigo_licitacion
    WHERE l.fecha_publicacion IS NOT NULL
      AND l.fecha_adjudicacion IS NOT NULL
),
ordenados AS (
    SELECT organismo, d,
           ROW_NUMBER() OVER (PARTITION BY organismo ORDER BY d) AS pos,
           COUNT(*)     OVER (PARTITION BY organismo)            AS n
    FROM dias
)
SELECT
    organismo,
    n AS procesos,
    MIN(CASE WHEN pos >= (n + 3) / 4     THEN d END) AS p25,
    MIN(CASE WHEN pos >= (n + 1) / 2     THEN d END) AS mediana,
    MIN(CASE WHEN pos >= (3 * n + 1) / 4 THEN d END) AS p75,
    MAX(d) AS maximo
FROM ordenados
GROUP BY organismo, n
ORDER BY mediana DESC;

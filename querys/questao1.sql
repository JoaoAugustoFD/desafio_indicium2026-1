SELECT
    COUNT(*)                    AS total_linhas,
    6                           AS total_colunas,
    MIN(sale_date)              AS data_minima,
    MAX(sale_date)              AS data_maxima,
    MIN(total)                  AS valor_minimo,
    MAX(total)                  AS valor_maximo,
    ROUND(AVG(total), 2)        AS valor_medio
FROM vendas_2023_2024;
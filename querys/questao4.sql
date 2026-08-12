WITH cambio_por_venda AS (
    SELECT
        v.id,
        v.id_product,
        v.sale_date,
        v.qtd,
        v.total AS receita,
        (
            SELECT c.taxa_venda
            FROM cambio c
            WHERE c.data_cotacao <= v.sale_date
            ORDER BY c.data_cotacao DESC
            LIMIT 1
        ) AS taxa_cambio
    FROM vendas v
),
custo_por_venda AS (
    SELECT
        cv.*,
        (
            SELECT ci.usd_price
            FROM custos ci
            WHERE ci.product_id = cv.id_product
              AND ci.start_date <= cv.sale_date
            ORDER BY ci.start_date DESC
            LIMIT 1
        ) AS custo_usd_unit
    FROM cambio_por_venda cv
),
transacoes AS (
    SELECT
        *,
        custo_usd_unit * qtd * taxa_cambio              AS custo_brl_total,
        (custo_usd_unit * qtd * taxa_cambio) - receita  AS resultado
    FROM custo_por_venda
    WHERE taxa_cambio    IS NOT NULL
      AND custo_usd_unit IS NOT NULL
)
SELECT
    id_product,
    ROUND(SUM(receita), 2)                                           AS receita_total,
    ROUND(SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END), 2) AS prejuizo_total,
    ROUND(
        SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END)
        / NULLIF(SUM(receita), 0) * 100
    , 2)                                                             AS percentual_perda
FROM transacoes
GROUP BY id_product
HAVING SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END) > 0
ORDER BY prejuizo_total DESC;
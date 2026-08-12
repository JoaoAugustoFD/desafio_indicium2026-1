import duckdb
import pandas as pd
import matplotlib.pyplot as plt

con = duckdb.connect("lh_nautical.db")

con.execute("""
    CREATE TABLE IF NOT EXISTS vendas AS
    SELECT 
        CAST(id AS INTEGER) AS id,
        CAST(id_client AS INTEGER) AS id_client,
        CAST(id_product AS INTEGER) AS id_product,
        CAST(qtd AS DOUBLE) AS qtd,
        CAST(total AS DOUBLE) AS total,
        CASE
            WHEN regexp_matches(sale_date, '^\d{4}-\d{2}-\d{2}$') THEN strptime(sale_date, '%Y-%m-%d')::DATE
            ELSE strptime(sale_date, '%d-%m-%Y')::DATE
        END AS sale_date
    FROM read_csv_auto('vendas_2023_2024.csv', all_varchar=true)
""")
con.execute("CREATE TABLE IF NOT EXISTS cambio AS SELECT data_cotacao::DATE AS data_cotacao, taxa_venda FROM read_csv_auto('cambio.csv')")
con.execute("CREATE TABLE IF NOT EXISTS custos AS SELECT product_id, product_name, category, start_date::DATE AS start_date, usd_price FROM read_csv_auto('custos_importacao.csv')")

resultado = con.execute("""
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
ORDER BY prejuizo_total DESC
""").df()

print(resultado.to_string(index=False))
resultado.to_csv("resultado_prejuizo.csv", index=False)
print(f"\nTotal de produtos com prejuízo: {len(resultado)}")
print("Arquivo salvo: resultado_prejuizo.csv")

top20 = resultado.head(20).sort_values("prejuizo_total")

fig, ax = plt.subplots(figsize=(12, 8))
bars = ax.barh(
    top20["id_product"].astype(str),
    top20["prejuizo_total"] / 1_000,
    color="#e05c5c",
    edgecolor="white"
)
ax.set_xlabel("Prejuízo Total (R$ mil)", fontsize=12)
ax.set_ylabel("ID do Produto", fontsize=12)
ax.set_title("Top 20 Produtos com Maior Prejuízo (BRL)", fontsize=14, fontweight="bold")
ax.bar_label(bars, fmt="R$ %.0fk", padding=4, fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig("prejuizo_por_produto.png", dpi=150)
print("Gráfico salvo: prejuizo_por_produto.png")

print("\n--- PRODUTO COM MAIOR PERCENTUAL DE PERDA ---")
maior = resultado.nlargest(1, 'percentual_perda')
print(maior.to_string(index=False))
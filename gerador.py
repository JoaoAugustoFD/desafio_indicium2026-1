import duckdb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

con = duckdb.connect("lh_nautical.db")

DATE_CASE = """CASE
    WHEN regexp_matches(sale_date, '^\\d{4}-\\d{2}-\\d{2}$') THEN strptime(sale_date, '%Y-%m-%d')::DATE
    ELSE strptime(sale_date, '%d-%m-%Y')::DATE
END"""

# Busca dados de prejuízo do banco
prej = con.execute(f"""
    WITH cpv AS (
        SELECT v.id, v.id_product, v.sale_date, v.qtd, v.total AS receita,
            (SELECT c.taxa_venda FROM cambio c
             WHERE c.data_cotacao <= {DATE_CASE.replace('sale_date', 'v.sale_date')}
             ORDER BY c.data_cotacao DESC LIMIT 1) AS taxa_cambio
        FROM vendas v
    ),
    cuv AS (
        SELECT cv.*,
            (SELECT ci.usd_price FROM custos ci
             WHERE ci.product_id = CAST(cv.id_product AS INTEGER)
               AND ci.start_date <= {DATE_CASE.replace('sale_date', 'cv.sale_date')}
             ORDER BY ci.start_date DESC LIMIT 1) AS custo_usd
        FROM cpv cv
    ),
    trans AS (
        SELECT *,
            (CAST(custo_usd AS DOUBLE) * CAST(qtd AS DOUBLE) * taxa_cambio) - CAST(receita AS DOUBLE) AS resultado
        FROM cuv WHERE taxa_cambio IS NOT NULL AND custo_usd IS NOT NULL
    )
    SELECT id_product,
        ROUND(SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END), 2) AS prejuizo_total,
        ROUND(SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END) / NULLIF(SUM(CAST(receita AS DOUBLE)),0) * 100, 2) AS percentual_perda
    FROM trans GROUP BY id_product
    HAVING SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END) > 0
    ORDER BY prejuizo_total DESC LIMIT 20
""").df()

con.close()

top20 = prej.sort_values("prejuizo_total")

# -------------------------------------------------------
# GRÁFICO EM ALTA RESOLUÇÃO
# -------------------------------------------------------
fig, ax = plt.subplots(figsize=(16, 10))
fig.patch.set_facecolor("#1a2236")
ax.set_facecolor("#1a2236")

colors = ["#ff4757" if v/top20["prejuizo_total"].max() > 0.5
          else "#ff6b35" if v/top20["prejuizo_total"].max() > 0.2
          else "#00d4ff"
          for v in top20["prejuizo_total"]]

bars = ax.barh(
    top20["id_product"].astype(str),
    top20["prejuizo_total"] / 1_000,
    color=colors,
    edgecolor="#0a0e1a",
    linewidth=0.8,
    height=0.7
)

# Labels nas barras
for bar, (_, row) in zip(bars, top20.iterrows()):
    w = bar.get_width()
    ax.text(
        w + 200, bar.get_y() + bar.get_height()/2,
        f"R$ {w:,.0f}k  ({row['percentual_perda']}%)",
        va="center", ha="left",
        fontsize=9, color="#8899b4",
        fontfamily="monospace"
    )

ax.set_xlabel("Prejuízo Total (R$ mil)", fontsize=13, color="#8899b4", labelpad=12)
ax.set_ylabel("ID do Produto", fontsize=13, color="#8899b4", labelpad=12)
ax.set_title("Top 20 Produtos com Maior Prejuízo Total (BRL)",
             fontsize=16, fontweight="bold", color="#e8edf5", pad=20)

ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R$ {x:,.0f}k"))
ax.tick_params(axis="both", colors="#8899b4", labelsize=10)
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color("#1e2d4a")
ax.grid(axis="x", color="#1e2d4a", linewidth=0.5, alpha=0.7)
ax.set_axisbelow(True)

plt.tight_layout(pad=2)
plt.savefig("grafico_prejuizo.png", dpi=300, facecolor="#1a2236", bbox_inches="tight")
plt.close()

print("✅ Gráfico salvo: grafico_prejuizo.png (300 DPI - alta resolução)")
print(f"   Top 3: id {int(top20.iloc[-1]['id_product'])} = R$ {top20.iloc[-1]['prejuizo_total']/1e3:.0f}k ({top20.iloc[-1]['percentual_perda']}%)")
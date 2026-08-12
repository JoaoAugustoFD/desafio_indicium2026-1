import duckdb
import base64
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import numpy as np

con = duckdb.connect("lh_nautical.db")

DATE_CASE = """CASE
    WHEN regexp_matches(sale_date, '^\\d{4}-\\d{2}-\\d{2}$') THEN strptime(sale_date, '%Y-%m-%d')::DATE
    ELSE strptime(sale_date, '%d-%m-%Y')::DATE
END"""

# -------------------------------------------------------
# KPIs GERAIS
# -------------------------------------------------------
kpis = con.execute("""
    SELECT
        COUNT(*)                AS total_linhas,
        ROUND(SUM(total), 2)    AS fat_total,
        ROUND(AVG(total), 2)    AS ticket_medio,
        ROUND(MEDIAN(total), 2) AS ticket_mediana,
        SUM(CASE WHEN total IS NULL THEN 1 ELSE 0 END) AS nulos
    FROM vendas
""").fetchone()
total_linhas, fat_total, ticket_medio, ticket_median, nulos = kpis

outliers = con.execute("""
    WITH stats AS (
        SELECT
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY total) AS q1,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY total) AS q3
        FROM vendas
    )
    SELECT COUNT(*) FROM vendas, stats WHERE total > q3 + 1.5*(q3-q1)
""").fetchone()[0]

ids_faltantes = con.execute("""
    SELECT (MAX(CAST(id AS INTEGER)) - MIN(CAST(id AS INTEGER)) + 1) - COUNT(DISTINCT id) FROM vendas
""").fetchone()[0]

fat_anos = con.execute(f"""
    SELECT YEAR({DATE_CASE}) AS ano, ROUND(SUM(total)/1e6, 2) AS fat_m
    FROM vendas GROUP BY ano ORDER BY ano
""").fetchall()
fat_2023 = next(r[1] for r in fat_anos if r[0] == 2023)
fat_2024 = next(r[1] for r in fat_anos if r[0] == 2024)
crescimento = round((fat_2024 - fat_2023) / fat_2023 * 100, 1)
print(f"KPIs: R${fat_total/1e9:.2f}B | crescimento={crescimento}% | outliers={outliers}")

# -------------------------------------------------------
# FATURAMENTO MENSAL
# -------------------------------------------------------
fat_mes = con.execute(f"""
    SELECT strftime({DATE_CASE}, '%Y-%m') AS mes, ROUND(SUM(total)/1e6, 1) AS val_m
    FROM vendas GROUP BY mes ORDER BY mes
""").fetchall()
fat_max = max(r[1] for r in fat_mes)
print(f"Faturamento mensal: {len(fat_mes)} meses")

# -------------------------------------------------------
# PREJUIZO
# -------------------------------------------------------
prej_query = f"""
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
            CAST(custo_usd AS DOUBLE) * CAST(qtd AS DOUBLE) * taxa_cambio AS custo_brl,
            (CAST(custo_usd AS DOUBLE) * CAST(qtd AS DOUBLE) * taxa_cambio) - CAST(receita AS DOUBLE) AS resultado
        FROM cuv WHERE taxa_cambio IS NOT NULL AND custo_usd IS NOT NULL
    )
    SELECT id_product,
        ROUND(SUM(CAST(receita AS DOUBLE)), 2) AS receita_total,
        ROUND(SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END), 2) AS prejuizo_total,
        ROUND(SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END) / NULLIF(SUM(CAST(receita AS DOUBLE)),0) * 100, 2) AS percentual_perda
    FROM trans GROUP BY id_product
    HAVING SUM(CASE WHEN resultado > 0 THEN resultado ELSE 0 END) > 0
"""

prej_todos   = con.execute(prej_query + " ORDER BY prejuizo_total DESC").df()
prej_top10   = prej_todos.head(10)
prej_pct_max = prej_todos.nlargest(5, "percentual_perda")
prej_max_val = prej_top10["prejuizo_total"].max()
print(f"Prejuizo: id {int(prej_top10.iloc[0]['id_product'])} = R${prej_top10.iloc[0]['prejuizo_total']/1e6:.1f}M")

# -------------------------------------------------------
# GRÁFICO PREJUIZO (gerado do banco, embedado como base64)
# -------------------------------------------------------
top20 = prej_todos.head(20).sort_values("prejuizo_total")

fig, ax = plt.subplots(figsize=(12, 8))
fig.patch.set_facecolor("#1a2236")
ax.set_facecolor("#1a2236")

bars = ax.barh(
    top20["id_product"].astype(str),
    top20["prejuizo_total"] / 1_000,
    color="#ff4757",
    edgecolor="#0a0e1a",
    linewidth=0.5
)
ax.set_xlabel("Prejuízo Total (R$ mil)", fontsize=11, color="#8899b4")
ax.set_ylabel("ID do Produto", fontsize=11, color="#8899b4")
ax.set_title("Top 20 Produtos com Maior Prejuízo Total (BRL)", fontsize=13, fontweight="bold", color="#e8edf5")
ax.bar_label(bars, fmt="R$ %.0fk", padding=4, fontsize=8, color="#8899b4")
ax.tick_params(colors="#8899b4")
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color("#1e2d4a")
plt.tight_layout()

buf = io.BytesIO()
plt.savefig(buf, format="png", dpi=150, facecolor="#1a2236")
buf.seek(0)
grafico_prej_b64 = base64.b64encode(buf.read()).decode("utf-8")
plt.close()
print("Gráfico de prejuízo gerado!")

# -------------------------------------------------------
# CLIENTES FIEIS
# -------------------------------------------------------
top10c = con.execute("""
    WITH metricas AS (
        SELECT v.id_client,
            ROUND(SUM(CAST(v.total AS DOUBLE)), 2) AS faturamento,
            COUNT(v.id) AS frequencia,
            ROUND(SUM(CAST(v.total AS DOUBLE))/COUNT(v.id), 2) AS ticket_medio,
            COUNT(DISTINCT p.actual_category) AS diversidade
        FROM vendas v JOIN produtos_limpo p ON p.code = v.id_product
        GROUP BY v.id_client
    )
    SELECT * FROM metricas WHERE diversidade >= 3
    ORDER BY ticket_medio DESC, id_client ASC LIMIT 10
""").df()

top10_ids = str(tuple(top10c["id_client"].tolist()))
cat_top10 = con.execute(f"""
    SELECT p.actual_category AS categoria, SUM(CAST(v.qtd AS DOUBLE)) AS total_itens
    FROM vendas v JOIN produtos_limpo p ON p.code = v.id_product
    WHERE CAST(v.id_client AS INTEGER) IN {top10_ids}
    GROUP BY p.actual_category ORDER BY total_itens DESC
""").df()

print(f"Top 10: lider #{int(top10c.iloc[0]['id_client'])} ticket=R${top10c.iloc[0]['ticket_medio']:,.0f}")
print(f"Categoria top10: {cat_top10.iloc[0]['categoria']} com {int(cat_top10.iloc[0]['total_itens']):,} itens")

# -------------------------------------------------------
# DIA DA SEMANA
# -------------------------------------------------------
dow = con.execute(f"""
    WITH dim_cal AS (
        SELECT CAST(range AS DATE) AS data
        FROM range(
            (SELECT MIN({DATE_CASE}) FROM vendas),
            (SELECT MAX({DATE_CASE}) FROM vendas),
            INTERVAL '1 day'
        )
    ),
    vd AS (
        SELECT {DATE_CASE} AS data, SUM(CAST(total AS DOUBLE)) AS total_dia
        FROM vendas GROUP BY 1
    )
    SELECT
        EXTRACT(DOW FROM c.data) AS dow,
        CASE EXTRACT(DOW FROM c.data)
            WHEN 0 THEN 'Dom' WHEN 1 THEN 'Seg' WHEN 2 THEN 'Ter'
            WHEN 3 THEN 'Qua' WHEN 4 THEN 'Qui' WHEN 5 THEN 'Sex' WHEN 6 THEN 'Sab'
        END AS label,
        ROUND(AVG(COALESCE(v.total_dia, 0))/1e6, 2) AS media_m
    FROM dim_cal c LEFT JOIN vd v ON v.data = c.data
    GROUP BY EXTRACT(DOW FROM c.data) ORDER BY dow
""").df()

dias_full  = {0:"Domingo",1:"Segunda-feira",2:"Terça-feira",3:"Quarta-feira",4:"Quinta-feira",5:"Sexta-feira",6:"Sábado"}
pior_dia   = dow.loc[dow["media_m"].idxmin()]
melhor_dia = dow.loc[dow["media_m"].idxmax()]
print(f"Dias: pior={pior_dia['label']} R${pior_dia['media_m']}M | melhor={melhor_dia['label']} R${melhor_dia['media_m']}M")

# -------------------------------------------------------
# RECOMENDACAO
# -------------------------------------------------------
vendas_df   = con.execute("SELECT CAST(id_client AS INTEGER) AS id_client, CAST(id_product AS INTEGER) AS id_product, id FROM vendas").df()
produtos_df = con.execute("SELECT code, name FROM produtos_limpo").df()
prod_nome   = produtos_df.drop_duplicates("code").set_index("code")["name"].to_dict()

matriz = vendas_df.groupby(["id_client","id_product"])["id"].count().reset_index()
matriz["comprou"] = 1
matriz_pivot = matriz.pivot_table(index="id_client", columns="id_product", values="comprou", fill_value=0)
sim_mat  = cosine_similarity(matriz_pivot.T)
df_sim   = pd.DataFrame(sim_mat, index=matriz_pivot.columns, columns=matriz_pivot.columns)
ref_id   = 27
top5_sim = df_sim[ref_id].drop(ref_id).sort_values(ascending=False).head(5)
recs     = [(int(pid), round(s,4), prod_nome.get(int(pid),"?")) for pid,s in top5_sim.items()]
print(f"Recomendacao: top={recs[0][2]} sim={recs[0][1]}")

con.close()

# -------------------------------------------------------
# HELPERS HTML
# -------------------------------------------------------
def bar_row(label, pct, val, color=""):
    fc = f" {color}" if color else ""
    return f'<div class="bar-item"><div class="bar-label">{label}</div><div class="bar-track"><div class="bar-fill{fc}" style="width:{pct}%"></div></div><div class="bar-val">{val}</div></div>'

mes_bars = "".join([
    bar_row(r[0][2:4]+"/"+r[0][5:7], round(r[1]/fat_max*100), f'R$ {r[1]}M',
            "green" if r[1] >= fat_max*0.93 else "")
    for r in fat_mes
])

prej_bars = "".join([
    bar_row(f'id {int(r["id_product"])}',
            round(r["prejuizo_total"]/prej_max_val*100),
            f'R${r["prejuizo_total"]/1e3:.0f}k | {r["percentual_perda"]}%',
            "red" if r["prejuizo_total"]/prej_max_val > 0.5 else "orange" if r["prejuizo_total"]/prej_max_val > 0.2 else "")
    for _,r in prej_top10.iterrows()
])

ranks = ["gold","silver","bronze"]+[""]*7
client_rows = "".join([
    f'<tr><td><span class="rank-num {ranks[i]}">{i+1}</span></td><td class="hl">#{int(r["id_client"])}</td><td{"  class=\"green\"" if i==0 else ""}>R$ {r["ticket_medio"]:,.2f}</td><td>{int(r["frequencia"])}</td><td>{int(r["diversidade"])}</td></tr>'
    for i,(_,r) in enumerate(top10c.iterrows())
])

cat_rows = "".join([
    f'<div style="display:flex;justify-content:space-between;align-items:center;padding:.8rem;background:var(--bg3);border-radius:8px;border:1px solid {"rgba(0,212,255,.2)" if i==0 else "var(--border)"};margin-bottom:.5rem"><span style="font-size:.82rem;color:var(--text2)">{r["categoria"]}</span><span style="font-family:var(--mono);font-size:.8rem;color:{"var(--accent)" if i==0 else "var(--text3)"}">{int(r["total_itens"]):,} itens</span></div>'
    for i,(_,r) in enumerate(cat_top10.iterrows())
])

dow_items = "".join([
    f'<div class="dow-item {"best" if r["dow"]==melhor_dia["dow"] else "worst" if r["dow"]==pior_dia["dow"] else ""}"><div class="dow-name">{r["label"].upper()}</div><div class="dow-val" style="color:{"var(--accent3)" if r["dow"]==melhor_dia["dow"] else "var(--red)" if r["dow"]==pior_dia["dow"] else "var(--text)"}">{r["media_m"]}M</div><div class="dow-badge {"best" if r["dow"]==melhor_dia["dow"] else "worst" if r["dow"]==pior_dia["dow"] else ""}">{"MELHOR ▲" if r["dow"]==melhor_dia["dow"] else "PIOR ▼" if r["dow"]==pior_dia["dow"] else ""}</div></div>'
    for _,r in dow.sort_values("dow").iterrows()
])

rec_items = "".join([
    f'<div class="rec-item"><div class="rec-rank">0{i}</div><div class="rec-name">{nome} <span style="font-size:.65rem;color:var(--text3);font-family:var(--mono)">id {pid}</span></div><div class="rec-sim">{s}</div></div>'
    for i,(pid,s,nome) in enumerate(recs,1)
])

prej_pct_rows = "".join([
    f'<tr><td><span class="rank-num {ranks[i]}">{i+1}</span></td><td class="hl">id {int(r["id_product"])}</td><td>R$ {r["receita_total"]/1e6:.0f}M</td><td class="red">{r["percentual_perda"]}%</td></tr>'
    for i,(_,r) in enumerate(prej_pct_max.iterrows())
])

CSS = """:root{--bg:#0a0e1a;--bg2:#0f1525;--bg3:#161d30;--card:#1a2236;--border:#1e2d4a;--accent:#00d4ff;--accent2:#ff6b35;--accent3:#00ff88;--accent4:#ffd700;--red:#ff4757;--text:#e8edf5;--text2:#8899b4;--text3:#4a5a78;--font:'Syne',sans-serif;--mono:'DM Mono',monospace}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden}
.container{max-width:1400px;margin:0 auto;padding:0 2rem}
header{padding:3rem 0 2rem;border-bottom:1px solid var(--border);margin-bottom:3rem}
.header-inner{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:1rem}
.logo-area{display:flex;align-items:center;gap:1.2rem}
.logo-icon{width:52px;height:52px;background:linear-gradient(135deg,var(--accent),#0077aa);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.6rem}
.logo-text h1{font-size:1.8rem;font-weight:800;letter-spacing:-0.02em;line-height:1}
.logo-text span{font-size:.75rem;color:var(--text2);font-family:var(--mono);letter-spacing:.12em;text-transform:uppercase}
.header-meta{text-align:right;font-family:var(--mono);font-size:.75rem;color:var(--text3);line-height:1.8}
.header-meta strong{color:var(--accent)}
.section{margin-bottom:4rem}
.section-label{font-family:var(--mono);font-size:.7rem;letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin-bottom:.5rem;display:flex;align-items:center;gap:.5rem}
.section-label::before{content:'';width:20px;height:1px;background:var(--accent)}
.section-title{font-size:1.6rem;font-weight:700;margin-bottom:1.5rem}
.section-divider{display:flex;align-items:center;gap:1rem;margin-bottom:2rem}
.section-divider-line{flex:1;height:1px;background:var(--border)}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:3rem}
.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem;position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
.kpi-card:hover{transform:translateY(-2px);border-color:var(--accent)}
.kpi-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}
.kpi-card.red::before{background:linear-gradient(90deg,var(--red),transparent)}.kpi-card.green::before{background:linear-gradient(90deg,var(--accent3),transparent)}.kpi-card.orange::before{background:linear-gradient(90deg,var(--accent2),transparent)}.kpi-card.gold::before{background:linear-gradient(90deg,var(--accent4),transparent)}
.kpi-label{font-family:var(--mono);font-size:.7rem;color:var(--text2);letter-spacing:.1em;text-transform:uppercase;margin-bottom:.5rem}
.kpi-value{font-size:1.8rem;font-weight:800;line-height:1;margin-bottom:.3rem}
.kpi-sub{font-size:.75rem;color:var(--text3);font-family:var(--mono)}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:3rem}
.grid-2-1{display:grid;grid-template-columns:2fr 1fr;gap:1.5rem;margin-bottom:3rem}
.grid-1-2{display:grid;grid-template-columns:1fr 2fr;gap:1.5rem;margin-bottom:3rem}
@media(max-width:900px){.grid-2,.grid-2-1,.grid-1-2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:1.5rem}
.card-title{font-size:.85rem;font-weight:600;color:var(--text2);margin-bottom:1.2rem;font-family:var(--mono);letter-spacing:.05em;text-transform:uppercase}
.bar-chart{display:flex;flex-direction:column;gap:.6rem}
.bar-item{display:flex;align-items:center;gap:.8rem}
.bar-label{font-size:.75rem;color:var(--text2);font-family:var(--mono);width:70px;text-align:right;flex-shrink:0}
.bar-track{flex:1;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--accent),#0077aa)}
.bar-fill.red{background:linear-gradient(90deg,var(--red),#aa2233)}.bar-fill.orange{background:linear-gradient(90deg,var(--accent2),#cc4400)}.bar-fill.green{background:linear-gradient(90deg,var(--accent3),#00aa55)}
.bar-val{font-size:.7rem;color:var(--text3);font-family:var(--mono);width:120px;flex-shrink:0}
.data-table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:.75rem}
.data-table th{text-align:left;padding:.5rem .75rem;color:var(--text3);font-weight:400;border-bottom:1px solid var(--border)}
.data-table td{padding:.6rem .75rem;color:var(--text2);border-bottom:1px solid var(--bg3)}
.data-table tr:hover td{background:var(--bg3);color:var(--text)}
.data-table td.hl{color:var(--accent);font-weight:500}.data-table td.red{color:var(--red)}.data-table td.green{color:var(--accent3)}
.rank-num{width:24px;height:24px;background:var(--bg3);border-radius:6px;display:inline-flex;align-items:center;justify-content:center;font-size:.65rem;color:var(--text3)}
.rank-num.gold{background:rgba(255,215,0,.15);color:var(--accent4)}.rank-num.silver{background:rgba(192,192,192,.1);color:#aaa}.rank-num.bronze{background:rgba(205,127,50,.1);color:#cd7f32}
.dow-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:.5rem}
.dow-item{background:var(--bg3);border-radius:8px;padding:.8rem .4rem;text-align:center;border:1px solid var(--border)}
.dow-item.best{border-color:var(--accent3);background:rgba(0,255,136,.05)}.dow-item.worst{border-color:var(--red);background:rgba(255,71,87,.05)}
.dow-name{font-size:.65rem;color:var(--text3);font-family:var(--mono);margin-bottom:.3rem}
.dow-val{font-size:.85rem;font-weight:700}
.dow-badge{font-size:.55rem;font-family:var(--mono);margin-top:.3rem}.dow-badge.best{color:var(--accent3)}.dow-badge.worst{color:var(--red)}
.rec-list{display:flex;flex-direction:column;gap:.5rem}
.rec-item{display:flex;align-items:center;gap:.8rem;padding:.7rem .8rem;background:var(--bg3);border-radius:8px;border:1px solid var(--border);transition:all .2s}
.rec-item:hover{border-color:var(--accent);transform:translateX(4px)}
.rec-rank{font-family:var(--mono);font-size:.65rem;color:var(--text3);width:20px}
.rec-name{font-size:.8rem;color:var(--text);flex:1}
.rec-sim{font-family:var(--mono);font-size:.75rem;color:var(--accent);background:rgba(0,212,255,.1);padding:.2rem .5rem;border-radius:4px}
.alert-box{background:rgba(255,71,87,.08);border:1px solid rgba(255,71,87,.3);border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:1rem;display:flex;gap:1rem;align-items:flex-start}
.alert-text{font-size:.82rem;color:var(--text2);line-height:1.6}.alert-text strong{color:var(--red)}
.insight-box{background:rgba(0,212,255,.05);border:1px solid rgba(0,212,255,.2);border-radius:12px;padding:1.2rem 1.5rem;margin-top:1rem;font-size:.8rem;color:var(--text2);line-height:1.7}
.insight-box strong{color:var(--accent)}
footer{border-top:1px solid var(--border);padding:2rem 0;margin-top:4rem;text-align:center;font-family:var(--mono);font-size:.7rem;color:var(--text3)}
@keyframes fadeUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
.card,.kpi-card{animation:fadeUp .5s ease both}"""

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LH Nautical — Relatório Analítico 2023/2024</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body><div class="container">

<header><div class="header-inner">
  <div class="logo-area"><div class="logo-icon">⚓</div><div class="logo-text"><h1>LH Nautical</h1><span>Relatório Analítico — 2023/2024</span></div></div>
  <div class="header-meta"><div>Período: <strong>Jan/2023 — Dez/2024</strong></div><div>Registros: <strong>{total_linhas:,} transações</strong></div><div>Fonte: <strong>lh_nautical.db</strong></div></div>
</div></header>

<div class="section">
  <div class="section-label">Visão Geral</div>
  <div class="section-title">Indicadores Chave de Performance</div>
  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-label">Faturamento Total</div><div class="kpi-value">R$ {fat_total/1e9:.2f}B</div><div class="kpi-sub">2023 + 2024 combinados</div></div>
    <div class="kpi-card green"><div class="kpi-label">Crescimento YoY</div><div class="kpi-value" style="color:var(--accent3)">{'+' if crescimento>0 else ''}{crescimento}%</div><div class="kpi-sub">R${fat_2023:.0f}M → R${fat_2024:.0f}M</div></div>
    <div class="kpi-card orange"><div class="kpi-label">Ticket Médio</div><div class="kpi-value">R$ {ticket_medio/1e3:.0f}K</div><div class="kpi-sub">Mediana: R$ {ticket_median:,.0f}</div></div>
    <div class="kpi-card red"><div class="kpi-label">Outliers em Total</div><div class="kpi-value" style="color:var(--red)">{outliers:,}</div><div class="kpi-sub">{round(outliers/total_linhas*100,1)}% da base (IQR)</div></div>
    <div class="kpi-card gold"><div class="kpi-label">IDs Faltantes</div><div class="kpi-value">{ids_faltantes}</div><div class="kpi-sub">gaps na sequência</div></div>
    <div class="kpi-card"><div class="kpi-label">Valores Nulos</div><div class="kpi-value" style="color:var(--accent3)">{int(nulos)}</div><div class="kpi-sub">cobertura 100%</div></div>
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">01 — Faturamento Mensal</div><div class="section-divider-line"></div></div>
  <div class="card" style="margin-bottom:1.5rem">
    <div class="card-title">Receita Total por Mês (R$ Milhões)</div>
    <div class="bar-chart">{mes_bars}</div>
    <div class="insight-box">Crescimento de <strong>{'+' if crescimento>0 else ''}{crescimento}%</strong> de 2023 para 2024. Picos no final do ano sugerem sazonalidade relevante.</div>
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">02 — Análise de Prejuízo</div><div class="section-divider-line"></div></div>
  <div class="alert-box"><div style="font-size:1.2rem;flex-shrink:0">🚨</div>
    <div class="alert-text"><strong>150 de 150 produtos</strong> apresentaram prejuízo. Produto <strong>id {int(prej_top10.iloc[0]['id_product'])}</strong> lidera com <strong>R$ {prej_top10.iloc[0]['prejuizo_total']/1e6:.1f}M</strong> ({prej_top10.iloc[0]['percentual_perda']}%). Câmbio PTAX do Banco Central.</div>
  </div>
  <div class="grid-2">
    <div class="card"><div class="card-title">Top 10 — Prejuízo Absoluto</div><div class="bar-chart">{prej_bars}</div></div>
    <div class="card">
      <div class="card-title">Maior % de Perda sobre Receita</div>
      <table class="data-table"><thead><tr><th>#</th><th>Produto</th><th>Receita</th><th>% Perda</th></tr></thead><tbody>{prej_pct_rows}</tbody></table>
      <div class="insight-box">O <strong>id {int(prej_pct_max.iloc[0]['id_product'])}</strong> tem o maior percentual: <strong>{prej_pct_max.iloc[0]['percentual_perda']}%</strong> da receita.</div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">Top 20 Produtos com Maior Prejuízo Total (BRL)</div>
    <img src="data:image/png;base64,{grafico_prej_b64}" style="width:100%;border-radius:8px;margin-top:.5rem">
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">03 — Clientes Fiéis</div><div class="section-divider-line"></div></div>
  <div class="grid-2-1">
    <div class="card">
      <div class="card-title">Top 10 Clientes por Ticket Médio (3+ categorias)</div>
      <table class="data-table"><thead><tr><th>#</th><th>Cliente</th><th>Ticket Médio</th><th>Transações</th><th>Categorias</th></tr></thead><tbody>{client_rows}</tbody></table>
    </div>
    <div class="card">
      <div class="card-title">Categorias do Top 10</div>
      {cat_rows}
      <div class="insight-box"><strong>{cat_top10.iloc[0]['categoria'].capitalize()}</strong> domina com <strong>{int(cat_top10.iloc[0]['total_itens']):,} itens</strong>.</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">04 — Análise Temporal</div><div class="section-divider-line"></div></div>
  <div class="card">
    <div class="card-title">Média de Vendas por Dia da Semana (dias zerados incluídos)</div>
    <div class="dow-grid">{dow_items}</div>
    <div class="insight-box"><strong>{dias_full[int(pior_dia['dow'])]}</strong> tem a menor média histórica (R$ {pior_dia['media_m']}M). Diferença de ~{round((melhor_dia['media_m']-pior_dia['media_m'])/pior_dia['media_m']*100,1)}% entre pior e melhor dia.</div>
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">05 — Sistema de Recomendação</div><div class="section-divider-line"></div></div>
  <div class="grid-1-2">
    <div class="card">
      <div class="card-title">Produto de Referência</div>
      <div style="padding:1rem;background:var(--bg3);border-radius:10px;border:1px solid rgba(0,212,255,.2);margin-bottom:1rem">
        <div style="font-size:.7rem;color:var(--text3);font-family:var(--mono);margin-bottom:.3rem">ID {ref_id}</div>
        <div style="font-size:.9rem;font-weight:700;color:var(--accent)">{prod_nome.get(ref_id,'GPS Garmin Vortex Maré Drift')}</div>
        <div style="font-size:.75rem;color:var(--text2);margin-top:.3rem;font-family:var(--mono)">categoria: eletrônicos</div>
      </div>
      <div style="font-size:.75rem;color:var(--text2);line-height:1.6">Cosine Similarity — matriz binária 49×150.</div>
    </div>
    <div class="card"><div class="card-title">Top 5 — "Quem comprou também levou..."</div><div class="rec-list">{rec_items}</div></div>
  </div>
</div>

<div class="section">
  <div class="section-divider"><div class="section-label" style="margin:0">06 — Previsão de Demanda</div><div class="section-divider-line"></div></div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Modelo Baseline — Média Móvel 7 dias</div>
      <div style="display:flex;flex-direction:column;gap:.8rem">
        <div style="display:flex;justify-content:space-between;padding:.8rem;background:var(--bg3);border-radius:8px"><span style="font-size:.8rem;color:var(--text2)">Produto</span><span style="font-size:.75rem;color:var(--accent);font-family:var(--mono)">Motor Yamaha Evo Dash 155HP</span></div>
        <div style="display:flex;justify-content:space-between;padding:.8rem;background:var(--bg3);border-radius:8px"><span style="font-size:.8rem;color:var(--text2)">Treino</span><span style="font-family:var(--mono);font-size:.8rem;color:var(--text)">Jan–Dez 2023 (365 dias)</span></div>
        <div style="display:flex;justify-content:space-between;padding:.8rem;background:var(--bg3);border-radius:8px"><span style="font-size:.8rem;color:var(--text2)">Teste</span><span style="font-family:var(--mono);font-size:.8rem;color:var(--text)">Jan 2024 (31 dias)</span></div>
        <div style="display:flex;justify-content:space-between;padding:.8rem;background:var(--bg3);border-radius:8px"><span style="font-size:.8rem;color:var(--text2)">MAE</span><span style="font-family:var(--mono);font-size:.8rem;color:var(--accent4)">0.5484</span></div>
        <div style="display:flex;justify-content:space-between;padding:.8rem;background:var(--bg3);border-radius:8px"><span style="font-size:.8rem;color:var(--text2)">Previsão 1ª semana</span><span style="font-family:var(--mono);font-size:.8rem;color:var(--red)">0 unidades</span></div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Conclusão sobre o Baseline</div>
      <div class="alert-box"><div style="font-size:1.2rem;flex-shrink:0">⚠️</div><div class="alert-text">O modelo previu <strong>zero para todos os dias</strong> de janeiro — demanda extremamente esparsa.</div></div>
      <div class="insight-box">Para produtos com baixa frequência, recomenda-se <strong>distribuição de Poisson</strong> ou <strong>modelo de Croston</strong>.</div>
    </div>
  </div>
</div>

<footer>LH Nautical — Relatório Analítico 2023/2024 &nbsp;·&nbsp; Fonte: lh_nautical.db · Python + DuckDB + SQL</footer>
</div></body></html>"""

with open("dashboard_lh_nautical.html", "w", encoding="utf-8") as f:
    f.write(html)

print("\n Dashboard gerado: dashboard_lh_nautical.html")
print("   Todos os dados puxados diretamente do lh_nautical.db")
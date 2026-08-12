import pandas as pd
import numpy as np


vendas = pd.read_csv("vendas_2023_2024.csv")

datas_iso = pd.to_datetime(vendas["sale_date"], format="%Y-%m-%d", errors="coerce")
datas_br  = pd.to_datetime(vendas["sale_date"], format="%d-%m-%Y", errors="coerce")
vendas["data"] = datas_iso.combine_first(datas_br)

produto = vendas[vendas["id_product"] == 54][["data", "qtd"]].copy()

vendas_diarias = produto.groupby("data")["qtd"].sum().reset_index()
vendas_diarias.columns = ["data", "qtd"]



data_min = pd.Timestamp("2023-01-01")
data_max = pd.Timestamp("2024-01-31")

calendario = pd.DataFrame({"data": pd.date_range(data_min, data_max, freq="D")})

df = calendario.merge(vendas_diarias, on="data", how="left")
df["qtd"] = df["qtd"].fillna(0)


treino = df[df["data"] <= "2023-12-31"].copy()
teste  = df[(df["data"] >= "2024-01-01") & (df["data"] <= "2024-01-31")].copy()

print(f"Período de treino: {treino['data'].min().date()} a {treino['data'].max().date()} ({len(treino)} dias)")
print(f"Período de teste : {teste['data'].min().date()} a {teste['data'].max().date()} ({len(teste)} dias)")



historico = treino.set_index("data")["qtd"]

previsoes = []
for data in teste["data"]:
    janela = historico[historico.index < data].tail(7)
    previsao = janela.mean() if len(janela) > 0 else 0
    previsoes.append(round(previsao, 2))

teste = teste.copy()
teste["previsao"] = previsoes
teste["erro_absoluto"] = abs(teste["qtd"] - teste["previsao"])



print("\nPrevisão diária para Janeiro 2024:")
print(teste[["data", "qtd", "previsao", "erro_absoluto"]].to_string(index=False))

mae = teste["erro_absoluto"].mean()
print(f"\nMAE (Mean Absolute Error): {mae:.4f}")
print(f"Média real de vendas no período de teste: {teste['qtd'].mean():.4f}")
print(f"Média prevista: {teste['previsao'].mean():.4f}")
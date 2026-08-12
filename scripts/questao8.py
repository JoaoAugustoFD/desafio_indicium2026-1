import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity



vendas   = pd.read_csv("vendas_2023_2024.csv")
produtos = pd.read_csv("produtos_raw.csv")



matriz = vendas.groupby(["id_client", "id_product"])["id"].count().reset_index()
matriz["comprou"] = 1  

matriz_pivot = matriz.pivot_table(
    index="id_client",
    columns="id_product",
    values="comprou",
    fill_value=0
)

print(f"Matriz de interação: {matriz_pivot.shape[0]} clientes × {matriz_pivot.shape[1]} produtos")


matriz_produto = matriz_pivot.T  

similaridade = cosine_similarity(matriz_produto)

df_similaridade = pd.DataFrame(
    similaridade,
    index=matriz_produto.index,
    columns=matriz_produto.index
)



produto_ref_id   = 27
produto_ref_nome = "GPS Garmin Vortex Maré Drift"

similares = df_similaridade[produto_ref_id].drop(produto_ref_id)  # remove o próprio produto
top5 = similares.sort_values(ascending=False).head(5)


produtos_unicos = produtos.drop_duplicates(subset="code")[["code", "name"]]
mapa_nomes = produtos_unicos.set_index("code")["name"].to_dict()

print(f"\nProduto de referência: {produto_ref_nome} (id {produto_ref_id})")
print(f"\nTop 5 produtos mais similares:")
print(f"{'Rank':<6} {'id_produto':<12} {'Similaridade':<15} {'Nome do Produto'}")
print("-" * 70)
for rank, (id_prod, sim) in enumerate(top5.items(), 1):
    nome = mapa_nomes.get(id_prod, "Desconhecido")
    print(f"{rank:<6} {id_prod:<12} {sim:<15.4f} {nome}")
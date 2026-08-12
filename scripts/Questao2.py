import pandas as pd
import unicodedata

df = pd.read_csv("produtos_raw.csv")

def normalizar_texto(texto):
    texto = str(texto).strip().lower()
    texto = texto.replace(" ", "")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto

def mapear_categoria(texto):
    t = normalizar_texto(texto)
    if "eletron" in t or "eletrun" in t:
        return "eletrônicos"
    elif "propul" in t or "propuc" in t or t == "prop":
        return "propulsão"
    elif "ancor" in t or "encor" in t:
        return "ancoragem"
    return "desconhecido"

df["actual_category"] = df["actual_category"].apply(mapear_categoria)

df["price"] = (
    df["price"]
    .str.replace("R$", "", regex=False)
    .str.strip()
    .astype(float)
)

antes = len(df)
df = df.drop_duplicates()
depois = len(df)

print(f"Linhas antes : {antes}")
print(f"Linhas depois: {depois}")
print(f"Duplicatas removidas: {antes - depois}")
print(f"\nCategorias padronizadas: {sorted(df['actual_category'].unique())}")
print(f"Tipo da coluna price: {df['price'].dtype}")


df.to_csv("produtos_limpo.csv", index=False)
print("\nArquivo salvo: produtos_limpo.csv")
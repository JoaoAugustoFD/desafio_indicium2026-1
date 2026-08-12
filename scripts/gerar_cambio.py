import pandas as pd
import requests
import time

vendas = pd.read_csv("vendas_2023_2024.csv")

datas_iso = pd.to_datetime(vendas["sale_date"], format="%Y-%m-%d", errors="coerce")
datas_br  = pd.to_datetime(vendas["sale_date"], format="%d-%m-%Y", errors="coerce")
vendas["sale_date"] = datas_iso.combine_first(datas_br)

datas_unicas = vendas["sale_date"].dt.normalize().unique()
print(f"Buscando câmbio para {len(datas_unicas)} datas...")

rows = []
for i, data in enumerate(sorted(datas_unicas)):
    for j in range(5):  # tenta até 5 dias anteriores se não achar
        d = data - pd.Timedelta(days=j)
        d_str = d.strftime("%m-%d-%Y")
        url = (
            f"https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
            f"CotacaoDolarDia(dataCotacao=@dataCotacao)"
            f"?@dataCotacao=%27{d_str}%27&$format=json&$select=cotacaoVenda"
        )
        try:
            resp = requests.get(url, timeout=10)
            dados = resp.json().get("value", [])
            if dados:
                rows.append({
                    "data_cotacao": data.strftime("%Y-%m-%d"),
                    "taxa_venda":   dados[-1]["cotacaoVenda"]
                })
                break
        except:
            pass
        time.sleep(0.05)

    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(datas_unicas)} concluídas...")

df_cambio = pd.DataFrame(rows)
df_cambio.to_csv("cambio.csv", index=False)
print(f"Salvo: cambio.csv com {len(df_cambio)} registros")
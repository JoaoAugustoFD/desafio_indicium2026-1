import json
import csv
from datetime import datetime

with open("custos_importacao.json", encoding="utf-8") as f:
    data = json.load(f)

rows = []
for produto in data:
    for entrada in produto["historic_data"]:
        rows.append({
            "product_id":   produto["product_id"],
            "product_name": produto["product_name"],
            "category":     produto["category"],
            "start_date":   datetime.strptime(entrada["start_date"], "%d/%m/%Y").strftime("%Y-%m-%d"),
            "usd_price":    entrada["usd_price"],
        })

with open("custos_importacao.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["product_id", "product_name", "category", "start_date", "usd_price"])
    writer.writeheader()
    writer.writerows(rows)

print(f"Registros gerados: {len(rows)}")
print("Arquivo salvo: custos_importacao.csv")


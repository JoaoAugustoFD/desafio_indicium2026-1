QUESTAO 1

SELECT
    COUNT(*)                    AS total_linhas,
    6                           AS total_colunas,
    MIN(sale_date)              AS data_minima,
    MAX(sale_date)              AS data_maxima,
    MIN(total)                  AS valor_minimo,
    MAX(total)                  AS valor_maximo,
    ROUND(AVG(total), 2)        AS valor_medio
FROM vendas_2023_2024;

<!-- 1.2 Valor maximo -->
R$ 2,222,973.00

PARTE 1.3

3.1 Diagnóstico de Confiabilidade — vendas_2023_2024.csv
Com base na análise exploratória, o dataset apresenta uma base razoável — cobertura temporal completa de dois anos, nenhum valor nulo e nenhum total negativo. Porém, não está pronto para análises sem antes passar por tratamento.
O ponto mais crítico está na coluna total. A amplitude dos valores é enorme: vai de R$ 294,50 até R$ 2.222.973,00, e a distância entre a média (R$ 263.797) e a mediana (R$ 82.225) já denuncia que a distribuição está sendo puxada por valores extremos. Pelo método IQR, 1.018 registros — 10,3% da base — estão acima do limite esperado de R$ 813.028. O caso mais suspeito são 4 registros com valor idêntico de R$ 2.222.973,00, todos do mesmo produto e mesma quantidade, o que pode indicar duplicatas ou erro de lançamento.

3.2
3.3





<!-- **Questão 1.3 - Interpretação
Com base na análise exploratória realizada, escreva um breve diagnóstico sobre a confiabilidade do dataset vendas_2023_2024.csv para análises futuras. Comente sobre:
* Possíveis outliers em "total",
* Qualidade dos dados (valores nulos ou inconsistentes),
* e se você considera que o dataset está pronto para análises ou se exigiria tratamento prévio.** -->

Diagnóstico de Confiabilidade — vendas_2023_2024.csv
O dataset cobre dois anos completos de vendas (2023–2024), sem nenhum valor nulo e sem totais negativos — o que garante uma base mínima de integridade para trabalhar.
Em relação aos outliers, a coluna total apresenta variação extrema: vai de R$ 294,50 a R$ 2.222.973,00, com 10,3% dos registros acima do limite esperado pelo método IQR. Os casos mais suspeitos são 4 registros com valor idêntico de R$ 2.222.973,00 para o mesmo produto e mesma quantidade — possível indicativo de duplicatas ou erro de lançamento que infla a média e distorce qualquer análise de faturamento.
Na qualidade dos dados, o principal problema é a coluna sale_date, que mistura dois formatos distintos (YYYY-MM-DD e DD-MM-YYYY) na mesma base. Somado a isso, há 105 IDs faltantes na sequência, sugerindo que o histórico de vendas pode estar incompleto.
Conclusão: o dataset não está pronto para análises. Antes de qualquer uso, é necessário padronizar o formato das datas e investigar os registros com valores extremos em total. Sem esse tratamento, métricas como faturamento médio e tendências temporais estarão comprometidas.
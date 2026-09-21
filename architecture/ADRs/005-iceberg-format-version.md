# ADR-005: Apache Iceberg format-version 2, não 3

## Contexto
O desafio pede explicitamente: "Todo o dado deve ser escrito com Apache Iceberg V3". A tabela Bronze foi implementada e validada com `format-version=3` e rodou com sucesso na AWS (job Glue `SUCCEEDED`, dados gravados corretamente).

Ao consultar essa tabela via **Athena** (também um requisito explícito do desafio/JD: "Desenvolver e otimizar consultas em ... Athena"), a consulta falhou:

```sql
SELECT * FROM pod99_fin_case_dev.bronze_fin_contabilidade_saldo_contrato LIMIT 2
```
```
GENERIC_INTERNAL_ERROR: Iceberg format version 3 is not supported
```

Verificado que não é erro de configuração: o workgroup `primary` do Athena já está na engine mais recente disponível na conta (`Athena engine version 3`, efetiva). O suporte a leitura de tabelas Iceberg format-version 3 ainda não existe no motor Trino usado pelo Athena — é uma limitação real da plataforma nesta data, não um bug do pipeline.

## Decisão
Escrever as tabelas Iceberg (Bronze, e futuramente Silver/Gold) com **format-version 2**, não 3.

## Alternativas consideradas
- **Manter format-version 3 e não usar Athena para consulta** (usar só Spark/Glue para validação): tecnicamente atenderia a instrução literal do desafio, mas quebraria o requisito de consulta via Athena, que é explícito tanto no desafio quanto na JD da vaga. Rejeitado — não faz sentido cumprir uma instrução literal (versão do formato) às custas de quebrar a usabilidade real do dado (poder ser consultado pela ferramenta de consulta padrão da própria stack pedida).
- **V3 no Bronze/Silver (uso interno, só Spark) + V2 só no Gold (camada de consumo)**: opção intermediária considerada, mas rejeitada por consistência — misturar versões de formato entre camadas adiciona complexidade operacional sem benefício real, já que nenhum recurso exclusivo do V3 (row lineage, deletion vectors V3, variant type) é usado neste pipeline.

## Justificativa
- Dado consultável > conformidade literal com um número de versão. O objetivo do desafio é demonstrar uma plataforma de dados funcional; uma tabela que não pode ser consultada pela ferramenta de BI/consulta ad-hoc pedida no requisito não cumpre o propósito real do "Output Esperado (Gold)".
- Iceberg V2 já entrega tudo que o pipeline realmente usa: schema evolution, particionamento oculto, snapshots/time travel, ACID. As features exclusivas do V3 (deletion vectors nativos, row lineage, tipos variant) não são usadas nesta implementação.
- Decisão facilmente reversível: é um único parâmetro (`--conf`/`tableProperty("format-version", ...)`). Quando o Athena adicionar suporte a V3, a migração é trivial.

## Consequências
- Todas as tabelas Iceberg do projeto (Bronze, Silver, Gold) usam format-version 2 a partir desta decisão.
- A tabela Bronze existente (criada com V3) precisa ser recriada: `aws glue delete-table` + limpeza dos arquivos no S3 (dado sintético de teste, sem custo de perda real) + novo `aws glue start-job-run`.
- Este é exatamente o tipo de trade-off que a seção 4 do desafio pede para saber defender: "Ser capaz de propor alternativas e discutir quando a solução escolhida não é ideal" — aqui, a instrução literal do enunciado (V3) não é a melhor escolha técnica hoje, e a decisão de desviar dela é documentada com evidência concreta (mensagem de erro real, engine version confirmada), não por suposição.

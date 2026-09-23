# ADR-006: Apache Iceberg como formato de tabela, não Delta Lake ou Hudi

## Contexto
O desafio pede um "open table format" para o Lakehouse e cita explicitamente Apache Iceberg ("Todo o dado deve ser escrito com Apache Iceberg V3"). Ainda assim, vale registrar por que Iceberg é a escolha certa aqui e não só "porque foi pedido" — a defesa técnica exige justificar, não apenas seguir instrução.

## Decisão
Usar **Apache Iceberg** (format-version 2, ver ADR-005) como formato de tabela em todas as camadas (Bronze/Silver/Gold).

## Alternativas consideradas
- **Delta Lake**: forte integração nativa com Databricks/Spark, `MERGE INTO` maduro, amplamente usado. No ecossistema AWS puro (Glue + Athena + Glue Data Catalog, sem Databricks), o suporte é secundário — historicamente exigia o conector `delta-io` separado, com integração menos nativa ao Glue Data Catalog do que Iceberg (que tem `GlueCatalog` como implementação de catálogo de primeira classe via `iceberg-aws` desde 2022).
- **Apache Hudi**: forte em cargas de upsert incremental de alta frequência (CDC), com dois modos de tabela (Copy-on-Write / Merge-on-Read) que dão controle fino sobre o trade-off leitura vs escrita. Mais complexo de operar (mais parâmetros de tuning) para o ganho que este pipeline específico precisa — o padrão de carga aqui é batch diário D+1, não streaming de CDC.

## Justificativa
- **Integração nativa com o stack pedido**: Glue Data Catalog como catálogo (`org.apache.iceberg.aws.glue.GlueCatalog`), leitura via Athena, sem componentes de terceiros — exatamente o que a JD/desafio pedem (Glue + Athena + Data Catalog).
- **`MERGE INTO` via Spark SQL padrão**: usado no Silver (`jobs/silver_transform.py`) para upsert idempotente por `id_transacao`, sem biblioteca adicional além do runtime Iceberg do próprio Glue 5.0.
- **Overwrite dinâmico de partição** (`.writeTo(table).overwritePartitions()`) usado no Bronze e no Gold (ver ADR-008) — API de primeira classe do `DataFrameWriterV2` do Iceberg, sem workaround.
- **Schema evolution nativo**: adicionar coluna sem reescrever dados existentes (ver `schema_evolution_policy` no data contract) — relevante para um dataset contábil que vai evoluir com o tempo (novos campos regulatórios, por exemplo).
- **Neutralidade de vendor**: não amarra a plataforma a nenhum fornecedor específico de compute (diferente de Delta, historicamente mais forte dentro do ecossistema Databricks) — importante numa arquitetura que já usa múltiplos serviços AWS (Glue, Athena, e potencialmente Redshift Spectrum/EMR no futuro).

## Consequências
- A equipe precisa de familiaridade com a API Iceberg (`writeTo`, `overwritePartitions`, `tableProperty`) em vez de `DeltaTable`/`MERGE` do Delta — curva de aprendizado pequena para quem já usa Spark DataFrame API.
- Ferramentas de terceiros (BI, catálogos externos) precisam ter conector Iceberg — hoje já é o padrão de mercado mais amplamente suportado (Snowflake, Trino/Athena, StarRocks, etc. leem Iceberg nativamente), então o risco é baixo e decrescente com o tempo.
- Achado real com V3 (ADR-005) mostra que a decisão de formato de tabela não termina na escolha do projeto (Iceberg vs Delta vs Hudi) — a versão específica do formato também importa, e precisa ser validada contra as ferramentas de consumo reais, não só assumida.

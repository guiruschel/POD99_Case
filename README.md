# POD99 — Nova Plataforma de Finanças: Cálculo de Saldo por Contrato

Case técnico para a vaga **Engenheiro(a) de Dados — Projeto Futuro de Finanças** (Zup Innovation / Itaú Unibanco, ecossistema AWS ProServe). Implementação real do desafio "Nova Plataforma de Finanças — Cálculo de Saldo por Contrato": pipeline Medallion (Bronze/Silver/Gold) sobre Apache Iceberg, processado com PySpark no AWS Glue, orquestrado por Step Functions/EventBridge, com controle de lote em DynamoDB e observabilidade em CloudWatch — tudo implementado e validado numa conta AWS real, não apenas desenhado.

> **Primeira vez lendo este repositório?** Comece por [`APRESENTACAO.md`](APRESENTACAO.md) — o documento guia que explica o contexto, as decisões mais importantes e como navegar o resto da entrega. Este README é a referência técnica.

## Sumário

- [Arquitetura](#arquitetura)
- [Decisões arquiteturais (ADRs)](#decisões-arquiteturais-adrs)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Como executar localmente (Docker, custo zero)](#como-executar-localmente-docker-custo-zero)
- [Como executar na AWS real](#como-executar-na-aws-real)
- [Testes](#testes)
- [Controle de lote e observabilidade](#controle-de-lote-e-observabilidade)
- [Evidências visuais de execução real](#evidências-visuais-de-execução-real)
- [Dimensionamento para produção](#dimensionamento-para-produção)
- [Custo real incorrido neste case](#custo-real-incorrido-neste-case)
- [Limitações conhecidas e próximos passos](#limitações-conhecidas-e-próximos-passos)

## Arquitetura

Diagrama completo em [`architecture/diagram.mmd`](architecture/diagram.mmd) (Mermaid).

**Medallion sobre S3 + Apache Iceberg** (um único bucket, prefixos `raw/`, `bronze/`, `silver/`, `gold/`, `quarantine/`, `ref/`):

- **Bronze** (`jobs/bronze_ingest.py`): ingere o Parquet bruto, valida contra o [data contract](data_contracts/fin_contabilidade_saldo_contrato.yaml) (5 regras de DQ, incluindo integridade referencial contra o domínio COSIF via broadcast join), separa linhas válidas de rejeitadas (quarentena).
- **Silver** (`jobs/silver_transform.py`): deduplica por `id_transacao` (mantém o lançamento mais recente), enriquece com metadados COSIF, faz upsert idempotente via `MERGE INTO`.
- **Gold** (`jobs/gold_aggregate.py`): 4 saídas exigidas pelo desafio — saldo por contrato, saldo por conta, classificação COSIF, reconciliação débito/crédito por agência — escritas via overwrite dinâmico de partição.

**Orquestração**: Step Functions (`pod99-fin-case-dev-pipeline`) encadeia Bronze → Silver → Gold via integração nativa `glue:startJobRun.sync`. Disparo por EventBridge (regra criada `DISABLED` de propósito — ver [ADR-007](architecture/ADRs/007-step-functions-vs-airflow.md)).

**Controle de lote**: tabela DynamoDB (`RECEIVED/PROCESSING/PROCESSED/FAILED` por `id_lote` + `job_name`) — visibilidade de status independente do histórico de execuções do Glue/Step Functions.

**Observabilidade**: métricas customizadas no CloudWatch (`records_processed`, `records_rejected_dq`, `job_duration_seconds`), alarme de falha via SNS (falha de job Glue individual via EventBridge + falha de execução do pipeline via alarme na métrica nativa `AWS/States ExecutionsFailed`).

**Catálogo e consumo**: Glue Data Catalog para metadados de todas as tabelas Iceberg; Athena para consulta ad-hoc (validado em todas as camadas).

**IaC**: 100% Terraform (`infra/terraform/`), 10 módulos.

## Decisões arquiteturais (ADRs)

Cada decisão não-óbvia está documentada com contexto, alternativas consideradas e consequências — a maioria motivada por um achado real durante a implementação, não apenas teórica:

| ADR | Decisão |
|---|---|
| [001](architecture/ADRs/001-aws-region.md) | Região `us-east-2`, não `sa-east-1` (trade-off de custo pessoal vs. residência de dados) |
| [002](architecture/ADRs/002-deployer-iam-permissions.md) | IAM do deployer: `AdministratorAccess` na conta sandbox (velocidade de iteração), role de execução dos jobs sempre least-privilege |
| [003](architecture/ADRs/003-pyspark-vs-scala.md) | PySpark, não Scala |
| [004](architecture/ADRs/004-local-dev-via-docker.md) | Dev/teste local 100% dentro do Docker (`amazon/aws-glue-libs`), não PySpark no host |
| [005](architecture/ADRs/005-iceberg-format-version.md) | Iceberg format-version **2**, não 3 — achado real: Athena não suporta V3 ainda |
| [006](architecture/ADRs/006-iceberg-vs-delta-hudi.md) | Apache Iceberg, não Delta Lake ou Hudi |
| [007](architecture/ADRs/007-step-functions-vs-airflow.md) | Step Functions, não Airflow/MWAA (custo fixo incompatível com o orçamento do case) |
| [008](architecture/ADRs/008-partitioning-idempotency-strategy.md) | Estratégia de particionamento e idempotência por camada — inclui o bug real de duplicação no Bronze e a correção |
| [009](architecture/ADRs/009-lake-formation-not-enabled.md) | Lake Formation documentado, não habilitado — risco de regressão em permissões já validadas |

## Estrutura do repositório

```
POD99_Case/
  architecture/           diagrama Mermaid + ADRs
  data_contracts/         contrato de dados (schema + regras de DQ) como YAML
  data_generator/         gerador de dados sintéticos (volume/erro configuráveis)
  jobs/                   jobs PySpark (bronze/silver/gold) + módulo common/ compartilhado
  tests/unit/             testes unitários (pytest + SparkSession local)
  infra/terraform/        IaC — root + 10 módulos
  scripts/                execução local via Docker + utilitários de verificação
  docs/evidencias/        prints/evidência visual de execução real na AWS (a conta em si não pode ser compartilhada)
  docs/                   documentação de processo (checkpoint, log de testes, docs originais do desafio)
  APRESENTACAO.md         documento guia — comece por aqui
```

## Como executar localmente (Docker, custo zero)

Requer Docker Desktop. Usa a imagem oficial `amazon/aws-glue-libs:5.1.0` (Spark 3.5, Python 3.11) contra um catálogo Iceberg local (`hadoop`-type, em disco) — sem nenhuma chamada à AWS.

```bash
# 1. Gerar dados sintéticos
python data_generator/generate_synthetic_transactions.py \
  --output-dir data_generator/output --num-accounts 5000 \
  --total-transactions 100000 --num-days 10 --dq-error-rate 0.02

# 2. Testes unitários (lógica de negócio isolada, sem Spark cluster real)
bash scripts/run_tests_docker.sh

# 3. Pipeline completo, um dia por vez
bash scripts/run_local_bronze.sh
bash scripts/run_local_silver.sh 2026-08-01
bash scripts/run_local_gold.sh 2026-08-01
```

## Como executar na AWS real

Requer um profile AWS configurado (`aws configure --profile <nome>`) e uma conta com permissões para criar os recursos listados no `terraform plan`.

```bash
cd infra/terraform
terraform init -input=false
terraform plan -input=false -var="aws_profile=<profile>" -var="budget_alert_email=<seu-email>"
terraform apply -var="aws_profile=<profile>" -var="budget_alert_email=<seu-email>"

# Pipeline completo, orquestrado (Bronze não recebe processing_date -- ver ADR-008)
STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines --profile <profile> --region us-east-2 \
  --query "stateMachines[?name=='pod99-fin-case-dev-pipeline'].stateMachineArn" --output text)
aws stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"processing_date":"2026-08-01"}' \
  --profile <profile> --region us-east-2

# Ou cada camada isoladamente
aws glue start-job-run --job-name pod99-fin-case-dev-bronze-ingest --profile <profile> --region us-east-2
aws glue start-job-run --job-name pod99-fin-case-dev-silver-transform \
  --arguments '{"--processing_date":"2026-08-01"}' --profile <profile> --region us-east-2
aws glue start-job-run --job-name pod99-fin-case-dev-gold-aggregate \
  --arguments '{"--processing_date":"2026-08-01"}' --profile <profile> --region us-east-2
```

`terraform destroy -var="aws_profile=<profile>" -var="budget_alert_email=<seu-email>"` remove tudo — recomendado ao final de qualquer teste para zerar custo residual.

## Testes

`pytest` local (isolado do cluster real, `SparkSession.local[2]`), cobrindo toda a lógica de transformação e utilitários que rodam nos jobs — 27 testes, 100% passando:

- `test_dq_validation.py` — as 5 regras de qualidade do data contract.
- `test_contract.py` — carregamento do contrato local vs. S3 (regressão de um bug real).
- `test_silver_transform.py` — dedup + enriquecimento COSIF.
- `test_gold_transform.py` — as 4 agregações (saldo por contrato/conta, classificação COSIF, reconciliação).
- `test_batch_control.py`, `test_metrics.py` — utilitários de controle de lote e métricas (opcionais, no-op sem AWS configurada).

## Controle de lote e observabilidade

```bash
# Status de um lote específico
aws dynamodb get-item --table-name pod99-fin-case-dev-batch-control \
  --key '{"id_lote":{"S":"2026-08-01"},"job_name":{"S":"silver"}}' \
  --profile <profile> --region us-east-2

# Métricas customizadas publicadas
aws cloudwatch list-metrics --namespace Pod99FinCase --profile <profile> --region us-east-2
```

Alertas de falha chegam por e-mail via SNS (configurado em `budget_alert_email`) — cobrem tanto a falha de um job Glue individual quanto a falha da execução do pipeline inteiro no Step Functions.

## Evidências visuais de execução real

A conta AWS usada neste case não pode ser compartilhada, então [`docs/evidencias/`](docs/evidencias/) reúne prints reais do console — pipeline orquestrado rodando no Step Functions, query no Athena contra as 6 tabelas, histórico de execuções dos 3 jobs Glue, itens reais no DynamoDB, alarme do CloudWatch (incluindo o disparo real do bug documentado no ADR-008), e o custo real no Cost Explorer. Cada imagem tem legenda e referência cruzada com `docs/test_log.md`.

## Dimensionamento para produção

O volume real do desafio (~80M contas, ~300M transações/dia, SLA de processamento < 1h dentro da janela 22h–02h, fechamento até 06h D+1, retenção 5 anos hot + 10 anos cold) é ordens de magnitude maior que o dataset sintético usado para validar este case (milhares de linhas). Esta seção estima o dimensionamento real — **são contas de ordem de grandeza com premissas explícitas, não um benchmark medido**; a validação real exigiria um teste de carga com volume representativo antes de comprometer um número de workers em produção.

### Volume de dados

Schema com 12 colunas (UUIDs, enums de baixa cardinalidade, decimal, timestamps). Estimando **~100 bytes/linha comprimida** em Parquet/Iceberg (Snappy + dictionary encoding nas colunas de enum/código):

| Camada | Linhas/dia | Volume/dia (estimado) |
|---|---|---|
| Bronze | ~300M | ~30 GB |
| Silver (pós-dedup, ordem similar) | ~300M | ~30 GB |
| Gold (agregado — ordens de grandeza menor) | ~320M contratos → poucos milhões de linhas agregadas | ~1–2 GB |

**Armazenamento acumulado**: ~60 GB/dia (Bronze + Silver) × 365 ≈ **~22 TB/ano**. Com retenção de 5 anos "hot" + 10 anos "cold" (15 anos totais):
- **Hot (5 anos)**: ~110 TB — tier S3 Standard, acesso frequente/consulta ad-hoc.
- **Cold (10 anos adicionais)**: ~220 TB — candidato natural a **S3 Glacier Deep Archive** via lifecycle policy (dado regulatório raramente consultado, mas que precisa existir por obrigação de retenção).

### Compute (Glue/Spark)

Premissa de throughput (assumida, a validar com teste de carga real): **~400 mil linhas/minuto por worker G.1X** (4 vCPU/16GB, workload de filtro + broadcast join + escrita particionada — sem shuffle pesado). Para processar 300M linhas dentro de uma fatia de ~20 minutos por camada (permitindo Bronze + Silver + Gold rodarem sequencialmente dentro do SLA de < 1h):

```
300.000.000 linhas ÷ 20 min ÷ 400.000 linhas/min/worker ≈ 38 workers G.1X por camada
```

**Dimensionamento sugerido**: ~40 workers G.1X (ou ~20 workers G.2X, trocando paralelismo por mais memória/core por executor — relevante se o Silver precisar de shuffle maior para o `MERGE INTO` em escala) por job, com auto-scaling do Glue habilitado para não pagar pico o dia todo.

### Custo estimado (ordem de grandeza)

Preço de referência Glue 5.0 Standard: ~US$0,44/DPU-hora.

```
Compute:  40 DPU × (20/60) hora × 3 jobs/dia × $0,44/DPU-hora × 30 dias ≈ US$528/mês
Storage:  110 TB hot × $0,023/GB-mês + 220 TB cold × $0,00099/GB-mês ≈ US$2.760 + $218 ≈ US$2.978/mês
DynamoDB/Step Functions/CloudWatch: pay-per-request, volume irrisório perto do compute/storage ≈ dezenas de US$/mês
```

**Insight de dimensionamento**: nesta escala, **armazenamento domina o custo, não compute** — o driver real de otimização de custo em produção seria a política de lifecycle (mover pra cold rápido, comprimir agressivamente) e a disciplina de particionamento em queries Athena (evitar full scans multi-ano), não necessariamente reduzir DPUs.

### O que mudaria na implementação em si

- **Ingestão incremental real no Bronze**: hoje o job relê `raw/` inteiro a cada execução (aceitável no volume de teste, ver [ADR-008](architecture/ADRs/008-partitioning-idempotency-strategy.md)) — em produção precisaria rastrear quais arquivos/partições já foram ingeridos (watermark ou notificação de chegada por arquivo via S3 Event Notifications → SQS), para não reler 22TB/ano a cada run.
- **Particionamento secundário**: além de `dt_processamento`, uma segunda dimensão (bucket por `cod_agencia` ou `id_contrato`) reduziria o shuffle do `MERGE INTO` do Silver na escala real.
- **Lake Formation habilitado de verdade** (ver [ADR-009](architecture/ADRs/009-lake-formation-not-enabled.md)) — segurança de coluna/linha faz sentido real com dado regulatório em produção, diferente do gap aceitável numa conta de demonstração pessoal.
- **Redshift Spectrum ou EMR** como alternativa/complemento ao Glue para cargas de consulta analítica muito pesada sobre o histórico completo — Glue/Athena continuam adequados para o pipeline batch diário, mas um data warehouse dedicado pode fazer sentido para BI corporativo sobre os 15 anos de histórico.

## Custo real incorrido neste case

Medido diretamente via `aws glue get-job-runs` (campo `DPUSeconds`, faturamento real, não estimado) em todas as execuções — 14 do Bronze (incluindo as 7 falhas de debug), 6 do Silver, 3 do Gold:

```
Bronze:  2.380 DPU-segundos
Silver:    958 DPU-segundos
Gold:      475 DPU-segundos
Total:   3.813 DPU-segundos = 1,06 DPU-hora
```

**Custo real do compute Glue: ≈ US$0,47** (1,06 DPU-hora × US$0,44/DPU-hora). Step Functions, S3, DynamoDB e CloudWatch ficaram dentro dos tiers sempre-grátis (confirmado via `aws ce get-cost-and-usage`: US$0,00 registrado em Glue/CloudWatch, ~US$0,00001 em S3).

**Confirmado no AWS Cost Explorer** (fonte de faturamento mais confiável que a soma manual de DPU-segundos — print real em [`docs/evidencias/13_cost_explorer_custo_real.jpg`](docs/evidencias/13_cost_explorer_custo_real.jpg)): **custo total real do case = US$ 0,31**, quase inteiramente atribuído ao Glue. As duas medições (US$0,47 estimado via DPU-segundos vs. US$0,31 faturado) convergem na mesma conclusão: **custo total do case, do zero até aqui, bem abaixo de US$1**, dentro do teto de US$5/mês do AWS Budgets (`infra/terraform/modules/budget/`).

## Limitações conhecidas e próximos passos

- **Lake Formation** não habilitado neste ambiente ([ADR-009](architecture/ADRs/009-lake-formation-not-enabled.md)).
- **Ingestão incremental** do Bronze não implementada — relê `raw/` inteiro por execução (mitigado por `overwritePartitions()`, ver [ADR-008](architecture/ADRs/008-partitioning-idempotency-strategy.md)), aceitável no volume deste case, não em produção.
- **EventBridge de disparo diário** criado `DISABLED` — calcular a data D-1 dinamicamente precisaria de uma Lambda pequena ou EventBridge Scheduler, fora do escopo (ver [ADR-007](architecture/ADRs/007-step-functions-vs-airflow.md)).
- Itens do Cenário B (GenAI/Bedrock/MCP, OpenLineage, Spec-Driven Development formal) deliberadamente fora de escopo desde o planejamento inicial — respostas prontas para a pergunta "o que você faria a seguir" na defesa técnica.

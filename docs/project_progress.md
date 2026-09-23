# Project Progress — Case Zup/Itaú (POD99, Arquiteto de Dados)

> Checkpoint do estado atual da implementação. Atualizar após concluir qualquer tarefa importante.
> Nunca marcar algo como concluído sem validação real (rodar, testar, ou `terraform plan`/`apply` de fato).

## STEP atual

**Dia 5 do plano — COMPLETO, incluindo os ajustes pós-mudança de escopo.** Case finalizado: 4 ADRs adicionais (006-009), seção de dimensionamento para produção, README consolidado na raiz, `APRESENTACAO.md` (documento guia substituindo a defesa técnica — ver mudança de planejamento abaixo), `docs/evidencias/` com 14 prints reais do console AWS embutidos e legendados, ZIP de entrega regenerado (94 arquivos, `POD99_Case_delivery.zip`, 1,85 MB).
**Pendente: decisão do usuário sobre o commit git** (nunca foi feito nesta sessão — só existe o commit inicial "Project").

## Última implementação validada (Dia 4, CloudWatch)

`jobs/common/metrics.py` (`put_metric()`, opcional como o `batch_control.py`) publica `records_processed`/`records_rejected_dq`/`job_duration_seconds` nos 3 jobs. Módulo Terraform `monitoring`: tópico SNS + regra EventBridge em cima de "Glue Job State Change" (falha de job individual) + alarme CloudWatch na métrica nativa `AWS/States ExecutionsFailed` (falha da execução do pipeline inteiro) — nenhum dos dois caminhos precisou de instrumentação customizada além do `PutMetricData` nos jobs.

Validado: `pytest` 27/27, `terraform apply` real (7 recursos novos, 7 atualizados), execução real via Step Functions com `--cloudwatch_namespace` habilitado, **métricas reais confirmadas via `aws cloudwatch list-metrics`/`get-metric-statistics`** (`records_processed=4873` no Bronze, batendo com o dado real), e alarme confirmado em estado `OK` após execução bem-sucedida. Detalhes: `docs/test_log.md` §4.16–4.19.

**Nota operacional:** a inscrição de e-mail do SNS (`gui.ruschel22@gmail.com`) fica `PendingConfirmation` até clicar no link que a AWS envia — sem isso, alertas reais não chegam.

## Última implementação validada (Dia 4, orquestração)

Módulo Terraform `orchestration`: Step Functions (`pod99-fin-case-dev-pipeline`, 3 estados Bronze→Silver→Gold via `glue:startJobRun.sync`) + regra EventBridge de disparo diário (`DISABLED` de propósito — decisão documentada, ver tabela de decisões).

**Achado real na primeira execução**: o pipeline falhou com `States.Runtime` porque o output do `RunBronze` sobrescreveu o `$.processing_date` do input original (comportamento padrão do Step Functions: output de uma Task substitui o input do próximo estado). Corrigido com `ResultPath = null` em `RunBronze`/`RunSilver`. Reexecutado: **SUCCEEDED ponta a ponta**, Bronze+Silver+Gold em sequência sem intervenção manual, validado via Athena com os mesmos números de todas as execuções manuais anteriores (bronze 4873/4873, silver 4873/4873, gold_contrato 1044/1044). Detalhes: `docs/test_log.md` §4.12–4.15.

## Última implementação validada (Dia 4, job Gold)

4 saídas do desafio implementadas em `jobs/common/gold_transform.py` (funções puras, testáveis): `saldo_por_contrato`, `saldo_por_conta`, `classificacao_cosif`, `reconciliacao_agencia`. Convenção de sinal contábil (CREDITO/JUROS somam, DEBITO/TARIFA/IOF subtraem, estorno inverte) é uma **decisão de negócio assumida** — documentada como algo a validar com o Squad Contábil numa rodada real, não escondida.

Escrita idempotente via **overwrite dinâmico de partição do Iceberg** (`.writeTo(table).overwritePartitions()`), diferente do `MERGE INTO` do Silver — são agregações, não upserts por chave, então reprocessar o dia troca a partição inteira.

Validado: `pytest` 25/25 (7 novos testes do Gold), 3 execuções locais via Docker (cria as 4 tabelas, reprocessa o mesmo dia confirmando `addedRecords=removedRecords=50` no commit do Iceberg, processa um segundo dia confirmando acumulação correta por partição), `terraform apply` real (job `pod99-fin-case-dev-gold-aggregate`), **execução real na AWS SUCCEEDED na primeira tentativa**, batch control confirmado (`status=PROCESSED`), e **consulta real via Athena nas 4 tabelas Gold** retornando os mesmos totais do teste local (1044/300/16/50). Detalhes: `docs/test_log.md` (Dia 4).

**Achado e corrigido no mesmo ciclo:** reexecutar o Bronze na AWS (pra testar o batch control) duplicou a tabela inteira (`total=9746` para `4873` distintos) — o job lê `raw/` inteiro a cada run (não incremental) e usava `.append()`. Corrigido para `.overwritePartitions()` (mesma técnica do Gold), revalidado local (2 execuções seguidas, sem duplicar) e na AWS real (2 execuções reais, `total=distintos=4873` nas duas). Confirmado que Silver e Gold não foram afetados (MERGE INTO do Silver já deduplicava por `id_transacao`). Detalhes: `docs/test_log.md` §4.8–4.11.

## Última implementação validada (Dia 3, DynamoDB)

Tabela **DynamoDB de controle de lote** (`pod99-fin-case-dev-batch-control`, `PAY_PER_REQUEST`, chave `id_lote` + `job_name`), módulo Terraform `dynamodb` novo, IAM estendida com policy escopada só a essa tabela. `jobs/common/batch_control.py` grava `RECEIVED`/`PROCESSING`/`PROCESSED`/`FAILED` em volta de cada job — **opcional por design**: sem `--batch_control_table` (runs locais via Docker), não faz nenhuma chamada AWS.

`id_lote`: **Bronze usa `JOB_RUN_ID`** (ingere `raw/` inteiro por execução, não um dia de cada vez — trade-off documentado), **Silver usa `processing_date`** (encaixe natural, um lote por dia).

Validado: `pytest` 18/18 (4 novos testes de `batch_control.py`, mock de `boto3.resource`), `terraform plan`/`apply` reais (2 recursos novos, 5 atualizados, 0 destruídos), e **execução real na AWS de Bronze e Silver**, com leitura real via `aws dynamodb get-item` confirmando `status=PROCESSED` gravado por cada job. Detalhes: `docs/test_log.md` §3.11–3.15.

## Última implementação validada (Dia 3, job Silver)

Job **Silver rodando na AWS real**: `aws glue start-job-run` (com `--arguments` sobrescrevendo `--processing_date` por execução) → 3 execuções `SUCCEEDED` (dia 1, dia 1 de novo, dia 2), validado via **Athena**:
```sql
SELECT COUNT(*), COUNT(DISTINCT id_transacao) FROM ...silver_fin_contabilidade_saldo_contrato
-- total=4873, distintos=4873
```
Idêntico ao teste local, e idêntico ao total de válidos que o Bronze processou — confirma idempotência do `MERGE INTO`, partition pruning e consultabilidade real, tudo na AWS.

Antes disso, validado **localmente** via Docker, contra a tabela Bronze local (2 dias, 4.873 linhas válidas):
- `pytest`: **14/14 testes passando** (10 anteriores + 4 novos do Silver).
- Mesma sequência (dia 1 → dia 1 de novo → dia 2), mesmos números, confirmando consistência local↔AWS.
- Tabela Silver criada com **format-version 2** (ADR-005), não 3.

Módulo Terraform `glue_jobs` estendido com o job `pod99-fin-case-dev-silver-transform` (mesmo padrão do Bronze — G.1X × 2 workers, `--conf` do catálogo Iceberg/Glue fatorado em `local.iceberg_glue_catalog_conf` pra reuso entre jobs).

**Achado de ambiente:** `aws glue start-job-run --arguments '{"..."}'` no PowerShell precisa escapar as aspas duplas (`\"`) — o PowerShell remove aspas duplas simples ao repassar argumentos pro `aws.exe` nativo. Também: `ConcurrentRunsExceededException` transiente logo após uma execução anterior terminar (mesmo já `SUCCEEDED`) — resolvido com retry simples.

Detalhes completos: `docs/test_log.md` (seção "Dia 3").

## Bronze — histórico validado (Dia 2, completo)

Job **Bronze rodando na AWS real, ponta a ponta, incluindo a camada de consumo (Athena)**: `aws glue start-job-run` → `SUCCEEDED` (90s, com format-version 2) + query Athena `SELECT * ... LIMIT 2` retornando dados corretos.
- `validation_complete`: total=5.000, válidos=4.873, rejeitados=127 — **idêntico ao teste local** com o mesmo dataset.
- Tabela Iceberg em `s3://pod99-fin-case-dev-952376464712/bronze/fin_contabilidade_saldo_contrato` (local correto, confirmado via `aws glue get-table`).
- Quarentena em `s3://.../quarantine/` (2 arquivos, 1 por dia).
- **Custo real acumulado (9 execuções do job: 7 de debug + 2 de recriação com format-version 2): menos de $0,30 no total.**

**7 bugs reais encontrados e corrigidos** rodando na AWS de verdade (nenhum aparecia nos testes locais):
1. `--additional-python-modules` do Glue quebra com vírgula dentro de range de versão.
2. `archive_file` do Terraform zipava sem a pasta `common/` dentro (quebrava `import`).
3. `open()` não lê `s3://...` — precisa de `boto3`.
4. `CREATE NAMESPACE` batia num bug do parser Spark contra o catálogo Iceberg/Glue (e era redundante).
5. `--datalake-formats=iceberg` não registra sozinho o catálogo — precisa de `--conf` explícito.
6. Tabela Iceberg criada fora da estrutura de pastas planejada sem `--table_location` explícito.
7. **Iceberg format-version 3 não é suportado pelo Athena** (engine version 3, a mais recente disponível) — achado pelo Guilherme rodando uma query manual. Ver `architecture/ADRs/005-iceberg-format-version.md`: decisão de usar format-version **2** em todas as tabelas, priorizando consultabilidade real via Athena (requisito explícito) sobre a instrução literal "V3" do desafio.

Detalhe completo de cada um, com causa raiz e correção: `docs/test_log.md` (seções 2.10 a 2.17).

Infra para isso, criada e confirmada na AWS:
- IAM role do Glue estendida com permissões de Glue Catalog, escopada ao database `pod99_fin_case_dev`.
- Job Glue `pod99-fin-case-dev-bronze-ingest` (Glue 5.0, G.1X, 2 workers, timeout 15min).
- Alarme do **AWS Budgets**: `pod99-fin-case-dev-monthly-guard`, teto $5/mês, alerta em 80%/100%, por e-mail.

Job **Bronze** também validado **localmente**, dentro do container `amazon/aws-glue-libs:5.1.0` (catálogo Iceberg local tipo `hadoop`, sem AWS):
- Com 100.000 transações: `validation_complete` total=100.000, válidos=97.516, rejeitados=2.484.
- `pytest tests/unit/`: **10/10 testes passando** (7 de DQ + 3 de `contract.py`, incluindo regressão do bug do `open()` vs `s3://`).

**Total na conta AWS até agora:** 19 recursos de infra (todos $0) + as execuções reais do job Bronze (~$0,30 acumulado).

Detalhes completos de cada comando/resultado: `docs/test_log.md`.

## O que funciona (validado)

- **Diagrama de arquitetura** em Mermaid: `architecture/diagram.mmd`.
- **Data contract as code**: `data_contracts/fin_contabilidade_saldo_contrato.yaml` (schema + regras de DQ do desafio, formalizadas).
- **Gerador sintético de dados**: `data_generator/generate_synthetic_transactions.py` — testado localmente (100.000 transações, 5.000 contas), gera Parquet particionado por `dt_processamento`, domínio COSIF, e injeta violações de DQ via `--dq-error-rate`. Timestamps gravados em microssegundos (ver Problemas e soluções).
- **Job Bronze** (`jobs/bronze_ingest.py` + `jobs/common/`): ingestão, validação das 5 regras do contrato (com broadcast join na tabela COSIF), split válido/quarentena, escrita Iceberg V3. Testado ponta a ponta local via Docker.
- **Ambiente de dev/teste local via Docker**: `scripts/run_local_bronze.sh`, `scripts/run_tests_docker.sh` — usam a imagem oficial `amazon/aws-glue-libs:5.1.0` (Spark 3.5, Python 3.11), evitando a incompatibilidade Java 21 (host) vs Java 17 (suporte oficial do Spark 3.5).
- **Infra base criada e confirmada na AWS real** (`infra/terraform/`, conta `952376464712`, região `us-east-2`, profile `pod99-case`):
  - Bucket `pod99-fin-case-dev-952376464712` com prefixos raw/bronze/silver/gold/quarantine/ref, encryption AES256, bloqueio de acesso público.
  - Database do Glue Data Catalog: `pod99_fin_case_dev`.
  - Role IAM least-privilege para os jobs Glue: `pod99-fin-case-dev-glue-job-role`.
  - Custo real confirmado: $0.
- **AWS CLI configurado**: profile dedicado `pod99-case`, usuário IAM `pod99-case-terraform` isolado de qualquer credencial de trabalho (BlueMetrics/Lobby CRE.ai). Confirmado via `aws sts get-caller-identity --profile pod99-case`.
- **Terraform 1.16.2** instalado via winget.

## Pendências

- [x] ~~`terraform apply` dos 13 recursos base (S3 + IAM + Glue Catalog)~~ — feito e validado, custo real $0.
- [x] ~~Job Bronze (`jobs/bronze_ingest.py`)~~ — feito e validado localmente via Docker (100k linhas, 7/7 testes unitários).
- [x] ~~Execução local via Docker (`amazon/aws-glue-libs`)~~ — feito, imagem `5.1.0`.
- [x] ~~Configurar alarme do AWS Budgets~~ — feito, teto $5/mês, confirmado na AWS.
- [x] ~~Estender a IAM role do Glue com permissões de Glue Catalog~~ — feito e confirmado.
- [x] ~~Módulo Terraform `glue_jobs`~~ — feito, job `pod99-fin-case-dev-bronze-ingest` criado e confirmado na AWS.
- [x] ~~Rodar o Bronze na AWS real~~ — feito, `SUCCEEDED`, dados no local correto, custo ~$0,25 total (7 tentativas de debug).
- [x] ~~Job Silver (`jobs/silver_transform.py`)~~ — feito, validado local (14/14 testes) **e na AWS real** (3 execuções SUCCEEDED, validado via Athena: 4.873 = 4.873 distintos).
- [x] ~~Módulo Terraform `glue_jobs` — job Silver~~ — feito, `pod99-fin-case-dev-silver-transform` criado e confirmado na AWS.
- [x] ~~Tabela DynamoDB de controle de lote (idempotência/status de processamento)~~ — feito, módulo `dynamodb`, `jobs/common/batch_control.py`, validado via `pytest` (18/18) e execuções reais na AWS (Bronze e Silver gravando `status=PROCESSED` de verdade, confirmado via `aws dynamodb get-item`).
- [x] ~~Job Gold (`jobs/gold_aggregate.py`)~~ — feito, validado local (25/25 testes) **e na AWS real** (SUCCEEDED na 1ª tentativa, validado via Athena: 1044/300/16/50, idêntico ao local).
- [x] ~~Módulo Terraform `glue_jobs` — job Gold~~ — feito, `pod99-fin-case-dev-gold-aggregate` criado e confirmado na AWS.
- [x] ~~Módulo Terraform para Step Functions + EventBridge (orquestração)~~ — feito, `pod99-fin-case-dev-pipeline` criado (Bronze → Silver → Gold via `glue:startJobRun.sync`); regra EventBridge de disparo diário criada `DISABLED` de propósito (decisão de custo/escopo, ver tabela de decisões).
- [x] ~~Módulo Terraform para CloudWatch (logs estruturados, métricas, alarmes)~~ — feito: `jobs/common/metrics.py` (métricas customizadas: `records_processed`, `records_rejected_dq`, `job_duration_seconds`) + módulo `monitoring` (SNS + alarme de falha do Step Functions + regra EventBridge de falha de job Glue). Validado via `pytest` (27/27) e execução real na AWS — métricas confirmadas via `aws cloudwatch list-metrics`/`get-metric-statistics`, alarme em estado `OK`.
- [ ] Testes unitários do Gold.
- [x] ~~ADRs adicionais: Iceberg vs Delta/Hudi, Step Functions vs Airflow/MWAA, estratégia de particionamento/idempotência~~ — feito (006, 007, 008). Também adicionado ADR-009 (Lake Formation não habilitado — gap descoberto na finalização).
- [x] ~~Seção de dimensionamento para produção~~ — feito, no `README.md` (volume, compute, custo estimado — premissas explícitas, não benchmark medido).
- [x] ~~README final consolidando tudo~~ — feito, `README.md` na raiz.
- [x] ~~Empacotamento ZIP para entrega~~ — feito, `POD99_Case_delivery.zip` (77 arquivos, 0,09 MB), gerado via staging + `Compress-Archive`, conteúdo verificado por extração.

## Decisões técnicas/arquiteturais

| Decisão | Registro |
|---|---|
| Cenário A ("entregar muito bem"), sem GenAI/MCP/OpenLineage/SDD formal | Confirmado pelo usuário |
| IaC: Terraform | Confirmado pelo usuário |
| Orçamento: mínimo possível (Glue Jobs não têm free tier) | Confirmado pelo usuário |
| Região: `us-east-2` (não `sa-east-1`) | `architecture/ADRs/001-aws-region.md` — decisão prática por já ser a conta/região usada pelo usuário, focando em corte de custo pessoal; residência de dados no Brasil documentada como o que seria feito em produção real |
| Bucket S3 único com prefixos (não 4 buckets separados) | Comentado em `infra/terraform/modules/s3/main.tf` — Iceberg já dá snapshot/versionamento por tabela, versioning de bucket seria redundante |
| IAM do deployer: `AdministratorAccess` na conta sandbox pessoal | `architecture/ADRs/002-deployer-iam-permissions.md` — velocidade de iteração no prazo de 5 dias; a role de **execução** dos jobs Glue continua least-privilege |
| Manter DynamoDB no escopo | Requisito explícito da JD (NoSQL) e tem *always-free tier* — sem trade-off real de custo |
| Profile AWS isolado (`pod99-case`) | Para não misturar billing/permissões com contas de trabalho |
| PySpark (não Scala) | `architecture/ADRs/003-pyspark-vs-scala.md` — pipeline usa API DataFrame/SQL (sem UDFs linha-a-linha), produtividade e ecossistema de testes em Python |
| Dev/teste local 100% dentro do Docker (não PySpark local no host) | `architecture/ADRs/004-local-dev-via-docker.md` — Java 21 do host é incompatível com o Spark 3.5 do Glue (suporte oficial até Java 17); roda dentro do container oficial `amazon/aws-glue-libs:5.1.0` para fidelidade ao ambiente real |
| `repartition("dt_processamento")` explícito antes de gravar Bronze/quarentena | Sem isso, ~2.484 linhas rejeitadas geravam ~2.000 arquivos Parquet (small-file problem). Corrigido e validado: caiu para 10 arquivos (1 por partição de data) |
| Teto do AWS Budgets: $5/mês | Rede de segurança para o "gasto mínimo possível" — alerta em 80% real e 100% previsto, por e-mail |
| `--datalake-formats=iceberg` + `--additional-python-modules=pyyaml` no job Glue (em vez de empacotar tudo num único zip) | Usa os mecanismos nativos do Glue para dependências Iceberg e PyPI, evitando gerenciar manualmente JARs/dependências |
| `--table_location` explícito por tabela (não confiar no default `<warehouse>/<db>.db/<tabela>` do Iceberg) | Achado real: sem isso, a tabela foi criada fora da estrutura de pastas planejada (bronze/silver/gold). Ver `docs/test_log.md` §2.16 |
| `load_contract()` com branch explícito para `s3://` (via boto3) vs caminho local (via `open()`) | `open()` não entende URIs S3 — só funcionava nos testes locais. Achado rodando na AWS de verdade. Teste de regressão em `tests/unit/test_contract.py` |
| **Iceberg format-version 2, não 3** (desvio da instrução literal do desafio) | `architecture/ADRs/005-iceberg-format-version.md` — achado real via Athena (`GENERIC_INTERNAL_ERROR: Iceberg format version 3 is not supported`, confirmado que é limitação do engine, não config). Dado consultável > conformidade literal com um número de versão. Válido para Bronze/Silver/Gold daqui pra frente |
| `--conf` do catálogo Iceberg/Glue fatorado em `local.iceberg_glue_catalog_conf` (Terraform) | Reuso entre os jobs Bronze e Silver, sem duplicar os 5 confs em cada `aws_glue_job` |
| `--processing_date` como placeholder no Terraform, sobrescrito via `--arguments` no `start-job-run` | O dia a processar muda a cada execução — não faz sentido fixar no código de infra. Um orquestrador real (Step Functions) passaria isso dinamicamente do mesmo jeito |
| DynamoDB `PAY_PER_REQUEST` (não provisionado) para o controle de lote | Volume de escrita é ínfimo (poucas gravações por execução de job) — não justifica planejamento de capacidade, e o modo on-demand tem always-free tier |
| Chave composta `id_lote` (hash) + `job_name` (range) na tabela de controle de lote | Um mesmo lote passa por múltiplos jobs (bronze/silver/gold), cada um com seu próprio status — evita colisão entre jobs no mesmo dia |
| `id_lote` do Bronze = `JOB_RUN_ID` do Glue; `id_lote` do Silver = `processing_date` | Bronze ingere o prefixo `raw/` inteiro por execução (não um dia por vez), então não tem uma data de negócio natural por lote; Silver processa um dia por vez, encaixe direto. Trade-off documentado, não escondido |
| `update_batch_status()` é opcional (no-op sem `--batch_control_table`) | Evita quebrar os runs locais via Docker (que não têm esse argumento nem credenciais AWS) — testado explicitamente em `test_batch_control.py` |
| Convenção de sinal contábil no Gold (CREDITO/JUROS somam, DEBITO/TARIFA/IOF subtraem, estorno inverte) | Desafio não especifica a regra exata — decisão de negócio assumida e documentada em `jobs/common/gold_transform.py`, a validar com o Squad Contábil (owner do contrato) numa rodada real |
| Gold escreve com `overwritePartitions()` (overwrite dinâmico de partição do Iceberg), não `MERGE INTO` | São agregações recalculadas do zero a cada run, não upserts linha a linha por chave — trocar a partição inteira é mais simples e correto que comparar/mesclar campo a campo |
| Bronze também passou a usar `overwritePartitions()` (era `.append()`) | Achado real: reexecutar o Bronze sem dado novo duplicava a tabela inteira, porque ele lê `raw/` inteiro a cada run (não é incremental por arquivo). Ver `docs/test_log.md` §4.8 |
| Step Functions usa `glue:startJobRun.sync` (integração nativa), não Lambda de polling | AWS gerencia o polling de conclusão do job Glue nativamente — menos código, menos pontos de falha |
| Regra EventBridge do disparo diário criada com `state = "DISABLED"` | Calcular "ontem" dinamicamente exigiria uma Lambda pequena ou EventBridge Scheduler com expressão de data — fora do escopo do case; deixar a regra `ENABLED` faria ela disparar sem supervisão pelo resto da vida do projeto, incorrendo custo. Documentado, não escondido — uma versão de produção habilitaria com uma etapa real de cálculo de data na frente |
| `ResultPath = null` em `RunBronze`/`RunSilver` no Step Functions | Achado real: sem isso, o output da task Glue sobrescreve o `$` do estado seguinte, apagando o `processing_date` do input original da execução (`States.Runtime` na 1ª tentativa real). Ver `docs/test_log.md` §4.13 |
| Alarme de falha do pipeline na métrica nativa `AWS/States ExecutionsFailed`, não em métricas customizadas dos jobs | O Step Functions já publica essa métrica automaticamente por máquina de estados — cobre falha de qualquer etapa (Bronze/Silver/Gold) com um único alarme, sem duplicar lógica por job |
| `cloudwatch:PutMetricData` com `resources = ["*"]` na policy IAM | Essa action não tem formato de ARN — não é possível escopar por namespace/métrica. É o least-privilege máximo possível para essa permissão específica |

## Arquivos importantes

- `docs/company_job_description.md`, `docs/desafio-tecnico-pod99-arquiteto-de-dados.md` — vaga e desafio técnico originais.
- `docs/claude_global.md`, `docs/data_eng_checklist.md` — preferências e checklist a seguir em toda implementação.
- `docs/project_progress.md` — este arquivo.
- `docs/test_log.md` — log cronológico de todo teste/execução real feito (comando, resultado, achados) — evidência para a defesa técnica.
- `architecture/diagram.mmd` — diagrama de arquitetura.
- `architecture/ADRs/` — decisões arquiteturais registradas (001-região, 002-IAM deployer, 003-PySpark vs Scala, 004-dev local via Docker, 005-Iceberg format-version 2).
- `data_contracts/fin_contabilidade_saldo_contrato.yaml` — contrato de dados.
- `data_generator/generate_synthetic_transactions.py` — gerador de dados sintéticos.
- `jobs/bronze_ingest.py`, `jobs/silver_transform.py`, `jobs/gold_aggregate.py`, `jobs/common/{contract,dq_validation,silver_transform,gold_transform,logging_utils,batch_control,metrics}.py` — jobs Bronze/Silver/Gold e utilitários.
- `tests/unit/test_dq_validation.py`, `tests/unit/test_contract.py`, `tests/unit/test_silver_transform.py`, `tests/unit/test_gold_transform.py`, `tests/unit/test_batch_control.py`, `tests/unit/test_metrics.py` + `conftest.py` — testes unitários (DQ, contrato local/S3, dedup/enrich do Silver, agregações do Gold, controle de lote, métricas).
- `scripts/run_local_bronze.sh`, `scripts/run_local_silver.sh`, `scripts/run_local_gold.sh`, `scripts/run_tests_docker.sh` — execução local via Docker.
- `infra/terraform/` — IaC (root + módulos `s3`, `iam`, `glue_catalog`, `glue_jobs`, `budget`, `dynamodb`, `orchestration`, `monitoring`).
- Plano detalhado (fora do repo): `C:\Users\Guilherme Ruschel\.claude\plans\olhar-os-mds-na-replicated-lake.md`.

## Comandos importantes

```bash
# Gerar dados sintéticos
python data_generator/generate_synthetic_transactions.py \
  --output-dir data_generator/output --num-accounts 5000 \
  --total-transactions 100000 --num-days 10 --dq-error-rate 0.02

# Instalar dependências do gerador
pip install -r data_generator/requirements.txt

# Verificar identidade AWS
aws sts get-caller-identity --profile pod99-case

# Terraform
cd infra/terraform
terraform init -input=false
terraform plan -input=false -var="aws_profile=pod99-case" -var="budget_alert_email=gui.ruschel22@gmail.com"
terraform apply -var="aws_profile=pod99-case" -var="budget_alert_email=gui.ruschel22@gmail.com"   # já executado, ver acima

# Rodar o job Bronze na AWS de verdade (já validado, gera custo real pequeno a cada run)
$run = aws glue start-job-run --job-name pod99-fin-case-dev-bronze-ingest --profile pod99-case --region us-east-2 --query "JobRunId" --output text
aws glue get-job-run --job-name pod99-fin-case-dev-bronze-ingest --run-id $run --profile pod99-case --region us-east-2 --query "JobRun.JobRunState"

# Ver logs do job (se falhar, o ErrorMessage do get-job-run costuma ser genérico -- o log completo tem a causa raiz)
aws logs get-log-events --log-group-name "/aws-glue/jobs/error" --log-stream-name $run --profile pod99-case --region us-east-2

# Rodar o job Bronze/Silver/Gold localmente (Docker, catálogo Iceberg local, $0)
bash scripts/run_local_bronze.sh
bash scripts/run_local_silver.sh 2026-08-01   # precisa de um dt_processamento
bash scripts/run_local_gold.sh 2026-08-01     # idem

# Rodar os testes unitários (Docker)
bash scripts/run_tests_docker.sh

# Rodar o job Silver na AWS de verdade (--processing_date via --arguments)
# ATENÇÃO no PowerShell: precisa escapar as aspas duplas do JSON com \"
# No bash (git-bash), NÃO escapar -- usar aspas simples/duplas normais.
$argsJson = '{\"--processing_date\":\"2026-08-01\"}'
$run = aws glue start-job-run --job-name pod99-fin-case-dev-silver-transform --arguments $argsJson --profile pod99-case --region us-east-2 --query "JobRunId" --output text

# Ver o status de um lote gravado na tabela de controle
aws dynamodb get-item --table-name pod99-fin-case-dev-batch-control \
  --key '{"id_lote":{"S":"2026-08-01"},"job_name":{"S":"silver"}}' \
  --profile pod99-case --region us-east-2

# Rodar o pipeline inteiro (Bronze -> Silver -> Gold) via Step Functions
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-2:952376464712:stateMachine:pod99-fin-case-dev-pipeline \
  --input '{"processing_date":"2026-08-01"}' \
  --profile pod99-case --region us-east-2

# Acompanhar a execução
aws stepfunctions describe-execution --execution-arn <executionArn> --profile pod99-case --region us-east-2 --query "status"
```

## Problemas e soluções

| Problema | Solução |
|---|---|
| Terraform CLI não estava instalado | `winget install --id Hashicorp.Terraform` (atenção: o id correto é `Hashicorp.Terraform`, com "H" maiúsculo apenas no início — `HashiCorp.Terraform` não é encontrado) |
| Profiles AWS pré-existentes (`default`, `glue-dev`) com credenciais inválidas/expiradas e origem incerta | Não reutilizados — criado profile novo isolado `pod99-case` com usuário IAM dedicado `pod99-case-terraform`, para não arriscar misturar com conta de trabalho |
| `pyarrow` não estava instalado no ambiente Python local | `pip install -r data_generator/requirements.txt` |
| Tag `glue_libs_5.0.0_image_01` não existe mais no Docker Hub | A partir do Glue 5.x a imagem mudou de esquema de tags — usar `amazon/aws-glue-libs:5.1.0` (versão simples), não o padrão antigo `glue_libs_X.Y.Z_image_01` (esse só existe até a 4.0.0) |
| Docker Desktop daemon não estava rodando | Iniciado manualmente (`Docker Desktop.exe`), aguardado ficar pronto antes do `docker pull` |
| Git-bash (MSYS) reescrevia os caminhos POSIX do container (`/home/hadoop/workspace`) como se fossem caminhos Windows, quebrando o `docker run` | `export MSYS_NO_PATHCONV=1` antes do `docker run`, nos scripts |
| `ENTRYPOINT` da imagem `amazon/aws-glue-libs:5.1.0` é `bash -l` (não um shell genérico) e o usuário é `hadoop` (não `glue_user`, que era o padrão só nas imagens 4.0.0) | Passar os comandos direto como `-c "..."` em vez de `bash -c "..."`, e montar em `/home/hadoop/workspace` |
| Parquet gerado pelo pandas/pyarrow usa timestamp em **nanossegundos**, que o Spark 3.5 rejeita (`Illegal Parquet type: INT64 (TIMESTAMP(NANOS))`) | `data_generator/generate_synthetic_transactions.py` agora converte `dt_lancamento` para `datetime64[us]` (microssegundos) antes de escrever |
| **Small-file problem**: ~2.484 linhas rejeitadas geravam ~2.000 arquivos Parquet na quarentena (quase 1 arquivo por linha) | Adicionado `.repartition("dt_processamento")` explícito antes da escrita em `jobs/bronze_ingest.py` — caiu para 10 arquivos (1 por dia) |
| `--additional-python-modules="pyyaml>=6.0,<7.0"` falhou no Glue (`Invalid requirement: '<7.0'`) | Glue usa vírgula como separador **entre pacotes**, não dentro de um range de versão — mudado para `"pyyaml>=6.0"` |
| `ModuleNotFoundError: No module named 'common'` no Glue | O `archive_file` do Terraform zipava o conteúdo de `jobs/common/` sem a pasta `common/` dentro — corrigido com blocos `source{}` explícitos preservando `common/<arquivo>.py` |
| `FileNotFoundError` ao ler o contrato via `s3://...` | `open()` do Python não entende URIs S3 — `load_contract()` agora usa `boto3` quando o caminho começa com `s3://` |
| `CREATE NAMESPACE` batia num bug do parser Spark SQL contra o catálogo Iceberg/Glue | Removida a linha (redundante — Terraform já cria o database) |
| `REQUIRES_SINGLE_PART_NAMESPACE` ao escrever a tabela | `--datalake-formats=iceberg` não registra sozinho o catálogo `glue_catalog` — precisa de `--conf` explícito pra extensão + catalog-impl + io-impl + warehouse |
| Tabela Iceberg criada fora da estrutura de pastas planejada (`pod99_fin_case_dev.db/` na raiz, não em `bronze/`) | Adicionado `--table_location` explícito, usado via `.tableProperty("location", ...)` |
| Athena: `GENERIC_INTERNAL_ERROR: Iceberg format version 3 is not supported` ao consultar a tabela Bronze | Confirmado que Athena engine version 3 (a mais recente) não lê Iceberg V3 ainda — mudado para format-version 2 em todas as tabelas (`architecture/ADRs/005-iceberg-format-version.md`); revalidado local + AWS + query Athena depois da correção |
| Docker Desktop não subia (`docker-desktop` do WSL2 ficava `Stopped` mesmo com os processos rodando) | `Stop-Process` em todos os processos Docker + `wsl --shutdown` + reabrir o Docker Desktop — resolvido, voltou a funcionar em ~10s |
| PowerShell removia as aspas duplas do JSON em `aws glue start-job-run --arguments '{"...":"..."}'` | Escapar as aspas duplas dentro da string de aspas simples: `'{\"--processing_date\":\"2026-08-01\"}'` |
| `ConcurrentRunsExceededException` ao iniciar um novo run logo após o anterior terminar (mesmo já `SUCCEEDED`) | Atraso de propagação do contador de concorrência do Glue — resolvido com um simples retry, sem mudança de código |

## Mudanças de planejamento

- Cenário B (Bedrock/MCP/OpenLineage/SDD formal) descartado para esta entrega — foco total no Cenário A.
- Região mudou de `sa-east-1` (proposta inicial, argumento de residência de dados) para `us-east-2` (decisão prática do usuário, por já ser a conta/região em uso e focar em corte de custo).
- IAM do deployer definido como `AdministratorAccess` (não policy customizada) para não consumir tempo do prazo de 5 dias úteis ajustando permissões a cada recurso novo.
- **Não haverá sessão de defesa técnica presencial** — a entrega é só o arquivo ZIP. Criado `APRESENTACAO.md` (documento guia em prosa) e `docs/evidencias/` (prints reais do console AWS, já que a conta não pode ser compartilhada) para compensar a ausência da apresentação ao vivo.

## Próximo passo

Case tecnicamente completo. Único item pendente: **commit git** — nunca foi feito nesta sessão (único commit existente é o inicial "Project"). Aguardando decisão explícita do usuário sobre quando/como commitar (protocolo do projeto: nunca commitar/dar push sem confirmação).

Depois do commit: revisar `POD99_Case_delivery.zip` uma última vez, e o case está pronto para entrega (formato final: arquivo ZIP, sem sessão de apresentação/defesa ao vivo).

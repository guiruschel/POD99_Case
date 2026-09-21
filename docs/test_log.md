# Test Log — evidências de validação

> Registro cronológico de **todo teste/execução real** feito no projeto — comando rodado, resultado exato, e o que foi descoberto. Serve como evidência para a defesa técnica ("como você sabe que isso funciona?"). Atualizado a cada validação nova, nunca depois do fato de memória.

---

## Dia 1 — Infraestrutura base (Terraform)

### 1.1 `terraform init`
```
cd infra/terraform
terraform init -input=false
```
**Resultado:** sucesso. Provider `hashicorp/aws v5.100.0` instalado, `.terraform.lock.hcl` gerado.

### 1.2 `terraform plan` contra a conta AWS real
```
terraform plan -input=false -var="aws_profile=pod99-case"
```
**Resultado:** `Plan: 13 to add, 0 to change, 0 to destroy`. Zero erros. Profile `pod99-case` autenticado corretamente (conta `952376464712`, `us-east-2`).

### 1.3 `terraform apply`
```
terraform apply -auto-approve -var="aws_profile=pod99-case"
```
**Resultado:** `Apply complete! Resources: 13 added, 0 changed, 0 destroyed.`

### 1.4 Verificação pós-apply (recursos existem de fato na AWS, não só no state)
```bash
aws s3 ls --profile pod99-case
aws s3 ls s3://pod99-fin-case-dev-952376464712/ --profile pod99-case
aws glue get-database --name pod99_fin_case_dev --profile pod99-case --region us-east-2 --query "Database.Name" --output text
aws iam get-role --role-name pod99-fin-case-dev-glue-job-role --profile pod99-case --query "Role.Arn" --output text
```
**Resultado:**
- Bucket `pod99-fin-case-dev-952376464712` existe, com os 6 prefixos (`raw/`, `bronze/`, `silver/`, `gold/`, `quarantine/`, `ref/`).
- Database Glue `pod99_fin_case_dev` existe.
- Role `arn:aws:iam::952376464712:role/pod99-fin-case-dev-glue-job-role` existe.

**Custo real confirmado:** $0 (bucket vazio, database vazio, IAM é sempre grátis).

---

## Dia 2 — Job Bronze

### 2.1 Gerador de dados sintéticos — smoke test inicial
```
python data_generator/generate_synthetic_transactions.py --output-dir data_generator/output --num-accounts 500 --total-transactions 20000 --num-days 5 --dq-error-rate 0.03
```
**Resultado:** 20.000 transações geradas. Verificação manual via pandas: valores negativos e `id_transacao` duplicado presentes na amostra (confirma que a injeção de violações de DQ funciona).

### 2.2 Ambiente de execução local
```
docker pull amazon/aws-glue-libs:5.1.0
```
**Achado:** a tag `glue_libs_5.0.0_image_01` (padrão de nomenclatura do Glue 4.0) não existe mais para a série 5.x — o esquema mudou para versões simples (`5.1.0`, `5.0.10`, etc). Corrigido usando `docker pull amazon/aws-glue-libs:5.1.0`.
**Resultado:** imagem baixada (5.43GB comprimida / 12.6GB em disco). `docker image inspect` confirmou `Architecture: amd64`, compatível com o host.

### 2.3 Testes unitários (`pytest`) — regras de DQ
```
bash scripts/run_tests_docker.sh
```
**Resultado:** `7 passed in 17.56s`. Cobrindo: linha válida passa, `id_transacao` duplicado é rejeitado, valor negativo é rejeitado, `dt_lancamento` após `dt_processamento` é rejeitado, `cod_cosif` desconhecido é rejeitado, `cod_cosif` nulo é permitido, campo obrigatório vazio é rejeitado.

### 2.4 Job Bronze — 1ª execução real (falhou)
```
bash scripts/run_local_bronze.sh
```
**Resultado:** falhou com `org.apache.spark.sql.AnalysisException: Illegal Parquet type: INT64 (TIMESTAMP(NANOS,false))`.
**Causa raiz:** pandas/pyarrow gravam timestamps em precisão de nanossegundos por padrão; o parser Parquet do Spark 3.5 (usado pelo Glue 5.x) não aceita `TIMESTAMP(NANOS)`, só `MICROS`/`MILLIS`.
**Correção:** `data_generator/generate_synthetic_transactions.py` agora converte `dt_lancamento` para `datetime64[us]` antes de escrever (`df.astype({"dt_lancamento": "datetime64[us]"})`).
**Verificação da correção:**
```python
import pyarrow.parquet as pq
pq.read_schema("data_generator/output/raw/.../part-0.parquet")
# dt_lancamento: timestamp[us]  <- confirmado
```

### 2.5 Job Bronze — 2ª execução real (passou, mas com achado de performance)
```
bash scripts/run_local_bronze.sh
```
**Resultado:** `job_finished` — sucesso. `validation_complete`: total=100.000, válidos=97.516, rejeitados=2.484.
**Achado (small-file problem):** a pasta de quarentena tinha **~2.000 arquivos Parquet para 2.484 linhas rejeitadas** (quase 1 arquivo por linha) — 22MB ocupados por dados que deveriam caber em poucas centenas de KB. Causa: o `Window` (contagem de duplicatas) + o broadcast join deixaram o DataFrame com muito mais partições em memória do que valores distintos de `dt_processamento`, e a escrita particionada multiplicou isso em arquivos minúsculos por task.
**Correção:** adicionado `.repartition("dt_processamento")` explícito antes de cada escrita (`valid_df` e `rejected_df`) em `jobs/bronze_ingest.py`.

### 2.6 Job Bronze — 3ª execução real (corrigida, validada)
```
rm -rf data_generator/output/warehouse data_generator/output/quarantine
bash scripts/run_local_bronze.sh
```
**Resultado:** `job_finished`. Mesmos números de validação (total=100.000, válidos=97.516, rejeitados=2.484 — confirma que a correção não alterou a lógica de negócio, só o layout físico dos arquivos).
**Verificação de arquivos:**
```bash
find data_generator/output/warehouse -name "*.parquet" | wc -l   # 10 (1 por dia)
find data_generator/output/quarantine -name "*.parquet" | wc -l  # 10 (1 por dia, era ~2000)
du -sh data_generator/output/quarantine                          # 294K (era 22M)
```
**Verificação da tabela Iceberg:**
```bash
find data_generator/output/warehouse -maxdepth 5 -type d
# .../bronze_fin_contabilidade_saldo_contrato/data/dt_processamento=2026-08-01 ... 08-10
# .../bronze_fin_contabilidade_saldo_contrato/metadata
```
Confirma: tabela Iceberg criada, particionada por `dt_processamento` (10 partições, uma por dia gerado), com pasta `metadata/` (manifests do Iceberg).

**Distribuição dos motivos de rejeição** (validação cruzada com pandas, lendo os arquivos de quarentena):
```python
import pandas as pd, glob
df = pd.concat([pd.read_parquet(f) for f in glob.glob("data_generator/output/quarantine/*/*.parquet")])
df["dq_rejection_reasons"].explode().value_counts()
```
```
uniqueness_id_transacao                     991
dt_lancamento_not_after_dt_processamento    515
valor_lancamento_positive                   498
cod_cosif_referential_integrity             490
```
Total de linhas rejeitadas: 2.484 (bate com o `validation_complete` do log do job).

---

## Dia 2 (cont.) — Infra para rodar o Bronze na AWS real (ainda sem executar)

### 2.7 Extensão da IAM role + módulo `glue_jobs` + `budget` — plan
```
terraform init -input=false -upgrade   # novo provider hashicorp/archive
terraform plan -input=false -var="aws_profile=pod99-case" -var="budget_alert_email=gui.ruschel22@gmail.com"
```
**Resultado:** `Plan: 6 to add, 0 to change, 0 to destroy`, 0 erros.

### 2.8 Apply
```
terraform apply -auto-approve -var="aws_profile=pod99-case" -var="budget_alert_email=gui.ruschel22@gmail.com"
```
**Resultado:** `Apply complete! Resources: 6 added, 0 changed, 0 destroyed.`

### 2.9 Verificação pós-apply na AWS real
```bash
aws glue get-job --job-name pod99-fin-case-dev-bronze-ingest --profile pod99-case --region us-east-2 \
  --query "Job.{Name:Name,GlueVersion:GlueVersion,Workers:NumberOfWorkers,WorkerType:WorkerType,Timeout:Timeout}"
aws s3 ls s3://pod99-fin-case-dev-952376464712/scripts/ --profile pod99-case
aws budgets describe-budget --account-id 952376464712 --budget-name pod99-fin-case-dev-monthly-guard --profile pod99-case
```
**Resultado:**
- Job Glue `pod99-fin-case-dev-bronze-ingest` existe: `GlueVersion=5.0`, `WorkerType=G.1X`, `Workers=2`, `Timeout=15min`.
- 3 arquivos no S3 (`scripts/bronze_ingest.py`, `scripts/common.zip`, `scripts/fin_contabilidade_saldo_contrato.yaml`).
- Budget `pod99-fin-case-dev-monthly-guard` existe, limite $5.00 USD, alertas em 80% (real) e 100% (previsto) por e-mail.

---

## Dia 2 (cont.) — Primeira execução real do Bronze na AWS: 6 falhas, 1 sucesso

Dataset de smoke test: 5.000 transações, 2 dias, 2% de erro de DQ, subido pro S3 (`raw/`, `ref/`) via `aws s3 sync`/`cp`.

Cada tentativa abaixo foi disparada com `aws glue start-job-run --job-name pod99-fin-case-dev-bronze-ingest ...` e acompanhada com `aws glue get-job-run ... --query JobRun.JobRunState` em loop até sair de `RUNNING`.

### 2.10 Tentativa 1 — FAILED (31s)
**Erro:** `LAUNCH ERROR | Installation of Additional Python Modules failed: ERROR: Invalid requirement: '<7.0'`
**Causa raiz:** `--additional-python-modules` do Glue usa vírgula como separador **entre pacotes diferentes** (ex: `"pandas==1.0,numpy==1.2"`). O valor `"pyyaml>=6.0,<7.0"` foi interpretado como dois pacotes: `pyyaml>=6.0` e `<7.0` (inválido, sem nome).
**Correção:** `infra/terraform/modules/glue_jobs/main.tf` — mudado para `"pyyaml>=6.0"` (sem limite superior, sem vírgula).

### 2.11 Tentativa 2 — FAILED (41s)
**Erro:** `ModuleNotFoundError: No module named 'common'`
**Causa raiz:** o `archive_file` do Terraform, com `source_dir = jobs/common`, zipa o **conteúdo** da pasta na raiz do zip (sem a pasta `common/` dentro). O `--extra-py-files` do Glue põe o zip no `sys.path`, mas sem a pasta `common/` lá dentro, `from common.contract import ...` não encontra nada.
**Correção:** reescrito o `data "archive_file" "common_zip"` usando blocos `source { content, filename }` explícitos por arquivo, preservando `common/<arquivo>.py` dentro do zip.

### 2.12 Tentativa 3 — FAILED (64s)
**Erro:** `FileNotFoundError: [Errno 2] No such file or directory: 's3://pod99-fin-case-dev-952376464712/scripts/fin_contabilidade_saldo_contrato.yaml'`
**Causa raiz:** `jobs/common/contract.py` usava `open(path)` puro — funciona pra caminho local (era assim que os testes locais rodavam), mas `open()` não entende URIs `s3://`.
**Correção:** `load_contract()` agora detecta prefixo `s3://` e usa `boto3.client("s3").get_object(...)` nesse caso; mantém `open()` pra caminhos locais. Adicionado teste de regressão (`tests/unit/test_contract.py`, 3 testes, com mock de `boto3.client` pro caso S3).

### 2.13 Tentativa 4 — FAILED (87s)
**Erro:** `[INTERNAL_ERROR] Undefined error message parameter for error class: '_LEGACY_ERROR_TEMP_1055'. Parameters: Map(database -> glue_catalog.pod99_fin_case_dev)`
**Causa raiz** (via CloudWatch Logs, `/aws-glue/jobs/error/<run-id>`): a linha `spark.sql("CREATE NAMESPACE IF NOT EXISTS glue_catalog.pod99_fin_case_dev")` batia num bug/limitação do parser do Spark SQL contra o catálogo Iceberg do Glue. Além disso, essa linha era **redundante** — o Terraform já cria o database.
**Correção:** removida a linha `CREATE NAMESPACE` de `jobs/bronze_ingest.py`. Revalidado local (grátis) antes de gastar outra execução AWS — passou.

### 2.14 Tentativa 5 — FAILED (75s)
**Erro:** `AnalysisException: [REQUIRES_SINGLE_PART_NAMESPACE] spark_catalog requires a single-part namespace, but got \`glue_catalog\`.\`pod99_fin_case_dev\`.`
**Causa raiz:** `--datalake-formats=iceberg` só coloca os JARs do conector Iceberg no classpath — **não registra sozinho** um catálogo chamado `glue_catalog`. Só tínhamos configurado `spark.sql.catalog.glue_catalog.warehouse` via `--conf`, faltando a definição do catálogo em si (`spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog`, `catalog-impl`, `io-impl`, e a extensão `IcebergSparkSessionExtensions`). Sem isso, `glue_catalog.pod99_fin_case_dev` era lido como namespace inválido no catálogo padrão do Spark.
**Correção:** `--conf` do job Glue expandido para incluir todos os 5 confs necessários (extensão + catálogo + catalog-impl + io-impl + warehouse), concatenados no formato `"key1=val1 --conf key2=val2 ..."` que o Glue repassa ao `spark-submit`.

### 2.15 Tentativa 6 — SUCCEEDED (171s, 343 DPU-segundos), mas com achado
**Log:** `validation_complete: total=5000, valid=4873, rejected=127` → `job_finished`.
**Achado:** a tabela Iceberg foi criada em `s3://.../pod99_fin_case_dev.db/bronze_fin_contabilidade_saldo_contrato/` — **fora** da estrutura de camadas planejada (`bronze/`, `silver/`, `gold/`). Causa: sem uma localização explícita por tabela, o catálogo Iceberg/Glue usa o padrão `<warehouse>/<database>.db/<tabela>/`, e nosso `warehouse` apontava pra raiz do bucket.
**Correção:** adicionado argumento `--table_location` (aponta explicitamente pra `s3://bucket/bronze/fin_contabilidade_saldo_contrato/`), usado via `.tableProperty("location", ...)` na criação da tabela em `jobs/bronze_ingest.py`. Também adicionado no script local (`scripts/run_local_bronze.sh`) pra manter os dois caminhos de execução consistentes.
**Limpeza:** `aws glue delete-table` + `aws s3 rm --recursive` no prefixo `pod99_fin_case_dev.db/` errado, e limpeza do `quarantine/` (estava em modo `append`, senão duplicaria dados do run anterior).

### 2.16 Tentativa 7 — SUCCEEDED (138s, 277 DPU-segundos) — validação final
```bash
aws logs get-log-events --log-group-name "/aws-glue/jobs/output" --log-stream-name <run-id> ...
aws s3 ls s3://pod99-fin-case-dev-952376464712/ --profile pod99-case         # sem pod99_fin_case_dev.db órfão
aws s3 ls s3://pod99-fin-case-dev-952376464712/bronze/ --recursive           # 2 arquivos de dado + metadata Iceberg
aws glue get-table --database-name pod99_fin_case_dev --name bronze_fin_contabilidade_saldo_contrato \
  --query "Table.StorageDescriptor.Location"
```
**Resultado:**
- `validation_complete: total=5000, valid=4873, rejected=127` — **idêntico à Tentativa 6 e ao teste local**, confirmando que a correção de local não mudou nenhum resultado de negócio.
- Bucket raiz limpo (sem `pod99_fin_case_dev.db/`).
- Tabela em `s3://pod99-fin-case-dev-952376464712/bronze/fin_contabilidade_saldo_contrato` — local correto, batendo com o desenho da arquitetura.
- Catálogo Glue: `StorageDescriptor.Location` confirma o mesmo caminho.
- `quarantine/`: 2 arquivos (1 por dia), sem duplicação.

### 2.17 Achado do usuário via Athena — Iceberg format-version 3 não suportado

Guilherme rodou manualmente no Athena:
```sql
SELECT * FROM pod99_fin_case_dev.bronze_fin_contabilidade_saldo_contrato LIMIT 2
```
**Erro:** `GENERIC_INTERNAL_ERROR: Iceberg format version 3 is not supported`

**Investigação:**
```bash
aws athena get-work-group --work-group primary --query "WorkGroup.Configuration.EngineVersion"
```
**Resultado:** `EffectiveEngineVersion: "Athena engine version 3"` — a mais recente disponível na conta. Confirma que não é erro de configuração: o motor Trino do Athena ainda não lê tabelas Iceberg format-version 3 (spec muito recente da indústria).

**Decisão:** `architecture/ADRs/005-iceberg-format-version.md` — usar format-version **2** em vez de 3 em todas as tabelas (Bronze/Silver/Gold), priorizando que o dado seja de fato consultável via Athena (requisito explícito do desafio e da JD) sobre a instrução literal "V3". Nenhuma feature exclusiva do V3 é usada neste pipeline.

**Correção e revalidação:**
1. `jobs/bronze_ingest.py`: `tableProperty("format-version", "3")` → `"2"`.
2. Revalidado localmente (grátis) — `validation_complete: total=5000, valid=4873, rejected=127`, `job_finished`. OK.
3. Limpeza da tabela V3 antiga: `aws glue delete-table` + `aws s3 rm --recursive` em `bronze/` e `quarantine/`.
4. Redeploy (`terraform apply`) + novo `aws glue start-job-run` → **SUCCEEDED** (90s — mais rápido que as tentativas anteriores).
5. **Reexecutada a mesma query que falhou antes**, via `aws athena start-query-execution`:
   ```sql
   SELECT * FROM pod99_fin_case_dev.bronze_fin_contabilidade_saldo_contrato LIMIT 2
   ```
   **Resultado:** `QueryExecution.Status.State = SUCCEEDED`, 2 linhas retornadas com schema e dados corretos (`cod_cosif`, `id_transacao`, `valor_lancamento`, etc.) — confirma a correção ponta a ponta, incluindo a camada de consumo (Athena) que o desafio pede.

**Custo real total da sequência (7 execuções, 6 falhas + 1 sucesso final):** ~10 minutos de tempo faturado somado, estimado em **menos de $0,25** no total (G.1X × 2 workers, Glue 5.0). Bem dentro do teto de $5/mês do Budget.

---

## Dia 3 — Job Silver (local, ainda sem AWS)

Lógica isolada em `jobs/common/silver_transform.py` (`dedup_and_enrich`), testável sem tocar catálogo/Iceberg.

### 3.1 Testes unitários (`pytest`, dentro do Docker)
```
bash scripts/run_tests_docker.sh
```
**Resultado:** `14 passed in 38.85s` — 10 anteriores (Bronze/contract) + 4 novos do Silver (dedup mantém entrada mais recente por `id_transacao`, enriquecimento com metadados COSIF quando há match, nulo quando não há match, todas as linhas preservadas mesmo sem match).

### 3.2 Primeira execução local — cria a tabela Silver
```
bash scripts/run_local_silver.sh 2026-08-01
```
**Resultado:** `transform_complete: bronze_rows=2412, silver_rows=2412` → `job_finished`. Tabela Iceberg Silver criada (format-version 2, conforme ADR-005), particionada por `dt_processamento`.

### 3.3 Reexecução do mesmo dia — validação de idempotência
```
bash scripts/run_local_silver.sh 2026-08-01   # de novo, mesmo dia
```
**Resultado:** `transform_complete: bronze_rows=2412, silver_rows=2412` → `job_finished` (dessa vez passou pelo caminho `MERGE INTO`, não `createOrReplace`).

**Verificação da tabela de fato (não só o log)**, via um script auxiliar (`scripts/_verify_silver_count.py`) rodando `SELECT COUNT(*), COUNT(DISTINCT id_transacao)`:
```
VERIFY total=2412 distinct_id_transacao=2412
```
Confirma: rodar o mesmo dia duas vezes **não duplicou nada** — `MERGE INTO` por `id_transacao` funcionando como esperado.

### 3.4 Segundo dia — validação de partition pruning + acumulação correta
```
bash scripts/run_local_silver.sh 2026-08-02
```
**Resultado:** `transform_complete: bronze_rows=2461, silver_rows=2461` → `job_finished`.

**Verificação:**
```
VERIFY total=4873 distinct_id_transacao=4873
```
`4873 = 2412 (dia 1) + 2461 (dia 2)`, todos distintos — e bate **exatamente** com o total de linhas válidas que o Bronze processou nos dois dias (`validation_complete` acumulado: 4873). Confirma: o filtro por `dt_processamento` (partition pruning) processou só o dia novo sem tocar no dia anterior, e o Silver não perdeu nem duplicou nenhuma linha do Bronze.

**Nota de ambiente:** nesta sessão, o Docker Desktop não subiu na primeira tentativa (distro WSL2 `docker-desktop` ficou em `Stopped`, mesmo com os processos do Docker Desktop rodando). Resolvido matando os processos (`Stop-Process`), `wsl --shutdown`, e reabrindo o Docker Desktop — voltou a funcionar em ~10s.

---

## Dia 3 (cont.) — Job Silver na AWS real

Extensão do módulo Terraform `glue_jobs`: novo recurso `aws_glue_job.silver_transform` (mesmo padrão do Bronze — G.1X × 2 workers, mesma configuração `--conf` do catálogo Iceberg/Glue, reaproveitada via `local.iceberg_glue_catalog_conf`), upload de `jobs/silver_transform.py` pro S3, e `jobs/common/silver_transform.py` adicionado ao `common.zip`. `--processing_date` fica com um placeholder no Terraform (`1970-01-01`) e é sobrescrito a cada execução via `--arguments`.

### 3.5 `terraform plan`/`apply`
**Resultado:** `Plan: 2 to add, 1 to change, 0 to destroy` → `Apply complete! Resources: 2 added, 1 changed, 0 destroyed.` Custo: $0 (só definição do job).

### 3.6 Pegadinha do PowerShell com JSON
```powershell
aws glue start-job-run --job-name ... --arguments '{"--processing_date":"2026-08-01"}' ...
```
**Erro:** `Invalid JSON: Expecting property name enclosed in double quotes` — o PowerShell removeu as aspas duplas ao repassar o argumento pro `aws.exe` nativo.
**Correção:** escapar as aspas duplas com `\"` dentro da string de aspas simples: `'{\"--processing_date\":\"2026-08-01\"}'`.

### 3.7 Execução 1 (dia 2026-08-01) — SUCCEEDED (105s)
```
{"message": "job_started", "processing_date": "2026-08-01"}
{"message": "transform_complete", "bronze_rows": 2412, "silver_rows": 2412}
{"message": "job_finished", "table": "glue_catalog.pod99_fin_case_dev.silver_fin_contabilidade_saldo_contrato"}
```
Tabela em `s3://pod99-fin-case-dev-952376464712/silver/fin_contabilidade_saldo_contrato` (local correto), confirmado via `aws glue get-table`.

### 3.8 Execução 2 (mesmo dia de novo, teste de idempotência real) — SUCCEEDED (90s)
Rodado o mesmo `--processing_date 2026-08-01` de novo.

### 3.9 Execução 3 (dia 2026-08-02) — `ConcurrentRunsExceededException` transiente
Primeira tentativa falhou com `ConcurrentRunsExceededException`, mesmo com a execução anterior já em `SUCCEEDED` (confirmado via `aws glue get-job-runs`) — atraso de propagação do contador de concorrência do Glue. Retry simples (sem nenhuma mudança de código) resolveu — **SUCCEEDED (75s)**.

### 3.10 Validação final via Athena (a camada de consulta real, não só o log do job)
```sql
SELECT COUNT(*) as total, COUNT(DISTINCT id_transacao) as distintos
FROM pod99_fin_case_dev.silver_fin_contabilidade_saldo_contrato
```
**Resultado:** `total=4873, distintos=4873` — **idêntico ao teste local** (mesma sequência de execuções: dia 1 → dia 1 de novo → dia 2) e **idêntico ao total de válidos que o Bronze processou** nos dois dias. Confirma: idempotência do `MERGE INTO`, partition pruning correto, e consultabilidade via Athena (format-version 2, ADR-005) — tudo validado na AWS real, não só localmente.

**Custo real acumulado do Silver (4 execuções: 3 SUCCEEDED + 1 erro transiente sem cobrança de DPU):** poucos centavos, dentro do padrão do Bronze.

---

## Dia 3 (cont.) — Tabela DynamoDB de controle de lote

Novo módulo Terraform `dynamodb` (`aws_dynamodb_table.batch_control`, `PAY_PER_REQUEST`, chave composta `id_lote` (hash) + `job_name` (range)). IAM estendida com policy escopada só a essa tabela (`GetItem`/`PutItem`/`UpdateItem`/`Query`). Novo módulo comum `jobs/common/batch_control.py` (`update_batch_status`), opcional por design: sem `--batch_control_table` (caso dos runs locais via Docker), a função não faz nenhuma chamada AWS — testado explicitamente (`test_update_batch_status_noop_without_table`).

Decisão de design: **Bronze usa `JOB_RUN_ID` como `id_lote`** (ingere o prefixo `raw/` inteiro por execução, não um dia de cada vez) e **Silver usa `processing_date`** (processa um dia por vez, encaixe natural com o conceito de "lote").

### 3.11 Testes unitários (`pytest`, dentro do Docker)
```
bash scripts/run_tests_docker.sh
```
**Resultado:** `18 passed in 29.34s` — 14 anteriores + 4 novos de `test_batch_control.py` (arg opcional presente/ausente, no-op sem tabela configurada, item gravado corretamente com a tabela configurada — mock de `boto3.resource`).

### 3.12 `terraform plan`/`apply`
```
terraform plan -input=false -var="aws_profile=pod99-case" -var="budget_alert_email=gui.ruschel22@gmail.com"
terraform apply -input=false <plan salvo>
```
**Resultado:** `Plan: 2 to add, 5 to change, 0 to destroy` → `Apply complete! Resources: 2 added, 5 changed, 0 destroyed.` (tabela DynamoDB + policy IAM novas; jobs Bronze/Silver atualizados com `--batch_control_table`/`--job_name_tag`; scripts no S3 re-sincronizados pelo novo `common.zip`).

### 3.13 Verificação pós-apply
```bash
aws dynamodb describe-table --table-name pod99-fin-case-dev-batch-control --profile pod99-case --region us-east-2 --query "Table.{Status:TableStatus,Billing:BillingModeSummary.BillingMode}"
```
**Resultado:** `{"Status": "ACTIVE", "Billing": "PAY_PER_REQUEST"}`.

### 3.14 Execução real do Silver (dia 2026-08-01) — grava status de verdade no DynamoDB
```bash
aws glue start-job-run --job-name pod99-fin-case-dev-silver-transform --arguments '{"--processing_date":"2026-08-01"}' --profile pod99-case --region us-east-2
# SUCCEEDED
aws dynamodb get-item --table-name pod99-fin-case-dev-batch-control --key '{"id_lote":{"S":"2026-08-01"},"job_name":{"S":"silver"}}' --profile pod99-case --region us-east-2
```
**Resultado:**
```json
{"Item": {"updated_at": {"S": "2026-09-21T15:19:34.333874+00:00"}, "id_lote": {"S": "2026-08-01"}, "status": {"S": "PROCESSED"}, "job_name": {"S": "silver"}}}
```
Confirma: `id_lote` = `processing_date`, status final `PROCESSED`, gravado de fato pela execução real na AWS (não só nos logs do job).

### 3.15 Execução real do Bronze — grava status de verdade no DynamoDB
```bash
aws glue start-job-run --job-name pod99-fin-case-dev-bronze-ingest --profile pod99-case --region us-east-2
# SUCCEEDED
aws dynamodb get-item --table-name pod99-fin-case-dev-batch-control --key '{"id_lote":{"S":"<JOB_RUN_ID>"},"job_name":{"S":"bronze"}}' --profile pod99-case --region us-east-2
```
**Resultado:**
```json
{"Item": {"updated_at": {"S": "2026-09-21T15:20:49.895407+00:00"}, "id_lote": {"S": "jr_d8dacd4e66bbc091df79d00433ac3116e5f1edc25f81947b14540ec77667d41b"}, "status": {"S": "PROCESSED"}, "job_name": {"S": "bronze"}}}
```
Confirma: `id_lote` = `JOB_RUN_ID` do Glue (não uma data de negócio, decisão documentada acima), status final `PROCESSED`.

**Custo real desta seção:** tabela DynamoDB `PAY_PER_REQUEST` ($0 sem tráfego — always-free tier cobre o volume deste caso) + 2 execuções de job Glue já contabilizadas no padrão de custo anterior (poucos centavos).

---

## Dia 4 — Job Gold

4 saídas exigidas pelo desafio, implementadas como funções puras testáveis em `jobs/common/gold_transform.py`: `saldo_por_contrato`, `saldo_por_conta`, `classificacao_cosif`, `reconciliacao_agencia`. Convenção de sinal (CREDITO/JUROS somam, DEBITO/TARIFA/IOF subtraem, estorno inverte) é uma decisão de negócio assumida e documentada — validar com o Squad Contábil numa rodada real.

Escrita idempotente via **overwrite dinâmico de partição do Iceberg** (`.writeTo(table).overwritePartitions()`), não `MERGE INTO`: como são agregações (não upserts por chave), reprocessar o mesmo dia troca a partição inteira em vez de comparar linha a linha.

### 4.1 Testes unitários (`pytest`, dentro do Docker)
```
bash scripts/run_tests_docker.sh
```
**Resultado:** `25 passed in 32.79s` — 18 anteriores + 7 novos de `test_gold_transform.py` (soma correta credito/debito, estorno inverte sinal, separação por contrato/conta/agência, enriquecimento COSIF, reconciliação por agência).

### 4.2 Primeira execução local — cria as 4 tabelas Gold
```
bash scripts/run_local_gold.sh 2026-08-01
```
**Resultado:** `aggregation_complete: silver_rows=2412, contratos=1044, contas=300, classificacoes_cosif=16, agencias=50` → `job_finished`. 4 tabelas Iceberg criadas (format-version 2), particionadas por `dt_processamento`.

### 4.3 Reexecução do mesmo dia — validação de idempotência (overwrite de partição)
```
bash scripts/run_local_gold.sh 2026-08-01
```
**Resultado:** `job_finished`. Log do commit do Iceberg confirma a troca exata da partição, ex. para `gold_reconciliacao_agencia`: `addedRecords=50, removedRecords=50, totalRecords=50` — 50 registros novos substituindo os 50 antigos, sem duplicar.
**Verificação via script auxiliar** (`scripts/_verify_gold_counts.py`):
```
VERIFY gold_saldo_contrato total=1044 dt_processamento_distinct=1
VERIFY gold_saldo_conta total=300 dt_processamento_distinct=1
VERIFY gold_cosif_classificacao total=16 dt_processamento_distinct=1
VERIFY gold_reconciliacao_agencia total=50 dt_processamento_distinct=1
```

### 4.4 Segundo dia — validação de acumulação por partição
```
bash scripts/run_local_gold.sh 2026-08-02
```
**Resultado:** `aggregation_complete: silver_rows=2461, contratos=1054, contas=299, classificacoes_cosif=16, agencias=50` → `job_finished`.
**Verificação:**
```
VERIFY gold_saldo_contrato total=2098 dt_processamento_distinct=2
VERIFY gold_saldo_conta total=599 dt_processamento_distinct=2
VERIFY gold_cosif_classificacao total=32 dt_processamento_distinct=2
VERIFY gold_reconciliacao_agencia total=100 dt_processamento_distinct=2
```
`2098 = 1044 + 1054`, `599 = 300 + 299`, `32 = 16 + 16`, `100 = 50 + 50` — confirma acumulação correta entre partições, sem sobrescrever o dia anterior.

### 4.5 `terraform plan`/`apply` — módulo `glue_jobs` estendido com o job Gold
**Resultado:** `Plan: 2 to add, 1 to change, 0 to destroy` → `Apply complete! Resources: 2 added, 1 changed, 0 destroyed.`

### 4.6 Execução real na AWS (dia 2026-08-01) — SUCCEEDED na primeira tentativa
```bash
aws glue start-job-run --job-name pod99-fin-case-dev-gold-aggregate --arguments '{"--processing_date":"2026-08-01"}' --profile pod99-case --region us-east-2
```
**Resultado:** `SUCCEEDED`. Batch control confirmado: `aws dynamodb get-item ... id_lote=2026-08-01 job_name=gold` → `status=PROCESSED`. 4 tabelas registradas no Glue Catalog (`aws glue get-tables`): `gold_saldo_contrato`, `gold_saldo_conta`, `gold_cosif_classificacao`, `gold_reconciliacao_agencia`.

### 4.7 Validação final via Athena
```sql
SELECT COUNT(*) FROM gold_saldo_contrato UNION ALL
SELECT COUNT(*) FROM gold_saldo_conta UNION ALL
SELECT COUNT(*) FROM gold_cosif_classificacao UNION ALL
SELECT COUNT(*) FROM gold_reconciliacao_agencia
```
**Resultado:** `1044, 300, 16, 50` — **idêntico à execução local** para o mesmo dia. Confirma pipeline Bronze → Silver → Gold ponta a ponta na AWS real, incluindo a camada de consumo (Athena).

**Custo real desta seção:** 1 execução de job Glue G.1X × 2 workers (~mesmo padrão de custo do Bronze/Silver, poucos centavos) + consultas Athena (cobradas por dado escaneado, volume ínfimo aqui).

---

## Dia 4 (cont.) — Achado real: Bronze duplicava dados ao reexecutar

Ao rodar o Bronze na AWS de novo (seção 3.15, só para testar o batch control), sem nenhum dado novo em `raw/`, a tabela dobrou de tamanho.

### 4.8 Detecção via Athena
```sql
SELECT COUNT(*) as total, COUNT(DISTINCT id_transacao) as distintos FROM bronze_fin_contabilidade_saldo_contrato
```
**Resultado:** `total=9746, distintos=4873` — exatamente o dobro. **Causa raiz:** `run_bronze_ingest()` lê o `raw_path` inteiro a cada execução (não é incremental por arquivo novo) e usava `valid_df.writeTo(table).append()` quando a tabela já existia — reprocessar sem filtro de data reescreve os mesmos dias e os acrescenta de novo, duplicando tudo. O mesmo valia para a escrita de quarentena (`.mode("append")`).

**Correção:** `jobs/bronze_ingest.py` — trocado `.append()` por `.overwritePartitions()` (mesma técnica idempotente usada no Gold) para a tabela Iceberg, e `.mode("overwrite")` com `spark.sql.sources.partitionOverwriteMode=dynamic` para a quarentena (Parquet simples). Agora reexecutar o Bronze substitui só as partições (`dt_processamento`) presentes na leitura atual, em vez de empilhar.

### 4.9 Revalidação local
```
rm -rf data_generator/output/warehouse data_generator/output/quarantine
bash scripts/run_local_bronze.sh   # 1ª execução
bash scripts/run_local_bronze.sh   # 2ª execução, mesmo raw/, sem regenerar dados
```
**Resultado:** ambas `validation_complete: total=5000, valid=4873, rejected=127`. Verificação real da tabela (`scripts/_verify_silver_count.py`): `VERIFY total=4873 distinct_id_transacao=4873` — confirma que a segunda execução não duplicou nada.
`pytest`: `25 passed` (nenhum teste unitário toca o caminho de escrita, mas confirma que a lógica de negócio não regrediu).

### 4.10 Correção na AWS real
```bash
# script corrigido já subido via terraform apply (só o S3 object, sem mudança de infra)
aws glue start-job-run --job-name pod99-fin-case-dev-bronze-ingest ...   # SUCCEEDED
```
Query Athena pós-fix: `total=4873, distintos=4873` — restaurado.

**Segunda execução real** (para confirmar idempotência de fato na AWS, não só localmente): a primeira tentativa bateu de novo no `ConcurrentRunsExceededException` transiente (mesmo padrão da seção 3.9); retry simples resolveu. Query Athena: `total=4873, distintos=4873` — **idempotente confirmado na AWS real**, mesmo rodando duas vezes seguidas sem dados novos.

### 4.11 Verificação de que Silver e Gold não foram afetados pela duplicação temporária do Bronze
```sql
SELECT 'silver', COUNT(*), COUNT(DISTINCT id_transacao) FROM silver_fin_contabilidade_saldo_contrato
UNION ALL
SELECT 'gold_contrato', COUNT(*), COUNT(DISTINCT id_contrato) FROM gold_saldo_contrato WHERE dt_processamento = DATE '2026-08-01'
```
**Resultado:** `silver: 4873/4873`, `gold_contrato: 1044/1044` — ambos intactos. Explicação: o `MERGE INTO` do Silver já deduplicava por `id_transacao` mesmo com o Bronze temporariamente duplicado (linhas duplicadas com o mesmo `id_transacao` só geram updates repetidos, não linhas novas), e o Gold é derivado do Silver, não do Bronze diretamente — o problema nunca se propagou pipeline abaixo.

**Lição para a defesa técnica:** o requisito de "considerar estratégias de reprocessamento (idempotência)" do desafio não é só sobre o job que você está reexecutando — é sobre garantir que *qualquer* rerun, em *qualquer* estágio, seja seguro. O Silver e o Gold já nasceram idempotentes (MERGE INTO / overwrite de partição); o Bronze foi o único ponto cego, e só foi encontrado rodando de verdade na AWS, não nos testes unitários (que testam lógica de negócio isolada, não o padrão de escrita).

---

## Ambiente / infraestrutura de suporte (achados ao longo do processo)

| Problema encontrado | Diagnóstico | Correção |
|---|---|---|
| Terraform CLI ausente | `terraform: command not found` | `winget install --id Hashicorp.Terraform` |
| Docker Desktop daemon parado | `failed to connect to the docker API` | `Start-Process "Docker Desktop.exe"`, aguardar ficar pronto |
| `docker pull amazon/aws-glue-libs:glue_libs_5.0.0_image_01` falhou | Tag não existe (esquema mudou no Glue 5.x) | Usar `amazon/aws-glue-libs:5.1.0` |
| `docker run` com erro de working directory inválido | Git-bash (MSYS) reescrevendo `/home/...` como caminho Windows | `export MSYS_NO_PATHCONV=1` antes do `docker run` |
| `bash -c "..."` dentro do container não executava nada / "cannot execute binary file" | `ENTRYPOINT` da imagem já é `bash -l`; usuário é `hadoop`, não `glue_user` (isso mudou desde as imagens 4.0.0) | Passar comando direto como `-c "..."`, montar em `/home/hadoop/workspace` |
| Profiles AWS CLI pré-existentes (`default`, `glue-dev`) com credenciais inválidas e origem incerta | Poderiam ser de conta de trabalho | Criado profile isolado `pod99-case` + usuário IAM dedicado `pod99-case-terraform` |

---

## Como este log vai evoluir

A cada novo teste relevante (Silver, Gold, execução real na AWS, Step Functions, etc.) uma nova seção é adicionada aqui, sempre com: comando exato, resultado literal (ou achado), e a correção aplicada quando houve. Nada entra como "validado" em `docs/project_progress.md` sem uma entrada correspondente aqui.

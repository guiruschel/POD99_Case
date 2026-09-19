# Project Progress — Case Zup/Itaú (POD99, Arquiteto de Dados)

> Checkpoint do estado atual da implementação. Atualizar após concluir qualquer tarefa importante.
> Nunca marcar algo como concluído sem validação real (rodar, testar, ou `terraform plan`/`apply` de fato).

## STEP atual

**Dia 1 do plano (scaffold + infra base) — completo.**
Próximo: Dia 2 (job Bronze).

## Última implementação validada

`terraform apply -var="aws_profile=pod99-case"` executado com sucesso: **13 recursos criados, 0 erros**. Confirmado que os recursos existem de fato na AWS (não só no state do Terraform), via `aws s3 ls`, `aws glue get-database` e `aws iam get-role` com o profile `pod99-case`:
- Bucket `pod99-fin-case-dev-952376464712` existe, com os 6 prefixos (`raw/`, `bronze/`, `silver/`, `gold/`, `quarantine/`, `ref/`).
- Database do Glue Catalog `pod99_fin_case_dev` existe.
- Role IAM `arn:aws:iam::952376464712:role/pod99-fin-case-dev-glue-job-role` existe.

Custo confirmado: $0 (apenas bucket vazio, database vazio, e IAM — nenhum serviço cobrado foi usado).

## O que funciona (validado)

- **Diagrama de arquitetura** em Mermaid: `architecture/diagram.mmd`.
- **Data contract as code**: `data_contracts/fin_contabilidade_saldo_contrato.yaml` (schema + regras de DQ do desafio, formalizadas).
- **Gerador sintético de dados**: `data_generator/generate_synthetic_transactions.py` — testado localmente (20.000 transações, 500 contas), gera Parquet particionado por `dt_processamento`, domínio COSIF, e injeta violações de DQ via `--dq-error-rate` (validado: valores negativos e `id_transacao` duplicado apareceram corretamente na amostra de teste).
- **Infra base criada e confirmada na AWS real** (`infra/terraform/`, conta `952376464712`, região `us-east-2`, profile `pod99-case`):
  - Bucket `pod99-fin-case-dev-952376464712` com prefixos raw/bronze/silver/gold/quarantine/ref, encryption AES256, bloqueio de acesso público.
  - Database do Glue Data Catalog: `pod99_fin_case_dev`.
  - Role IAM least-privilege para os jobs Glue: `pod99-fin-case-dev-glue-job-role`.
  - Custo real confirmado: $0.
- **AWS CLI configurado**: profile dedicado `pod99-case`, usuário IAM `pod99-case-terraform` isolado de qualquer credencial de trabalho (BlueMetrics/Lobby CRE.ai). Confirmado via `aws sts get-caller-identity --profile pod99-case`.
- **Terraform 1.16.2** instalado via winget.

## Pendências

- [x] ~~`terraform apply` dos 13 recursos base (S3 + IAM + Glue Catalog)~~ — feito e validado, custo real $0.
- [ ] Configurar alarme do AWS Budgets **antes** do primeiro apply que envolva custo real (Glue Jobs).
- [ ] Job Bronze (`jobs/bronze_ingest.py`) — ingestão + validação do contrato + quarentena.
- [ ] Job Silver (`jobs/silver_transform.py`) — dedup, join COSIF, merge idempotente.
- [ ] Job Gold (`jobs/gold_aggregate.py`) — saldo por contrato/conta, reconciliação.
- [ ] Módulo Terraform para DynamoDB (controle de lote/idempotência).
- [ ] Módulo Terraform para Step Functions + EventBridge (orquestração).
- [ ] Módulo Terraform para CloudWatch (logs estruturados, métricas, alarmes).
- [ ] Testes unitários (`pytest` + SparkSession local) e testes de DQ.
- [ ] Execução local via Docker (`amazon/aws-glue-libs`) antes de rodar na AWS.
- [ ] ADRs adicionais: PySpark vs Scala, Iceberg vs Delta/Hudi, Step Functions vs Airflow/MWAA, estratégia de particionamento/idempotência.
- [ ] Seção de dimensionamento para produção (custo/tempo estimado no volume real: 80M contas, 300M transações/dia).
- [ ] README final consolidando tudo.
- [ ] Empacotamento ZIP para entrega.

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

## Arquivos importantes

- `docs/company_job_description.md`, `docs/desafio-tecnico-pod99-arquiteto-de-dados.md` — vaga e desafio técnico originais.
- `docs/claude_global.md`, `docs/data_eng_checklist.md` — preferências e checklist a seguir em toda implementação.
- `docs/project_progress.md` — este arquivo.
- `architecture/diagram.mmd` — diagrama de arquitetura.
- `architecture/ADRs/` — decisões arquiteturais registradas.
- `data_contracts/fin_contabilidade_saldo_contrato.yaml` — contrato de dados.
- `data_generator/generate_synthetic_transactions.py` — gerador de dados sintéticos.
- `infra/terraform/` — IaC (root + módulos `s3`, `iam`, `glue_catalog`).
- Plano detalhado (fora do repo): `C:\Users\Guilherme Ruschel\.claude\plans\olhar-os-mds-na-replicated-lake.md`.

## Comandos importantes

```bash
# Gerar dados sintéticos
python data_generator/generate_synthetic_transactions.py \
  --output-dir data_generator/output --num-accounts 20000 \
  --total-transactions 1000000 --num-days 30 --dq-error-rate 0.03

# Instalar dependências do gerador
pip install -r data_generator/requirements.txt

# Verificar identidade AWS
aws sts get-caller-identity --profile pod99-case

# Terraform
cd infra/terraform
terraform init -input=false
terraform plan -input=false -var="aws_profile=pod99-case"
terraform apply -var="aws_profile=pod99-case"   # ainda NÃO executado
```

## Problemas e soluções

| Problema | Solução |
|---|---|
| Terraform CLI não estava instalado | `winget install --id Hashicorp.Terraform` (atenção: o id correto é `Hashicorp.Terraform`, com "H" maiúsculo apenas no início — `HashiCorp.Terraform` não é encontrado) |
| Profiles AWS pré-existentes (`default`, `glue-dev`) com credenciais inválidas/expiradas e origem incerta | Não reutilizados — criado profile novo isolado `pod99-case` com usuário IAM dedicado `pod99-case-terraform`, para não arriscar misturar com conta de trabalho |
| `pyarrow` não estava instalado no ambiente Python local | `pip install -r data_generator/requirements.txt` |

## Mudanças de planejamento

- Cenário B (Bedrock/MCP/OpenLineage/SDD formal) descartado para esta entrega — foco total no Cenário A.
- Região mudou de `sa-east-1` (proposta inicial, argumento de residência de dados) para `us-east-2` (decisão prática do usuário, por já ser a conta/região em uso e focar em corte de custo).
- IAM do deployer definido como `AdministratorAccess` (não policy customizada) para não consumir tempo do prazo de 5 dias úteis ajustando permissões a cada recurso novo.

## Próximo passo

Iniciar o job **Bronze** (`jobs/bronze_ingest.py`): ingestão + validação do contrato de dados + quarentena. Validar localmente via Docker (`amazon/aws-glue-libs`) antes de qualquer execução paga na AWS. Depois, testes unitários do Bronze (Dia 2 do plano).

# ADR-007: Step Functions como orquestrador, não Airflow/MWAA

## Contexto
A JD cita Step Functions, EventBridge **e** Airflow como ferramentas de orquestração usadas no time. O desafio pede "considerar estratégias de re-processamento (idempotência)" e implicitamente uma forma de encadear Bronze → Silver → Gold. É preciso escolher um orquestrador para este pipeline de 3 etapas sequenciais.

## Decisão
Usar **AWS Step Functions** (com a integração nativa `glue:startJobRun.sync`), disparado por **EventBridge**.

## Alternativas consideradas
- **Amazon MWAA (Managed Airflow)**: motor de orquestração mais rico — DAGs em Python, sensores, retries configuráveis por task, UI de observabilidade madura, backfills, e é a ferramenta citada na JD junto com Step Functions. Trade-off real: MWAA cobra por ambiente rodando 24/7 (custo mínimo de um ambiente `mw1.small` gira em torno de dezenas de dólares/mês, independente de quantos pipelines rodam nele) — incompatível com o orçamento "gasto mínimo" deste case. Para 3 tasks sequenciais sem lógica de DAG complexa (branching condicional, sensores externos, backfill em massa), a ferramenta é desproporcional ao problema.
- **Orquestração "manual"** (um Lambda ou script chamando os 3 jobs em sequência): mais barato ainda, mas perde a máquina de estados visual, o tratamento de erro declarativo (`Catch`/`Retry` do ASL), e o histórico de execuções nativo do Step Functions (`aws stepfunctions describe-execution`, `get-execution-history`) — que foi, na prática, a ferramenta usada para diagnosticar o bug real de `ResultPath` encontrado nesta implementação (ver `docs/test_log.md` §4.13).

## Justificativa
- **Custo**: Step Functions Standard cobra por transição de estado (US$25 por milhão de transições) — a execução completa deste pipeline usa ~9 transições (3 estados × início/fim + catch), essencialmente gratuito no volume deste case e mesmo em produção D+1 (1 execução/dia = ~270 transições/mês).
- **Integração nativa com Glue**: `arn:aws:states:::glue:startJobRun.sync` faz o polling da conclusão do job automaticamente — sem precisar de Lambda de espera nem de lógica de retry customizada para "job ainda rodando".
- **Escopo do problema real**: 3 etapas sequenciais com uma política de erro simples (falhar tudo e alertar) é exatamente o caso de uso para o qual Step Functions foi desenhado — DAGs complexas com dependências condicionais, branches paralelos ou sensores de longa duração são onde Airflow/MWAA compensa o custo fixo.
- **Observabilidade nativa**: histórico de execução no console/CLI sem configuração adicional (usado diretamente para depurar o bug do `ResultPath`, ver ADR e test log).

## Consequências
- Se o pipeline crescer para dezenas de datasets com dependências cruzadas, agendamento complexo (backfills, SLA por dataset, catálogo de DAGs versionado), branching condicional real, ou se a equipe já operar MWAA para outros pipelines (custo fixo já absorvido), a decisão deveria ser revisitada — Step Functions não escala bem como "motor de orquestração de plataforma de dados inteira" no sentido que o Airflow escala (nº de DAGs, comunidade de operators).
- ASL (Amazon States Language, a definição em JSON da máquina de estados) tem uma curva de aprendizado própria e menos expressividade que DAGs Python do Airflow para lógica condicional complexa — aceitável para 3 estados sequenciais, seria um ponto de dor para pipelines muito mais ramificados.
- O disparo por EventBridge está com a regra `DISABLED` (ver `infra/terraform/modules/orchestration/main.tf`) — calcular a data D-1 dinamicamente exigiria uma Lambda pequena ou EventBridge Scheduler com expressão de data, fora do escopo deste case (documentado, não escondido).

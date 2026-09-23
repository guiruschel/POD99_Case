# ADR-008: Estratégia de particionamento e idempotência

## Contexto
O desafio pede explicitamente para "considerar estratégias de re-processamento (idempotência)". Esta não é uma decisão única — cada camada (Bronze/Silver/Gold) tem uma natureza de escrita diferente, e a estratégia certa muda por camada. Uma delas (`overwritePartitions` no Bronze) só foi descoberta como necessária depois de um bug real em produção (ver `docs/test_log.md` §4.8), não foi prevista de antemão — vale registrar a decisão final e por que ela não foi óbvia desde o início.

## Decisão
- **Particionamento**: todas as tabelas Iceberg (Bronze/Silver/Gold) particionadas por `dt_processamento`, espelhando a coluna de particionamento do dado de origem (Parquet em `raw/`) e o campo usado pelo SLA regulatório ("fechamento contábil D+1").
- **Idempotência por camada**:
  - **Bronze**: `overwritePartitions()` (overwrite dinâmico de partição do Iceberg). Substituído de `.append()` depois do achado real de duplicação (ver ADR abaixo/test log).
  - **Silver**: `MERGE INTO ... ON id_transacao` (upsert por chave de negócio).
  - **Gold**: `overwritePartitions()`, igual ao Bronze.
- **Controle de lote**: tabela DynamoDB (`RECEIVED/PROCESSING/PROCESSED/FAILED` por `id_lote` + `job_name`) para visibilidade de status entre execuções, complementar (não substituto) à idempotência da escrita.

## Alternativas consideradas
- **`append()` em todas as camadas + deduplicação só na leitura** (ex.: `ROW_NUMBER() OVER (PARTITION BY id_transacao ORDER BY ...)` em toda query de consumo): rejeitado — empurra o custo de deduplicação para *todo* consumidor da tabela (Athena, qualquer job downstream), repetidamente, em vez de resolver uma vez na escrita. Também foi a causa raiz do bug real do Bronze (ver abaixo).
- **`MERGE INTO` em todas as camadas** (Bronze e Gold também): tecnicamente possível, mas desnecessário — Bronze e Gold não têm uma chave natural de "linha" para comparar campo a campo da forma que o Silver tem (`id_transacao`); são recomputados inteiramente a partir da entrada (`raw/` inteiro no Bronze, o dia inteiro da Silver no Gold). Substituir a partição inteira é mais simples, mais barato computacionalmente (sem join de comparação linha a linha) e igualmente correto para esse padrão de escrita.
- **Particionar por `cod_agencia` ou `id_contrato` em vez de/além de `dt_processamento`**: rejeitado para este volume — a query de acesso dominante é sempre "processar/consultar o dia X" (SLA D+1), então partition pruning por data é o que realmente importa. Uma segunda dimensão de particionamento (ex.: `dt_processamento` + bucket de `cod_agencia`) seria uma otimização válida na escala real de produção (ver seção de dimensionamento no README), não neste volume de teste.

## Justificativa (o achado real que definiu a decisão do Bronze)
A primeira versão do Bronze usava `.append()` quando a tabela já existia. Funcionou nos testes locais e nas primeiras execuções reais — porque, até então, cada execução real processava dado novo. O bug só apareceu quando o Bronze foi reexecutado **sem nenhum dado novo** (rodando de novo o mesmo `raw/`, para testar o batch control): a tabela duplicou inteira (9.746 linhas para 4.873 `id_transacao` distintos), porque o job lê o prefixo `raw/` inteiro a cada execução — não é incremental por arquivo. `append()` presumia implicitamente que cada execução trazia só dado novo, uma suposição nunca verdadeira para este job.

A correção (`overwritePartitions()`) elimina essa suposição: reprocessar sempre produz o mesmo resultado, não importa quantas vezes ou com que dado (desde que `raw/` não mude entre execuções). Isso é a definição prática de idempotência, e é mais forte do que "não falha ao reprocessar" — garante que o *resultado* de reprocessar é sempre igual.

## Consequências
- Qualquer novo job escrito neste pipeline deve, por padrão, assumir que **vai** ser reexecutado (por engano, por retry automático do orquestrador, ou por reprocessamento intencional de um dia com problema) e escolher a estratégia de idempotência adequada à sua natureza de escrita (chave de upsert → `MERGE INTO`; recomputação total → `overwritePartitions`) antes de ir para produção, não depois de um incidente.
- O teste unitário de lógica de negócio (pytest) **não pega esse tipo de bug** — ele testa a transformação isolada, não o padrão de escrita/gravação. Só foi encontrado rodando de verdade na AWS e validando via Athena (`COUNT(*)` vs `COUNT(DISTINCT id_transacao)`), reforçando por que este projeto trata "rodar na AWS real" como validação obrigatória, não opcional (ver protocolo em `docs/project_progress.md`).
- Em produção, a estratégia de Bronze mudaria de "reler `raw/` inteiro" para ingestão incremental real (rastreamento de quais arquivos já foram lidos, via um checkpoint/watermark), o que tornaria `overwritePartitions()` ainda mais barato (só a partição do dia novo seria reescrita, não potencialmente todo o histórico) — fora do escopo deste case, mas é o próximo passo natural de evolução.

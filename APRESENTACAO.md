# Apresentação do Case — por onde começar

Este documento substitui a sessão de defesa técnica presencial. Ele existe para que quem avaliar este case consiga acompanhar sozinho o raciocínio que normalmente eu explicaria ao vivo: o que foi construído, por que cada decisão não-óbvia foi tomada daquele jeito, e onde encontrar a prova de que tudo isso rodou de verdade — não só no papel.

Se você só puder ler um documento antes de abrir o código, leia este.

## Como este pacote está organizado

| Você quer... | Vá para... |
|---|---|
| Entender a arquitetura, como rodar o pipeline, e ver o dimensionamento para produção | [`README.md`](README.md) |
| Ver a lista de decisões arquiteturais formais, cada uma com contexto/alternativas/consequências | [`architecture/ADRs/`](architecture/ADRs/) |
| Ver o diagrama da arquitetura completa | [`architecture/project-diagram.png`](architecture/project-diagram.png) |
| Confirmar que tudo foi de fato executado (comandos reais, resultados literais, bugs encontrados e corrigidos) | [`docs/test_log.md`](docs/test_log.md) |
| Ver evidência visual da execução real na conta AWS (prints do console, já que a conta não pode ser compartilhada) | [`docs/evidencias/`](docs/evidencias/) |
| Entender o histórico de decisões de planejamento e o estado do projeto ao longo do desenvolvimento | [`docs/project_progress.md`](docs/project_progress.md) |

Este documento (`APRESENTACAO.md`) cobre o "porquê" em prosa. Os outros cobrem o "o quê" e o "como" em detalhe técnico.

## O contexto

O desafio pedia uma plataforma de cálculo de saldo por contrato para o Itaú Unibanco: ~80 milhões de contas, ~300 milhões de transações/dia, fechamento contábil regulatório D+1, usando Spark/Glue sobre um Lakehouse em Apache Iceberg. Minha experiência atual (arquitetura Lakehouse Bronze/Silver/Gold com Apache Iceberg em produção) é essencialmente o núcleo técnico deste desafio — por isso decidi tratar isso não como um exercício teórico, mas como eu trataria um projeto real: implementar de verdade, numa conta AWS real, com gasto mínimo e controlado, e documentar cada decisão e cada problema real encontrado no caminho.

Isso molda tudo que vem a seguir. Este não é um repositório de código que "deveria funcionar" — é um repositório onde cada camada, cada job, cada peça de infraestrutura foi executada de verdade na AWS e validada com evidência (contagens de linhas via Athena, status reais no DynamoDB, métricas reais no CloudWatch), antes de ser marcada como concluída. Esse foi o protocolo que segui do início ao fim: **nunca marcar algo como pronto sem rodar e confirmar**.

## Escopo: o que entrou e o que ficou de fora, e por quê

Defini dois cenários possíveis logo no início: um cenário sólido e completo, aderente ao que o desafio pediu (o que chamei de Cenário A), e um cenário mais ambicioso com extras de IA generativa, observabilidade de linhagem de dados (OpenLineage) e desenvolvimento orientado por especificação formal (Cenário B). Escolhi o Cenário A deliberadamente — não por falta de tempo, mas porque entregar bem o que foi pedido vale mais do que entregar parcialmente algo maior. Os itens do Cenário B ficam como resposta pronta para "o que você faria a seguir", não como trabalho fingido.

Dentro do próprio Cenário A, um item que estava no escopo original (Lake Formation) acabou não sendo implementado — não por esquecimento, mas por uma decisão consciente tomada na reta final: habilitar o modelo de permissões do Lake Formation em cima de uma infraestrutura já validada por IAM puro é uma mudança de modelo de segurança, não um acréscimo aditivo, e arriscava quebrar acessos que já funcionavam, sem sobrar tempo para testar a migração com cuidado. Prefiro documentar esse gap com honestidade (ver [ADR-009](architecture/ADRs/009-lake-formation-not-enabled.md)) a fingir que foi feito ou a esconder que estava no plano original.

## As decisões que mais importam (e por que)

Cada uma dessas tem um ADR completo com alternativas consideradas e consequências — aqui está o resumo do raciocínio, em prosa:

**Apache Iceberg format-version 2, não 3, mesmo o desafio pedindo V3 explicitamente.** Esta é a decisão que melhor representa como abordei o projeto inteiro. Implementei com V3, rodei na AWS, e ao consultar a tabela via Athena (que o próprio desafio exige como camada de consumo) a consulta falhou: o motor do Athena ainda não lê tabelas Iceberg V3. Não é bug meu — é limitação real da plataforma, confirmada checando a versão do engine. A escolha foi entre seguir a instrução literal (V3) e quebrar a consulta, ou desviar da instrução e manter o dado utilizável. Escolhi manter o dado consultável. Isso só foi possível porque eu estava rodando contra a AWS real — num ambiente só local/simulado, esse problema nunca teria aparecido, e eu teria entregado uma tabela "correta" no papel mas inutilizável na prática.

**Um bug de idempotência real, encontrado rodando o pipeline de verdade.** O job Bronze lê o prefixo inteiro de dados brutos a cada execução (não é incremental por arquivo). A primeira versão gravava com `append()` quando a tabela já existia — funcionou nos testes e nas primeiras execuções reais, porque até então cada execução trazia dado novo. Quando reexecutei o Bronze sem nenhum dado novo (testando outra parte do sistema), a tabela duplicou inteira: 9.746 linhas para 4.873 transações distintas. Só percebi porque validei via Athena (`COUNT(*)` vs `COUNT(DISTINCT id_transacao)`) antes de seguir em frente — não confiei apenas no log "sucesso" do job. Corrigi trocando para overwrite dinâmico de partição, que torna qualquer reexecução idempotente por definição. Esse é exatamente o tipo de problema que testes unitários isolados não pegam (eles testam a lógica de transformação, não o padrão de escrita) — só aparece rodando de verdade, com dados reais, contra a infraestrutura real.

**Step Functions em vez de Airflow/MWAA**, apesar de a vaga citar as duas ferramentas. MWAA cobra por ambiente rodando 24/7 — um custo fixo mensal considerável, incompatível com um pipeline de 3 etapas sequenciais e com o orçamento mínimo deste case. Step Functions cobra por transição de estado, essencialmente gratuito neste volume. A troca é honesta: Airflow ganha em DAGs complexas com muita ramificação condicional; para um pipeline linear Bronze→Silver→Gold, Step Functions é a ferramenta certa pelo problema real, não a mais "impressionante" no papel.

**PySpark em vez de Scala.** O pipeline usa quase inteiramente a API DataFrame/SQL do Spark (sem UDFs linha-a-linha), que compila para o mesmo plano de execução independente da linguagem — a penalidade clássica de performance do PySpark não se aplica aqui. Python também é minha linguagem de trabalho atual, o que reduziu risco de erro e acelerou a implementação dentro do prazo.

**Desenvolvimento local via Docker antes de qualquer execução paga na AWS.** O host tem Java 21; o Spark 3.5 do Glue 5.0 suporta oficialmente até Java 17. Em vez de forçar uma instalação paralela de JDK no host, rodei tudo dentro da imagem oficial `amazon/aws-glue-libs`, com um catálogo Iceberg local em disco — fidelidade real ao ambiente do Glue, sem gastar um centavo até a lógica estar validada. Só depois de validado localmente é que qualquer coisa rodava contra a AWS de verdade.

## O ciclo de trabalho que segui (e por que ele importa mais que qualquer decisão individual)

A disciplina por trás deste projeto foi: **escrever a lógica → testar localmente com `pytest` (grátis) → validar contra um catálogo Iceberg local via Docker (grátis) → só então rodar contra a AWS real (custo real, pequeno e monitorado) → validar o resultado com uma consulta independente (Athena, DynamoDB, CloudWatch) → só então marcar como concluído**. Todo o [`docs/test_log.md`](docs/test_log.md) é o registro cronológico desse ciclo — cada comando, cada resultado literal, cada bug real e sua correção.

Essa disciplina é o motivo pelo qual encontrei (e corrigi) três problemas reais que nenhum teste unitário isolado teria pego: a incompatibilidade Iceberg V3/Athena, a duplicação no Bronze, e um bug de referência de dados no Step Functions (o output de uma task substituindo o input original — corrigido com `ResultPath: null`, ver [ADR-008](architecture/ADRs/008-partitioning-idempotency-strategy.md) e o test log). Nenhum desses apareceria numa demonstração só local ou só teórica.

## Infraestrutura e ferramentas internas

- **Terraform** (10 módulos: `s3`, `iam`, `glue_catalog`, `glue_jobs`, `dynamodb`, `orchestration`, `monitoring`, `budget`) — toda a infraestrutura provisionada como código, sem clique manual no console. IAM do deployer usa `AdministratorAccess` na conta sandbox pessoal (velocidade de iteração no prazo de 5 dias), mas as roles de **execução** dos jobs são sempre least-privilege, escopadas por recurso.
- **AWS Budgets** com teto de US$5/mês configurado *antes* do primeiro `apply` real — rede de segurança para o "gasto mínimo possível". O gasto real medido (via `aws glue get-job-runs`, não estimativa) ficou em menos de US$1 no total, incluindo todas as execuções de debug.
- **Perfil AWS isolado** (`pod99-case`, usuário IAM dedicado), separado de qualquer credencial de trabalho.
- Cada Terraform `apply` real foi precedido de `plan` revisado manualmente — nenhuma mudança de infraestrutura foi aplicada às cegas.

## O que eu faria a seguir, se este fosse um projeto real continuando

- Ingestão incremental de verdade no Bronze (hoje relê o prefixo inteiro por execução — aceitável no volume de teste, não em produção).
- Habilitar Lake Formation com segurança de coluna/linha sobre dado regulatório (COSIF), com tempo dedicado a testar a migração do modelo de permissões.
- Os itens do Cenário B: observabilidade de linhagem de dados (OpenLineage), e uso de IA generativa em pontos específicos (ex.: classificação assistida de novos códigos COSIF, geração de relatórios de reconciliação em linguagem natural para o time contábil).
- Um teste de carga real com volume representativo antes de comprometer o dimensionamento de workers estimado no README (a seção de dimensionamento é uma conta de ordem de grandeza com premissas explícitas, não um benchmark medido).

## Uma nota sobre uso de IA neste desenvolvimento

O desafio permite e encoraja o uso de IA. Usei o **Claude Code** como par de desenvolvimento ao longo de todo o projeto.


**O problema que esse processo resolve**: uma sessão de IA tem janela de contexto limitada — em um projeto de 5 dias, com múltiplas sessões de trabalho, a IA "esquece" o que foi decidido e feito em sessões anteriores assim que o contexto estoura ou uma nova conversa começa. Sem estrutura, isso vira retrabalho, decisões inconsistentes entre sessões, ou coisas marcadas como prontas duas vezes (ou nenhuma). Resolvi isso com dois documentos vivos, que o Claude Code é instruído a ler antes de continuar qualquer trabalho:

- **[`docs/project_progress.md`](docs/project_progress.md) — o checkpoint de estado.** Estruturado sempre com as mesmas seções: STEP atual, última implementação validada, o que funciona, pendências, decisões técnicas/arquiteturais (numa tabela, com a justificativa de cada uma), arquivos importantes, comandos importantes, problemas e soluções encontrados, mudanças de planejamento, e o próximo passo. No início de cada sessão nova, o protocolo era sempre o mesmo: ler esse arquivo primeiro, inspecionar de verdade os arquivos relacionados ao passo atual (não confiar cegamente no que o markdown diz — conferir se bate com o código/infra real), apresentar um resumo do estado antes de continuar, e só então seguir implementando. Isso transformou o que poderia ter sido 5 dias de contexto fragmentado em algo que se lê como um projeto único e coerente.
- **[`docs/test_log.md`](docs/test_log.md) — o log cronológico de evidência.** Toda vez que algo era testado ou executado — localmente ou na AWS real — entrava aqui: o comando exato, o resultado literal (não resumido), e quando dava errado, a causa raiz e a correção aplicada. Este arquivo é, na prática, o motivo pelo qual eu consigo afirmar com confiança neste documento que os bugs reais (duplicação no Bronze, incompatibilidade Iceberg V3/Athena, o `ResultPath` do Step Functions) realmente aconteceram e foram corrigidos — não é uma reconstrução de memória, é o registro no momento em que aconteceu.

**A regra que governou tudo**, escrita explicitamente nas instruções do projeto e repetida em toda sessão: **nunca marcar algo como concluído sem validação real** — rodar de fato, testar de fato, ou `terraform plan`/`apply` de fato. Isso na prática significava que "o código está escrito" nunca foi suficiente; a barra sempre foi "eu rodei isso e confirmei o resultado com uma fonte independente" (uma contagem via Athena, um item lido direto do DynamoDB, uma métrica puxada do CloudWatch). Essa disciplina — não a IA em si — é o que descobriu os três bugs reais documentados neste case.

**A divisão de trabalho real**: eu tomei toda decisão de arquitetura e de escopo (Cenário A vs B, quais serviços AWS usar, quando desviar de uma instrução literal do desafio, como reagir a cada bug encontrado); o Claude Code implementou, testou, e manteve a disciplina de documentação junto comigo. Um exemplo concreto de onde o julgamento humano foi decisivo: fui eu quem, rodando uma query manual no Athena, descobri que o Iceberg V3 não era suportado — não foi a IA que "achou" esse problema sozinha, fui eu inspecionando o resultado real em vez de aceitar "o job rodou com sucesso" como prova suficiente.

Duas outras instruções permanentes seguidas em todo o desenvolvimento, também registradas como arquivos no repositório: [`docs/claude_global.md`](docs/claude_global.md) (preferir soluções simples, sem over-engineering, explicar decisões arquiteturais, nunca expor segredos, nunca dar push sem aprovação explícita) e [`docs/data_eng_checklist.md`](docs/data_eng_checklist.md) (checklist de confiabilidade, qualidade de dado, performance, observabilidade, segurança e testes, aplicado a cada camada do pipeline).

Toda decisão arquitetural, cada trade-off e cada correção de bug documentados aqui eu entendo e sei defender em detalhe — a IA acelerou a execução e ajudou a manter a disciplina de processo, mas não substituiu o julgamento sobre o que construir, por quê, e quando um resultado "bom o suficiente" na verdade não estava.

# ADR-009: Lake Formation documentado, não habilitado neste ambiente

## Contexto
O plano inicial do Cenário A incluía Lake Formation ("permissões mínimas documentadas/aplicadas sobre o catálogo") como item dentro do escopo comprometido — diferente dos itens do Cenário B (Bedrock/MCP/OpenLineage/SDD), que foram descartados desde o início. O diagrama de arquitetura (`architecture/diagram.mmd`) já mostra Lake Formation como parte da camada de governança.

Ao chegar na fase de finalização, o restante do pipeline (Bronze/Silver/Gold, orquestração, DynamoDB, CloudWatch) já estava implementado e validado na AWS real usando um modelo de permissões **puramente IAM** sobre o Glue Data Catalog (policies escopadas por database/tabela, ver `infra/terraform/modules/iam/main.tf`).

## Decisão
**Não habilitar** Lake Formation neste ambiente. Documentar como item de governança avançada, desenhado mas não executado.

## Justificativa
Habilitar Lake Formation numa conta que já opera com permissões IAM puras sobre o Glue Data Catalog não é aditivo por padrão — é uma mudança de modelo. O modo `IAMAllowedPrincipals` (compatibilidade retroativa, ligado por padrão em contas que nunca usaram LF) faz o Lake Formation "sair do caminho" e deixar o IAM decidir, mas o caminho recomendado da AWS para adotar LF de verdade é revogar esse modo e conceder permissões explícitas (`lakeformation:GrantPermissions`) por tabela/coluna. Se essa revogação for feita sem replicar corretamente cada grant necessário, o resultado real é **perda de acesso** para quem já funcionava — nas palavras práticas deste projeto: o job Glue que grava a tabela Silver, o Athena que consulta o Gold, tudo que já foi validado na AWS ao longo de 4 dias de trabalho.

Fazer essa migração de modelo de permissão de forma segura exige tempo dedicado de teste (validar cada grant, cada papel, cada tabela, antes e depois) — exatamente o tipo de mudança que não deveria ser feita às pressas na etapa de finalização, sob risco de quebrar algo já validado sem sobrar tempo para corrigir antes da entrega.

## Alternativas consideradas
- **Habilitar mesmo assim, com cuidado**: rejeitado por risco/tempo — o ganho (demonstrar 1 tela a mais de configuração de permissões) não compensa o risco de regressão em algo que já está validado ponta a ponta.
- **Remover Lake Formation do diagrama e fingir que nunca esteve no escopo**: rejeitado — seria menos honesto do que registrar a decisão real. A capacidade de dizer "eu sabia que isso estava no escopo, avaliei o risco de implementar agora, e decidi documentar em vez de arriscar" é exatamente o tipo de julgamento que a seção 4 do desafio pede para a defesa técnica.

## O que uma implementação real faria
- Registrar o bucket S3 do data lake como Data Lake Location (`aws lakeformation register-resource`).
- Migrar o database `pod99_fin_case_dev` para o modelo de permissões LF (`lakeformation:GrantPermissions`), revogando `IAMAllowedPrincipals` de forma controlada, tabela por tabela.
- Conceder permissões `SELECT`/`DESCRIBE` na granularidade real necessária — por exemplo, mascarar ou restringir colunas sensíveis (`valor_lancamento`, `id_conta`) para grupos de consumidores que só precisam de agregados (Gold), sem acesso a transação individual (Silver/Bronze) — um caso de uso real de segurança de dados regulatórios (COSIF) que faz mais sentido em produção do que numa conta de demonstração pessoal.

## Consequências
- A governança de acesso deste projeto, como está, é IAM-only: least-privilege por role/recurso (ver ADR-002 e as policies em `infra/terraform/modules/iam/`), sem controle de coluna/linha.
- Este é um gap conhecido e documentado, não um gap descoberto tarde demais — fica registrado como próximo passo explícito para uma eventual continuidade do projeto.

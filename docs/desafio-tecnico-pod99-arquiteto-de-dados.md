# Desafio Técnico

> AWS ProServe — Desafio Técnico | Confidencial
> POD99 — Nova Plataforma de Finanças | Arquiteto de Dados

## 1. Introdução e Contexto

Este documento descreve o desafio técnico para a posição de Arquiteto de Dados no time da POD99 da AWS para a construção da nova plataforma de Finanças.

O papel de Arquiteto de Dados no ProServe exige:

- Domínio técnico em plataformas de processamento distribuído (Apache Spark)
- Capacidade de traduzir requisitos de negócio em arquiteturas de dados escaláveis
- Experiência com infraestrutura como código e práticas DevOps
- Habilidade de comunicar trade-offs técnicos de forma clara para stakeholders

Esperamos que o candidato demonstre não apenas a habilidade de implementar, mas principalmente a capacidade de tomar decisões arquiteturais fundamentadas e defendê-las em uma sessão de revisão técnica. O uso de AI é totalmente permitido e até encorajado.

## 2. Caso de Negócio — Cálculo de Saldo por Contrato

### 2.1 Contexto do Problema

A área financeira do Itaú Unibanco necessita calcular diariamente o saldo consolidado de conta corrente por contrato para toda a sua base de clientes. Este processo é crítico para a contabilidade regulatória, conciliação de balanço.

O cenário envolve:

- Mais de 80 milhões de contas ativas
- Múltiplos contratos por conta (crédito, investimento, seguros, consórcio)
- Volume diário de centenas de milhões de transações (débitos, créditos, tarifas, juros)
- Necessidade de fechamento contábil até as 06:00 do dia seguinte (D+1)
- Conformidade com normas COSIF (Plano Contábil das Instituições Financeiras)

### 2.2 Volumetria e Requisitos de Performance

| Métrica | Valor Esperado |
| --- | --- |
| Contas ativas | ~80 milhões |
| Contratos por conta (média) | 3 a 5 contratos |
| Transações diárias | ~300 milhões |
| SLA de processamento | < 1 horas (D+0 22h → D+1 02h) |
| Janela de fechamento contábil | Até 06:00 D+1 |
| Retenção histórica | 5 anos (hot) + 10 anos (cold) |

### 2.3 Contrato de Dados — Exemplo

Abaixo está um exemplo de contrato de dados para o dataset de contabilidade que alimenta o cálculo de saldo. O candidato deve usar este contrato como base para modelar as camadas da arquitetura Medallion.

**Nome do Dataset:** `fin_contabilidade_saldo_contrato`

**Domínio:** Financeiro / Contabilidade

**Owner:** Squad Contábil — VP Finanças

**SLA de Disponibilidade:** D+1 às 06:00 BRT

**Classificação:** Confidencial — Dados regulatórios

**Formato de origem:** Parquet (particionado por data de processamento)

#### Schema do Contrato (Bronze → Ingestão)

| Campo | Tipo | Nullable | Descrição |
| --- | --- | --- | --- |
| id_transacao | STRING | Não | Identificador único da transação (UUID) |
| id_contrato | STRING | Não | Identificador do contrato do cliente |
| id_conta | STRING | Não | Número da conta corrente |
| cod_agencia | STRING | Não | Código da agência |
| tipo_contrato | STRING | Não | CC, POUP, CDB, LCI, CONSORCIO, SEGURO |
| tipo_lancamento | STRING | Não | DEBITO, CREDITO, TARIFA, JUROS, IOF |
| valor_lancamento | DECIMAL(18,2) | Não | Valor monetário do lançamento em BRL |
| dt_lancamento | TIMESTAMP | Não | Data/hora do lançamento contábil |
| dt_processamento | DATE | Não | Data de processamento (partição) |
| cod_cosif | STRING | Sim | Código contábil COSIF para classificação |
| flag_estorno | BOOLEAN | Não | Indica se o lançamento é um estorno |
| id_lote | STRING | Não | Identificador do lote de processamento |

#### Regras de Qualidade (Data Quality)

- `id_transacao` deve ser único globalmente
- `valor_lancamento > 0` (estornos usam `flag_estorno = true`)
- `dt_lancamento <= dt_processamento`
- `cod_cosif` deve existir na tabela de domínio COSIF (referencial)
- Completude: campos NOT NULL não podem conter valores vazios ou nulos

#### Output Esperado (Gold)

- Saldo consolidado por contrato (`id_contrato`) com data de referência
- Saldo consolidado por conta (`id_conta`) agregando todos os contratos
- Classificação contábil COSIF por tipo de contrato
- Métricas de reconciliação: total de débitos vs. créditos por agência
- Todo o dado deve ser escrito com Apache Iceberg V3

## 3. Requisitos Técnicos do Desafio

O candidato deve implementar um pipeline de processamento de dados utilizando Apache Spark como engine, executado no serviço AWS Glue. O pipeline deve:

- Utilizar PySpark ou Scala (justificar a escolha da linguagem)
- Implementar jobs Glue com configuração adequada de workers, timeout e retries
- Demonstrar conhecimento de otimizações Spark (partitioning, caching, broadcast joins)
- Implementar tratamento de erros e logging estruturado
- Utilizar Glue Data Catalog para gerenciamento de metadados
- Considerar estratégias de re-processamento (idempotência)
- Apresentar desenho de arquitetura de solução.

## 4. Uso de Inteligência Artificial

O uso de ferramentas de Inteligência Artificial é PERMITIDO e até encorajado como parte do processo de desenvolvimento. Acreditamos que a capacidade de utilizar IA de forma eficaz é uma competência relevante para o profissional moderno.

**Contudo, o candidato DEVE:**

- Saber explicar em detalhes cada decisão arquitetural tomada
- Justificar os trade-offs técnicos
- Demonstrar entendimento do código gerado — serão feitas perguntas específicas na defesa
- Ser capaz de propor alternativas e discutir quando a solução escolhida não é ideal

## 5. Prazo e Entregáveis

**Prazo:** 5 dias úteis a partir do recebimento deste documento.

**Formato de entrega:** arquivo ZIP.

**Defesa Técnica:**

Após a entrega, será agendada uma sessão de 60 minutos onde o candidato deverá:

- Apresentar a solução em 20 minutos (arquitetura, pipeline, infra)
- Responder a 40 minutos de perguntas técnicas sobre trade-offs e alternativas
- Demonstrar execução do pipeline (local com docker ou em conta AWS)

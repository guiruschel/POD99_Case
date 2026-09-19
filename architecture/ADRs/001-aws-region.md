# ADR-001: AWS region

## Contexto
Dados regulatórios financeiros brasileiros (COSIF) idealmente ficam em `sa-east-1` (São Paulo) por residência de dados. A conta AWS usada para esta demonstração já opera em `us-east-2` pensando unicamente em corte de custos pessoais.

## Decisão
Usar `us-east-2` na infraestrutura provisionada para este case (via `var.aws_region`), para não misturar contas/perfis e manter o setup local simples.

## Alternativas consideradas
- `sa-east-1`: mais correto para o cenário real de produção, porém exigiria configurar credenciais/perfil separados só para essa região.

## Consequências
- Este case demonstra a arquitetura e o pipeline, não a topologia de região final.
- Em uma implementação real para o Itaú, a região seria `sa-east-1` (ou multi-região com DR), documentado aqui como decisão consciente a ser revisitada fora do escopo da demo.

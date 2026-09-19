# ADR-002: Permissões do usuário IAM usado para o deploy (Terraform)

## Contexto
Terraform precisa criar recursos heterogêneos ao longo dos 5 dias (S3, IAM, Glue, Step Functions, EventBridge, DynamoDB, CloudWatch). É preciso decidir o nível de permissão do usuário/credencial usado para rodar `terraform apply`.

## Decisão
Usar um usuário IAM dedicado a este case (`pod99-case-terraform`, isolado de qualquer credencial de trabalho), com `AdministratorAccess`, nesta conta AWS pessoal/sandbox.

## Alternativas consideradas
- **Policy customizada e escopada por serviço**: mais correta como prática de least-privilege, mas exigiria ampliar a policy a cada novo tipo de recurso adicionado ao longo da semana, consumindo tempo do prazo de 5 dias úteis sem agregar valor à demonstração técnica em si.

## Consequências
- Isso é o *deployer* (identidade humana/CI que roda `terraform apply`), não a identidade de execução do pipeline.
- A **role de execução dos jobs Glue** (`infra/terraform/modules/iam`) já segue least-privilege de verdade: assume role apenas por `glue.amazonaws.com`, policy customizada restrita ao bucket do projeto, sem `AdministratorAccess`. É essa role, não o deployer, que representaria a identidade em produção.
- Justificativa aceitável porque a conta é pessoal, isolada, sem outros tenants/cargas de trabalho — risco de blast radius é baixo. Em um ambiente real de cliente (ex.: Itaú), o deployer seguiria least-privilege via pipeline de CI/CD com permissões escopadas por ambiente.

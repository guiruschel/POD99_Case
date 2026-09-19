# ADR-004: Desenvolvimento e testes locais via imagem oficial do Glue (Docker)

## Contexto
O desafio permite (e recomenda) validar a execução localmente via Docker antes de rodar em conta AWS real. A máquina de desenvolvimento tem Java 21 instalado, mas o Spark 3.5 (usado pelo AWS Glue 5.x) tem suporte oficial só até Java 17 — misturar os dois localmente tende a gerar erros de JVM (module system do Java 17+/21 bloqueando acesso reflexivo que o Spark usa internamente).

## Decisão
Rodar **todo** o desenvolvimento/teste local — tanto a execução dos jobs quanto os testes `pytest` — dentro do container oficial `amazon/aws-glue-libs:5.1.0`, nunca com PySpark instalado direto no host Windows.

## Alternativas consideradas
- **PySpark local no host** (`pip install pyspark`): mais rápido para iterar (sem overhead de `docker run` a cada teste), mas arrisca incompatibilidade de versão de Java, e a versão do Spark/Iceberg instalada via pip pode divergir sutilmente da que realmente roda no Glue (JARs do conector Iceberg, versão exata do Spark, variáveis de ambiente específicas do runtime Glue).

## Justificativa
- Fidelidade ao ambiente real: mesma versão de Spark, Java e JARs do Iceberg que rodam de fato no AWS Glue 5.x — reduz o risco de "funciona local, quebra na AWS".
- Evita gastar tempo do prazo de 5 dias úteis depurando incompatibilidade de JVM que não existiria em produção.
- O próprio desafio cita essa forma de validação como aceitável para a demonstração na defesa técnica.

## Consequências
- Cada execução de teste/job tem overhead de `docker run` (alguns segundos a mais que rodar nativo).
- Scripts (`scripts/run_local_bronze.sh`, `scripts/run_tests_docker.sh`) encapsulam essa complexidade, então o dia a dia de desenvolvimento continua sendo "um comando só".
- Os testes usam um catálogo Iceberg local do tipo `hadoop` (gravando em disco montado, dentro do container) em vez do Glue Data Catalog real — sem custo e sem depender de credenciais AWS durante o desenvolvimento. A execução contra o Glue Data Catalog real acontece só na demonstração final em conta AWS.

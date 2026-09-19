# ADR-003: PySpark vs Scala como linguagem dos jobs Glue

## Contexto
O desafio exige "Utilizar PySpark ou Scala (justificar a escolha da linguagem)" para os jobs de processamento no AWS Glue.

## Decisão
Usar **PySpark**.

## Alternativas consideradas
- **Scala**: vantagens reais e reconhecidas — roda nativo na JVM (sem overhead de serialização Python↔JVM em UDFs), tipagem estática pega erros em tempo de compilação, e historicamente é a linguagem "de primeira classe" do Spark (novas APIs às vezes chegam primeiro em Scala).

## Justificativa
- Este pipeline usa quase exclusivamente a API DataFrame/SQL do Spark (sem UDFs Python linha-a-linha), que já é compilada para o mesmo plano de execução Catalyst/Tungsten independente da linguagem — a penalidade de performance clássica do PySpark (overhead de UDF) não se aplica aqui.
- Produtividade e manutenibilidade: é a linguagem do dia a dia do candidato (Python/PySpark, uso profissional atual), o que reduz risco de bugs bobos e acelera iteração dentro do prazo de 5 dias úteis.
- Ecossistema de testes: `pytest` + SparkSession local para testar a lógica de DQ isoladamente (`tests/unit/test_dq_validation.py`), sem exigir um ambiente Scala/sbt separado.
- Todo o resto do stack do desafio (contrato de dados, gerador de dados sintéticos, scripts de orquestração/infra) já é Python — manter uma linguagem única reduz a superfície de contexto a trocar durante a implementação e a defesa técnica.

## Consequências
- Em cargas de trabalho que dependessem pesadamente de UDFs Python fazendo processamento linha-a-linha, a escolha mudaria para Scala (ou para Pandas UDFs/Arrow no PySpark) — é um trade-off a discutir na defesa, não uma regra absoluta.
- Se o volume real de produção (300M transações/dia) revelar gargalos de serialização em algum ponto específico do pipeline, a resposta não é reescrever tudo em Scala, e sim isolar esse ponto específico (ex.: reescrever uma transformação isolada em Scala/UDF nativo, ou usar Pandas UDF vetorizado) — otimização cirúrgica, não migração de linguagem completa.

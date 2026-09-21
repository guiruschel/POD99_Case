import sys

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()
db = sys.argv[1]

for table_name in ["gold_saldo_contrato", "gold_saldo_conta", "gold_cosif_classificacao", "gold_reconciliacao_agencia"]:
    df = spark.table(f"{db}.{table_name}")
    print(f"VERIFY {table_name} total={df.count()} dt_processamento_distinct={df.select('dt_processamento').distinct().count()}")

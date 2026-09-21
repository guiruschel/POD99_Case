import sys

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()
table = sys.argv[1]
df = spark.table(table)
print(f"VERIFY total={df.count()} distinct_id_transacao={df.select('id_transacao').distinct().count()}")

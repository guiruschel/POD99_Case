"""Silver-layer transformation: dedup + enrich with the COSIF domain table."""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def dedup_and_enrich(bronze_df: DataFrame, cosif_domain: DataFrame) -> DataFrame:
    """Keeps the latest entry per id_transacao (guards against a re-run of the
    same lote producing overlapping rows) and joins in COSIF domain metadata."""
    dedup_window = Window.partitionBy("id_transacao").orderBy(F.col("dt_lancamento").desc())
    deduped_df = (
        bronze_df.withColumn("_rn", F.row_number().over(dedup_window)).filter(F.col("_rn") == 1).drop("_rn")
    )

    # cosif_domain is a handful of rows: broadcast instead of shuffling the
    # (potentially large) transactions table to join it.
    cosif_lookup = F.broadcast(
        cosif_domain.select(
            "cod_cosif",
            F.col("descricao").alias("cosif_descricao"),
            F.col("tipo_contrato_esperado").alias("cosif_tipo_contrato_esperado"),
        )
    )
    return deduped_df.join(cosif_lookup, on="cod_cosif", how="left")

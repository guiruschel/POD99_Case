"""Gold job transforms: saldo por contrato/conta, classificacao COSIF, reconciliacao debito/credito por agencia.

Sign convention for the accounting balance: CREDITO/JUROS increase it,
DEBITO/TARIFA/IOF decrease it; a reversal (flag_estorno) flips whatever sign
the original entry would have had. This mirrors standard double-entry
bookkeeping but is a business assumption made for this case study -- the
accounting squad (owner in the data contract) would be the actual source of
truth for this rule in a real rollout.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

CREDIT_LIKE_ENTRY_TYPES = ("CREDITO", "JUROS")


def with_signed_value(df: DataFrame) -> DataFrame:
    base_sign = F.when(F.col("tipo_lancamento").isin(*CREDIT_LIKE_ENTRY_TYPES), F.lit(1)).otherwise(F.lit(-1))
    estorno_sign = F.when(F.col("flag_estorno"), F.lit(-1)).otherwise(F.lit(1))
    return df.withColumn("valor_sinalizado", F.col("valor_lancamento") * base_sign * estorno_sign)


def saldo_por_contrato(df: DataFrame) -> DataFrame:
    return with_signed_value(df).groupBy(
        "id_contrato", "id_conta", "cod_agencia", "tipo_contrato", "dt_processamento"
    ).agg(
        F.sum("valor_sinalizado").alias("saldo"),
        F.count("id_transacao").alias("qtd_lancamentos"),
    )


def saldo_por_conta(saldo_contrato_df: DataFrame) -> DataFrame:
    return saldo_contrato_df.groupBy("id_conta", "dt_processamento").agg(
        F.sum("saldo").alias("saldo"),
        F.count("id_contrato").alias("qtd_contratos"),
    )


def classificacao_cosif(df: DataFrame, cosif_domain: DataFrame) -> DataFrame:
    cosif_lookup = F.broadcast(cosif_domain.select("cod_cosif", F.col("descricao").alias("cosif_descricao")))
    return (
        with_signed_value(df)
        .groupBy("tipo_contrato", "cod_cosif", "dt_processamento")
        .agg(
            F.sum("valor_sinalizado").alias("saldo"),
            F.count("id_transacao").alias("qtd_lancamentos"),
        )
        .join(cosif_lookup, on="cod_cosif", how="left")
    )


def reconciliacao_agencia(df: DataFrame) -> DataFrame:
    return (
        df.groupBy("cod_agencia", "dt_processamento")
        .agg(
            F.sum(F.when(F.col("tipo_lancamento") == "DEBITO", F.col("valor_lancamento")).otherwise(F.lit(0.0))).alias(
                "total_debito"
            ),
            F.sum(F.when(F.col("tipo_lancamento") == "CREDITO", F.col("valor_lancamento")).otherwise(F.lit(0.0))).alias(
                "total_credito"
            ),
        )
        .withColumn("diferenca_credito_debito", F.col("total_credito") - F.col("total_debito"))
    )

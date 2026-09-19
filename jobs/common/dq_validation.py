"""Data quality validation against the fin_contabilidade_saldo_contrato contract.

Implements the rules from data_contracts/fin_contabilidade_saldo_contrato.yaml:
  - uniqueness_id_transacao
  - valor_lancamento_positive_unless_estorno
  - dt_lancamento_not_after_dt_processamento
  - cod_cosif_referential_integrity
  - completeness_not_null_fields
"""
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from common.contract import required_columns

REJECTION_COLUMN = "dq_rejection_reasons"


def validate_dataframe(df: DataFrame, contract: dict, cosif_domain: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Splits df into (valid_df, rejected_df). rejected_df keeps a dq_rejection_reasons array column."""
    id_count_window = Window.partitionBy("id_transacao")
    df = df.withColumn("_id_transacao_count", F.count("id_transacao").over(id_count_window))

    # cosif_domain is a handful of rows: broadcasting it avoids shuffling the
    # (potentially huge) transactions table just to check referential integrity.
    cosif_lookup = broadcast_cosif_lookup(cosif_domain)
    df = df.join(cosif_lookup, on="cod_cosif", how="left")

    failure_checks = {
        "uniqueness_id_transacao": F.col("_id_transacao_count") > 1,
        "valor_lancamento_positive": F.col("valor_lancamento") <= 0,
        "dt_lancamento_not_after_dt_processamento": F.to_date("dt_lancamento") > F.col("dt_processamento"),
        "cod_cosif_referential_integrity": F.col("cod_cosif").isNotNull() & F.col("_cosif_match").isNull(),
    }
    for column in required_columns(contract):
        failure_checks[f"completeness_{column}"] = F.col(column).isNull() | (F.trim(F.col(column).cast("string")) == "")

    reasons = F.array(*[F.when(cond, F.lit(rule_id)) for rule_id, cond in failure_checks.items()])
    df = df.withColumn(REJECTION_COLUMN, F.array_except(reasons, F.array(F.lit(None).cast("string"))))

    internal_columns = ["_id_transacao_count", "_cosif_match"]
    valid_df = df.filter(F.size(REJECTION_COLUMN) == 0).drop(*internal_columns, REJECTION_COLUMN)
    rejected_df = df.filter(F.size(REJECTION_COLUMN) > 0).drop(*internal_columns)

    return valid_df, rejected_df


def broadcast_cosif_lookup(cosif_domain: DataFrame) -> DataFrame:
    return F.broadcast(cosif_domain.select("cod_cosif").withColumn("_cosif_match", F.lit(True)))

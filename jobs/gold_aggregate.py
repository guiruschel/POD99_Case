"""Gold job: saldo por contrato/conta, classificacao COSIF, reconciliacao debito/credito por agencia."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from common.batch_control import update_batch_status
from common.gold_transform import (
    classificacao_cosif,
    reconciliacao_agencia,
    saldo_por_conta,
    saldo_por_contrato,
)
from common.logging_utils import get_logger, log_event

JOB_ARGS = [
    "JOB_NAME",
    "ref_path",
    "processing_date",
    "catalog_name",
    "catalog_database",
    "saldo_contrato_location",
    "saldo_conta_location",
    "cosif_classificacao_location",
    "reconciliacao_agencia_location",
]

# One entry per Gold table: (arg key for its S3 location, target table name).
GOLD_TABLES = [
    ("saldo_contrato_location", "gold_saldo_contrato", ["id_contrato", "id_conta"]),
    ("saldo_conta_location", "gold_saldo_conta", ["id_conta"]),
    ("cosif_classificacao_location", "gold_cosif_classificacao", ["tipo_contrato", "cod_cosif"]),
    ("reconciliacao_agencia_location", "gold_reconciliacao_agencia", ["cod_agencia"]),
]


def write_gold_table(df: DataFrame, table: str, location: str) -> None:
    # Dynamic partition overwrite: reprocessing the same dt_processamento
    # replaces just that partition's rows instead of duplicating them or
    # requiring a MERGE INTO (these are aggregates, not upserts by key).
    if df.sparkSession.catalog.tableExists(table):
        df.writeTo(table).overwritePartitions()
    else:
        (
            df.writeTo(table)
            .using("iceberg")
            .tableProperty("format-version", "2")  # see architecture/ADRs/005-iceberg-format-version.md
            .tableProperty("location", location)
            .partitionedBy("dt_processamento")
            .createOrReplace()
        )


def run_gold_aggregate(spark, args: dict, logger) -> None:
    silver_table = f"{args['catalog_name']}.{args['catalog_database']}.silver_fin_contabilidade_saldo_contrato"

    silver_df = spark.table(silver_table).filter(F.col("dt_processamento") == args["processing_date"])
    cosif_domain = spark.read.parquet(args["ref_path"])
    silver_df.cache()

    contrato_df = saldo_por_contrato(silver_df)
    conta_df = saldo_por_conta(contrato_df)
    cosif_df = classificacao_cosif(silver_df, cosif_domain)
    reconciliacao_df = reconciliacao_agencia(silver_df)

    log_event(
        logger,
        "aggregation_complete",
        silver_rows=silver_df.count(),
        contratos=contrato_df.count(),
        contas=conta_df.count(),
        classificacoes_cosif=cosif_df.count(),
        agencias=reconciliacao_df.count(),
    )

    results = {
        "gold_saldo_contrato": contrato_df,
        "gold_saldo_conta": conta_df,
        "gold_cosif_classificacao": cosif_df,
        "gold_reconciliacao_agencia": reconciliacao_df,
    }
    for location_key, table_name, _ in GOLD_TABLES:
        full_table = f"{args['catalog_name']}.{args['catalog_database']}.{table_name}"
        write_gold_table(results[table_name], full_table, args[location_key])

    log_event(logger, "job_finished", tables=list(results.keys()))
    silver_df.unpersist()


def main() -> None:
    args = getResolvedOptions(sys.argv, JOB_ARGS)
    logger = get_logger("gold_aggregate")
    log_event(logger, "job_started", processing_date=args["processing_date"])

    # Gold processes one business day at a time, like Silver -- processing_date
    # is a natural, stable id_lote.
    id_lote = args["processing_date"]
    update_batch_status(id_lote, "gold", "RECEIVED", logger)

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    try:
        update_batch_status(id_lote, "gold", "PROCESSING", logger)
        run_gold_aggregate(spark, args, logger)
        update_batch_status(id_lote, "gold", "PROCESSED", logger)
        job.commit()
    except Exception as e:
        update_batch_status(id_lote, "gold", "FAILED", logger, error_message=str(e)[:500])
        logger.exception("job_failed")
        raise


if __name__ == "__main__":
    main()

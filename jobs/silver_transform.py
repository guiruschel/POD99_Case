"""Silver job: dedup Bronze transactions, enrich with COSIF domain, upsert idempotently into Iceberg."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

from common.batch_control import update_batch_status
from common.logging_utils import get_logger, log_event
from common.silver_transform import dedup_and_enrich

JOB_ARGS = [
    "JOB_NAME",
    "ref_path",
    "processing_date",
    "catalog_name",
    "catalog_database",
    "table_location",
]


def run_silver_transform(spark, args: dict, logger) -> None:
    bronze_table = f"{args['catalog_name']}.{args['catalog_database']}.bronze_fin_contabilidade_saldo_contrato"
    silver_table = f"{args['catalog_name']}.{args['catalog_database']}.silver_fin_contabilidade_saldo_contrato"

    # Partition pruning: only read the day being processed, not the whole
    # Bronze history -- avoids re-reading every past day on every run.
    bronze_df = spark.table(bronze_table).filter(F.col("dt_processamento") == args["processing_date"])
    cosif_domain = spark.read.parquet(args["ref_path"])

    silver_df = dedup_and_enrich(bronze_df, cosif_domain).repartition("dt_processamento")
    silver_df.cache()

    bronze_count = bronze_df.count()
    silver_count = silver_df.count()
    log_event(logger, "transform_complete", bronze_rows=bronze_count, silver_rows=silver_count)

    silver_df.createOrReplaceTempView("silver_source")

    if spark.catalog.tableExists(silver_table):
        # Idempotent upsert: reprocessing the same day/lote just updates the
        # matching rows by id_transacao instead of duplicating them.
        spark.sql(
            f"""
            MERGE INTO {silver_table} t
            USING silver_source s
            ON t.id_transacao = s.id_transacao
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
            """
        )
    else:
        (
            silver_df.writeTo(silver_table)
            .using("iceberg")
            .tableProperty("format-version", "2")  # see architecture/ADRs/005-iceberg-format-version.md
            .tableProperty("location", args["table_location"])
            .partitionedBy("dt_processamento")
            .createOrReplace()
        )

    log_event(logger, "job_finished", table=silver_table)
    silver_df.unpersist()


def main() -> None:
    args = getResolvedOptions(sys.argv, JOB_ARGS)
    logger = get_logger("silver_transform")
    log_event(logger, "job_started", processing_date=args["processing_date"])

    # Silver processes one business day at a time, so processing_date is a
    # natural, stable id_lote -- reprocessing the same day updates the same
    # batch-control row instead of creating a new one.
    id_lote = args["processing_date"]
    update_batch_status(id_lote, "silver", "RECEIVED", logger)

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    try:
        update_batch_status(id_lote, "silver", "PROCESSING", logger)
        run_silver_transform(spark, args, logger)
        update_batch_status(id_lote, "silver", "PROCESSED", logger)
        job.commit()
    except Exception as e:
        update_batch_status(id_lote, "silver", "FAILED", logger, error_message=str(e)[:500])
        logger.exception("job_failed")
        raise


if __name__ == "__main__":
    main()

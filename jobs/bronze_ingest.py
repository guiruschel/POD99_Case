"""Bronze job: ingest raw Parquet, validate against the data contract, write Iceberg (valid) + quarantine (rejected)."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from common.contract import load_contract
from common.dq_validation import validate_dataframe
from common.logging_utils import get_logger, log_event

JOB_ARGS = [
    "JOB_NAME",
    "raw_path",
    "ref_path",
    "quarantine_path",
    "catalog_name",
    "catalog_database",
    "contract_path",
]


def run_bronze_ingest(spark, args: dict, logger) -> None:
    contract = load_contract(args["contract_path"])
    cosif_domain = spark.read.parquet(args["ref_path"])
    raw_df = spark.read.parquet(args["raw_path"])

    valid_df, rejected_df = validate_dataframe(raw_df, contract, cosif_domain)
    valid_df.cache()
    rejected_df.cache()

    log_event(
        logger,
        "validation_complete",
        total=raw_df.count(),
        valid=valid_df.count(),
        rejected=rejected_df.count(),
    )

    table = f"{args['catalog_name']}.{args['catalog_database']}.bronze_fin_contabilidade_saldo_contrato"
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {args['catalog_name']}.{args['catalog_database']}")

    if spark.catalog.tableExists(table):
        valid_df.writeTo(table).append()
    else:
        (
            valid_df.writeTo(table)
            .using("iceberg")
            .tableProperty("format-version", "3")
            .partitionedBy("dt_processamento")
            .createOrReplace()
        )

    (rejected_df.write.mode("append").partitionBy("dt_processamento").parquet(args["quarantine_path"]))

    log_event(logger, "job_finished", table=table)
    valid_df.unpersist()
    rejected_df.unpersist()


def main() -> None:
    args = getResolvedOptions(sys.argv, JOB_ARGS)
    logger = get_logger("bronze_ingest")
    log_event(logger, "job_started", raw_path=args["raw_path"])

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    try:
        run_bronze_ingest(spark, args, logger)
        job.commit()
    except Exception:
        logger.exception("job_failed")
        raise


if __name__ == "__main__":
    main()

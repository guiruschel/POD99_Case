"""Bronze job: ingest raw Parquet, validate against the data contract, write Iceberg (valid) + quarantine (rejected)."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from common.batch_control import get_optional_arg, update_batch_status
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
    "table_location",
]


def run_bronze_ingest(spark, args: dict, logger) -> None:
    contract = load_contract(args["contract_path"])
    cosif_domain = spark.read.parquet(args["ref_path"])
    raw_df = spark.read.parquet(args["raw_path"])

    valid_df, rejected_df = validate_dataframe(raw_df, contract, cosif_domain)
    # Without this, the window function + broadcast join upstream leave the
    # DataFrame with far more partitions than dt_processamento has distinct
    # values, and a partitioned write turns into one tiny file per partition
    # *per upstream task* (observed: ~2,500 rejected rows -> ~2,000 files).
    # Repartitioning by the partition column first caps it at one file per
    # dt_processamento value.
    valid_df = valid_df.repartition("dt_processamento")
    rejected_df = rejected_df.repartition("dt_processamento")
    valid_df.cache()
    rejected_df.cache()

    log_event(
        logger,
        "validation_complete",
        total=raw_df.count(),
        valid=valid_df.count(),
        rejected=rejected_df.count(),
    )

    # The database/namespace is provisioned by Terraform (infra/terraform/modules/glue_catalog),
    # not by this job -- "CREATE NAMESPACE" here was redundant and, against the
    # real AWS Glue Catalog, hit a Spark SQL parser bug where the two-part
    # "catalog.namespace" identifier gets validated as a single (invalid)
    # database name instead of being routed to the Iceberg catalog plugin.
    table = f"{args['catalog_name']}.{args['catalog_database']}.bronze_fin_contabilidade_saldo_contrato"

    if spark.catalog.tableExists(table):
        # Dynamic partition overwrite, not append: this job reads the whole
        # raw_path on every run (not just newly-arrived files), so appending
        # would duplicate every previously-ingested day each time it reruns.
        # Found for real: a second production run (with no new raw data)
        # doubled the table (9,746 rows for 4,873 distinct id_transacao).
        # Overwriting by partition makes reruns idempotent without needing to
        # track which raw files were already ingested.
        valid_df.writeTo(table).overwritePartitions()
    else:
        # Without an explicit "location", Iceberg's Glue catalog defaults to
        # <warehouse>/<database>.db/<table>/, which landed data outside our
        # planned bronze/silver/gold prefix layout on the first real run.
        #
        # format-version 2, not 3: confirmed on a real run that Athena (engine
        # version 3, the latest available) cannot yet read Iceberg V3 tables
        # ("GENERIC_INTERNAL_ERROR: Iceberg format version 3 is not
        # supported"). See architecture/ADRs/005-iceberg-format-version.md.
        (
            valid_df.writeTo(table)
            .using("iceberg")
            .tableProperty("format-version", "2")
            .tableProperty("location", args["table_location"])
            .partitionedBy("dt_processamento")
            .createOrReplace()
        )

    # Same idempotency fix as above, for the plain-Parquet quarantine output:
    # dynamic partition overwrite mode replaces only the dt_processamento
    # partitions present in this run instead of appending duplicates.
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    (rejected_df.write.mode("overwrite").partitionBy("dt_processamento").parquet(args["quarantine_path"]))

    log_event(logger, "job_finished", table=table)
    valid_df.unpersist()
    rejected_df.unpersist()


def main() -> None:
    args = getResolvedOptions(sys.argv, JOB_ARGS)
    logger = get_logger("bronze_ingest")
    log_event(logger, "job_started", raw_path=args["raw_path"])

    # Bronze ingests the whole raw/ prefix per run (not one business day at a
    # time, unlike Silver/Gold), so JOB_RUN_ID -- not a processing date -- is
    # the natural "lote" unit here. A production version would get id_lote
    # from the upstream file-arrival event instead.
    id_lote = get_optional_arg("JOB_RUN_ID") or "local-run"
    update_batch_status(id_lote, "bronze", "RECEIVED", logger)

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    try:
        update_batch_status(id_lote, "bronze", "PROCESSING", logger)
        run_bronze_ingest(spark, args, logger)
        update_batch_status(id_lote, "bronze", "PROCESSED", logger)
        job.commit()
    except Exception as e:
        update_batch_status(id_lote, "bronze", "FAILED", logger, error_message=str(e)[:500])
        logger.exception("job_failed")
        raise


if __name__ == "__main__":
    main()

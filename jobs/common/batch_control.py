"""DynamoDB-backed batch control: tracks per-job processing status
(RECEIVED / PROCESSING / PROCESSED / FAILED) per id_lote.

Optional by design: local Docker runs (against a local hadoop-type Iceberg
catalog, no AWS credentials) don't pass --batch_control_table, so status
updates are silently skipped instead of failing the job.
"""
import sys
from datetime import datetime, timezone


def get_optional_arg(name: str) -> str | None:
    """Reads an optional --name value CLI arg without requiring it (unlike
    awsglue's getResolvedOptions, which raises if a declared option is
    missing)."""
    flag = f"--{name}"
    argv = sys.argv
    if flag in argv:
        idx = argv.index(flag)
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return None


def update_batch_status(id_lote: str, job_name: str, status: str, logger=None, **extra) -> None:
    table_name = get_optional_arg("batch_control_table")
    if not table_name:
        return

    import boto3

    table = boto3.resource("dynamodb").Table(table_name)
    item = {
        "id_lote": id_lote,
        "job_name": job_name,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    item.update(extra)
    table.put_item(Item=item)

    if logger is not None:
        logger.info(f"batch_control status={status} id_lote={id_lote} job_name={job_name}")

#!/usr/bin/env bash
# Runs the Bronze job inside the official AWS Glue Docker image, against a
# local Iceberg (hadoop-type) catalog on disk -- no AWS calls, no AWS cost.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="amazon/aws-glue-libs:5.1.0"
WAREHOUSE_PATH="/home/glue_user/workspace/data_generator/output/warehouse"

docker run --rm \
  -v "$REPO_ROOT":/home/glue_user/workspace/ \
  -e DISABLE_SSL=true \
  "$IMAGE" \
  bash -c "
    pip install -q -r /home/glue_user/workspace/requirements-dev.txt &&
    spark-submit \
      --conf spark.sql.catalog.local_iceberg=org.apache.iceberg.spark.SparkCatalog \
      --conf spark.sql.catalog.local_iceberg.type=hadoop \
      --conf spark.sql.catalog.local_iceberg.warehouse=$WAREHOUSE_PATH \
      /home/glue_user/workspace/jobs/bronze_ingest.py \
      --JOB_NAME bronze_ingest_local \
      --raw_path /home/glue_user/workspace/data_generator/output/raw \
      --ref_path /home/glue_user/workspace/data_generator/output/ref/cosif_domain.parquet \
      --quarantine_path /home/glue_user/workspace/data_generator/output/quarantine \
      --catalog_name local_iceberg \
      --catalog_database pod99_fin_case_dev \
      --contract_path /home/glue_user/workspace/data_contracts/fin_contabilidade_saldo_contrato.yaml
  "

#!/usr/bin/env bash
# Runs the Gold job inside the official AWS Glue Docker image, against the
# local Iceberg (hadoop-type) catalog on disk -- no AWS calls, no AWS cost.
# Usage: scripts/run_local_gold.sh <dt_processamento, e.g. 2026-08-01>
set -euo pipefail

PROCESSING_DATE="${1:?Usage: run_local_gold.sh <dt_processamento>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="amazon/aws-glue-libs:5.1.0"
WORKSPACE="/home/hadoop/workspace"
WAREHOUSE_PATH="$WORKSPACE/data_generator/output/warehouse"
DB_PATH="$WAREHOUSE_PATH/pod99_fin_case_dev"

export MSYS_NO_PATHCONV=1

docker run --rm \
  -v "$REPO_ROOT":"$WORKSPACE"/ \
  -w "$WORKSPACE" \
  "$IMAGE" \
  -c "
    pip install -q --user -r requirements-dev.txt &&
    spark-submit \
      --conf spark.sql.catalog.local_iceberg=org.apache.iceberg.spark.SparkCatalog \
      --conf spark.sql.catalog.local_iceberg.type=hadoop \
      --conf spark.sql.catalog.local_iceberg.warehouse=$WAREHOUSE_PATH \
      jobs/gold_aggregate.py \
      --JOB_NAME gold_aggregate_local \
      --ref_path $WORKSPACE/data_generator/output/ref/cosif_domain.parquet \
      --processing_date $PROCESSING_DATE \
      --catalog_name local_iceberg \
      --catalog_database pod99_fin_case_dev \
      --saldo_contrato_location $DB_PATH/gold_saldo_contrato \
      --saldo_conta_location $DB_PATH/gold_saldo_conta \
      --cosif_classificacao_location $DB_PATH/gold_cosif_classificacao \
      --reconciliacao_agencia_location $DB_PATH/gold_reconciliacao_agencia
  "

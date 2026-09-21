locals {
  repo_root      = "${path.module}/../../../.."
  scripts_prefix = "scripts"

  # --datalake-formats=iceberg only puts the Iceberg connector JARs on the
  # classpath -- it does NOT by itself register a catalog named
  # "glue_catalog". Without these, any 2-part "glue_catalog.<db>" reference
  # gets misread as a single-part namespace in the default spark_catalog
  # (found the hard way: REQUIRES_SINGLE_PART_NAMESPACE on a real run).
  # Shared by every job in this module.
  iceberg_glue_catalog_conf = join(" ", [
    "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog",
    "--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog",
    "--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO",
    "--conf spark.sql.catalog.glue_catalog.warehouse=s3://${var.data_lake_bucket_name}/",
  ])
}

# `source_dir` alone zips the *contents* of jobs/common/ flattened at the
# zip root (no "common/" folder inside), which breaks `from common.x import
# y` once Glue puts this zip on sys.path via --extra-py-files. Listing each
# file explicitly under "common/<name>" keeps the package structure intact.
data "archive_file" "common_zip" {
  type        = "zip"
  output_path = "${path.module}/.build/common.zip"

  source {
    content  = file("${local.repo_root}/jobs/common/__init__.py")
    filename = "common/__init__.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/batch_control.py")
    filename = "common/batch_control.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/contract.py")
    filename = "common/contract.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/dq_validation.py")
    filename = "common/dq_validation.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/logging_utils.py")
    filename = "common/logging_utils.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/silver_transform.py")
    filename = "common/silver_transform.py"
  }
  source {
    content  = file("${local.repo_root}/jobs/common/gold_transform.py")
    filename = "common/gold_transform.py"
  }
}

resource "aws_s3_object" "bronze_script" {
  bucket = var.data_lake_bucket_name
  key    = "${local.scripts_prefix}/bronze_ingest.py"
  source = "${local.repo_root}/jobs/bronze_ingest.py"
  etag   = filemd5("${local.repo_root}/jobs/bronze_ingest.py")
}

resource "aws_s3_object" "silver_script" {
  bucket = var.data_lake_bucket_name
  key    = "${local.scripts_prefix}/silver_transform.py"
  source = "${local.repo_root}/jobs/silver_transform.py"
  etag   = filemd5("${local.repo_root}/jobs/silver_transform.py")
}

resource "aws_s3_object" "gold_script" {
  bucket = var.data_lake_bucket_name
  key    = "${local.scripts_prefix}/gold_aggregate.py"
  source = "${local.repo_root}/jobs/gold_aggregate.py"
  etag   = filemd5("${local.repo_root}/jobs/gold_aggregate.py")
}

resource "aws_s3_object" "common_zip" {
  bucket = var.data_lake_bucket_name
  key    = "${local.scripts_prefix}/common.zip"
  source = data.archive_file.common_zip.output_path
  etag   = data.archive_file.common_zip.output_md5
}

resource "aws_s3_object" "data_contract" {
  bucket = var.data_lake_bucket_name
  key    = "${local.scripts_prefix}/fin_contabilidade_saldo_contrato.yaml"
  source = "${local.repo_root}/data_contracts/fin_contabilidade_saldo_contrato.yaml"
  etag   = filemd5("${local.repo_root}/data_contracts/fin_contabilidade_saldo_contrato.yaml")
}

# Minimal worker config on purpose: this is a demo-scale dataset (synthetic,
# a few hundred thousand rows), not the real 300M/day production volume. See
# the "dimensionamento para produção" section in the README for how this
# would actually be sized.
resource "aws_glue_job" "bronze_ingest" {
  name              = "${var.project_name}-${var.environment}-bronze-ingest"
  role_arn          = var.glue_job_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 15
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${var.data_lake_bucket_name}/${aws_s3_object.bronze_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${var.data_lake_bucket_name}/tmp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--datalake-formats"                 = "iceberg"
    # Glue's --additional-python-modules splits on commas to separate
    # DIFFERENT packages (e.g. "pandas==1.0,numpy==1.2"), so a comma inside a
    # single package's version range ("pyyaml>=6.0,<7.0") gets misread as a
    # second, invalid package named "<7.0". A single-bound constraint avoids it.
    "--additional-python-modules"        = "pyyaml>=6.0"
    "--extra-py-files"                   = "s3://${var.data_lake_bucket_name}/${aws_s3_object.common_zip.key}"
    "--conf"                             = local.iceberg_glue_catalog_conf
    "--raw_path"                         = "s3://${var.data_lake_bucket_name}/raw/"
    "--ref_path"                         = "s3://${var.data_lake_bucket_name}/ref/cosif_domain.parquet"
    "--quarantine_path"                  = "s3://${var.data_lake_bucket_name}/quarantine/"
    "--catalog_name"                     = "glue_catalog"
    "--catalog_database"                 = var.glue_database_name
    "--contract_path"                    = "s3://${var.data_lake_bucket_name}/${aws_s3_object.data_contract.key}"
    "--table_location"                   = "s3://${var.data_lake_bucket_name}/bronze/fin_contabilidade_saldo_contrato/"
    "--batch_control_table"              = var.batch_control_table
    "--job_name_tag"                     = "bronze"
  }
}

resource "aws_glue_job" "silver_transform" {
  name              = "${var.project_name}-${var.environment}-silver-transform"
  role_arn          = var.glue_job_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 15
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${var.data_lake_bucket_name}/${aws_s3_object.silver_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${var.data_lake_bucket_name}/tmp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--datalake-formats"                 = "iceberg"
    "--additional-python-modules"        = "pyyaml>=6.0"
    "--extra-py-files"                   = "s3://${var.data_lake_bucket_name}/${aws_s3_object.common_zip.key}"
    "--conf"                             = local.iceberg_glue_catalog_conf
    "--ref_path"                         = "s3://${var.data_lake_bucket_name}/ref/cosif_domain.parquet"
    "--catalog_name"                     = "glue_catalog"
    "--catalog_database"                 = var.glue_database_name
    "--table_location"                   = "s3://${var.data_lake_bucket_name}/silver/fin_contabilidade_saldo_contrato/"
    # Placeholder -- overridden per run via
    # `aws glue start-job-run --arguments '{"--processing_date":"YYYY-MM-DD"}'`.
    # A real orchestrator (Step Functions) would pass this dynamically too.
    "--processing_date"                  = "1970-01-01"
    "--batch_control_table"              = var.batch_control_table
    "--job_name_tag"                     = "silver"
  }
}

resource "aws_glue_job" "gold_aggregate" {
  name              = "${var.project_name}-${var.environment}-gold-aggregate"
  role_arn          = var.glue_job_role_arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 15
  max_retries       = 0

  command {
    name            = "glueetl"
    script_location = "s3://${var.data_lake_bucket_name}/${aws_s3_object.gold_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${var.data_lake_bucket_name}/tmp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--datalake-formats"                 = "iceberg"
    "--additional-python-modules"        = "pyyaml>=6.0"
    "--extra-py-files"                   = "s3://${var.data_lake_bucket_name}/${aws_s3_object.common_zip.key}"
    "--conf"                             = local.iceberg_glue_catalog_conf
    "--ref_path"                         = "s3://${var.data_lake_bucket_name}/ref/cosif_domain.parquet"
    "--catalog_name"                     = "glue_catalog"
    "--catalog_database"                 = var.glue_database_name
    "--saldo_contrato_location"          = "s3://${var.data_lake_bucket_name}/gold/saldo_contrato/"
    "--saldo_conta_location"             = "s3://${var.data_lake_bucket_name}/gold/saldo_conta/"
    "--cosif_classificacao_location"     = "s3://${var.data_lake_bucket_name}/gold/cosif_classificacao/"
    "--reconciliacao_agencia_location"   = "s3://${var.data_lake_bucket_name}/gold/reconciliacao_agencia/"
    # Placeholder -- overridden per run via --arguments, same pattern as Silver.
    "--processing_date"                  = "1970-01-01"
    "--batch_control_table"              = var.batch_control_table
    "--job_name_tag"                     = "gold"
  }
}

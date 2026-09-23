data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_job" {
  name               = "${var.project_name}-${var.environment}-glue-job-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json
}

# AWS-managed baseline permissions for Glue jobs (CloudWatch Logs, Glue's own
# internal S3 paths). It does NOT grant access to our own bucket, so we add
# a scoped custom policy below for that.
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_job.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "data_lake_access" {
  statement {
    sid = "DataLakeReadWrite"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]

    resources = [
      var.data_lake_bucket_arn,
      "${var.data_lake_bucket_arn}/*",
    ]
  }
}

# Scoped to this project's bucket only (least privilege). Extended in later
# days with DynamoDB access and CloudWatch custom metrics, as those resources
# are added.
resource "aws_iam_role_policy" "data_lake_access" {
  name   = "${var.project_name}-${var.environment}-data-lake-access"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.data_lake_access.json
}

# Added when the Bronze job started writing Iceberg tables to the real Glue
# Data Catalog (previously only tested against a local hadoop-type catalog).
# Scoped to this project's database only, not catalog-wide.
data "aws_iam_policy_document" "glue_catalog_access" {
  statement {
    sid = "GlueCatalogReadWrite"

    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:GetPartitions",
      "glue:BatchCreatePartition",
    ]

    resources = [
      var.glue_catalog_arn,
      var.glue_database_arn,
      var.glue_tables_arn,
    ]
  }
}

resource "aws_iam_role_policy" "glue_catalog_access" {
  name   = "${var.project_name}-${var.environment}-glue-catalog-access"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.glue_catalog_access.json
}

# Batch control table: jobs read/write their own status rows (RECEIVED /
# PROCESSING / PROCESSED / FAILED), scoped to this single table only.
data "aws_iam_policy_document" "batch_control_access" {
  statement {
    sid = "BatchControlReadWrite"

    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]

    resources = [var.batch_control_table_arn]
  }
}

resource "aws_iam_role_policy" "batch_control_access" {
  name   = "${var.project_name}-${var.environment}-batch-control-access"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.batch_control_access.json
}

# cloudwatch:PutMetricData does not support resource-level scoping (it's
# always "*" in AWS IAM -- there's no ARN format for a CloudWatch metric),
# so this is as tight as this permission can get.
data "aws_iam_policy_document" "custom_metrics_access" {
  statement {
    sid       = "PublishCustomMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "custom_metrics_access" {
  name   = "${var.project_name}-${var.environment}-custom-metrics-access"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.custom_metrics_access.json
}

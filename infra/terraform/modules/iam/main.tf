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
# days with Glue Catalog table permissions, DynamoDB access and CloudWatch
# custom metrics, as those resources are added.
resource "aws_iam_role_policy" "data_lake_access" {
  name   = "${var.project_name}-${var.environment}-data-lake-access"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.data_lake_access.json
}

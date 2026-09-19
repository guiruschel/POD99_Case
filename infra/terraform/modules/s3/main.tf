locals {
  bucket_name = "${var.project_name}-${var.environment}-${var.account_id}"

  # Single bucket with layer prefixes instead of 4 separate buckets: simpler
  # IAM policies and lower operational overhead for this case study. Apache
  # Iceberg already gives per-table snapshot history, so bucket versioning
  # would just duplicate that and add storage cost for no extra benefit here.
  layer_prefixes = ["raw/", "bronze/", "silver/", "gold/", "quarantine/", "ref/"]
}

resource "aws_s3_bucket" "data_lake" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Folder markers so the layer layout is visible in the console before any
# job has written data yet.
resource "aws_s3_object" "layer_markers" {
  for_each = toset(local.layer_prefixes)

  bucket  = aws_s3_bucket.data_lake.id
  key     = each.value
  content = ""
}

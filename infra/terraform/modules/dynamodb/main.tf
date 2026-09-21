# Batch control table: tracks processing status per (id_lote, job_name) so a
# failed or re-triggered run can tell what's already PROCESSED vs what still
# needs work, without relying only on Glue job-run history.
#
# Key design: id_lote (the processing_date, e.g. "2026-08-01") as partition
# key, job_name (bronze/silver/gold) as sort key -- a single batch touches
# multiple jobs, each with its own status.
#
# On-demand billing (not provisioned): this table sees a handful of writes
# per job run in this case study, nowhere near enough traffic to justify
# provisioned capacity planning, and on-demand has an always-free tier.
resource "aws_dynamodb_table" "batch_control" {
  name         = "${var.project_name}-${var.environment}-batch-control"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id_lote"
  range_key    = "job_name"

  attribute {
    name = "id_lote"
    type = "S"
  }

  attribute {
    name = "job_name"
    type = "S"
  }
}

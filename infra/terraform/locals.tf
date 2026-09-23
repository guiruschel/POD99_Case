locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  glue_catalog_arn  = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:catalog"
  glue_database_arn = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:database/${module.glue_catalog.database_name}"
  glue_tables_arn   = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${module.glue_catalog.database_name}/*"

  bronze_job_arn = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${module.glue_jobs.bronze_job_name}"
  silver_job_arn = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${module.glue_jobs.silver_job_name}"
  gold_job_arn   = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${module.glue_jobs.gold_job_name}"
}
